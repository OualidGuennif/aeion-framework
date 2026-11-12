"""HTTP transport: the routes of AxiomSpec/api/openapi.json over the service.

The contract file is the interface; this module conforms to it and serves it at /v1/openapi.json. An answer
that is a function of a release named by digest is immutable: it carries an ETag and may be cached forever.
An answer that also reads the code beside the release (its annotations and bindings) carries an ETag and is
revalidated, because the digest does not cover the code. In sandbox mode no other method and no
organization route exists.
"""
from contextlib import asynccontextmanager
import hashlib
import json
import os
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from mcp.server.transport_security import TransportSecuritySettings
from starlette.concurrency import run_in_threadpool

from . import mcp_tools
from .http_limits import RequestLimits, problem
from .service import EDITION, MAX_BODY_BYTES, PACKAGE, QueryError, Service, strict_json

IMMUTABLE = 'public, max-age=31536000, immutable'
INTEGER = re.compile(r'[0-9]{1,9}')


def configured_app():
    """Uvicorn factory: every worker builds its own service over the same configured files."""
    options = json.loads(os.environ['AXIOM_SERVICE_OPTIONS'])
    return create_app(Service(**options['service']), **options['http'])


def integer(request, name, default):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if INTEGER.fullmatch(raw) is None:
        raise QueryError('INVALID_PARAMETER', f'{name} is an integer')
    return int(raw)


def required(request, name):
    value = request.query_params.get(name)
    if not value:
        raise QueryError('INVALID_PARAMETER', f'{name} is required')
    return value


def create_app(service, allowed_hosts=(), max_inflight=32, body_timeout=15, allowed_origins=()):
    mcp_server = mcp_tools.build(service)
    hosts = ['127.0.0.1:*', 'localhost:*', '[::1]:*', *allowed_hosts]
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path='/', json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                                     allowed_origins=[f'http://{host}' for host in hosts] + list(allowed_origins)))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title='AxiomSpec service', version=EDITION, openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(RequestLimits, max_inflight=max_inflight, body_timeout=body_timeout)
    app.add_exception_handler(QueryError, lambda request, error: problem(error))
    # Any other exception is a defect of the service. The caller still receives a problem document.
    app.add_exception_handler(Exception, lambda request, error: problem(
        QueryError('INTERNAL_ERROR', 'The service could not answer this request', 500)))
    contract = (PACKAGE / 'api/openapi.json').read_bytes()

    def answer(request, result, immutable=False, status=200):
        """JSON with an ETag. `immutable` says the answer is a function of the digests the request names."""
        body = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        headers = {'ETag': etag, 'Cache-Control': IMMUTABLE if immutable else 'no-cache'}
        if request.headers.get('if-none-match') == etag:
            return Response(status_code=304, headers=headers)
        return Response(body, status_code=status, media_type='application/json', headers=headers)

    def of_release(digest):
        """A read of the release alone: immutable when it is named by digest."""
        return digest != 'current'

    def of_code(digest):
        """A read that also uses annotations and bindings: immutable only when no code is read."""
        return digest != 'current' and not service.reads_code

    async def body_of(request):
        """The request body as strict JSON within the size of one store file."""
        too_large = QueryError('PAYLOAD_TOO_LARGE', f'A body is at most {MAX_BODY_BYTES} bytes; send the compact form, '
                               'or place a larger release in the store as parts', 413)
        declared = request.headers.get('content-length', '')
        if INTEGER.fullmatch(declared) and int(declared) > MAX_BODY_BYTES:
            raise too_large
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY_BYTES:
                raise too_large
        try:
            return await run_in_threadpool(strict_json, bytes(raw))
        except (ValueError, RecursionError) as error:
            raise QueryError('INVALID_DOCUMENT', f'The body is not strict JSON: {str(error)[:200]}', 422)

    def paging(request):
        return dict(budget_bytes=integer(request, 'budget_bytes', 32768), cursor=request.query_params.get('cursor'))

    @app.get('/health/live')
    async def live():
        return JSONResponse({'status': 'live'}, headers={'Cache-Control': 'no-store'})

    @app.get('/health/ready')
    def ready():
        if not service.ready():
            return problem(QueryError('STORAGE_UNAVAILABLE', 'The configured store is not accessible.', 503))
        return JSONResponse({'status': 'ready', 'mode': service.mode, 'version': EDITION}, headers={'Cache-Control': 'no-store'})

    @app.get('/v1/openapi.json')
    def get_contract():
        return Response(contract, media_type='application/json')

    @app.get('/v1/snapshots')
    def list_snapshots(request: Request):
        return answer(request, service.call('listSnapshots'))

    @app.get('/v1/snapshots/{digest}/index')
    def get_index(request: Request, digest: str):
        return answer(request, service.call('getIndex', digest=digest), of_code(digest))

    @app.get('/v1/snapshots/{digest}/nodes/{id}')
    def lookup(request: Request, digest: str, id: str):
        return answer(request, service.call('lookup', digest=digest, id=id, detail=request.query_params.get('detail', 'brief')),
                      of_code(digest))

    @app.get('/v1/snapshots/{digest}/context')
    def context(request: Request, digest: str):
        ids = [part for part in required(request, 'ids').split(',') if part]
        return answer(request, service.call('context', digest=digest, ids=ids, scope=request.query_params.get('scope', 'direct'),
                                            **paging(request)), of_release(digest))

    @app.get('/v1/snapshots/{digest}/trace')
    def trace(request: Request, digest: str):
        query = request.query_params
        return answer(request, service.call('trace', digest=digest, path=query.get('path'), symbol=query.get('symbol'),
                                            id=query.get('id'), **paging(request)), of_code(digest))

    @app.get('/v1/snapshots/{digest}/gaps')
    def gaps(request: Request, digest: str):
        return answer(request, service.call('gaps', digest=digest, phase=request.query_params.get('phase', 'design'),
                                            **paging(request)), of_code(digest))

    if service.mode == 'organization':
        @app.get('/v1/projects/{project_id}')
        def get_project(request: Request, project_id: str):
            return answer(request, service.call('getProject', project_id=project_id))

        @app.get('/v1/releases/{digest}')
        def get_release(request: Request, digest: str):
            return answer(request, service.call('getRelease', digest=digest), of_release(digest))

        @app.put('/v1/releases/{digest}')
        async def put_release(request: Request, digest: str):
            body = await body_of(request)
            return answer(request, await run_in_threadpool(service.call, 'putRelease', digest=digest, body=body))

        @app.get('/v1/releases/{digest}/approvals')
        def get_approvals(request: Request, digest: str):
            return answer(request, service.call('getApprovals', digest=digest))

        @app.put('/v1/releases/{digest}/approvals')
        async def put_approvals(request: Request, digest: str):
            body = await body_of(request)
            return answer(request, await run_in_threadpool(service.call, 'putApprovals', digest=digest, body=body))

        @app.get('/v1/releases/{digest}/verdict')
        def get_verdict(request: Request, digest: str):
            return answer(request, service.call('getVerdict', digest=digest))

        @app.get('/v1/releases/{digest}/statement')
        def get_statement(request: Request, digest: str):
            return answer(request, service.call('getStatement', digest=digest, actor=required(request, 'actor'),
                                                key=required(request, 'key')), of_release(digest))

        @app.get('/v1/compare')
        def compare(request: Request):
            return answer(request, service.call('compare', baseline=required(request, 'baseline'), candidate=required(request, 'candidate')),
                          immutable=True)

        @app.get('/v1/impact')
        def impact(request: Request):
            return answer(request, service.call('impact', baseline=required(request, 'baseline'), candidate=required(request, 'candidate')))

        @app.post('/v1/candidates')
        async def propose(request: Request):
            body = await body_of(request)
            if (not isinstance(body, dict) or set(body) != {'baseline', 'version', 'operations'}
                    or not isinstance(body['baseline'], str) or not isinstance(body['version'], str)):
                raise QueryError('INVALID_PARAMETER', 'The body has baseline and version as strings, and operations')
            result = await run_in_threadpool(service.call, 'propose', **body)
            # 201 only when a release was created; a refused candidate creates nothing and gets 200.
            response = answer(request, result, status=201 if result.get('held') else 200)
            if result.get('held'):
                response.headers['Location'] = f"/v1/releases/{result['spec_sha256']}"
            return response

    app.mount('/mcp', mcp_app)
    return app
