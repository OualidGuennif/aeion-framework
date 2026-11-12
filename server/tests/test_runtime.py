"""Bounded overload, durable publication and the worker startup contract."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
from axiom_service.__main__ import arguments  # noqa: E402
from axiom_service.app import configured_app, create_app  # noqa: E402
from axiom_service.http_limits import RequestLimits  # noqa: E402
from axiom_service.service import MAX_BODY_BYTES, Service  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.responses import Response  # noqa: E402
from test_service import Case, LEDGER, canonical, digest  # noqa: E402
import release_store  # noqa: E402
import spec_parts  # noqa: E402


class Runtime(Case):
    def limited(self, service=None, **options):
        service = service or Service([self.store], 'organization')
        client = TestClient(create_app(service, **options))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return service, client

    def test_the_service_is_fastapi_and_exposes_cheap_live_and_storage_probes(self):
        service, client = self.limited()
        self.assertIsInstance(create_app(service), FastAPI)
        self.assertEqual(client.get('/health/live').json(), {'status': 'live'})
        self.assertEqual(client.get('/health/ready').json()['status'], 'ready')
        self.assertEqual(client.get('/health/ready').headers['cache-control'], 'no-store')
        self.store.rename(self.store.with_name('unavailable'))
        self.assertEqual(client.get('/health/live').status_code, 200)
        response = client.get('/health/ready')
        self.assertEqual((response.status_code, response.json()['code']), (503, 'STORAGE_UNAVAILABLE'))
        self.assertEqual(client.get('/v1/snapshots').status_code, 503)

    def test_excess_work_is_rejected_and_slots_recover_without_blocking_probes(self):
        service, client = self.limited(max_inflight=1)
        entered, release = threading.Event(), threading.Event()
        lookup = service._lookup

        def slow(**arguments):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('test worker did not get released')
            return lookup(**arguments)

        with mock.patch.object(service, '_lookup', side_effect=slow), ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.get, f'/v1/snapshots/{self.head}/nodes/REQ-004')
            try:
                self.assertTrue(entered.wait(3))
                rejected = client.get('/v1/snapshots')
                self.assertEqual((rejected.status_code, rejected.json()['code']), (503, 'OVERLOADED'))
                self.assertEqual(rejected.headers['retry-after'], '1')
                self.assertEqual(client.get('/health/live').status_code, 200)
                self.assertEqual(client.get('/health/ready').status_code, 200)
            finally:
                release.set()
            self.assertEqual(pending.result().status_code, 200)
        self.assertEqual(client.get('/v1/snapshots').status_code, 200)

    def test_operation_lock_wait_is_bounded(self):
        service, client = self.limited()
        service.lock_timeout = 0.02
        entered, release = threading.Event(), threading.Event()

        def hold_lock():
            with service.lock:
                entered.set()
                release.wait(5)

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(hold_lock)
            try:
                self.assertTrue(entered.wait(3))
                response = client.get('/v1/snapshots')
                self.assertEqual((response.status_code, response.json()['code']), (503, 'STORE_BUSY'))
                self.assertEqual(response.headers['retry-after'], '1')
            finally:
                release.set()
            pending.result()
        self.assertEqual(client.get('/v1/snapshots').status_code, 200)

    def test_body_limits_apply_before_both_rest_and_mcp_parse(self):
        _, client = self.limited()
        for path in ('/mcp/', f'/v1/releases/{self.head}'):
            response = client.post(path, content=b'x' * (MAX_BODY_BYTES + 1))
            self.assertEqual((response.status_code, response.json()['code']), (413, 'PAYLOAD_TOO_LARGE'))
            self.assertNotIn('Traceback', response.text)
        response = client.post('/mcp/', content=iter([b'x' * 600000, b'x' * 600000]))
        self.assertEqual((response.status_code, response.json()['code']), (413, 'PAYLOAD_TOO_LARGE'))
        self.assertEqual(client.get('/health/ready').status_code, 200)

    def test_a_zero_padded_content_length_is_not_mistaken_for_an_oversized_body(self):
        _, client = self.limited()
        response = client.request('GET', '/v1/snapshots', content=b'{}', headers={'Content-Length': '0000000002'})
        self.assertEqual(response.status_code, 200)

    def test_immutable_reads_skip_listing_but_unknown_digests_and_verdicts_refresh(self):
        service = Service([self.store], 'organization')
        with mock.patch.object(release_store, 'listing', wraps=release_store.listing) as listing:
            for _ in range(5):
                service.call('lookup', digest=self.head, id='REQ-004')
            self.assertEqual(listing.call_count, 0)
            with self.assertRaises(ValueError):
                service.call('lookup', digest='f' * 64, id='REQ-004')
            self.assertEqual(listing.call_count, 1)
            service.call('getVerdict', digest=self.head)
            self.assertEqual(listing.call_count, 2)

    def test_a_dense_invalid_specification_returns_a_bounded_diagnostic(self):
        _, client = self.limited()
        invalid = dict(self.identity, nodes=[0] * 400000)
        raw = canonical(invalid)
        self.assertLess(len(raw), MAX_BODY_BYTES)
        response = client.put('/v1/releases/' + digest(raw), content=raw)
        self.assertEqual((response.status_code, response.json()['code']), (422, 'INVALID_DOCUMENT'))
        self.assertLess(len(response.content), 2048)

    def test_a_failed_flush_never_publishes_an_acknowledged_release(self):
        service, client = self.limited()
        candidate = self.successor(self.spec, '1.1.1')
        key = digest(canonical(candidate))
        with mock.patch('axiom_service.service.os.fsync', side_effect=OSError(errno.ENOSPC, 'full storage')):
            response = client.put(f'/v1/releases/{key}', content=canonical(candidate))
        self.assertEqual((response.status_code, response.json()['code']), (503, 'STORAGE_UNAVAILABLE'))
        self.assertFalse((self.store / f'{key}.json').exists())
        self.assertFalse(list(self.store.glob('.incoming-*')))
        self.assertEqual(client.get(f'/v1/releases/{key}').status_code, 404)
        self.assertEqual(client.put(f'/v1/releases/{key}', content=canonical(candidate)).status_code, 200)
        self.assertEqual(Service([self.store], 'organization').call('getRelease', digest=key), candidate)

    def test_a_modified_part_invalidates_a_cached_release(self):
        directory = Path(self.directory.name) / 'parts'
        manifest = spec_parts.write(self.identity, directory, budget=2000)
        service = Service([manifest], 'organization')
        key = digest(canonical(self.identity))
        self.assertEqual(service.call('getRelease', digest=key), self.identity)
        part = next(directory.glob('*.part-*.json'))
        original = part.read_bytes()
        part.write_bytes(original + b' ')
        with self.assertRaises(ValueError) as error:
            service.call('getRelease', digest=key)
        self.assertEqual(error.exception.code, 'NOT_FOUND')
        self.assertTrue(service.store.rejected)
        part.write_bytes(original)
        self.assertEqual(service.call('getRelease', digest=key), self.identity)

    def test_concurrent_publication_is_idempotent_and_never_overwrites_other_bytes(self):
        path = self.store / 'publication.json'
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: Service.place(path, b'complete'), range(32)))
        self.assertEqual(path.read_bytes(), b'complete')
        with self.assertRaises(ValueError) as error:
            Service.place(path, b'other')
        self.assertEqual(error.exception.code, 'STORE_CONFLICT')
        self.assertEqual(path.read_bytes(), b'complete')
        self.assertFalse(list(self.store.glob('.incoming-*')))

    def test_each_worker_factory_builds_its_own_fastapi_service(self):
        settings = dict(service=dict(store_paths=[str(LEDGER / 'spec.json')]),
                        http=dict(max_inflight=4, body_timeout=3))
        with mock.patch.dict(os.environ, AXIOM_SERVICE_OPTIONS=json.dumps(settings)):
            first, second = configured_app(), configured_app()
        self.assertIsInstance(first, FastAPI)
        self.assertIsNot(first, second)


class BodyDeadline(unittest.IsolatedAsyncioTestCase):
    async def test_a_slow_body_is_timed_out_and_the_slot_is_reusable(self):
        async def downstream(scope, receive, send):
            await Response(b'ok')(scope, receive, send)

        middleware = RequestLimits(downstream, max_inflight=1, body_timeout=0.01)
        scope = dict(type='http', method='POST', path='/mcp/', headers=[])
        messages = []

        async def slow():
            await asyncio.sleep(1)

        async def send(message):
            messages.append(message)

        await middleware(scope, slow, send)
        self.assertEqual(messages[0]['status'], 408)
        self.assertEqual(json.loads(messages[1]['body'])['code'], 'BODY_TIMEOUT')
        messages.clear()

        async def complete():
            return dict(type='http.request', body=b'{}', more_body=False)

        await middleware(scope, complete, send)
        self.assertEqual(messages[0]['status'], 200)


class Startup(unittest.TestCase):
    def test_runtime_defaults_and_environment_overrides(self):
        with mock.patch.dict(os.environ, AXIOM_WORKERS='2', AXIOM_MAX_INFLIGHT='8', AXIOM_BODY_TIMEOUT='4'):
            options = arguments(['--store', '/data'])
        self.assertEqual((options.workers, options.max_inflight, options.body_timeout), (2, 8, 4))
        self.assertFalse(options.proxy_headers)
        self.assertFalse(options.access_log)


if __name__ == '__main__':
    unittest.main()
