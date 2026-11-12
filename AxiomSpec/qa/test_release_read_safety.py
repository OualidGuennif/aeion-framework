"""Release authority, invalid-input isolation and bounded reads."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import check_package as qa  # noqa: E402
import fictional_keys as fk  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_store  # noqa: E402


def successor(baseline, version):
    spec = copy.deepcopy(baseline)
    spec['release'] = dict(version=version, compatibility=[], previous=dict(
        version=baseline['release']['version'], spec_sha256=qa.digest(qa.canonical(baseline))))
    return spec


class ReleaseAuthority(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')
        self.store = release_store.load([ROOT / 'examples'])

    def entry(self, report, spec):
        return next(r for r in report['releases'] if r['spec_sha256'] == qa.digest(qa.canonical(spec)))

    def test_an_unapproved_policy_cannot_authorize_its_descendants(self):
        policy = successor(self.spec, '1.1.1')
        for band in policy['approval']['policy'].values():
            band['approvers'] = 0
        child = successor(policy, '1.1.2')
        for spec in (policy, child):
            self.assertEqual(qa.reference_errors(spec), [])
            self.store.add_release(spec, spec['release']['version'])
        report = release_store.verify(self.store)
        self.assertEqual(self.entry(report, child)['status'], 'fail')
        self.assertIn('BASELINE_NOT_ACCEPTED', [e['code'] for e in report['errors']])
        project = next(p for p in report['projects'] if p['project_id'] == self.spec['project']['id'])
        self.assertEqual(project['accepted_head']['version'], '1.1.0')
        # Once the policy change is authorized under the old policy, its successor can pass.
        self.store.add_approvals(fk.approvals_for(policy, self.spec, [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')]))
        self.assertEqual(self.entry(release_store.verify(self.store), child)['status'], 'pass')

    def test_rotated_keys_need_an_approved_rotation_in_the_chain(self):
        rotation = successor(self.spec, '1.1.1')
        key = rotation['approval']['keys'][0]
        key['public_key'] = fk.public_key(key['algorithm'], 'unapproved rotation')
        child = successor(rotation, '1.1.2')
        changed = next(n for n in child['nodes'] if n['id'] == 'REQ-004')
        changed['title'] += ' revised'
        changed['revision'] += 1
        approvals = fk.approvals_for(child, rotation, [('ACTOR-003', 'KEY-002')])
        approvals['approvals'].append(fk.approve(child, rotation, 'ACTOR-001', key['id'], label='unapproved rotation'))
        self.store.add_release(rotation, 'rotation')
        self.store.add_release(child, 'child')
        self.store.add_approvals(approvals)
        entry = self.entry(release_store.verify(self.store), child)
        self.assertEqual((entry['approvals'], entry['status']), ('pass', 'fail'))

    def test_a_missing_ancestor_stays_unknown_in_either_arrival_order(self):
        parent = successor(self.spec, '1.1.1')
        child = successor(parent, '1.1.2')
        parent_approvals = fk.approvals_for(parent, self.spec, [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')])
        child_approvals = fk.approvals_for(child, parent, [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')])
        statuses = []
        for documents in ((parent, child), (child, parent)):
            store = release_store.Store()
            for spec in documents:
                store.add_release(spec, spec['release']['version'])
            store.add_approvals(parent_approvals)
            store.add_approvals(child_approvals)
            report = release_store.verify(store)
            statuses.append(self.entry(report, child)['status'])
            self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(statuses, ['unknown', 'unknown'])

    def test_invalid_relations_do_not_prevent_other_verdicts(self):
        invalid = successor(self.spec, '1.1.1')
        invalid['edges'].append(dict(id='EDGE-999999', relation='governs', origin='declared',
                                     rationale='Invalid self-link', **{'from': 'DEC-001', 'to': 'DEC-001'}))
        queries.spec_validator().validate(invalid)
        self.store.add_release(invalid, 'invalid')
        child = successor(invalid, '1.1.2')
        child['edges'].pop()
        self.store.add_release(child, 'child')
        report = release_store.verify(self.store)
        self.assertEqual(self.entry(report, self.spec)['status'], 'pass')
        self.assertEqual(self.entry(report, invalid)['status'], 'fail')
        self.assertEqual(self.entry(report, child)['status'], 'fail')
        self.assertTrue(any('WRONG_EDGE_TYPE' in e['message'] for e in report['errors']))


class ReadBudgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read('examples/identity-adapter/spec.json')
        cls.snapshot = queries.Snapshot(cls.spec)

    def test_many_omissions_are_paged_within_the_byte_budget(self):
        items = [dict(id=f'REQ-{n:03d}', content='é' * 20000) for n in range(150)]
        for budget in (4096, 32768):
            cursor, omitted = None, []
            while True:
                page = queries.page(self.snapshot, 'test', {}, items, budget, cursor)
                self.assertLessEqual(len(qa.canonical(page)), budget)
                omitted += [item['id'] for item in page['omissions']]
                cursor = page['next_cursor']
                self.assertFalse(page['complete'])
                if cursor is None:
                    break
            self.assertEqual(omitted, [item['id'] for item in items])

    def test_a_lookup_never_returns_an_oversized_statement_or_content(self):
        spec = copy.deepcopy(self.spec)
        req = next(n for n in spec['nodes'] if n['kind'] == 'Requirement')
        for field in ('response', 'trigger'):
            large = copy.deepcopy(spec)
            target = next(n for n in large['nodes'] if n['id'] == req['id'])
            target['data'][field] = 'é' * 16384
            queries.spec_validator().validate(large)
            for detail in ('brief', 'full'):
                with self.assertRaises(queries.QueryError) as raised:
                    queries.lookup(queries.Snapshot(large), req['id'], detail)
                self.assertEqual(raised.exception.code, 'RESPONSE_TOO_LARGE')


class PythonAnnotations(unittest.TestCase):
    def scan(self, source):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'app.py').write_text(source)
            return graph_index.scan(directory)

    def test_only_comments_and_actual_docstrings_are_annotations(self):
        source = '\n'.join([
            '"""Module @req REQ-001"""',
            'payload = "@req REQ-002"',
            '# @req REQ-003',
            'def f():',
            '    """Function @req REQ-004"""',
            '    return "@req REQ-005"',
            '"""Unattached string @req REQ-006"""',
        ])
        found = self.scan(source)
        self.assertEqual([a['ids'] for a in found], [['REQ-001'], ['REQ-003'], ['REQ-004']])
        self.assertEqual([a['line'] for a in found], [1, 3, 5])

    def test_comments_survive_an_incomplete_python_edit_without_guessing_docstrings(self):
        found = self.scan('# @req REQ-001\nx = "@req REQ-002"\ndef broken(:\n')
        self.assertEqual([a['ids'] for a in found], [['REQ-001']])


if __name__ == '__main__':
    unittest.main()
