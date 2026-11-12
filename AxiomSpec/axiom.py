#!/usr/bin/env python3
"""Check an AxiomSpec file or generate its Markdown reading view. Reads never execute product code."""
import argparse
import html
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
    errors = sorted((dict(pointer='/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in e.absolute_path),
                          message=e.message[:400]) for e in validator.iter_errors(spec)),
                    key=lambda e: (e['pointer'], e['message']))
    references = reference_errors(spec) if not errors else []
    # These shapes are deliberately restricted by AX-C-002, beyond the outer specification schema.
    if not errors:
        for number, environment in enumerate(spec['environments']):
            try:
                check_environment(environment['schema'])
            except (ValueError, KeyError, TypeError, SchemaError) as exc:
                errors.append(dict(pointer=f'/environments/{number}/schema',
                                   message=str(exc)[:400]))
    return dict(format='axiomspec-check/0.1', scope='structure_and_references', edition=EDITION,
                status='fail' if errors or references else 'pass', spec_sha256=digest(canonical(spec)),
                schema_errors=errors[:50], schema_error_count=len(errors), reference_errors=references,
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
    options = parser.parse_args(arguments)
    if sys.version_info < MIN_PYTHON:
        print('AxiomSpec needs Python 3.14 or later', file=sys.stderr)
        return 4
    try:
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
        body = markdown(spec, report)
        if options.output is None:
            sys.stdout.write(body)
        else:
            with options.output.open('x', encoding='utf-8', newline='\n') as output:
                output.write(body)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        message = f'{type(exc).__name__}: {str(exc)[:400]}'
        if options.command == 'check' and options.json:
            print(json.dumps(dict(format='axiomspec-check/0.1', scope='structure_and_references', edition=EDITION,
                                  status='error', message=message, limitations=LIMITS)))
        else:
            print(message, file=sys.stderr)
        return 4


if __name__ == '__main__':
    sys.exit(main())
