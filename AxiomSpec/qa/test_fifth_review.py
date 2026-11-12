"""Regressions from the fifth review: each case failed on edition 0.7.0 and names the defect it closes.

The review ran the store, the approvals and the queries against hostile and concurrent inputs. What it found
was silence: a forged approval that replaced a valid one, a store file dropped without a word, an annotation
skipped because of a colon. Every case here requires the loud, deterministic outcome instead.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import approvals  # noqa: E402
import check_package as qa  # noqa: E402
import fictional_keys as fk  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_diff  # noqa: E402
import release_store  # noqa: E402

LEDGER = 'examples/refund-ledger'
PASSKEYS = [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')]
digest = lambda document: qa.digest(qa.canonical(document))


def successor(spec, version, edit=lambda new: None):
    new = copy.deepcopy(spec)
    new['release'] = dict(version=version, compatibility=[], previous=dict(version=spec['release']['version'], spec_sha256=digest(spec)))
    edit(new)
    return new


def reweigh(spec):
    """A patch-level edit of a critical requirement: it needs two approvers and has none."""
    requirement = next(n for n in spec['nodes'] if n['id'] == 'REQ-004')
    requirement['data']['weight_minor'] = 1000
    requirement['revision'] += 1


def store_of(*documents):
    store = release_store.Store()
    for document in documents:
        if document['format'] == release_diff.FORMAT:
            store.add_release(document, 'memory')
        else:
            store.add_approvals(document)
    return store


class Examples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec, cls.base = qa.read(LEDGER + '/spec.json'), qa.read(LEDGER + '/releases/1.0.0.json')
        cls.spec_approvals = qa.read(LEDGER + '/approvals.json')
        cls.base_approvals = qa.read(LEDGER + '/releases/1.0.0.approvals.json')
        cls.identity = qa.read('examples/identity-adapter/spec.json')
        cls.identity_approvals = qa.read('examples/identity-adapter/approvals.json')

    def everything(self):
        return [self.base, self.base_approvals, self.spec, self.spec_approvals, self.identity, self.identity_approvals]

    def forged(self):
        """Approvals of the same actors and keys whose signatures verify nothing and sort before the real ones."""
        hostile = copy.deepcopy(self.spec_approvals)
        for approval in hostile['approvals']:
            approval['signature'] = '++++'
            if approval['authenticator_data'] is not None:
                approval['authenticator_data'] = '++++'
        return hostile


class ApprovalsAreASet(Examples):
    def test_a_forged_approval_of_the_same_key_never_takes_the_place_of_a_valid_one(self):
        hostile = self.forged()
        self.assertEqual(approvals.verify(self.spec, hostile, self.base)['status'], 'fail')
        for merged in (approvals.merge(self.spec_approvals, hostile), approvals.merge(hostile, self.spec_approvals)):
            report = approvals.verify(self.spec, merged, self.base)
            self.assertEqual((report['status'], [r['code'] for r in report['rejected']]), ('pass', ['INVALID_SIGNATURE'] * 2))
            self.assertEqual(len(merged['approvals']), 4)
        report = release_store.verify(store_of(*self.everything(), hostile))
        self.assertEqual((report['status'], {r['status'] for r in report['releases']}), ('pass', {'pass'}))

    def test_merge_is_still_a_union_with_several_approvals_of_one_key(self):
        valid, hostile, resigned = self.spec_approvals, self.forged(), fk.approvals_for(self.spec, self.base, PASSKEYS)
        merge = approvals.merge
        self.assertEqual(merge(merge(valid, hostile), resigned), merge(valid, merge(hostile, resigned)))
        self.assertEqual(merge(merge(valid, hostile), resigned), merge(merge(resigned, hostile), valid))
        self.assertEqual(merge(merge(valid, hostile), hostile), merge(valid, hostile))
        self.assertEqual(len(merge(merge(valid, hostile), resigned)['approvals']), 6)

    def test_counted_keeps_the_approvals_that_verify_and_nothing_else(self):
        mixed = approvals.merge(self.spec_approvals, self.forged())
        self.assertEqual(sorted(a['signature'] for a in approvals.counted(self.spec, mixed, self.base)),
                         sorted(a['signature'] for a in self.spec_approvals['approvals']))
        self.assertEqual(approvals.counted(self.spec, self.forged(), self.base), [])
        self.assertEqual(approvals.counted(self.base, self.spec_approvals, self.base), [])  # approvals of another release

    def test_a_merged_set_larger_than_one_file_is_still_verified_by_the_store(self):
        junk = copy.deepcopy(self.spec_approvals)
        junk['approvals'] = [dict(junk['approvals'][0], signature=f'{number:04d}') for number in range(1024)]
        store = store_of(*self.everything(), junk, self.forged())
        self.assertGreater(len(store.approvals[digest(self.spec)]['approvals']), 1024)
        report = release_store.verify(store)
        self.assertEqual({r['status'] for r in report['releases']}, {'pass'})
        self.assertEqual(next(r for r in report['releases'] if r['version'] == '1.1.0')['approvals_set_aside'], 1026)

    def test_the_store_compares_a_release_with_its_baseline_once(self):
        store = store_of(*self.everything())
        with mock.patch.object(release_diff, 'compare', wraps=release_diff.compare) as compare:
            release_store.verify(store)
        self.assertEqual(compare.call_count, 1)  # one release of the examples names a baseline
        supplied = release_diff.compare(self.base, self.spec)
        with mock.patch.object(release_diff, 'compare', wraps=release_diff.compare) as compare:
            report = approvals.verify(self.spec, self.spec_approvals, self.base, supplied)
        self.assertEqual((compare.call_count, report), (0, approvals.verify(self.spec, self.spec_approvals, self.base)))


class StoreFiles(Examples):
    def directory(self):
        folder = tempfile.TemporaryDirectory(prefix='axiomspec-fifth-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        for position, document in enumerate(self.everything()):
            (root / f'{position}.json').write_text(json.dumps(document))
        return root

    def test_a_store_file_that_cannot_be_read_is_named_not_dropped(self):
        root = self.directory()
        big = successor(self.spec, '1.1.1')
        goal = next(n for n in big['nodes'] if n['kind'] == 'Goal')
        big['nodes'] += [dict(copy.deepcopy(goal), id=f'GOAL-{number:05d}') for number in range(1000, 3400)]
        (root / 'too-large.json').write_text(json.dumps(big, indent=2))
        self.assertGreater((root / 'too-large.json').stat().st_size, qa.BOUNDS['max_input_bytes'])
        (root / 'float.json').write_text(json.dumps(successor(self.spec, '1.1.1')).replace('"weight_minor_units": 10', '"weight_minor_units": 10.0'))
        (root / 'cut.json').write_text('{"format": "axiomspec-approvals/0.1", "approvals": [')
        (root / 'foreign-large.json').write_text(json.dumps(dict(format='something-else/1.0', rows=['x' * 100] * 12000)))
        report = release_store.verify(release_store.load([root]))
        self.assertEqual([Path(r['path']).name for r in report['rejected_files']], ['cut.json', 'float.json', 'too-large.json'])
        self.assertEqual((report['status'], {r['status'] for r in report['releases']}), ('incomplete', {'pass'}))
        self.assertIn('Input byte limit', next(r['reason'] for r in report['rejected_files'] if r['path'].endswith('too-large.json')))

    def test_nothing_is_read_below_a_name_that_starts_with_a_dot(self):
        root = self.directory()
        (root / '.incoming-x').mkdir()
        (root / '.incoming-x' / 'half.json').write_text('{"format": "axiomspec/0.3", ')
        (root / '.staged.json').write_text('{"format": "axiomspec/0.3", ')
        self.assertEqual(release_store.verify(release_store.load([root]))['status'], 'pass')

    def test_a_refused_release_is_the_head_and_never_the_accepted_head(self):
        refused = successor(self.spec, '1.1.1', reweigh)
        report = release_store.verify(store_of(*self.everything(), refused))
        project = next(p for p in report['projects'] if p['project_id'] == 'PROJECT-001')
        self.assertEqual(next(r for r in report['releases'] if r['version'] == '1.1.1')['status'], 'fail')
        self.assertEqual((project['head'], project['accepted_head']),
                         (dict(version='1.1.1', spec_sha256=digest(refused)), dict(version='1.1.0', spec_sha256=digest(self.spec))))
        alone = release_store.verify(store_of(self.spec))  # baseline absent: unknown, so nothing is accepted yet
        self.assertEqual((alone['projects'][0]['head']['version'], alone['projects'][0]['accepted_head']), ('1.1.0', None))

    def test_impact_measures_a_consumer_at_its_accepted_head(self):
        step = successor(self.identity, '2.0.0')
        requirement = next(n for n in step['nodes'] if n['id'] == 'REQ-001')
        requirement['data']['response'] = 'return a principal marked verified for any credential'
        requirement['revision'] += 1
        refused = successor(self.spec, '1.1.1', reweigh)
        store = store_of(*self.everything(), refused)
        consumer, = release_store.impact(store, self.identity, step)['consumers']
        self.assertEqual((consumer['version'], consumer['score']), ('1.1.0', '23.750'))  # 950 x 25%, not the refused 1000
        unjudged, = release_store.impact(store_of(self.spec, self.identity), self.identity, step)['consumers']
        self.assertEqual(unjudged['version'], '1.1.0')  # nothing passes there: the preferred head stands in


class AnnotationScan(unittest.TestCase):
    def tree(self, files):
        folder = tempfile.TemporaryDirectory(prefix='axiomspec-scan-')
        self.addCleanup(folder.cleanup)
        for name, text in files.items():
            path = Path(folder.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text))
        return Path(folder.name)

    def test_common_spellings_are_read_and_the_token_without_an_id_is_reported(self):
        root = self.tree({'src/a.py': '''\
            # @req: REQ-004
            def f(): pass
            # @req(REQ-005, REQ-006)
            def g(): pass
            # @req REQ-007,REQ-008
            def h(): pass
            # @req
            # @req REQ-0000001
            # @req req-004
            # write to dev@req.example.com or see docs/@req/usage
            # @requires REQ-001
            '''})
        found = graph_index.scan(root)
        self.assertEqual([(a['line'], a['symbol'], a['ids']) for a in found],
                         [(1, 'f', ['REQ-004']), (3, 'g', ['REQ-005', 'REQ-006']), (5, 'h', ['REQ-007', 'REQ-008']),
                          (7, None, []), (8, None, []), (9, None, [])])
        spec = qa.read(LEDGER + '/spec.json')
        problems = graph_index.check(spec, found)
        self.assertEqual([(p['code'], p['line']) for p in problems if p['code'] == 'MALFORMED_ANNOTATION'],
                         [('MALFORMED_ANNOTATION', 7), ('MALFORMED_ANNOTATION', 8), ('MALFORMED_ANNOTATION', 9)])
        gaps = queries.gaps(queries.Snapshot(spec, found), 'implementation')
        self.assertEqual(sum(g['code'] == 'MALFORMED_ANNOTATION' for g in gaps['items']), 3)
        flag, absent = graph_index.check(spec, [dict(path='x.py', line=1, symbol=None, ids=['FLAG-001', 'REQ-999'])])
        self.assertEqual((flag['code'], 'not as a node' in flag['message'], 'does not hold' in absent['message']),
                         ('UNKNOWN_ANNOTATION_ID', True, True))

    def test_a_path_that_does_not_exist_is_an_error_not_an_empty_scan(self):
        root = self.tree({'src/a.py': '# @req REQ-004\n'})
        for function in (graph_index.scan, graph_index.signature, graph_index.source_files):
            with self.assertRaisesRegex(ValueError, 'does not exist: scr'):
                function(root, ['scr'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(graph_index.main(['build', str(ROOT / LEDGER / 'spec.json'), '--repo', str(root), '--include', 'src']), 0)

    def test_a_named_folder_is_always_read_and_output_folders_below_it_are_not(self):
        root = self.tree({'src/build/planner.py': '# @req REQ-004\n', 'src/build/dist/copy.py': '# @req REQ-005\n',
                          'src/node_modules/x.js': '// @req REQ-006\n', 'src/keep.py': '# @req REQ-007\n'})
        self.assertEqual([a['path'] for a in graph_index.scan(root, ['src/build'])], ['src/build/planner.py'])
        self.assertEqual([a['path'] for a in graph_index.scan(root)], ['src/keep.py'])

    def test_the_signature_changes_exactly_when_a_scanned_file_does(self):
        root = self.tree({'src/a.py': '# @req REQ-004\n', 'notes.md': 'x\n'})
        before = graph_index.signature(root)
        (root / 'notes.md').write_text('changed\n')
        self.assertEqual(graph_index.signature(root), before)
        (root / 'src/b.py').write_text('# @req REQ-005\n')
        self.assertNotEqual(graph_index.signature(root), before)


class Queries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read(LEDGER + '/spec.json')
        cls.annotations = graph_index.scan(ROOT, [LEDGER])
        cls.snapshot = queries.Snapshot(cls.spec, cls.annotations, ROOT)

    def test_a_place_in_the_code_is_listed_once(self):
        doubled = 0
        for node in self.spec['nodes']:
            rows = queries.lookup(self.snapshot, node['id'])['traces']
            places = [tuple(row.values()) for row in rows]
            self.assertEqual(len(places), len(set(places)), node['id'])
            doubled += len(self.snapshot.traces.get(node['id'], [])) - len(rows)
        self.assertGreater(doubled, 0)  # the ledger does link one place to a requirement by two routes

    def test_a_bound_file_that_does_not_parse_is_a_gap_not_a_failure(self):
        folder = tempfile.TemporaryDirectory(prefix='axiomspec-gaps-')
        self.addCleanup(folder.cleanup)
        shutil.copytree(ROOT / LEDGER, Path(folder.name) / LEDGER, ignore=shutil.ignore_patterns('__pycache__'))
        code = Path(folder.name) / LEDGER / 'app/ledger.py'
        code.write_text(code.read_text() + '\ndef broken(:\n')
        answer = queries.gaps(queries.Snapshot(self.spec, self.annotations, folder.name), 'implementation')
        unparsed = [g for g in answer['items'] if g['code'] == 'UNRESOLVED_BINDING' and 'cannot be parsed' in g['message']]
        bound = [b['id'] for b in self.spec['bindings'] if b['path'].endswith('app/ledger.py') and b['expected_resolution'] != 'planned']
        self.assertEqual(sorted(g['id'] for g in unparsed), sorted(bound))
        code.write_bytes(b'\xff\xfe not utf-8')
        again = queries.gaps(queries.Snapshot(self.spec, self.annotations, folder.name), 'implementation')
        self.assertEqual(sorted(g['id'] for g in again['items'] if g['code'] == 'UNRESOLVED_BINDING'), sorted(bound))

    def test_a_binding_is_never_resolved_outside_the_repository(self):
        folder = tempfile.TemporaryDirectory(prefix='axiomspec-gaps-')
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / 'outside.py').write_text('def authorize():\n    pass\n')
        (Path(folder.name) / 'repo').mkdir()
        spec = copy.deepcopy(self.spec)
        binding = next(b for b in spec['bindings'] if b['symbol'] == 'authorize')
        binding['path'] = '../outside.py'
        answer = queries.gaps(queries.Snapshot(spec, [], Path(folder.name) / 'repo'), 'implementation')
        self.assertIn(binding['id'], [g['id'] for g in answer['items'] if g['code'] == 'UNRESOLVED_BINDING'])

    def test_a_cursor_does_not_continue_across_a_rescan_of_the_code(self):
        first = queries.context(self.snapshot, ['REQ-004'], 'change')
        self.assertIsNotNone(first['next_cursor'])
        rescanned = queries.Snapshot(self.spec, self.annotations[:-1], ROOT)
        self.assertEqual(rescanned.digest, self.snapshot.digest)
        with self.assertRaises(queries.QueryError) as refused:
            queries.context(rescanned, ['REQ-004'], 'change', cursor=first['next_cursor'])
        self.assertEqual(refused.exception.code, 'INVALID_CURSOR')
        same = queries.Snapshot(self.spec, list(self.annotations), ROOT)
        self.assertTrue(queries.context(same, ['REQ-004'], 'change', cursor=first['next_cursor'])['items'])

    def test_a_candidate_says_whether_it_is_held_and_refuses_a_version_that_is_not_text(self):
        node = copy.deepcopy(next(n for n in self.spec['nodes'] if n['id'] == 'REQ-010'))
        node['title'] += ' (reworded)'
        result = queries.propose(self.spec, '1.1.1', [dict(op='put', section='nodes', item=node)])
        queries.contract_validator('CandidateResult').validate(result)
        self.assertEqual((result['status'], result['held']), ('pass', False))  # the reference function writes nothing
        for version in (5, None, ['1.1.1']):
            with self.assertRaises(queries.QueryError) as refused:
                queries.propose(self.spec, version, [dict(op='retire', id='CON-006')])
            self.assertEqual(refused.exception.code, 'INVALID_PARAMETER')


if __name__ == '__main__':
    unittest.main()
