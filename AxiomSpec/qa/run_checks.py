#!/usr/bin/env python3
"""Replay package tests, record their local receipt, then run artifact QA."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITION = '0.3.0'
TEST_COMMAND = ['python3', 'qa/run_checks.py', '--tests-only']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    require(path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink(), 'Unsafe output path')
    require(not any(parent.is_symlink() for parent in path.parents
                    if parent != ROOT and parent.is_relative_to(ROOT)), 'Output parent is a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    body = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(body)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def toolchain(root):
    packages = {}
    for line in (root / 'qa/requirements-qa.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            name = line.split('==')[0]
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = 'unavailable'
    return dict(python=platform.python_version(), implementation=platform.python_implementation(),
                system=platform.system(), machine=platform.machine(), dependencies=packages)


def regression_manifest(root):
    result = []
    for folder in ['qa', 'schemas', 'fixtures', 'examples']:
        for path in sorted((root / folder).rglob('*')):
            require(not path.is_symlink(), 'Regression inputs cannot contain symlinks')
            if path.is_file() and '__pycache__' not in path.parts:
                result.append(dict(path=path.relative_to(root).as_posix(), sha256=sha(path)))
    return sorted(result, key=lambda entry: entry['path'])


def validate_receipt(root, receipt):
    require(receipt.get('format') == 'axiomspec-review-regression-run/0.2', 'Replay tests: unsupported regression receipt')
    require(receipt.get('scope') == 'package_checker' and receipt.get('edition') == EDITION,
            'Regression receipt scope/edition mismatch')
    require(receipt.get('status') == 'pass' and type(receipt.get('exit_code')) is int
            and receipt['exit_code'] == 0, 'Regression receipt does not report a successful run')
    require(receipt.get('command') == TEST_COMMAND, 'Regression collection command mismatch')
    require(receipt.get('inputs') == regression_manifest(root), 'Stale or incomplete regression input receipt')
    current_tools = toolchain(root)
    require(all(version != 'unavailable' for version in current_tools['dependencies'].values()),
            'Required QA dependency version metadata is unavailable')
    require(receipt.get('toolchain') == current_tools, 'Regression toolchain mismatch')
    details = receipt.get('tests', {})
    ids = details.get('test_ids', [])
    require(isinstance(ids, list) and ids and all(type(item) is str for item in ids)
            and len(ids) == len(set(ids)), 'Missing or duplicate collected test IDs')
    require(type(details.get('tests_run')) is int and details['tests_run'] == len(ids), 'Collected/executed test count mismatch')
    for field in ['failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes']:
        require(type(details.get(field)) is int and details[field] == 0, f'Regression result has {field}')
    raw = receipt.get('raw_output', {})
    require(raw.get('path') == 'review/regression-output.txt'
            and raw.get('sha256') == sha(root / 'review/regression-output.txt'), 'Regression raw-output digest mismatch')
    return len(ids)


def run_tests():
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'qa'), pattern='test_*.py')
    def collect(group):
        for item in group:
            if isinstance(item, unittest.TestSuite):
                yield from collect(item)
            else:
                yield item.id()
    ids = list(collect(suite))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    details = dict(test_ids=ids, tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), expected_failures=len(result.expectedFailures),
                   unexpected_successes=len(result.unexpectedSuccesses))
    print(json.dumps(details))
    return 0 if result.wasSuccessful() and result.testsRun > 0 and not result.skipped and not result.expectedFailures else 1


def failure_marker(message):
    # Distinct format: a consumer must not reuse the previous successful report.
    outputs = [
        (ROOT / 'validation/package-report.json', dict(format='axiomspec-verification-incomplete/0.1',
              scope='package', status='error', message=message)),
        (ROOT / 'validation/croa-input-review.json', dict(format='axiomspec-croa-input-review/0.2',
              scope='selected_readiness_inputs', input_status='error', assessment_status='not_scored',
              conformance_status='not_assessed', findings=[], limitations=[message])),
        (ROOT / 'VALIDATION.md', '# Package validation: error\n\n' + message + '\n')]
    for path, value in outputs:
        try:
            write(path, value)
        except (OSError, ValueError):
            print(f'Cannot publish current diagnostic at {path.relative_to(ROOT)}; do not reuse an older result.', file=sys.stderr)


def main():
    try:
        failure_marker('Verification is in progress or was interrupted. No current pass is established.')
        for path in ROOT.rglob('*'):
            require(not path.is_symlink(), 'Package symlinks are not allowed')
        before = regression_manifest(ROOT)
        runtime = toolchain(ROOT)
        run = subprocess.run([sys.executable, str(Path(__file__)), '--tests-only'], cwd=ROOT,
              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True)
        raw = run.stderr
        try:
            details = json.loads(run.stdout)
        except (ValueError, TypeError):
            details = {}
            raw += '\nUnparseable test-run result:\n' + run.stdout
        unchanged = before == regression_manifest(ROOT) and runtime == toolchain(ROOT)
        successful = run.returncode == 0 and unchanged
        write(ROOT / 'review/regression-output.txt', raw)
        receipt = dict(format='axiomspec-review-regression-run/0.2', scope='package_checker', edition=EDITION,
            status='pass' if successful else 'fail', exit_code=run.returncode if unchanged else 1,
            command=TEST_COMMAND, evaluated_at=datetime.now(timezone.utc).isoformat(), tests=details,
            inputs=before, toolchain=runtime,
            raw_output=dict(path='review/regression-output.txt', sha256=sha(ROOT / 'review/regression-output.txt')),
            limitations=['Local untrusted producer. Hash consistency does not authenticate this receipt.',
                         'No application tests, execution authority or deployed CROA assessment.'])
        if successful:
            try:
                validate_receipt(ROOT, receipt)
            except (ValueError, TypeError, KeyError, AttributeError):
                successful = False
                receipt.update(status='fail', exit_code=1)
        write(ROOT / 'review/regression-run.json', receipt)
        checked = subprocess.run([sys.executable, 'qa/check_package.py'], cwd=ROOT,
              env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        if checked.returncode:
            print('Package verification failed; inspect current diagnostics.', file=sys.stderr)
        return 0 if successful and checked.returncode == 0 else 1
    except Exception as exc:
        failure_marker(f'{type(exc).__name__}: verification could not complete; inspect local inputs and dependencies.')
        print('Package verification could not complete.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if sys.argv[1:] == ['--tests-only']:
        sys.exit(run_tests())
    if sys.argv[1:]:
        failure_marker('Unsupported verification arguments; no current verification completed.')
        print('Usage: python3 qa/run_checks.py', file=sys.stderr)
        sys.exit(2)
    sys.exit(main())
