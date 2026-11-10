"""Regression checks for defects reproduced during the 0.1.1 artifact review.

Run: python3 -m unittest discover -s qa -p 'test_*.py' -v
These are package-checker tests, never application or production-gate tests.
"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from referencing.exceptions import Unresolvable

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_checker', ROOT / 'qa/check_package.py')
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.baseline = qa.read('examples/refund-ledger/spec.json')
        self.observations = qa.read('examples/refund-ledger/observations.json')
        self.vectors = qa.read('fixtures/conformance.json', fixture_values=True)['vectors']
        self.validator = qa.Draft202012Validator(qa.read('schemas/spec.schema.json'))

    def test_reference_corpus_still_exercises_45_expectations(self):
        self.assertEqual(qa.check_observation_corpus(self.baseline, self.observations), (9, 45))
        self.assertEqual(qa.check_vector_corpus(self.baseline, self.vectors, self.validator), (10, 30))

    def test_missing_or_empty_observations_are_rejected(self):
        for cases in [[], self.observations['cases'][:-1]]:
            with self.subTest(count=len(cases)):
                self.observations['cases'] = cases
                with self.assertRaisesRegex(ValueError, 'Observation coverage'):
                    qa.check_observation_corpus(self.baseline, self.observations)

    def test_removing_an_expectation_from_both_copies_is_rejected(self):
        case = self.observations['cases'][0]
        case['expected'].pop('CON-001')
        node = next(n for n in self.baseline['nodes'] if n['id'] == case['scenario_id'])
        node['data']['constraint_expectations'] = [e for e in node['data']['constraint_expectations'] if e['constraint_id'] != 'CON-001']
        with self.assertRaisesRegex(ValueError, 'Missing, extra'):
            qa.check_observation_corpus(self.baseline, self.observations)

    def test_empty_or_missing_vector_is_rejected(self):
        for vectors in [[], self.vectors[1:]]:
            with self.subTest(count=len(vectors)), self.assertRaisesRegex(ValueError, 'corpus coverage'):
                qa.check_vector_corpus(self.baseline, vectors, self.validator)

    def test_wrong_expected_gate_or_verdict_is_rejected(self):
        for key, value in [('expected_gate', 'G13'), ('expected_outcome', 'pass')]:
            candidate = copy.deepcopy(self.vectors)
            candidate[5][key] = value
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'gate/outcome'):
                qa.check_vector_corpus(self.baseline, candidate, self.validator)

    def test_unrelated_reference_error_does_not_satisfy_vector(self):
        # V-006 must detect an unknown target, not merely any invalid reference.
        self.vectors[5]['mutation'] = dict(op='replace', path='/nodes/0/owner', value='ACTOR-999')
        with self.assertRaisesRegex(ValueError, 'expected diagnostic'):
            qa.check_vector_corpus(self.baseline, self.vectors, self.validator)

    def test_bad_pointer_escape_is_rejected_even_if_matching_key_exists(self):
        with self.assertRaisesRegex(ValueError, 'Pointer escape'):
            qa.ReferenceEvaluator().evaluate(dict(kind='path', root='env', pointer='/a~2b'), {'a~2b': True})

    def test_valid_pointer_escapes_resolve(self):
        self.assertIs(qa.ReferenceEvaluator().evaluate(dict(kind='path', root='env', pointer='/a~1b/~0tag'), {'a/b': {'~tag': True}}), True)

    def test_work_budget_is_per_evaluation(self):
        evaluator = qa.ReferenceEvaluator(max_steps=1)
        for _ in range(2):
            self.assertIs(evaluator.evaluate(dict(kind='literal', value=True), {}), True)
            self.assertEqual(evaluator.steps, 1)

    def test_unit_term_reference_is_checked(self):
        self.baseline['environments'][0]['units'][0]['term_id'] = 'TERM-999'
        self.assertIn('UNKNOWN_UNIT_TERM', qa.reference_errors(self.baseline))

    def test_review_protocol_is_not_accepted_as_state_guard(self):
        model = next(n for n in self.baseline['nodes'] if n['kind'] == 'StateModel')
        model['data']['transitions'][0]['guard_id'] = 'CON-006'
        self.assertIn('INCOMPATIBLE_GUARD', qa.reference_errors(self.baseline))

    def test_unknown_mutation_operation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown fixture mutation'):
            qa.mutate(self.baseline, dict(op='invent', path='/project/name', value='x'))

    def test_canonical_bytes_have_fixed_unicode_and_control_escaping(self):
        self.assertEqual(qa.canonical({'z': '\u00e9/\n', 'a': 1}), b'{"a":1,"z":"\xc3\xa9/\\n"}')
        self.assertEqual(qa.canonical({'q': '"\\\x00'}), r'{"q":"\"\\\u0000"}'.encode('utf-8'))
        self.assertNotEqual(qa.canonical([1, 2]), qa.canonical([2, 1]))

    def test_external_schema_references_are_rejected_without_network(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')) as network:
            with self.assertRaises(Unresolvable):
                qa.make_validator({'$ref': 'https://example.invalid/forbidden'}).validate({})
            network.assert_not_called()

    def test_500_row_uniqueness_is_explicitly_unresolved_under_default_budget(self):
        expression = next(n for n in self.baseline['nodes'] if n['id'] == 'CON-004')['data']['expression']
        environment = copy.deepcopy(self.observations['cases'][0]['environment'])
        environment['state']['refunds'] = [dict(id=f'r{i}', key=f'k{i}', amount_minor=1, status='reserved') for i in range(500)]
        with self.assertRaises(qa.BudgetExceeded):
            qa.ReferenceEvaluator().evaluate(expression, environment)

    def test_malformed_input_replaces_previous_green_report(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-regression-') as directory:
            target = Path(directory) / 'package'
            shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns('__pycache__'))
            (target / 'validation/package-report.json').write_text('{"status":"pass"}')
            (target / 'validation/croa-input-review.json').write_text('{"input_status":"complete"}')
            (target / 'examples/refund-ledger/spec.json').write_text('{invalid')
            result = subprocess.run([sys.executable, str(target / 'qa/check_package.py')],
                                    capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads((target / 'validation/package-report.json').read_text())
            self.assertEqual(report['status'], 'error')
            self.assertEqual(json.loads((target / 'validation/croa-input-review.json').read_text())['input_status'], 'error')
            self.assertIn(': error', (target / 'VALIDATION.md').read_text())
            qa.Draft202012Validator(qa.read('schemas/report.schema.json')).validate(report)


if __name__ == '__main__':
    unittest.main()
