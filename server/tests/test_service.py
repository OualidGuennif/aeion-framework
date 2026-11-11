"""The reference service against its contract (AxiomSpec/api/openapi.json).

Each answer is validated against the schema the contract names and compared with the reference query it
transports, so the HTTP routes and the MCP tools cannot add or lose anything. The store is a temporary copy
of the examples; the keys are the fictional ones of the package.
"""
import asyncio
import copy
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))
from axiom_service.app import create_app  # noqa: E402
from axiom_service import mcp_tools  # noqa: E402
from axiom_service.service import PACKAGE, Service  # noqa: E402

import approvals  # noqa: E402
import fictional_keys as fk  # noqa: E402
import queries  # noqa: E402
import release_diff  # noqa: E402
from check_package import canonical, digest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402
from mcp import Client  # noqa: E402
import uvicorn  # noqa: E402

LEDGER = PACKAGE / 'examples/refund-ledger'
CONTRACT = json.loads((PACKAGE / 'api/openapi.json').read_text())
APP = 'examples/refund-ledger/app/ledger.py'
PASSKEYS = [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')]
load = lambda path: json.loads(Path(path).read_text())


def valid(name, body):
    queries.contract_validator(name).validate(body)
    return body


class Case(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='axiomspec-service-')
        self.store = Path(self.directory.name) / 'store'
        shutil.copytree(PACKAGE / 'examples', self.store, ignore=shutil.ignore_patterns('app', 'tests', 'axiom-graph.json'))
        self.spec, self.base = load(LEDGER / 'spec.json'), load(LEDGER / 'releases/1.0.0.json')
        self.identity = load(PACKAGE / 'examples/identity-adapter/spec.json')
        self.head, self.first, self.provider = (digest(canonical(d)) for d in (self.spec, self.base, self.identity))
        self.addCleanup(self.directory.cleanup)

    def sandbox(self):
        return Service([self.store], snapshot=self.head, repository=PACKAGE, include=['examples/refund-ledger'])

    def client(self, service):
        client = TestClient(create_app(service))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def successor(self, baseline, version, nid='REQ-010'):
        spec = copy.deepcopy(baseline)
        spec['release'] = dict(version=version, compatibility=[], previous=dict(version=baseline['release']['version'],
                                                                              spec_sha256=digest(canonical(baseline))))
        node = next(n for n in spec['nodes'] if n['id'] == nid)
        node['title'] += ' (reworded)'
        node['revision'] += 1
        return spec


class Sandbox(Case):
    def setUp(self):
        super().setUp()
        self.service = self.sandbox()
        self.http = self.client(self.service)
        self.snapshot = queries.Snapshot(self.spec, self.service.snapshot('current').annotations, PACKAGE)

    def get(self, path, status=200, **headers):
        response = self.http.get(path, headers=headers)
        self.assertEqual(response.status_code, status, response.text[:300])
        return response

    def test_it_serves_exactly_one_snapshot(self):
        body = valid('SnapshotList', self.get('/v1/snapshots').json())
        self.assertEqual(body, dict(mode='sandbox', snapshots=[dict(project_id='PROJECT-001', version='1.1.0', spec_sha256=self.head)]))
        for other in (self.first, self.provider, 'f' * 64):
            problem = valid('Problem', self.get(f'/v1/snapshots/{other}/nodes/REQ-004', 404).json())
            self.assertEqual(problem['code'], 'NOT_FOUND')
        with self.assertRaisesRegex(ValueError, 'one snapshot'):
            Service([self.store])
        with self.assertRaisesRegex(ValueError, 'not in the store'):
            Service([self.store], snapshot='0' * 64)
        self.assertEqual(Service([LEDGER / 'spec.json']).only, self.head)

    def test_only_the_read_operations_exist_and_only_as_get(self):
        for path, item in CONTRACT['paths'].items():
            concrete = path.replace('{digest}', self.head).replace('{id}', 'REQ-004').replace('{project_id}', 'PROJECT-001')
            for method, operation in item.items():
                response = self.http.request(method.upper(), concrete, json={})
                if 'sandbox' in operation['x-axiom-modes']:
                    self.assertNotIn(response.status_code, (404, 405), path)
                else:
                    self.assertIn(response.status_code, (404, 405), path)
            if 'get' in item and 'sandbox' in item['get']['x-axiom-modes']:
                for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                    self.assertEqual(self.http.request(method, concrete, json={}).status_code, 405, path)
        self.assertEqual(self.get('/v1/openapi.json').json(), CONTRACT)

    def test_every_read_answers_what_the_reference_query_answers(self):
        base = f'/v1/snapshots/{self.head}'
        self.assertEqual(valid('GraphIndex', self.get(base + '/index').json()), self.snapshot.graph)
        self.assertEqual(self.get(base + '/index').json(), load(LEDGER / 'axiom-graph.json'))
        for detail in ('brief', 'full'):
            self.assertEqual(valid('NodeView', self.get(f'{base}/nodes/REQ-007?detail={detail}').json()),
                             queries.lookup(self.snapshot, 'REQ-007', detail))
        self.assertEqual(valid('ContextPage', self.get(base + '/context?ids=REQ-007').json()), queries.context(self.snapshot, ['REQ-007']))
        self.assertEqual(valid('ContextPage', self.get(base + '/context?ids=REQ-005,REQ-004&scope=change&budget_bytes=8192').json()),
                         queries.context(self.snapshot, ['REQ-004', 'REQ-005'], 'change', 8192))
        self.assertEqual(valid('TracePage', self.get(f'{base}/trace?path={APP}&symbol=Ledger.reserve').json()),
                         queries.trace(self.snapshot, path=APP, symbol='Ledger.reserve'))
        self.assertEqual(valid('TracePage', self.get(base + '/trace?id=REQ-004').json()), queries.trace(self.snapshot, object_id='REQ-004'))
        for phase in ('design', 'implementation'):
            self.assertEqual(valid('GapsPage', self.get(f'{base}/gaps?phase={phase}').json()), queries.gaps(self.snapshot, phase))

    def test_pages_follow_their_cursor_over_http(self):
        path = f'/v1/snapshots/current/context?ids=REQ-004&scope=change'
        page, seen = self.get(path).json(), []
        while True:
            self.assertLessEqual(len(self.get(path).content), 32768)
            seen += [item['id'] for item in page['items']]
            if page['next_cursor'] is None:
                break
            page = valid('ContextPage', self.get(f"{path}&cursor={page['next_cursor']}").json())
        self.assertEqual((len(seen), len(set(seen)), page['complete']), (page['total_visible_count'], len(seen), True))

    def test_a_named_digest_is_cacheable_forever_and_current_is_not(self):
        named = self.get(f'/v1/snapshots/{self.head}/nodes/REQ-004')
        alias = self.get('/v1/snapshots/current/nodes/REQ-004')
        self.assertEqual(named.json(), alias.json())
        self.assertEqual((named.headers['cache-control'], alias.headers['cache-control']), ('public, max-age=31536000, immutable', 'no-cache'))
        self.assertEqual(named.headers['etag'], alias.headers['etag'])
        again = self.get(f'/v1/snapshots/{self.head}/nodes/REQ-004', 304, **{'If-None-Match': named.headers['etag']})
        self.assertEqual(again.content, b'')
        self.get(f'/v1/snapshots/{self.head}/nodes/REQ-004', 200, **{'If-None-Match': '"something-else"'})
        self.assertEqual(named.headers['content-type'], 'application/json')

    def test_errors_are_problem_documents_with_a_code(self):
        base = '/v1/snapshots/current'
        cursor = self.get(base + '/context?ids=REQ-004&scope=change').json()['next_cursor']
        for path, status, code in [
                (base + '/nodes/REQ-999', 404, 'NOT_FOUND'), (base + '/nodes/REQ-004?detail=all', 400, 'INVALID_PARAMETER'),
                (base + '/context', 400, 'INVALID_PARAMETER'), (base + '/context?ids=REQ-004&scope=wide', 400, 'INVALID_PARAMETER'),
                (base + '/context?ids=REQ-004&budget_bytes=many', 400, 'INVALID_PARAMETER'),
                (base + '/context?ids=REQ-004&budget_bytes=12', 400, 'INVALID_PARAMETER'),
                (base + f'/context?ids=REQ-005&scope=change&cursor={cursor}', 400, 'INVALID_CURSOR'),
                (base + '/context?ids=REQ-999', 404, 'NOT_FOUND'), (base + '/trace', 400, 'INVALID_PARAMETER'),
                (base + '/trace?id=REQ-004&path=x.py', 400, 'INVALID_PARAMETER'), (base + '/gaps?phase=release', 400, 'INVALID_PARAMETER')]:
            response = self.get(path, status)
            self.assertEqual(response.headers['content-type'], 'application/problem+json')
            problem = valid('Problem', response.json())
            self.assertEqual((problem['status'], problem['code']), (status, code), path)

    def test_the_service_never_writes(self):
        before = sorted(p.name for p in self.store.rglob('*'))
        with self.assertRaises(queries.QueryError) as raised:
            self.service.call('propose', baseline=self.head, version='1.1.1', operations=[dict(op='retire', id='CON-006')])
        self.assertEqual(raised.exception.code, 'READ_ONLY')
        self.assertEqual(sorted(p.name for p in self.store.rglob('*')), before)


class Organization(Case):
    def setUp(self):
        super().setUp()
        self.service = Service([self.store], 'organization')
        self.http = self.client(self.service)

    def get(self, path, status=200):
        response = self.http.get(path)
        self.assertEqual(response.status_code, status, response.text[:300])
        return response.json()

    def test_every_operation_of_the_contract_has_a_route(self):
        for path, item in CONTRACT['paths'].items():
            concrete = (path.replace('{digest}', self.head).replace('{id}', 'REQ-004').replace('{project_id}', 'PROJECT-001'))
            for method in item:
                response = self.http.request(method.upper(), concrete, json={})
                self.assertNotEqual(response.status_code, 405, path)
                self.assertFalse(response.status_code == 404 and 'Not Found' in response.text and 'code' not in response.text, path)

    def test_releases_projects_and_verdicts(self):
        listed = valid('SnapshotList', self.get('/v1/snapshots'))
        self.assertEqual([(s['project_id'], s['version']) for s in listed['snapshots']],
                         [('PROJECT-001', '1.0.0'), ('PROJECT-001', '1.1.0'), ('PROJECT-002', '1.0.0')])
        project = valid('Project', self.get('/v1/projects/PROJECT-001'))
        self.assertEqual(project, dict(project_id='PROJECT-001', head=dict(version='1.1.0', spec_sha256=self.head), tied_heads=[], orphaned_heads=[],
                                       releases=[dict(version='1.0.0', spec_sha256=self.first, status='pass'),
                                                 dict(version='1.1.0', spec_sha256=self.head, status='pass')]))
        self.assertEqual(valid('Release', self.get(f'/v1/releases/{self.head}')), self.spec)
        self.assertEqual(valid('Approvals', self.get(f'/v1/releases/{self.head}/approvals')), load(LEDGER / 'approvals.json'))
        verdict = valid('Verdict', self.get(f'/v1/releases/{self.head}/verdict'))
        self.assertEqual((verdict['status'], verdict['link'], verdict['comparison'], verdict['approvals'], verdict['errors']),
                         ('pass', 'present', 'pass', 'pass', []))
        self.assertEqual(verdict['imports'], [dict(id='IMP-001', project_id='PROJECT-002', version='1.0.0', state='resolved')])
        self.assertEqual(valid('Problem', self.get('/v1/projects/PROJECT-777', 404))['code'], 'NOT_FOUND')
        self.assertEqual(valid('Problem', self.get(f"/v1/releases/{'e' * 64}", 404))['code'], 'NOT_FOUND')
        # Any release of the store can be read as a snapshot here, by digest only.
        self.assertEqual(self.get(f'/v1/snapshots/{self.provider}/nodes/REQ-001')['requirement']['risk'], 'critical')
        self.assertEqual(self.get('/v1/snapshots/current/nodes/REQ-001', 404)['code'], 'NOT_FOUND')

    def test_compare_impact_and_statement(self):
        comparison = valid('Comparison', self.get(f'/v1/compare?baseline={self.first}&candidate={self.head}'))
        self.assertEqual(comparison, release_diff.compare(self.base, self.spec))
        self.assertEqual(self.get(f'/v1/compare?baseline={self.first}', 400)['code'], 'INVALID_PARAMETER')
        candidate = copy.deepcopy(self.identity)
        candidate['release'] = dict(version='2.0.0', compatibility=[], previous=dict(version='1.0.0', spec_sha256=self.provider))
        requirement = next(n for n in candidate['nodes'] if n['id'] == 'REQ-001')
        requirement['data']['response'] = 'return a principal marked verified for any credential'
        requirement['revision'] += 1
        key = digest(canonical(candidate))
        self.assertEqual(self.http.put(f'/v1/releases/{key}', json=candidate).status_code, 200)
        impact = valid('Impact', self.get(f'/v1/impact?baseline={self.provider}&candidate={key}'))
        consumer, = impact['consumers']
        self.assertEqual((consumer['project_id'], consumer['requirements'], consumer['score']),
                         ('PROJECT-001', [dict(id='REQ-004', weight_minor=950, factor_percent=25)], '23.750'))
        statement = valid('Statement', self.get(f'/v1/releases/{self.head}/statement?actor=ACTOR-001&key=KEY-001'))
        message = approvals.statement(self.spec, 'ACTOR-001', 'KEY-001', 'device_passkey')
        self.assertEqual(statement, dict(statement=message.decode(), sha256=digest(message), webauthn_challenge=approvals.challenge(message)))
        self.assertEqual(self.get(f'/v1/releases/{self.head}/statement?actor=ACTOR-001&key=KEY-404', 404)['code'], 'NOT_FOUND')
        self.assertEqual(self.get(f'/v1/releases/{self.head}/statement?actor=ACTOR-001', 400)['code'], 'INVALID_PARAMETER')

    def test_a_release_is_uploaded_by_digest_and_a_repeat_changes_nothing(self):
        candidate = self.successor(self.spec, '1.1.1')
        key = digest(canonical(candidate))
        first = self.http.put(f'/v1/releases/{key}', json=candidate)
        self.assertEqual(first.status_code, 200)
        verdict = valid('Verdict', first.json())
        self.assertEqual((verdict['status'], verdict['link'], verdict['comparison'], verdict['approvals']), ('pass', 'present', 'pass', 'pass'))
        self.assertEqual(load(self.store / f'{key}.json'), candidate)
        files = sorted(p.name for p in self.store.rglob('*.json'))
        self.assertEqual(self.http.put(f'/v1/releases/{key}', json=candidate).json(), verdict)
        self.assertEqual(sorted(p.name for p in self.store.rglob('*.json')), files)
        self.assertEqual(self.get('/v1/projects/PROJECT-001')['head'], dict(version='1.1.1', spec_sha256=key))
        for digest_in_path, body, status, code in [(self.head, candidate, 409, 'DIGEST_MISMATCH'), ('1' * 64, {}, 409, 'DIGEST_MISMATCH')]:
            problem = self.http.put(f'/v1/releases/{digest_in_path}', json=body)
            self.assertEqual((problem.status_code, valid('Problem', problem.json())['code']), (status, code))
        shapeless = dict(format='axiomspec/0.3', nodes=[])
        problem = self.http.put(f'/v1/releases/{digest(canonical(shapeless))}', json=shapeless)
        self.assertEqual((problem.status_code, problem.json()['code']), (422, 'INVALID_DOCUMENT'))
        problem = self.http.put(f'/v1/releases/{key}', content=b'{not json', headers={'content-type': 'application/json'})
        self.assertEqual((problem.status_code, problem.json()['code']), (422, 'INVALID_DOCUMENT'))
        self.assertFalse(list(self.store.rglob('*.tmp')))

    def test_approvals_arrive_separately_and_merge_by_union(self):
        candidate = self.successor(self.spec, '1.1.1', 'REQ-004')  # critical: two approvers by passkey
        key = digest(canonical(candidate))
        self.assertEqual(self.http.put(f'/v1/releases/{key}', json=candidate).json()['approvals'], 'fail')
        halves = [fk.approvals_for(candidate, self.spec, [signer]) for signer in PASSKEYS]
        after_one = valid('Verdict', self.http.put(f'/v1/releases/{key}/approvals', json=halves[1]).json())
        self.assertEqual((after_one['status'], [e['code'] for e in after_one['errors']]), ('fail', ['INSUFFICIENT_APPROVALS']))
        after_two = self.http.put(f'/v1/releases/{key}/approvals', json=halves[0]).json()
        self.assertEqual((after_two['status'], after_two['approvals'], after_two['errors']), ('pass', 'pass', []))
        self.assertEqual(self.http.put(f'/v1/releases/{key}/approvals', json=halves[0]).json(), after_two)
        held = self.get(f'/v1/releases/{key}/approvals')
        self.assertEqual(held, approvals.merge(halves[0], halves[1]))
        self.assertEqual(load(self.store / f'{key}.approvals.json'), held)
        wrong = self.http.put(f'/v1/releases/{self.head}/approvals', json=halves[0])
        self.assertEqual((wrong.status_code, wrong.json()['code']), (409, 'DIGEST_MISMATCH'))
        unknown = self.http.put(f"/v1/releases/{'2' * 64}/approvals", json=halves[0])
        self.assertEqual((unknown.status_code, unknown.json()['code']), (404, 'NOT_FOUND'))
        shapeless = self.http.put(f'/v1/releases/{key}/approvals', json=dict(format='axiomspec-approvals/0.1'))
        self.assertEqual((shapeless.status_code, shapeless.json()['code']), (422, 'INVALID_DOCUMENT'))

    def test_a_candidate_is_built_from_edits_and_always_has_the_same_digest(self):
        node = copy.deepcopy(next(n for n in self.spec['nodes'] if n['id'] == 'REQ-010'))
        node['title'] += ' (reworded)'
        request = dict(baseline=self.head, version='1.1.1', operations=[dict(op='put', section='nodes', item=node)])
        created = self.http.post('/v1/candidates', json=request)
        self.assertEqual(created.status_code, 201)
        result = valid('CandidateResult', created.json())
        self.assertEqual(result, queries.propose(self.spec, '1.1.1', request['operations']))
        self.assertEqual((result['status'], result['comparison']['required_step']), ('pass', 'patch'))
        self.assertEqual(self.http.post('/v1/candidates', json=request).json()['spec_sha256'], result['spec_sha256'])
        self.assertEqual(self.get(f"/v1/releases/{result['spec_sha256']}"), result['candidate'])
        self.assertEqual(self.get(f"/v1/releases/{result['spec_sha256']}/verdict")['approvals'], 'pass')  # low band: no approver
        for body, status, code in [(dict(request, operations=[dict(op='delete', id='REQ-001')]), 400, 'INVALID_PARAMETER'),
                                   (dict(request, baseline='3' * 64), 404, 'NOT_FOUND'), (dict(baseline=self.head), 400, 'INVALID_PARAMETER'),
                                   ([], 400, 'INVALID_PARAMETER')]:
            problem = self.http.post('/v1/candidates', json=body)
            self.assertEqual((problem.status_code, valid('Problem', problem.json())['code']), (status, code))
        shapeless = self.http.post('/v1/candidates', json=dict(request, operations=[dict(op='put', section='nodes', item=dict(id='REQ-050'))])).json()
        self.assertEqual(shapeless['status'], 'fail')
        self.assertEqual(self.get(f"/v1/releases/{shapeless['spec_sha256']}", 404)['code'], 'NOT_FOUND')  # a shapeless candidate is not held

    def test_two_processes_on_one_directory_answer_the_same(self):
        other = self.client(Service([self.store], 'organization'))
        candidate = self.successor(self.spec, '1.1.1')
        key = digest(canonical(candidate))
        self.assertEqual(other.get(f'/v1/releases/{key}').status_code, 404)
        self.assertEqual(self.http.put(f'/v1/releases/{key}', json=candidate).status_code, 200)
        # The second process kept no state: it finds the new file when asked for a digest it has not seen.
        self.assertEqual(other.get(f'/v1/releases/{key}').json(), candidate)
        self.assertEqual(other.get(f'/v1/releases/{key}/verdict').json(), self.get(f'/v1/releases/{key}/verdict'))
        self.assertEqual(other.get('/v1/projects/PROJECT-001').json(), self.get('/v1/projects/PROJECT-001'))


class Tools(Case):
    def session(self, service, work):
        async def run():
            async with Client(mcp_tools.build(service)) as client:
                return await work(client)
        return asyncio.run(run())

    def test_the_sandbox_offers_four_tools_and_the_organization_eight(self):
        listed = self.session(self.sandbox(), lambda client: client.list_tools())
        self.assertEqual([tool.name for tool in listed.tools], ['axiom_lookup', 'axiom_context', 'axiom_trace', 'axiom_gaps'])
        organization = self.session(Service([self.store], 'organization'), lambda client: client.list_tools())
        self.assertEqual(len(organization.tools), 8)
        for tool in organization.tools:
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator.check_schema(tool.output_schema)
            self.assertNotIn('#/components/', json.dumps(tool.output_schema))  # self-contained: a client resolves nothing
        size = len(json.dumps([dict(name=t.name, description=t.description, inputSchema=t.input_schema) for t in listed.tools]))
        self.assertLess(size, 2600)

    def test_a_tool_answers_exactly_what_the_http_route_answers(self):
        service = self.sandbox()
        http = self.client(service)
        calls = [('axiom_lookup', dict(id='REQ-007'), '/v1/snapshots/current/nodes/REQ-007'),
                 ('axiom_lookup', dict(id='REQ-007', detail='full', snapshot=self.head), f'/v1/snapshots/{self.head}/nodes/REQ-007?detail=full'),
                 ('axiom_context', dict(ids=['REQ-007']), '/v1/snapshots/current/context?ids=REQ-007'),
                 ('axiom_context', dict(ids=['REQ-004'], scope='change', budget_bytes=8192), '/v1/snapshots/current/context?ids=REQ-004&scope=change&budget_bytes=8192'),
                 ('axiom_trace', dict(path=APP, symbol='authorize'), f'/v1/snapshots/current/trace?path={APP}&symbol=authorize'),
                 ('axiom_trace', dict(id='REQ-004'), '/v1/snapshots/current/trace?id=REQ-004'),
                 ('axiom_gaps', dict(phase='implementation'), '/v1/snapshots/current/gaps?phase=implementation')]
        tools = {tool.name: tool for tool in self.session(service, lambda client: client.list_tools()).tools}
        for name, arguments, path in calls:
            result = self.session(service, lambda client: client.call_tool(name, arguments))
            expected = http.get(path).json()
            self.assertFalse(result.is_error, name)
            self.assertEqual(result.structured_content, expected, name)
            self.assertEqual(json.loads(result.content[0].text), expected)
            Draft202012Validator(tools[name].output_schema).validate(result.structured_content)
        first = self.session(service, lambda client: client.call_tool('axiom_context', dict(ids=['REQ-004'], scope='change')))
        cursor = first.structured_content['next_cursor']
        second = self.session(service, lambda client: client.call_tool('axiom_context', dict(ids=['REQ-004'], scope='change', cursor=cursor)))
        self.assertEqual(second.structured_content, http.get(f'/v1/snapshots/current/context?ids=REQ-004&scope=change&cursor={cursor}').json())

    def test_a_tool_reports_an_error_with_its_code(self):
        service = self.sandbox()
        for name, arguments, code in [('axiom_lookup', dict(id='REQ-999'), 'NOT_FOUND'), ('axiom_lookup', dict(), 'INVALID_PARAMETER'),
                                      ('axiom_lookup', dict(id='REQ-004', extra=1), 'INVALID_PARAMETER'),
                                      ('axiom_context', dict(ids=['REQ-004'], scope='wide'), 'INVALID_PARAMETER'),
                                      ('axiom_trace', dict(), 'INVALID_PARAMETER'), ('axiom_lookup', dict(id='REQ-004', snapshot=self.first), 'NOT_FOUND'),
                                      ('axiom_propose', dict(baseline=self.head, version='1.1.1', operations=[dict(op='retire', id='CON-006')]), 'NOT_FOUND')]:
            result = self.session(service, lambda client: client.call_tool(name, arguments))
            self.assertTrue(result.is_error, name)
            self.assertTrue(result.content[0].text.startswith(code + ':'), result.content[0].text)

    def test_the_organization_tools_reach_the_store(self):
        service = Service([self.store], 'organization')
        verdict = self.session(service, lambda client: client.call_tool('axiom_verdict', dict(digest=self.head)))
        self.assertEqual(verdict.structured_content['status'], 'pass')
        compared = self.session(service, lambda client: client.call_tool('axiom_compare', dict(baseline=self.first, candidate=self.head)))
        self.assertEqual(compared.structured_content, release_diff.compare(self.base, self.spec))
        proposed = self.session(service, lambda client: client.call_tool('axiom_propose', dict(
            baseline=self.head, version='1.1.1', operations=[dict(op='retire', id='CON-006')])))
        self.assertEqual(proposed.structured_content['spec_sha256'], queries.propose(self.spec, '1.1.1', [dict(op='retire', id='CON-006')])['spec_sha256'])
        self.assertTrue((self.store / f"{proposed.structured_content['spec_sha256']}.json").is_file())
        lookup = self.session(service, lambda client: client.call_tool('axiom_lookup', dict(id='REQ-001', snapshot=self.provider)))
        self.assertEqual(lookup.structured_content['requirement']['risk'], 'critical')
        unnamed = self.session(service, lambda client: client.call_tool('axiom_lookup', dict(id='REQ-001')))
        self.assertTrue(unnamed.is_error)


class OverTheWire(Case):
    """One run over real sockets: what an agent in a sandbox does with curl, and an MCP client over HTTP."""

    def test_http_and_mcp_on_a_listening_port(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(self.sandbox(), ['axiom.test:*']), host='127.0.0.1', port=port, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if server.started:
                    break
                time.sleep(0.02)
            self.assertTrue(server.started)
            base = f'http://127.0.0.1:{port}'
            brief = httpx.get(f'{base}/v1/snapshots/current/nodes/REQ-004')
            self.assertEqual((brief.status_code, brief.json()['requirement']['weight_minor']), (200, 950))
            self.assertEqual(httpx.put(f'{base}/v1/releases/{self.head}', json=self.spec).status_code, 404)

            async def ask():
                async with Client(f'{base}/mcp/') as client:
                    listed = await client.list_tools()
                    answer = await client.call_tool('axiom_lookup', dict(id='REQ-004'))
                    return [tool.name for tool in listed.tools], answer
            names, answer = asyncio.run(ask())
            self.assertEqual(names, ['axiom_lookup', 'axiom_context', 'axiom_trace', 'axiom_gaps'])
            self.assertEqual(answer.structured_content, brief.json())
            call = dict(jsonrpc='2.0', id=1, method='tools/list')
            headers = {'accept': 'application/json, text/event-stream', 'content-type': 'application/json'}
            self.assertEqual(httpx.post(f'{base}/mcp/', json=call, headers=dict(headers, host='attacker.example')).status_code, 421)
            self.assertNotEqual(httpx.post(f'{base}/mcp/', json=call, headers=dict(headers, host=f'axiom.test:{port}')).status_code, 421)
        finally:
            server.should_exit = True
            thread.join(timeout=10)


if __name__ == '__main__':
    unittest.main()
