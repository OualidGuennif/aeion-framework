#!/usr/bin/env python3
"""Check, read and compare AxiomSpec files, or verify a release store. Never executes product code."""
import argparse
import html
from heapq import nsmallest
import json
from pathlib import Path
import re
import sys

from jsonschema.exceptions import SchemaError

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'qa'))

from check_package import BOUNDS, canonical, check_environment, digest, make_validator, reference_errors, strict_json  # noqa: E402
from queries import KIND_ORDER, statement  # noqa: E402
from run_checks import EDITION, MIN_PYTHON  # noqa: E402
import spec_parts  # noqa: E402
import release_diff  # noqa: E402
import release_store  # noqa: E402

LIMITS = ['Checks strict JSON, the specification schema and selected reference rules only.',
          'Does not establish product readiness, evaluate BCIR, verify approvals or execute tests.']


def load_spec(path):
    with Path(path).open('rb') as source:
        spec = strict_json(source.read(BOUNDS['max_input_bytes'] + 1))
    if isinstance(spec, dict) and spec.get('format') == spec_parts.MANIFEST:
        return spec_parts.read(path)
    return spec


def check(spec):
    """A deterministic report for one parsed file. No clock, network, repository scan or writes."""
    validator = make_validator(json.loads((ROOT / 'schemas/spec.schema.json').read_text()), check_formats=True)
    error_count = 0

    def diagnostics():
        nonlocal error_count
        for error in validator.iter_errors(spec):
            error_count += 1
            yield dict(pointer='/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in error.absolute_path),
                       message=error.message[:400])
        if error_count:
            return
        # AX-C-002 restricts these shapes beyond the outer specification schema.
        for number, environment in enumerate(spec['environments']):
            try:
                check_environment(environment['schema'])
            except (ValueError, KeyError, TypeError, SchemaError) as exc:
                error_count += 1
                yield dict(pointer=f'/environments/{number}/schema', message=str(exc)[:400])

    # Keep the same first 50 sorted diagnostics and exact count without retaining every error.
    errors = nsmallest(50, diagnostics(), key=lambda error: (error['pointer'], error['message']))
    references = reference_errors(spec) if not error_count else []
    return dict(format='axiomspec-check/0.1', scope='structure_and_references', edition=EDITION,
                status='fail' if errors or references else 'pass', spec_sha256=digest(canonical(spec)),
                schema_errors=errors, schema_error_count=error_count, reference_errors=references,
                limitations=LIMITS)


def prose(value):
    """Literal source text, without active HTML, images, links or Markdown formatting."""
    text = html.escape(' '.join(str(value).split()), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#!|])', r'\\\1', text)


def json_block(value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    fence = '`' * max(3, 1 + max((len(run) for run in re.findall(r'`+', body)), default=0))
    return [fence + 'json', body, fence, '']


def markdown(spec, report):
    """The whole declared model, sorted by kind and ID. Generated text is a view, not another authority."""
    if report['status'] != 'pass' or report['spec_sha256'] != digest(canonical(spec)):
        raise ValueError('Markdown generation requires a passing check of this specification')
    lines = [f"# {prose(spec['project']['name'])}", '', prose(spec['project']['description']), '',
             f"Release: {spec['release']['version']} · Format: {spec['format']} · Profile: {spec['profile']}", '',
             f"Specification SHA-256: `{report['spec_sha256']}`", '',
             f"Weight minor units per point: {spec['project']['weight_minor_units']}", '',
             'Generated from the specification. Regenerate this file after editing the source.', '',
             'Structure and selected reference checks: pass. Approvals, executed tests, BCIR semantics and '
             'product readiness are not assessed by this export.', '', '## Open decisions', '']
    pending = sorted((n for n in spec['nodes'] if n['kind'] == 'Decision' and n['status'] != 'retired'
                      and n['data']['answer'] is None), key=lambda n: n['id'])
    lines += [f"- [{n['id']}](#{n['id'].lower()}): {prose(n['data']['question'])}"
              + (' (blocking)' if n['data']['blocking'] else '') for n in pending] or ['None declared.']
    lines.append('')

    def fields(data):
        for name, value in sorted(data.items()):
            label = prose(name.replace('_', ' ').capitalize())
            if isinstance(value, (dict, list)) and value:
                lines.extend([f'**{label}:**', '', *json_block(value)])
            else:
                rendered = 'Not set' if value is None else json.dumps(value) if isinstance(value, (bool, list, dict)) else prose(value)
                lines.extend([f'**{label}:** {rendered}', ''])

    for kind in KIND_ORDER:
        nodes = sorted((n for n in spec['nodes'] if n['kind'] == kind), key=lambda n: n['id'])
        if not nodes:
            continue
        lines.extend([f'## {kind}', ''])
        for node in nodes:
            lines.extend([f"### {node['id']}", '', f"**{prose(node['title'])}**", '',
                          f"Status: {node['status']} · Revision: {node['revision']} · Owner: {node['owner']} · Created by: {node['created_by']}", '',
                          'Sources: ' + (', '.join(node['source_ids']) or 'None declared.'), ''])
            if kind == 'Requirement':
                lines.extend([prose(statement(node)), ''])
                fields({name: node['data'][name] for name in ('category', 'priority', 'risk', 'verification_mode',
                                                             'weight_minor', 'flag_id')})
            else:
                fields(node['data'])

    lines.extend(['## Relationships', '', '| From | Relation | To |', '|---|---|---|'])
    for edge in sorted(spec['edges'], key=lambda e: (e['from'], e['relation'], e['to'], e['id'])):
        lines.append(f"| [{edge['from']}](#{edge['from'].lower()}) | {edge['relation']} | [{edge['to']}](#{edge['to'].lower()}) |")
    lines.extend(['', '## Release and approval declarations', '',
                  'The following policy and keys are declarations. No signature verification was run.', '',
                  *json_block(dict(project=spec['project'], release=spec['release'], approval=spec['approval'],
                                   exports=sorted(spec['exports'])))])
    for section in ('actors', 'sources', 'environments', 'flags', 'imports', 'bindings', 'context_assets'):
        lines.extend([f"## {section.replace('_', ' ').capitalize()}", ''])
        if not spec[section]:
            lines.extend(['None declared.', ''])
        for item in sorted(spec[section], key=lambda row: row['id']):
            lines.extend([f"### {item['id']}", '', *json_block(item)])
    return '\n'.join(lines)


def comparison_markdown(report):
    """A reading view of the existing G14 report; it adds no classification or approval decision."""
    risk = report['risk']
    lines = ['# AxiomSpec release comparison', '',
             f"Status: {report['status']} · Declared step: {report['declared_step']} · Required step: {report['required_step']}", '',
             f"Baseline: {report['baseline']['version']} · `{report['baseline']['spec_sha256']}`", '',
             f"Candidate: {report['candidate']['version']} · `{report['candidate']['spec_sha256']}`", '',
             f"Change risk score: {risk['score']} points · Exposure: {risk['exposure_permille']}/1000", '',
             '## Changes', '', '| ID | Kind | Change | Level | Accepted as | Reasons |', '|---|---|---|---|---|---|']
    for change in report['changes']:
        values = [change['subject_id'], change['kind'], change['change'], change['level'],
                  change['accepted_as'] or '—', '; '.join(change['reasons'])]
        lines.append('| ' + ' | '.join(prose(value) for value in values) + ' |')
    lines.extend(['', '## Errors', ''])
    lines += [f"- {prose(error['code'])} · {prose(error['subject_id'] or 'release')}: {prose(error['message'])}"
              for error in report['errors']] or ['None.']
    lines.extend(['', '## Risk detail', '',
                  f"Weight minor units per point: {risk['weight_minor_units']} · Total active weight: {risk['total_weight_minor']}", '',
                  '| Requirement | Weight minor | Factor percent | Reach |', '|---|---|---|---|'])
    for requirement in risk['requirements']:
        lines.append('| ' + ' | '.join(prose(requirement[name]) for name in ('id', 'weight_minor', 'factor_percent', 'reach')) + ' |')
    lines.extend(['', 'Unmapped changes: ' + (', '.join(prose(item) for item in risk['unmapped_changes']) or 'None.'), '',
                  '## Scope', ''])
    lines += ['- ' + prose(limit) for limit in report['limitations']]
    return '\n'.join(lines) + '\n'


def emit(body, output=None):
    """Write stdout or a new file; preserve every existing file, including inputs."""
    if output is None:
        sys.stdout.write(body)
    else:
        with output.open('x', encoding='utf-8', newline='\n') as target:
            target.write(body)


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=f'AxiomSpec {EDITION}')
    commands = parser.add_subparsers(dest='command', required=True)
    checker = commands.add_parser('check', help='check strict JSON, schema, environments and references')
    checker.add_argument('spec', type=Path, help='a specification or parts manifest')
    checker.add_argument('--json', action='store_true', help='emit the deterministic report as JSON')
    writer = commands.add_parser('markdown', help='generate a Markdown view after checking the specification')
    writer.add_argument('spec', type=Path, help='a specification or parts manifest')
    writer.add_argument('--output', type=Path, help='write a new file instead of stdout; existing files are preserved')
    comparer = commands.add_parser('compare', help='compare two releases with the reference G14 classifier')
    comparer.add_argument('baseline', type=Path, help='the baseline specification or parts manifest')
    comparer.add_argument('candidate', type=Path, help='its candidate specification or parts manifest')
    comparer.add_argument('--format', choices=('json', 'markdown'), default='json', help='report format (default: json)')
    comparer.add_argument('--output', type=Path, help='write a new report file instead of stdout')
    store_checker = commands.add_parser('verify-store', help='verify release chains, approvals and imports from files')
    store_checker.add_argument('paths', type=Path, nargs='+', help='release/approval files or store directories')
    store_checker.add_argument('--json', action='store_true', help='emit the full reference store report as JSON')
    options = parser.parse_args(arguments)
    if sys.version_info < MIN_PYTHON:
        print('AxiomSpec needs Python 3.14 or later', file=sys.stderr)
        return 4
    try:
        if options.command == 'verify-store':
            for path in options.paths:
                if not path.exists():
                    raise ValueError(f'Store path does not exist: {path}')
            report = release_store.verify(release_store.load(options.paths))
            if options.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"AxiomSpec store: {report['status']} ({len(report['releases'])} releases, {len(report['projects'])} projects)")
                for release in report['releases']:
                    missing = ['baseline release'] if release['link'] == 'unknown' else []
                    missing += ['approvals'] if release['approvals'] == 'unknown' else []
                    missing += [f"{item['project_id']} {item['version']} ({item['id']})"
                                for item in release['imports'] if item['state'] == 'unresolved']
                    print(f"{release['project_id']} {release['version']}: {release['status']} {release['spec_sha256']}"
                          + (f" · missing: {', '.join(missing)}" if missing else ''))
                for error in report['errors']:
                    print(f"{error['code']} ({error['subject']}): {error['message']}")
                for rejected in report['rejected_files']:
                    print(f"Rejected {rejected['path']}: {rejected['reason']}")
                for limit in report['limitations']:
                    print(limit)
            return {'pass': 0, 'fail': 2, 'incomplete': 3}[report['status']]
        if options.command == 'compare':
            documents = []
            for path in (options.baseline, options.candidate):
                spec = load_spec(path)
                report = check(spec)
                if report['status'] != 'pass':
                    print(json.dumps(dict(report, input=str(path)), ensure_ascii=False, indent=2),
                          file=sys.stdout if options.format == 'json' else sys.stderr)
                    return 2
                documents.append(spec)
            report = release_diff.compare(*documents)
            emit(comparison_markdown(report) if options.format == 'markdown' else json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                 options.output)
            return 0 if report['status'] == 'pass' else 2
        spec = load_spec(options.spec)
        report = check(spec)
        if options.command == 'check':
            if options.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"AxiomSpec check: {report['status']} (structure and selected references)")
                for error in report['schema_errors']:
                    print(f"{error['pointer']}: {error['message']}")
                for code in report['reference_errors']:
                    print(code)
                for limit in report['limitations']:
                    print(limit)
            return 0 if report['status'] == 'pass' else 2
        if report['status'] != 'pass':
            print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        emit(markdown(spec, report), options.output)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        message = f'{type(exc).__name__}: {str(exc)[:400]}'
        if options.command == 'check' and options.json:
            print(json.dumps(dict(format='axiomspec-check/0.1', scope='structure_and_references', edition=EDITION,
                                  status='error', message=message, limitations=LIMITS)))
        elif (options.command == 'compare' and options.format == 'json') or (options.command == 'verify-store' and options.json):
            print(json.dumps(dict(format='axiomspec-cli-error/0.1', command=options.command,
                                  edition=EDITION, status='error', message=message)))
        else:
            print(message, file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
