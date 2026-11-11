"""Fourth review: rules the contracts state that the reference checks did not enforce.

Each case violates one stated rule on the reference ledger and expects its own diagnostic.
The before-correction results are kept in review/probes-review4-before.json.
"""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('fourth_review_checker', ROOT / 'qa/check_package.py')
qa = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(qa)


class StatedRulesAreChecked(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')

    def node(self, node_id):
        return next(n for n in self.spec['nodes'] if n['id'] == node_id)

    def errors(self):
        return qa.reference_errors(self.spec)

    def test_reference_ledger_has_no_reference_error(self):
        self.assertEqual(self.errors(), [])

    def test_witness_scenario_must_illustrate_a_verified_requirement(self):
        # AX-G-007. TEST-013 verifies REQ-007; SCN-003 illustrates REQ-001 only.
        self.node('TEST-013')['data']['witness_scenario_ids'] = ['SCN-003']
        self.assertEqual(self.errors(), ['SCENARIO_NOT_ILLUSTRATING'])

    def test_must_requirement_needs_an_active_goal(self):
        # AX-G-003. REQ-004 is the only requirement satisfying GOAL-002.
        self.node('GOAL-002')['status'] = 'draft'
        self.assertEqual(self.errors(), ['REQUIREMENT_PROVENANCE'])

    def test_constraint_needs_an_active_requirement(self):
        # AX-G-003. CON-005 formalizes REQ-004 only.
        self.node('REQ-004')['status'] = 'draft'
        self.assertEqual(self.errors(), ['UNLINKED_CONSTRAINT'])

    def test_product_baseline_needs_an_active_goal_and_requirement(self):
        self.spec['project']['mode'] = 'product'
        self.assertEqual(self.errors(), [])
        for node in self.spec['nodes']:
            if node['kind'] == 'Goal':
                node['status'] = 'draft'
        self.assertIn('EMPTY_BASELINE', self.errors())

    def test_requirement_pattern_fixes_its_populated_fields(self):
        # AX-M-006: every pattern accepts exactly one combination of conditions, trigger and feature.
        shapes = {(c, t, f): dict(conditions=['the ledger is open'] if c else [], trigger='a request arrives' if t else None,
                                  feature='auditing is enabled' if f else None)
                  for c in (False, True) for t in (False, True) for f in (False, True)}
        for pattern, expected in qa.PATTERN_FIELDS.items():
            for shape, fields in shapes.items():
                with self.subTest(pattern=pattern, populated=shape):
                    self.spec = qa.read('examples/refund-ledger/spec.json')
                    # REQ-010 keeps its flag in every shape, so only the pattern rule can fire (AX-M-019).
                    self.node('REQ-010')['data'].update(pattern=pattern, **fields)
                    self.assertEqual(self.errors(), [] if shape == expected else ['PATTERN_FIELDS'])

    def test_effective_window_is_utc_and_not_reversed(self):
        # AX-C-013.
        cases = [(None, None, True), ('2026-01-01T00:00:00Z', None, True), (None, '2026-01-01T00:00:00+00:00', True),
                 ('2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z', True),
                 ('2026-02-01T00:00:00Z', '2026-01-01T00:00:00Z', False),   # reversed
                 ('2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', False),   # empty
                 ('2026-01-01T00:00:00+05:00', None, False),                # not UTC
                 ('2026-01-01T00:00:00', None, False)]                      # no offset
        for start, end, valid in cases:
            with self.subTest(start=start, end=end):
                self.node('CON-001')['data'].update(effective_from=start, effective_until=end)
                self.assertEqual(self.errors(), [] if valid else ['INVALID_WINDOW'])

    def test_transition_ids_use_the_trn_prefix(self):
        # AX-M-003.
        self.node('MODEL-001')['data']['transitions'][0]['id'] = 'REQ-001'
        self.assertEqual(self.errors(), ['WRONG_PREFIX'])

    def test_terminal_state_has_no_exit_and_every_state_is_reachable(self):
        # AX-G-005 topology; guards are ignored.
        model = self.node('MODEL-001')['data']
        model['transitions'].append(dict(id='TRN-005', to='reserved', event='undo', guard_id=None, effect_ref=None,
                                         **{'from': 'committed'}))
        self.assertEqual(self.errors(), ['TERMINAL_HAS_EXIT'])
        model['transitions'].pop()
        model['states'].append(dict(name='orphan', terminal=False))
        self.assertEqual(self.errors(), ['UNREACHABLE_STATE'])

    def test_asset_binding_locator_is_declared_and_agrees(self):
        # AX-X-002.
        asset = self.spec['context_assets'][0]
        asset.update(locator='binding:BIND-001', binding_id=None)
        self.assertEqual(self.errors(), [])
        asset.update(binding_id='BIND-001')
        self.assertEqual(self.errors(), [])
        asset.update(binding_id='BIND-002')
        self.assertEqual(self.errors(), ['ASSET_BINDING_MISMATCH'])
        asset.update(locator='binding:BIND-999', binding_id=None)
        self.assertEqual(self.errors(), ['UNKNOWN_ASSET_LOCATOR'])

    def test_unit_annotation_names_one_integer_leaf(self):
        # AX-C-008.
        units = self.spec['environments'][0]['units']
        for pointer, term in [('/state/nope', 'TERM-001'),            # no such path
                              ('/state/tenant_id', 'TERM-001'),       # a string, not an integer
                              ('/state/refunds/amount_minor', 'TERM-001'),  # array level not marked with *
                              ('/state/captured_minor', 'TERM-002')]:  # second, different unit for one path
            with self.subTest(pointer=pointer, term=term):
                units.append(dict(pointer=pointer, term_id=term))
                self.assertEqual(self.errors(), ['UNIT_ANNOTATION'])
                units.pop()
        units.append(copy.deepcopy(units[0]))  # a repeated identical annotation is not a conflict
        self.assertEqual(self.errors(), [])


class CheckerDefects(unittest.TestCase):
    def test_add_creates_a_member_and_never_overwrites(self):
        spec = qa.read('examples/refund-ledger/spec.json')
        self.assertIs(qa.mutate(spec, dict(op='add', path='/project/is_ready', value=True))['project']['is_ready'], True)
        for path in ['/actors/0', '/project/name']:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'new object member'):
                qa.mutate(spec, dict(op='add', path=path, value='x'))

    def test_local_link_must_match_file_name_case(self):
        # A case-insensitive filesystem resolves both spellings; only one works everywhere.
        with tempfile.TemporaryDirectory(prefix='axiomspec-case-') as directory:
            root = Path(directory).resolve()
            (root / 'docs').mkdir()
            (root / 'docs/Guide.md').write_text('Temporary test data')
            for link in ['docs/Guide.md', './docs/Guide.md', 'docs/../docs/Guide.md#part']:
                qa.check_local_link(root / 'README.md', link, root=root)
            for link in ['docs/guide.md', 'Docs/Guide.md']:
                with self.subTest(link=link), self.assertRaisesRegex(ValueError, 'letter case|Broken local link'):
                    qa.check_local_link(root / 'README.md', link, root=root)


if __name__ == '__main__':
    unittest.main()
