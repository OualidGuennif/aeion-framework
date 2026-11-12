"""Bound admission and request bodies before REST or MCP parses untrusted input."""
import json
import threading

import anyio
from starlette.responses import Response

from .service import MAX_BODY_BYTES, QueryError

TITLES = {400: 'Invalid request', 404: 'Not found', 405: 'Method not allowed', 408: 'Request timeout', 409: 'Conflict',
          413: 'Body too large', 422: 'Invalid document', 500: 'Internal error', 503: 'Service unavailable'}


def problem(error):
    body = dict(type='about:blank', title=TITLES.get(error.status, 'Error'), status=error.status,
                code=error.code, detail=str(error))
    headers = {'Cache-Control': 'no-store'}
    if error.status == 503:
        headers['Retry-After'] = '1'
    return Response(json.dumps(body), status_code=error.status, media_type='application/problem+json', headers=headers)


class RequestLimits:
    """A fail-fast per-process gate. No unbounded admission queue or background work after rejection."""

    def __init__(self, app, max_inflight=32, body_timeout=15):
        if max_inflight < 1 or body_timeout <= 0:
            raise ValueError('max_inflight and body_timeout must be positive')
        self.app, self.body_timeout = app, body_timeout
        self.slots = threading.BoundedSemaphore(max_inflight)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or (scope['method'] == 'GET' and scope['path'] in ('/health/live', '/health/ready')):
            return await self.app(scope, receive, send)

        async def reject(error):
            return await problem(error)(scope, receive, send)

        if not self.slots.acquire(blocking=False):
            return await reject(QueryError('OVERLOADED', 'This worker is at capacity; retry with backoff.', 503))
        try:
            lengths = [value for name, value in scope['headers'] if name.lower() == b'content-length']
            if lengths:
                if len(lengths) != 1 or not lengths[0] or not all(48 <= byte <= 57 for byte in lengths[0]):
                    return await reject(QueryError('INVALID_PARAMETER', 'Content-Length must be one non-negative integer.'))
                normalized = lengths[0].lstrip(b'0') or b'0'
                if len(normalized) > 9 or int(normalized) > MAX_BODY_BYTES:
                    return await reject(QueryError('PAYLOAD_TOO_LARGE', f'A body is at most {MAX_BODY_BYTES} bytes.', 413))
            raw = bytearray()
            try:
                with anyio.fail_after(self.body_timeout):
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return
                        chunk = message.get('body', b'')
                        if len(raw) + len(chunk) > MAX_BODY_BYTES:
                            return await reject(QueryError('PAYLOAD_TOO_LARGE', f'A body is at most {MAX_BODY_BYTES} bytes.', 413))
                        raw.extend(chunk)
                        if not message.get('more_body', False):
                            break
            except TimeoutError:
                return await reject(QueryError('BODY_TIMEOUT', 'The request body did not arrive in time.', 408))
            body, delivered = bytes(raw), False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return dict(type='http.request', body=body, more_body=False)
                return await receive()

            return await self.app(scope, buffered_receive, send)
        finally:
            self.slots.release()
