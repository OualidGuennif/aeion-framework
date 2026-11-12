"""The standalone checker and Markdown generator on user-supplied files."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'qa')]
import axiom  # noqa: E402
import check_package as qa  # noqa: E402
import run_checks  # noqa: E402
import spec_parts  # noqa: E402
import release_diff  # noqa: E402
import release_store  # noqa: E402


class SpecTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = qa.read('examples/refund-ledger/spec.json')

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='axiomspec-cli-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / 'spec.json'
        self.path.write_bytes(qa.canonical(self.spec))

    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, str(ROOT / 'axiom.py'), *map(str, arguments)],
                              cwd=self.root, capture_output=True, text=True)

    def test_check_is_read_only_and_works_from_another_directory(self):
        before = self.path.read_bytes()
        result = self.run_cli('check', self.path, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual((report['status'], report['spec_sha256']), ('pass', qa.digest(before)))
        self.assertEqual(report['scope'], 'structure_and_references')
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.path])
        self.assertIn('Does not establish product readiness', ' '.join(report['limitations']))

    def test_invalid_json_has_a_machine_readable_error(self):
        for raw in (b'{"format":1,"format":2}', b'{"number":1.5}', b'{"x":"\\ud800"}'):
            self.path.write_bytes(raw)
            result = self.run_cli('check', self.path, '--json')
            self.assertEqual(result.returncode, 4)
            self.assertEqual(json.loads(result.stdout)['status'], 'error')
            self.assertNotIn('Traceback', result.stderr)

    def test_schema_and_reference_errors_are_distinct(self):
        spec = copy.deepcopy(self.spec)
        del spec['project']['owner']
        report = axiom.check(spec)
        self.assertEqual(report['status'], 'fail')
        self.assertTrue(report['schema_errors'])
        self.assertEqual(report['reference_errors'], [])
        spec = copy.deepcopy(self.spec)
        spec['edges'][0]['to'] = 'REQ-999999'
        self.path.write_bytes(qa.canonical(spec))
        result = self.run_cli('check', self.path, '--json')
        report = json.loads(result.stdout)
        self.assertEqual((result.returncode, report['schema_errors']), (2, []))
        self.assertIn('UNKNOWN_TARGET', report['reference_errors'])

    def test_unsupported_environment_shapes_are_reported(self):
        spec = copy.deepcopy(self.spec)
        spec['environments'][0]['schema']['$ref'] = 'https://example.invalid/schema'
        report = axiom.check(spec)
        self.assertEqual(report['status'], 'fail')
        self.assertTrue(any('Unsupported environment keyword' in e['message'] for e in report['schema_errors']))

    def test_malformed_environment_keyword_shapes_are_controlled_failures(self):
        for schema in (dict(type='object', properties=[], additionalProperties=False),
                       dict(type='array', maxItems=2),
                       dict(type='object', properties={'x': True}, required=['x'], additionalProperties=False)):
            with self.subTest(schema=schema):
                spec = copy.deepcopy(self.spec)
                spec['environments'][0]['schema'] = schema
                self.assertEqual(axiom.check(spec)['status'], 'fail')
                self.assertIn('INVALID_ENVIRONMENT_SCHEMA', qa.reference_errors(spec))

    def test_dense_invalid_input_keeps_the_exact_count_and_only_fifty_sorted_diagnostics(self):
        report = axiom.check(dict(self.spec, nodes=[0] * 2000))
        self.assertEqual((report['status'], report['schema_error_count'], len(report['schema_errors'])), ('fail', 2000, 50))
        self.assertEqual([e['pointer'] for e in report['schema_errors']],
                         sorted(f'/nodes/{i}' for i in range(2000))[:50])

    def test_parts_are_checked_and_rendered_like_the_single_file(self):
        manifest = spec_parts.write(self.spec, self.root / 'parts', budget=30000)
        self.assertEqual(axiom.load_spec(manifest), self.spec)
        result = self.run_cli('check', manifest, '--json')
        self.assertEqual((result.returncode, json.loads(result.stdout)['spec_sha256']),
                         (0, qa.digest(qa.canonical(self.spec))))
        self.assertEqual(self.run_cli('markdown', manifest).stdout, self.run_cli('markdown', self.path).stdout)

    def test_malformed_parts_keep_machine_readable_errors(self):
        part = self.root / 'part.json'
        manifest = self.root / 'manifest.json'
        for payload in (0, [], dict(format=spec_parts.PART, fields=[], items={}),
                        dict(format=spec_parts.PART, fields={}, items=[])):
            with self.subTest(part=payload):
                part.write_bytes(qa.canonical(payload))
                manifest.write_text(json.dumps(dict(format=spec_parts.MANIFEST, spec_sha256='0' * 64,
                    parts=[dict(path=part.name, sha256=qa.digest(part.read_bytes()))])))
                result = self.run_cli('check', manifest, '--json')
                self.assertEqual(result.returncode, 4)
                self.assertEqual(json.loads(result.stdout)['status'], 'error')
                self.assertNotIn('Traceback', result.stderr)
        for entry in (None, {}, dict(path=0, sha256='0' * 64)):
            with self.subTest(entry=entry):
                manifest.write_text(json.dumps(dict(format=spec_parts.MANIFEST, spec_sha256='0' * 64, parts=[entry])))
                result = self.run_cli('check', manifest, '--json')
                self.assertEqual(result.returncode, 4)
                self.assertEqual(json.loads(result.stdout)['status'], 'error')

    def test_markdown_covers_the_model_and_uses_resolving_internal_links(self):
        result = self.run_cli('markdown', self.path)
        self.assertEqual(result.returncode, 0, result.stderr)
        for node in self.spec['nodes']:
            self.assertIn(f"### {node['id']}\n", result.stdout)
        for section in ('Bindings', 'Imports', 'Environments', 'Relationships', 'Open decisions'):
            self.assertIn('## ' + section, result.stdout)
        anchors = set(re.findall(r'^### ([A-Z][A-Z0-9_]*-[0-9]+)$', result.stdout, re.M))
        for target in re.findall(r'\]\(#([a-z0-9_-]+)\)', result.stdout):
            self.assertIn(target.upper(), anchors)
        self.assertIn('No signature verification was run', result.stdout)
        self.assertIn(qa.digest(qa.canonical(self.spec)), result.stdout)

    def test_generation_is_deterministic_under_record_reordering(self):
        spec = copy.deepcopy(self.spec)
        for section in ('nodes', 'edges', 'bindings', 'sources'):
            spec[section].reverse()
        first = axiom.markdown(self.spec, axiom.check(self.spec))
        report = axiom.check(spec)
        second = axiom.markdown(spec, report)
        # Reordering changes canonical identity; the reading order itself stays fixed.
        self.assertEqual(second.replace(report['spec_sha256'], qa.digest(qa.canonical(self.spec))), first)

    def test_source_text_cannot_inject_links_html_or_a_fence_end(self):
        spec = copy.deepcopy(self.spec)
        req = next(n for n in spec['nodes'] if n['kind'] == 'Requirement')
        req['data']['response'] = '<script>alert(1)</script> ![image](https://example.invalid)'
        decision = next(n for n in spec['nodes'] if n['kind'] == 'Decision')
        decision['data']['options'].append('```\n<script>bad</script>\n```')
        body = axiom.markdown(spec, axiom.check(spec))
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('![image](', body)
        self.assertIn('````json', body)

    def test_output_never_overwrites_the_spec_or_an_existing_file(self):
        before = self.path.read_bytes()
        self.assertEqual(self.run_cli('markdown', self.path, '--output', self.path).returncode, 4)
        self.assertEqual(self.path.read_bytes(), before)
        output = self.root / 'spec.md'
        result = self.run_cli('markdown', self.path, '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), self.run_cli('markdown', self.path).stdout)
        self.assertEqual(self.run_cli('markdown', self.path, '--output', output).returncode, 4)

    def test_invalid_input_does_not_create_a_markdown_file(self):
        self.path.write_text('{}')
        output = self.root / 'spec.md'
        result = self.run_cli('markdown', self.path, '--output', output)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_compare_reuses_g14_and_accepts_parts_from_another_directory(self):
        baseline = ROOT / 'examples/refund-ledger/releases/1.0.0.json'
        expected = release_diff.compare(qa.strict_json(baseline.read_bytes()), self.spec)
        for candidate in (self.path, spec_parts.write(self.spec, self.root / 'parts', budget=30000)):
            result = self.run_cli('compare', baseline, candidate)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)
        before = self.path.read_bytes()
        output = self.root / 'comparison.md'
        result = self.run_cli('compare', baseline, self.path, '--format', 'markdown', '--output', output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual(output.read_text(), axiom.comparison_markdown(expected))
        self.assertIn('## Changes', output.read_text())
        self.assertIn(expected['risk']['score'], output.read_text())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.run_cli('compare', baseline, self.path, '--output', self.path).returncode, 4)
        self.assertEqual(self.path.read_bytes(), before)

    def test_compare_failed_checks_and_invalid_inputs_do_not_create_reports(self):
        baseline = ROOT / 'examples/refund-ledger/releases/1.0.0.json'
        failed = copy.deepcopy(self.spec)
        failed['release']['previous']['spec_sha256'] = 'f' * 64
        self.path.write_bytes(qa.canonical(failed))
        result = self.run_cli('compare', baseline, self.path)
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (2, 'fail'))
        self.assertIn('BASELINE_MISMATCH', [e['code'] for e in json.loads(result.stdout)['errors']])
        self.path.write_text('{}')
        output = self.root / 'invalid.md'
        result = self.run_cli('compare', baseline, self.path, '--format', 'markdown', '--output', output)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stderr)['status'], 'fail')
        self.assertFalse(output.exists())
        result = self.run_cli('compare', baseline, self.root / 'missing.json')
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (4, 'error'))
        self.assertNotIn('Traceback', result.stderr)

    def test_comparison_markdown_escapes_diagnostic_text(self):
        baseline = qa.read('examples/refund-ledger/releases/1.0.0.json')
        report = release_diff.compare(baseline, self.spec)
        report['errors'].append(dict(code='REVIEW', subject_id=None,
                                    message='<script>bad</script> ![image](https://example.invalid) | cell'))
        body = axiom.comparison_markdown(report)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('![image](', body)
        self.assertIn('\\| cell', body)

    def test_verify_store_reuses_the_reference_report_and_writes_nothing(self):
        store = ROOT / 'examples'
        expected = release_store.verify(release_store.load([store]))
        before = self.path.read_bytes()
        result = self.run_cli('verify-store', store, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), expected)
        result = self.run_cli('verify-store', store)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('AxiomSpec store: pass (3 releases, 2 projects)', result.stdout)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_verify_store_distinguishes_failed_incomplete_and_unreadable_inputs(self):
        result = self.run_cli('verify-store', self.path, '--json')
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (3, 'incomplete'))
        result = self.run_cli('verify-store', self.path)
        self.assertEqual(result.returncode, 3)
        self.assertIn('missing: baseline release, approvals, PROJECT-002 1.0.0 (IMP-001)', result.stdout)
        result = self.run_cli('verify-store', ROOT / 'examples/refund-ledger/releases/1.0.0.json', '--json')
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (2, 'fail'))
        result = self.run_cli('verify-store', self.root / 'missing', '--json')
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (4, 'error'))
        self.assertNotIn('Traceback', result.stderr)

    def test_the_cli_is_covered_by_the_regression_input_receipt(self):
        self.assertIn('axiom.py', [row['path'] for row in run_checks.regression_manifest(ROOT)])


if __name__ == '__main__':
    unittest.main()
