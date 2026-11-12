"""Regressions from the sixth review, of edition 0.7.1. Each case failed there.

A second pass over the corrected code found smaller things of the same kind as the first: an ID dropped in
silence, a scan that could not leave a folder out, a worked example with a gap its own query reported.
"""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import approvals  # noqa: E402
import check_package as qa  # noqa: E402
import fictional_keys as fk  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_store  # noqa: E402
import spec_parts  # noqa: E402

LEDGER = 'examples/refund-ledger'


def quiet(function, arguments):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return function(list(arguments))


class Temporary(unittest.TestCase):
    def folder(self, files=None):
        directory = tempfile.TemporaryDirectory(prefix='axiomspec-sixth-')
        self.addCleanup(directory.cleanup)
        for name, text in (files or {}).items():
            path = Path(directory.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return Path(directory.name)


class Scan(Temporary):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read(LEDGER + '/spec.json')
        cls.ledger = graph_index.scan(ROOT, [LEDGER])

    def test_a_repository_that_contains_the_package_leaves_it_out(self):
        whole = graph_index.scan(ROOT)  # this package mentions the token in its own code and tests
        self.assertTrue([p for p in graph_index.check(self.spec, whole) if p['path'].startswith('qa/')])
        self.assertEqual(graph_index.scan(ROOT, exclude=['qa']), self.ledger)
        self.assertEqual(graph_index.check(self.spec, graph_index.scan(ROOT, exclude=['qa'])), [])
        self.assertFalse([path for path, _, _ in graph_index.signature(ROOT, exclude=['qa']) if path.startswith('qa/')])
        spec = str(ROOT / LEDGER / 'spec.json')
        self.assertEqual(quiet(graph_index.main, ['build', spec, '--repo', str(ROOT)]), 2)
        self.assertEqual(quiet(graph_index.main, ['build', spec, '--repo', str(ROOT), '--exclude', 'qa']), 0)

    def test_an_excluded_path_wins_over_whatever_names_it(self):
        root = self.folder({'src/a.py': '# @req REQ-004\n', 'src/vendor/b.py': '# @req REQ-999\n', 'src/c.py': '# @req REQ-005\n'})
        paths = lambda **arguments: [a['path'] for a in graph_index.scan(root, **arguments)]
        self.assertEqual(paths(exclude=['src/vendor']), ['src/a.py', 'src/c.py'])
        self.assertEqual(paths(exclude=['src/c.py']), ['src/a.py', 'src/vendor/b.py'])
        self.assertEqual(paths(include=['src/vendor', 'src/a.py'], exclude=['src/vendor']), ['src/a.py'])
        self.assertEqual(paths(include=['src/c.py'], exclude=['src/c.py']), [])
        self.assertEqual(paths(exclude=['no/such/folder']), ['src/a.py', 'src/c.py', 'src/vendor/b.py'])

    def test_an_id_of_the_release_left_on_the_line_is_reported(self):
        root = self.folder({'a.py': '# @req REQ-004 and CON-005\n# @req REQ-006; REQ-007\n# @req REQ-008 / FLAG-001\n'
                                    '# @req REQ-001 hashed with SHA-256, dated as ISO-8601, see TICKET-1234\n'
                                    '# @req(REQ-002, REQ-003) checked at the boundary\n'
                                    '# @req REQ-009 and here @req REQ-010 then REQ-005\n'})
        found = graph_index.scan(root)
        self.assertEqual([(a['line'], a['ids'], a['rest']) for a in found],
                         [(1, ['REQ-004'], ['CON-005']), (2, ['REQ-006'], ['REQ-007']), (3, ['REQ-008'], ['FLAG-001']),
                          (4, ['REQ-001'], ['SHA-256', 'ISO-8601', 'TICKET-1234']), (5, ['REQ-002', 'REQ-003'], []),
                          (6, ['REQ-009'], []), (6, ['REQ-010'], ['REQ-005'])])
        problems = graph_index.check(self.spec, found)
        self.assertEqual([(p['code'], p['line'], p['subject_id']) for p in problems],
                         [('MALFORMED_ANNOTATION', 1, 'CON-005'), ('MALFORMED_ANNOTATION', 2, 'REQ-007'),
                          ('MALFORMED_ANNOTATION', 3, 'FLAG-001'), ('MALFORMED_ANNOTATION', 6, 'REQ-005')])
        self.assertEqual(graph_index.check(self.spec, self.ledger), [])


class Store(Temporary):
    def test_the_listing_is_what_the_store_reads_and_nothing_else(self):
        root = self.folder({'a.json': '{}', 'deep/er/b.json': '{}', 'notes.txt': 'x', '.hidden/c.json': '{}',
                            '.d.json': '{}', 'deep/.staged/e.json': '{}'})
        os.symlink(root / 'a.json', root / 'link.json')
        os.symlink(root / 'deep', root / 'linked-folder')
        listed = release_store.listing([root, root / 'a.json', root / 'absent.json'])
        self.assertEqual(sorted(path.relative_to(root).as_posix() for path in listed), ['a.json', 'absent.json', 'deep/er/b.json'])
        self.assertEqual((listed[root / 'a.json'][0], listed[root / 'absent.json']), (2, None))
        self.assertEqual(release_store.files([root]), [root / 'a.json', root / 'deep/er/b.json'])
        self.assertEqual(release_store.verify(release_store.load([ROOT / 'examples']))['status'], 'pass')
        with self.assertRaises(OSError):
            release_store.load([root / 'absent.json'])

    def test_a_part_that_is_a_link_is_refused(self):
        spec = qa.read(LEDGER + '/spec.json')
        root = self.folder()
        manifest = spec_parts.write(spec, root / 'parts', budget=60000)
        self.assertEqual(spec_parts.read(manifest), spec)
        part = sorted((root / 'parts').glob('*.part-*.json'))[0]
        part.rename(root / 'parts' / 'moved.json')
        os.symlink(root / 'parts' / 'moved.json', part)  # same bytes, same folder, but a link
        with self.assertRaisesRegex(ValueError, 'regular file'):
            spec_parts.read(manifest)


class Example(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read(LEDGER + '/spec.json')
        cls.nodes = {n['id']: n for n in cls.spec['nodes']}

    def test_every_must_requirement_has_a_witness_and_a_counterexample(self):
        intents = {}
        for edge in self.spec['edges']:
            if edge['relation'] == 'illustrates':
                intents.setdefault(edge['to'], set()).add(self.nodes[edge['from']]['data']['intent'])
        for node in self.spec['nodes']:
            if node['kind'] == 'Requirement' and node['status'] == 'active' and node['data']['priority'] == 'must':
                self.assertEqual(intents.get(node['id']), {'witness', 'counterexample'}, node['id'])

    def test_the_report_predicate_holds_only_for_the_right_amount_and_only_when_enabled(self):
        holds = lambda **observation: qa.ReferenceEvaluator().evaluate(self.nodes['CON-012']['data']['expression'], observation)
        base = dict(flag_enabled=True, captured_minor=1000, consumed_minor=600, reported=True, remaining_minor=400)
        self.assertTrue(holds(**base))
        for change in (dict(remaining_minor=401), dict(remaining_minor=1000), dict(reported=False), dict(flag_enabled=False)):
            self.assertFalse(holds(**dict(base, **change)), change)
        self.assertTrue(holds(**dict(base, flag_enabled=False, reported=False, remaining_minor=0)))
        self.assertTrue(holds(**dict(base, consumed_minor=1000, remaining_minor=0)))
        linked = {(e['from'], e['relation'], e['to']) for e in self.spec['edges']}
        self.assertLessEqual({('CON-012', 'formalizes', 'REQ-010'), ('TEST-019', 'checks', 'CON-012'), ('TEST-020', 'checks', 'CON-012'),
                              ('SCN-035', 'illustrates', 'REQ-004')}, linked)

    def test_the_fictional_signing_command_takes_actor_and_key_pairs(self):
        base = qa.read(LEDGER + '/releases/1.0.0.json')
        with tempfile.TemporaryDirectory() as directory:
            written = Path(directory) / 'approvals.json'
            files = [str(ROOT / LEDGER / 'spec.json'), str(ROOT / LEDGER / 'releases/1.0.0.json'), str(written)]
            self.assertEqual(quiet(fk.main, files + ['ACTOR-001', 'KEY-001', 'ACTOR-003', 'KEY-002']), 0)
            self.assertEqual(approvals.verify(self.spec, json.loads(written.read_text()), base)['status'], 'pass')
            for wrong in (files, files + ['ACTOR-001'], files + ['ACTOR-001', 'KEY-001', 'ACTOR-003']):
                self.assertEqual(quiet(fk.main, wrong), 4)


if __name__ == '__main__':
    unittest.main()
