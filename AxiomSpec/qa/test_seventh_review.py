"""Regressions from the seventh review, of edition 0.7.2. Each case failed there.

A third pass found one defect of the store's central promise, that the verdict is a function of the set of
files alone, and an unbounded query. The service's own regressions are in server/tests/test_service.py.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import check_package as qa  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_store  # noqa: E402

LEDGER = 'examples/refund-ledger'


class Store(unittest.TestCase):
    def test_approvals_under_another_version_neither_block_nor_depend_on_order(self):
        directory = tempfile.TemporaryDirectory(prefix='axiomspec-seventh-')
        self.addCleanup(directory.cleanup)
        bogus = copy.deepcopy(qa.read(LEDGER + '/approvals.json'))
        bogus['version'] = '9.9.9'  # the digest of 1.1.0 under a version that release is not
        path = Path(directory.name) / 'bogus.approvals.json'
        path.write_text(json.dumps(bogus))
        files = release_store.files([ROOT / 'examples'])
        verdicts = []
        for order in ([path, *files], [*files, path]):
            store = release_store.Store()
            for file in order:
                release_store.add_file(store, file)
            report = release_store.verify(store)
            verdicts.append(report)
            ledger = next(r for r in report['releases'] if r['version'] == '1.1.0' and r['project_id'] == 'PROJECT-001')
            self.assertEqual((ledger['status'], ledger['approvals']), ('pass', 'pass'))
            self.assertEqual([Path(r['path']).name for r in report['rejected_files']], ['bogus.approvals.json'])
            self.assertEqual(report['status'], 'incomplete')  # reported, never counted
        self.assertEqual(verdicts[0], verdicts[1])
        self.assertEqual(release_store.verify(release_store.load([ROOT / 'examples']))['status'], 'pass')


class Context(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = queries.Snapshot(qa.read(LEDGER + '/spec.json'), graph_index.scan(ROOT, ['examples/refund-ledger']), ROOT)

    def test_a_context_names_at_most_one_hundred_ids(self):
        with self.assertRaises(queries.QueryError) as raised:
            queries.context(self.snapshot, [f'REQ-{n:03d}' for n in range(101)])
        self.assertEqual(raised.exception.code, 'INVALID_PARAMETER')
        self.assertEqual(queries.context(self.snapshot, ['REQ-004'] * 100)['items'][0]['id'], 'REQ-004')

    def test_a_long_list_of_unknown_ids_gives_a_short_message(self):
        with self.assertRaises(queries.QueryError) as raised:
            queries.context(self.snapshot, [f'REQ-{n:03d}' for n in range(500, 600)])
        self.assertEqual(raised.exception.code, 'NOT_FOUND')
        self.assertIn('and 90 more', str(raised.exception))
        self.assertLess(len(str(raised.exception)), 200)


if __name__ == '__main__':
    unittest.main()
