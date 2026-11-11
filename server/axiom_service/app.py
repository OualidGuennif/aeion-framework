"""HTTP transport: the routes of AxiomSpec/api/openapi.json over the service.

The contract file is the interface; this module conforms to it and serves it at /v1/openapi.json. A read is
a GET on a release named by digest, so its answer is immutable: it carries an ETag and may be cached forever.
In sandbox mode no other method and no organization route exists.
"""
from contextlib import asynccontextmanager
import hashlib
import json

from fastapi import FastAPI, Request
from fastapi.responses import Response
from mcp.server.transport_security import TransportSecuritySettings

from . import mcp_tools
from .service import PACKAGE, QueryError, canonical

IMMUTABLE = 'public, max-age=31536000, immutable'
TITLES = {400: 'Invalid request', 404: 'Not found', 409: 'Digest mismatch', 422: 'Invalid document'}


def problem(error):
    body = dict(type='about:blank', title=TITLES.get(error.status, 'Error'), status=error.status, code=error.code, detail=str(error))
    return Response(json.dumps(body), status_code=error.status, media_type='application/problem+json')


def integer(request, name, default):
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not raw.isdigit():
        raise QueryError('INVALID_PARAMETER', f'{name} is an integer')
    return int(raw)


def required(request, name):
    value = request.query_params.get(name)
    if not value:
        raise QueryError('INVALID_PARAMETER', f'{name} is required')
    return value


def create_app(service, allowed_hosts=()):
    mcp_server = mcp_tools.build(service)
    hosts = ['127.0.0.1:*', 'localhost:*', '[::1]:*', *allowed_hosts]
    mcp_app = mcp_server.streamable_http_app(
        streamable_http_path='/', json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts,
                                                     allowed_origins=[f'http://{host}' for host in hosts]))

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title='AxiomSpec service', version='1.0.0', openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_exception_handler(QueryError, lambda request, error: problem(error))
    contract = (PACKAGE / 'api/openapi.json').read_bytes()

    def answer(request, result, digest=None, status=200):
        """JSON with caching headers: immutable when the request named the release by digest."""
        body = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        headers = {'ETag': etag, 'Cache-Control': IMMUTABLE if digest not in (None, 'current') else 'no-cache'}
        if request.headers.get('if-none-match') == etag:
            return Response(status_code=304, headers=headers)
        return Response(body, status_code=status, media_type='application/json', headers=headers)

    async def body_of(request):
        raw = await request.body()
        try:
            return json.loads(raw)
        except ValueError:
            raise QueryError('INVALID_DOCUMENT', 'The body is not JSON', 422)

    def paging(request):
        return dict(budget_bytes=integer(request, 'budget_bytes', 32768), cursor=request.query_params.get('cursor'))

    @app.get('/v1/openapi.json')
    def get_contract():
        return Response(contract, media_type='application/json')

    @app.get('/v1/snapshots')
    def list_snapshots(request: Request):
        return answer(request, service.call('listSnapshots'))

    @app.get('/v1/snapshots/{digest}/index')
    def get_index(request: Request, digest: str):
        return answer(request, service.call('getIndex', digest=digest), digest)

    @app.get('/v1/snapshots/{digest}/nodes/{id}')
    def lookup(request: Request, digest: str, id: str):
        return answer(request, service.call('lookup', digest=digest, id=id, detail=request.query_params.get('detail', 'brief')), digest)

    @app.get('/v1/snapshots/{digest}/context')
    def context(request: Request, digest: str):
        ids = [part for part in required(request, 'ids').split(',') if part]
        return answer(request, service.call('context', digest=digest, ids=ids, scope=request.query_params.get('scope', 'direct'),
                                            **paging(request)), digest)

    @app.get('/v1/snapshots/{digest}/trace')
    def trace(request: Request, digest: str):
        query = request.query_params
        return answer(request, service.call('trace', digest=digest, path=query.get('path'), symbol=query.get('symbol'),
                                            id=query.get('id'), **paging(request)), digest)

    @app.get('/v1/snapshots/{digest}/gaps')
    def gaps(request: Request, digest: str):
        return answer(request, service.call('gaps', digest=digest, phase=request.query_params.get('phase', 'design'),
                                            **paging(request)), digest)

    if service.mode == 'organization':
        @app.get('/v1/projects/{project_id}')
        def get_project(request: Request, project_id: str):
            return answer(request, service.call('getProject', project_id=project_id))

        @app.get('/v1/releases/{digest}')
        def get_release(request: Request, digest: str):
            return answer(request, service.call('getRelease', digest=digest), digest)

        @app.put('/v1/releases/{digest}')
        async def put_release(request: Request, digest: str):
            return answer(request, service.call('putRelease', digest=digest, body=await body_of(request)))

        @app.get('/v1/releases/{digest}/approvals')
        def get_approvals(request: Request, digest: str):
            return answer(request, service.call('getApprovals', digest=digest))

        @app.put('/v1/releases/{digest}/approvals')
        async def put_approvals(request: Request, digest: str):
            return answer(request, service.call('putApprovals', digest=digest, body=await body_of(request)))

        @app.get('/v1/releases/{digest}/verdict')
        def get_verdict(request: Request, digest: str):
            return answer(request, service.call('getVerdict', digest=digest))

        @app.get('/v1/releases/{digest}/statement')
        def get_statement(request: Request, digest: str):
            return answer(request, service.call('getStatement', digest=digest, actor=required(request, 'actor'),
                                                key=required(request, 'key')), digest)

        @app.get('/v1/compare')
        def compare(request: Request):
            return answer(request, service.call('compare', baseline=required(request, 'baseline'), candidate=required(request, 'candidate')), 'immutable')

        @app.get('/v1/impact')
        def impact(request: Request):
            return answer(request, service.call('impact', baseline=required(request, 'baseline'), candidate=required(request, 'candidate')))

        @app.post('/v1/candidates')
        async def propose(request: Request):
            body = await body_of(request)
            if not isinstance(body, dict) or set(body) != {'baseline', 'version', 'operations'}:
                raise QueryError('INVALID_PARAMETER', 'The body has baseline, version and operations')
            return answer(request, service.call('propose', **body), status=201)

    app.mount('/mcp', mcp_app)
    return app
