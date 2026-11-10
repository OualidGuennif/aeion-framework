"""Evidence integrity, scoped CROA inputs and reference-evaluator cross-checks."""
import copy
import importlib.util
import io
from pathlib import Path
import random
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import run_checks
from croa_readiness import assess_inputs

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('third_review_checker', ROOT / 'qa/check_package.py')
qa = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(qa)


class ThirdReview(unittest.TestCase):
    def test_absolute_internal_link_is_not_portable(self):
        with self.assertRaisesRegex(ValueError, 'must be relative'):
            qa.check_local_link(ROOT / 'README.md', str(ROOT / 'README.md'))

    def test_read_rejects_symlink_before_opening_target(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-read-') as directory:
            parent = Path(directory)
            root = parent / 'package'
            root.mkdir()
            (parent / 'outside.json').write_text('{}')
            (root / 'linked.json').symlink_to(parent / 'outside.json')
            with patch.object(qa, 'ROOT', root), patch.object(Path, 'open', side_effect=AssertionError('Opened target')):
                with self.assertRaisesRegex(ValueError, 'escapes|symlinks'):
                    qa.read('linked.json')

    def test_writers_refuse_symlinked_output_parent(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-write-') as directory:
            parent = Path(directory)
            root, outside = parent / 'package', parent / 'outside'
            root.mkdir()
            outside.mkdir()
            (root / 'validation').symlink_to(outside, target_is_directory=True)
            with patch.object(qa, 'ROOT', root), patch.object(run_checks, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'Output path|Output parent'):
                    qa.write_atomic(root / 'validation/result.json', '{}')
                with redirect_stderr(io.StringIO()):
                    run_checks.failure_marker('Synthetic verification failure')
            self.assertEqual(list(outside.iterdir()), [])
            self.assertIn(': error', (root / 'VALIDATION.md').read_text())

    def test_detected_input_change_prevents_publication(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-snapshot-') as directory:
            root = Path(directory)
            (root / 'README.md').write_text('Before')
            with patch.object(qa, 'ROOT', root):
                before = qa.input_manifest()
                (root / 'README.md').write_text('After')
                with self.assertRaisesRegex(ValueError, 'changed during verification'):
                    qa.require_unchanged_inputs(before)

    def test_generated_outputs_do_not_invalidate_input_snapshot(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-generated-') as directory:
            root = Path(directory)
            (root / 'README.md').write_text('Stable input')
            with patch.object(qa, 'ROOT', root):
                before = qa.input_manifest()
                (root / 'validation').mkdir()
                (root / 'validation/report.json').write_text('{}')
                (root / 'VALIDATION.md').write_text('Generated')
                self.assertEqual(qa.require_unchanged_inputs(before), before)

    def test_reference_checks_do_not_depend_on_node_order(self):
        spec = qa.read('examples/refund-ledger/spec.json')
        observations = qa.read('examples/refund-ledger/observations.json')
        rng = random.Random(613)
        for _ in range(5):
            for field in ['nodes', 'edges', 'actors', 'sources', 'bindings']:
                rng.shuffle(spec[field])
            self.assertEqual(qa.reference_errors(spec), [])
            self.assertEqual(qa.check_observation_corpus(spec, observations), (9, 45))

    def test_100_seeded_states_match_direct_domain_oracles(self):
        spec = qa.read('examples/refund-ledger/spec.json')
        expressions = {n['id']: n['data']['expression'] for n in spec['nodes']
                       if n['kind'] == 'Constraint' and n['data']['representation'] == 'bcir'}
        template = qa.read('examples/refund-ledger/observations.json')['cases'][0]['environment']
        validator = qa.make_validator(spec['environments'][0]['schema'])
        rng = random.Random(613)
        outcomes = {cid: set() for cid in expressions}
        for sample in range(100):
            env = copy.deepcopy(template)
            rows = [dict(id=f'r{i}', key=f'k{rng.randrange(i+1)}' if rng.choice([True, False]) else f'k{i}',
                         amount_minor=rng.randrange(31), status=rng.choice(['reserved','committed','released','rejected']))
                    for i in range(rng.randrange(21))]
            env['state']['refunds'] = rows
            env['state']['captured_minor'] = rng.randrange(501)
            env['input']['amount_minor'] = rng.randrange(101)
            env['input']['tenant_id'] = rng.choice(['tenant_a', 'tenant_b'])
            env['state']['tenant_id'] = rng.choice(['tenant_a', 'tenant_b'])
            env['auth'] = dict(verified=rng.choice([True, False]), tenant_id=rng.choice(['tenant_a', 'tenant_b']))
            validator.validate(env)
            used = sum(r['amount_minor'] for r in rows if r['status'] in {'reserved', 'committed'})
            expected = {'CON-001': used <= env['state']['captured_minor'],
                        'CON-002': env['input']['amount_minor'] > 0 and used + env['input']['amount_minor'] <= env['state']['captured_minor'],
                        'CON-003': all(r['amount_minor'] > 0 for r in rows),
                        'CON-004': len({r['key'] for r in rows}) == len(rows),
                        'CON-005': env['auth']['verified'] and env['auth']['tenant_id'] == env['input']['tenant_id'] == env['state']['tenant_id']}
            for cid, expression in expressions.items():
                with self.subTest(sample=sample, constraint=cid):
                    actual = qa.ReferenceEvaluator().evaluate(expression, env)
                    self.assertIs(actual, expected[cid])
                    outcomes[cid].add(actual)
        self.assertTrue(all(values == {True, False} for values in outcomes.values()))


class LocalReceiptChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='axiomspec-receipt-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / 'package'
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns('__pycache__'))
        raw = self.root / 'review/regression-output.txt'
        raw.write_text('Synthetic receipt-verifier fixture; no executed-test claim.\n')
        self.receipt = dict(format='axiomspec-review-regression-run/0.2', scope='package_checker', edition=run_checks.EDITION,
            status='pass', exit_code=0, command=run_checks.TEST_COMMAND, inputs=run_checks.regression_manifest(self.root),
            toolchain=run_checks.toolchain(self.root), tests=dict(test_ids=['synthetic.case'], tests_run=1,
            failures=0, errors=0, skipped=0, expected_failures=0, unexpected_successes=0),
            raw_output=dict(path='review/regression-output.txt', sha256=run_checks.sha(raw)))

    def test_consistent_receipt_metadata_is_locally_checkable(self):
        self.assertEqual(run_checks.validate_receipt(self.root, self.receipt), 1)

    def test_changed_source_and_toolchain_reject_old_receipt(self):
        wrong_tools = copy.deepcopy(self.receipt)
        wrong_tools['toolchain']['python'] = 'different'
        with self.assertRaisesRegex(ValueError, 'toolchain mismatch'):
            run_checks.validate_receipt(self.root, wrong_tools)
        source = self.root / 'qa/check_package.py'
        source.write_text(source.read_text() + '\n# New input\n')
        with self.assertRaisesRegex(ValueError, 'Stale or incomplete'):
            run_checks.validate_receipt(self.root, self.receipt)

    def test_missing_input_or_changed_raw_output_rejects_receipt(self):
        missing = copy.deepcopy(self.receipt)
        missing['inputs'].pop()
        with self.assertRaisesRegex(ValueError, 'Stale or incomplete'):
            run_checks.validate_receipt(self.root, missing)
        (self.root / 'review/regression-output.txt').write_text('Changed')
        with self.assertRaisesRegex(ValueError, 'raw-output digest'):
            run_checks.validate_receipt(self.root, self.receipt)

    def test_zero_duplicate_or_skipped_tests_do_not_pass_receipt(self):
        for changes in [dict(test_ids=[], tests_run=0), dict(test_ids=['same','same'], tests_run=2), dict(skipped=1)]:
            receipt = copy.deepcopy(self.receipt)
            receipt['tests'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                run_checks.validate_receipt(self.root, receipt)

    def test_interrupted_test_process_cannot_leave_an_old_pass(self):
        with patch.object(run_checks, 'ROOT', self.root), patch.object(run_checks.subprocess, 'run', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                run_checks.main()
        import json
        current = json.loads((self.root / 'validation/package-report.json').read_text())
        self.assertEqual(current['status'], 'error')
        self.assertEqual(current['format'], 'axiomspec-verification-incomplete/0.1')
        self.assertIn('interrupted', (self.root / 'VALIDATION.md').read_text())


class CroaEvidenceChecks(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')
        self.record = qa.read('examples/refund-ledger/croa-readiness.json')

    def assess(self):
        self.record['spec_sha256'] = qa.digest(qa.canonical(self.spec))
        return assess_inputs(self.spec, self.record, self.record['spec_sha256'])

    def test_retired_mapping_is_rejected_on_current_snapshot(self):
        next(n for n in self.spec['nodes'] if n['id'] == 'CON-001')['status'] = 'retired'
        with self.assertRaisesRegex(ValueError, 'Retired CROA'):
            self.assess()

    def test_unrelated_method_binding_is_rejected(self):
        self.record['invariant_metadata'][0]['method_binding_id'] = 'BIND-001'
        with self.assertRaisesRegex(ValueError, 'same constraint'):
            self.assess()

    def test_unsupported_operational_score_does_not_clear_finding(self):
        self.record['assessment_kind'] = 'evidence_record'
        self.record['answers']['B2']['score'] = 0
        result = self.assess()
        self.assertEqual(result['declared_scores']['B2'], 0)
        self.assertIsNone(result['effective_scores']['B2'])
        self.assertEqual(next(r for r in result['findings'] if r['id'] == 'CRF-001')['state'], 'unknown')

    def test_captured_reviewed_source_reference_is_still_only_declared(self):
        self.spec['sources'].append(dict(id='SRC-002', type='document', locator='fixture:synthetic-receipt-test',
                                         capture_sha256='0'*64, review_state='reviewed'))
        self.record['assessment_kind'] = 'evidence_record'
        self.record['answers']['B2'].update(score=0, source_ids=['SRC-002'])
        result = self.assess()
        self.assertEqual(result['source_verification'], 'declared_only')
        self.assertEqual(next(r for r in result['findings'] if r['id'] == 'CRF-001')['state'], 'not_triggered')
        self.assertEqual(result['conformance_status'], 'not_assessed')


if __name__ == '__main__':
    unittest.main()
