"""Second review: checker boundaries and optional declarations."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('second_review_checker', ROOT / 'qa/check_package.py')
qa = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(qa)
from croa_readiness import ITEMS, assess_inputs, findings


class SecondReview(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')
        self.vectors = qa.read('fixtures/conformance.json', fixture_values=True)['vectors']
        self.validator = qa.make_validator(qa.read('schemas/spec.schema.json'))

    def test_deep_valid_chain_and_deep_cycle_do_not_use_recursion(self):
        prototype = next(n for n in self.spec['nodes'] if n['kind'] == 'Requirement')
        edge_id = max(int(e['id'].split('-')[1]) for e in self.spec['edges']) + 1
        for i in range(1200):
            node = copy.deepcopy(prototype)
            node['id'] = f'REQ-{10000+i}'
            self.spec['nodes'].append(node)
            self.spec['edges'].append(dict(id=f'EDGE-{edge_id}', origin='declared', rationale='Review dependency chain',
                relation='satisfies', **{'from': node['id'], 'to': 'GOAL-001'}))
            edge_id += 1
            if i:
                self.spec['edges'].append(dict(id=f'EDGE-{edge_id}', origin='declared', rationale='Review dependency chain',
                    relation='depends_on', **{'from': f'REQ-{9999+i}', 'to': node['id']}))
                edge_id += 1
        self.assertLessEqual(len(qa.canonical(self.spec)), qa.BOUNDS['max_input_bytes'])
        self.assertTrue(self.validator.is_valid(self.spec))
        self.assertEqual(qa.reference_errors(self.spec), [])
        self.spec['edges'].append(dict(id=f'EDGE-{edge_id}', origin='declared', rationale='Cycle fixture',
            relation='depends_on', **{'from': 'REQ-11199', 'to': 'REQ-10000'}))
        self.assertIn('DEPENDENCY_CYCLE', qa.reference_errors(self.spec))

    def test_replace_and_remove_require_existing_target(self):
        for op in ['replace', 'remove']:
            with self.subTest(op=op), self.assertRaisesRegex(ValueError, 'does not exist'):
                qa.mutate(self.spec, dict(op=op, path='/project/nonexistent', value=True))

    def test_noncanonical_array_indexes_are_rejected(self):
        for index in ['-1', '01', '+1']:
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'array index'):
                qa.mutate(self.spec, dict(op='replace', path=f'/nodes/{index}/revision', value=2))

    def test_invalid_future_metadata_is_rejected_without_execution(self):
        self.vectors[10]['expected_outcome'] = 'invented-verdict'
        with self.assertRaisesRegex(ValueError, 'expected gate or outcome'):
            qa.check_vector_corpus(self.spec, self.vectors, self.validator)

    def test_external_local_link_is_not_a_portable_package_link(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-links-') as directory:
            parent = Path(directory)
            root = parent / 'package'
            root.mkdir()
            outside = parent / 'outside.txt'
            outside.write_text('Temporary test data')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                qa.check_local_link(root / 'README.md', '../outside.txt', root=root)

    def test_symlink_is_rejected_before_packaging(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-symlink-') as directory:
            parent = Path(directory)
            root = parent / 'package'
            root.mkdir()
            outside = parent / 'outside.txt'
            outside.write_text('Temporary test data')
            (root / 'linked.txt').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                qa.package_files(root)

    def test_execution_mode_does_not_accept_an_authority_boolean(self):
        execution = qa.read('examples/refund-ledger/execution.json')
        validator = qa.make_validator(qa.read('schemas/execution.schema.json'))
        self.assertTrue(validator.is_valid(execution))
        self.assertIsNone(execution['decision_policy_ref']['sha256'])
        execution['autonomous'] = True
        self.assertFalse(validator.is_valid(execution))


class CroaReadiness(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')
        self.record = qa.read('examples/refund-ledger/croa-readiness.json')
        self.digest = qa.digest(qa.canonical(self.spec))

    def test_unknown_answers_do_not_become_scores_or_conformance(self):
        result = assess_inputs(self.spec, self.record, self.digest)
        self.assertEqual(len(result['missing_scores']), 37)
        self.assertEqual(len(result['findings']), 13)
        self.assertTrue(all(row['state'] == 'unknown' for row in result['findings']))
        self.assertEqual(result['conformance_status'], 'not_assessed')
        self.assertIsNone(result['maturity_baseline'])
        self.assertIsNone(result['need_score'])

    def test_red_flag_thresholds_match_guide(self):
        cases = [
            ('CRF-001', {'B2':3,'B3':3}, {'B2':2,'B3':3}),
            ('CRF-002', {'R1':3,'B1':3,'B2':0}, {'R1':2,'B1':3,'B2':3}),
            ('CRF-003', {'A3':3,'B3':2}, {'A3':3,'B3':1}),
            ('CRF-004', {'B4':3}, {'B4':2}),
            ('CRF-005', {'A2':3,'B6':3}, {'A2':3,'B6':2}),
            ('CRF-006', {'A4':3,'B1':3}, {'A4':2,'B1':3}),
            ('CRF-007', {'D4':1}, {'D4':2}),
            ('CRF-008', {'E3':1,'E4':2}, {'E3':2,'E4':2}),
            ('CRF-009', {'D3':1}, {'D3':2}),
            ('CRF-010', {'D5':1,'A7':2}, {'D5':1,'A7':1}),
            ('CRF-011', {'D6':1}, {'D6':2}),
            ('CRF-012', {'B5':3}, {'B5':2}),
            ('CRF-013', {'A6':3,'B1':3}, {'A6':3,'B1':2}),
        ]
        for rid, positive, negative in cases:
            for values, expected in [(positive,'triggered'), (negative,'not_triggered')]:
                scores = dict.fromkeys(ITEMS)
                scores.update(values)
                with self.subTest(finding=rid, expected=expected):
                    row = next(r for r in findings(scores) if r['id'] == rid)
                    self.assertEqual(row['state'], expected)

    def test_three_valued_logic_for_missing_inputs(self):
        scores = dict.fromkeys(ITEMS)
        scores.update(B2=2, E3=1)
        rows = {r['id']:r['state'] for r in findings(scores)}
        self.assertEqual(rows['CRF-001'], 'not_triggered')  # false AND unknown
        self.assertEqual(rows['CRF-008'], 'triggered')      # true OR unknown
        self.assertEqual(rows['CRF-002'], 'unknown')

    def test_scores_are_strict_integers(self):
        for invalid in [True, 4.0, -1, 5]:
            scores = dict.fromkeys(ITEMS)
            scores['A1'] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                findings(scores)

    def test_stale_model_digest_is_rejected(self):
        self.record['spec_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Stale CROA'):
            assess_inputs(self.spec, self.record, self.digest)

    def test_unknown_mapped_node_is_rejected(self):
        self.record['traceability'][0]['node_ids'] = ['CON-999']
        with self.assertRaisesRegex(ValueError, 'Unknown CROA mapped node'):
            assess_inputs(self.spec, self.record, self.digest)

    def test_missing_item_or_changed_baseline_fails_schema(self):
        validator = qa.make_validator(qa.read('schemas/croa-readiness.schema.json'))
        self.assertTrue(validator.is_valid(self.record))
        del self.record['answers']['D4']
        self.assertFalse(validator.is_valid(self.record))
        self.record = qa.read('examples/refund-ledger/croa-readiness.json')
        self.record['framework']['sha256'] = '0' * 64
        self.assertFalse(validator.is_valid(self.record))

    def test_fictional_source_cannot_substantiate_operational_answer(self):
        self.record['assessment_kind'] = 'evidence_record'
        self.record['answers']['D4'].update(score=4, source_ids=['SRC-001'])
        with self.assertRaisesRegex(ValueError, 'fixture cannot substantiate'):
            assess_inputs(self.spec, self.record, self.digest)


if __name__ == '__main__':
    unittest.main()
