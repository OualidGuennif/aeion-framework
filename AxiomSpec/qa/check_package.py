#!/usr/bin/env python3
"""Local artifact QA. Not the AxiomSpec product validator or a trusted runner."""
import ast
import base64
import binascii
import copy
from collections import deque
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import unquote

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry
from croa_readiness import assess_inputs
from run_checks import (EDITION, EXAMPLE_RECEIPT, validate_example_receipt, validate_receipt,
                        toolchain as runtime_toolchain)

ROOT = Path(__file__).resolve().parents[1]
SAFE = 9007199254740991
BOUNDS = dict(max_input_bytes=1048576, max_expression_depth=24,
              max_expression_nodes=2000, max_steps=1000000,
              max_collection_items=10000)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw, fixture_values=False):
    require(len(raw) <= BOUNDS['max_input_bytes'], 'Input byte limit')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'Duplicate JSON key: {key}')
            result[key] = value
        return result

    def no_float(value):
        raise ValueError(f'Non-integer JSON number: {value}')

    result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                        parse_float=float if fixture_values else no_float, parse_constant=no_float)

    def visit(value, depth=0):
        require(depth <= 128, 'QA JSON depth limit')
        if isinstance(value, dict):
            for key, item in value.items():
                require(key.isascii(), 'Non-ASCII object key')
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif type(value) is int:
            require(abs(value) <= SAFE, 'Unsafe integer')
        elif isinstance(value, str):
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'Unicode surrogate')
    visit(result)
    return result


def read(relative, fixture_values=False):
    lexical = PurePosixPath(relative)
    require(not lexical.is_absolute() and '..' not in lexical.parts, 'Input path must be package-relative')
    path = ROOT / relative
    require(path.resolve().is_relative_to(ROOT.resolve()), 'Input path escapes the package')
    require(not path.is_symlink() and not any(parent.is_symlink() for parent in path.parents
            if parent != ROOT and parent.is_relative_to(ROOT)),
            'Input symlinks are not allowed')
    with path.open('rb') as source:
        raw = source.read(BOUNDS['max_input_bytes'] + 1)
    return strict_json(raw, fixture_values=fixture_values)


def write_atomic(path, text):
    require(path.resolve().is_relative_to(ROOT.resolve()) and not path.is_symlink(),
            'Output path escapes the package or is a symlink')
    require(not any(parent.is_symlink() for parent in path.parents
                    if parent != ROOT and parent.is_relative_to(ROOT)), 'Output parent is a symlink')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.qa-', delete=False) as temporary:
        temporary.write(text)
        name = temporary.name
    try:
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def package_files(root=None):
    root = root or ROOT
    files = []
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Package symlinks are not allowed')
        if path.is_file() and '__pycache__' not in path.parts:
            files.append(path)
    return files


def check_local_link(path, destination, root=None):
    root = (root or ROOT).resolve()
    clean = unquote(destination.strip('<>').split('#', 1)[0])
    require(not PurePosixPath(clean).is_absolute() and '\\' not in clean and ':' not in clean,
            'Local documentation links must be relative')
    target = (path.parent / clean).resolve()
    require(target.is_relative_to(root), 'Local documentation link escapes the package')
    require(target.exists(), f'Broken local link: {destination}')
    # A case-insensitive filesystem accepts a link that breaks elsewhere: compare each name exactly.
    current = path.parent
    for part in PurePosixPath(clean).parts:
        if part == '..':
            current = current.parent
        elif part != '.':
            require(current.is_dir() and part in {entry.name for entry in current.iterdir()},
                    f'Local link differs in letter case from the file name: {destination}')
            current = current / part


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def make_validator(schema, check_formats=False):
    # An empty explicit registry permits local fragments, never remote retrieval.
    return Draft202012Validator(schema, registry=Registry(),
                                format_checker=FormatChecker() if check_formats else None)


def croa_input_error():
    return dict(format='axiomspec-croa-input-review/0.2', scope='selected_readiness_inputs',
                input_status='error', assessment_status='not_scored', conformance_status='not_assessed',
                findings=[], limitations=['Current inputs could not be checked; previous diagnostics are not current evidence.'])


RELATIONS = {
    'satisfies': ({'Requirement'}, {'Goal'}),
    'uses_term': ({'Requirement', 'Constraint'}, {'Term'}),
    'formalizes': ({'Constraint'}, {'Requirement'}),
    'models': ({'StateModel'}, {'Requirement'}),
    'illustrates': ({'Scenario'}, {'Requirement'}),
    'verifies': ({'TestCase'}, {'Requirement'}),
    'checks': ({'TestCase'}, {'Constraint'}),
    'implements': ({'Component'}, {'Requirement'}),
    'depends_on': ({'Requirement'}, {'Requirement'}),
    'assumes': ({'Requirement', 'Constraint'}, {'Assumption'}),
    'governs': ({'Decision'}, {'Goal', 'Requirement', 'Constraint', 'StateModel'}),
    'threatens': ({'Risk'}, {'Goal', 'Requirement'}),
    'mitigates': ({'Control'}, {'Risk'}),
    'realizes': ({'Requirement'}, {'Control'}),
}
PREFIXES = dict(Goal='GOAL', Term='TERM', Requirement='REQ', Constraint='CON',
                StateModel='MODEL', Scenario='SCN', TestCase='TEST', Component='COMP',
                Decision='DEC', Assumption='ASM', Risk='RISK', Control='CTRL')


BINDING_TARGETS = {  # AX-M-014: binding kind -> node kinds it may name
    'code': {'Component', 'Constraint'}, 'test': {'TestCase'},
    'enforcement': {'Constraint', 'Control'}, 'observation': {'Constraint', 'Requirement'}}


def literal_collection(expression):
    """AX-C-005: True when an aggregate or quantifier iterates anything but a path."""
    pending = [expression]
    while pending:
        e = pending.pop()
        if isinstance(e, dict):
            if e.get('kind') in {'aggregate', 'quantifier'} and e['collection'].get('kind') != 'path':
                return True
            pending.extend(e.values())
        elif isinstance(e, list):
            pending.extend(e)
    return False


PATTERN_FIELDS = {  # AX-M-006: pattern -> (conditions, trigger, feature) populated
    'ubiquitous': (False, False, False), 'event': (False, True, False), 'state': (True, False, False),
    'unwanted': (False, True, False), 'optional': (False, False, True), 'composite': (True, True, False)}


def utc_instant(value):
    """AX-C-013: an ISO 8601 instant in UTC (Z or +00:00); ValueError otherwise."""
    moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if moment.utcoffset() is None or moment.utcoffset().total_seconds() != 0:
        raise ValueError('Not a UTC instant')
    return moment


def version_tuple(text):
    """AX-M-017: MAJOR.MINOR.PATCH as integers, compared numerically."""
    return tuple(int(part) for part in text.split('.'))


def version_step(previous, current):
    """AX-L-008: 'major', 'minor' or 'patch' when `current` is the next version at that level, else None."""
    a, b = version_tuple(previous), version_tuple(current)
    for level, expected in (('major', (a[0] + 1, 0, 0)), ('minor', (a[0], a[1] + 1, 0)), ('patch', (a[0], a[1], a[2] + 1))):
        if b == expected:
            return level
    return None


BANDS = ('low', 'medium', 'high', 'critical')
EXPORTABLE = {'Requirement', 'Constraint', 'Term', 'StateModel'}
KEY_BYTES = {'ed25519': 32, 'webauthn-es256': 65}


def decode_base64(text):
    """Standard base64 with padding, or None. Used for keys and signatures (AX-M-020)."""
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def valid_public_key(algorithm, text):
    """AX-M-020: 32 raw bytes for Ed25519; an uncompressed P-256 point (0x04, X, Y) for a passkey."""
    raw = decode_base64(text)
    return raw is not None and len(raw) == KEY_BYTES[algorithm] and (algorithm == 'ed25519' or raw[0] == 4)


def eligible_approvers(spec, band):
    """AX-M-020: the actors who could approve at this band under this specification's keys and methods."""
    allowed = set(spec['approval']['policy'][band]['methods'])
    keys = [k for k in spec['approval']['keys'] if not allowed or k['method'] in allowed]
    actors = {k['actor_id'] for k in keys if not k['attests']}
    if any(k['attests'] for k in keys):
        actors |= {a['id'] for a in spec['actors'] if a['type'] != 'service'}
    return actors


def weight_band(weight_minor, units):
    """AX-M-018: the risk label a weight implies. Bands are 1-25, above 25-50, above 50-75, above 75-100."""
    for label, top in (('low', 25), ('medium', 50), ('high', 75)):
        if weight_minor <= top * units:
            return label
    return 'critical'


def annotated_leaf(schema, pointer):
    """AX-C-008: the environment schema node a unit annotation names; `*` is one array-element level."""
    if not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        return None
    node = schema
    for token in pointer.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        if not isinstance(node, dict):
            return None
        if token == '*' and node.get('type') == 'array':
            node = node.get('items')
        elif node.get('type') == 'object' and token in node.get('properties', {}):
            node = node['properties'][token]
        else:
            return None
    return node if isinstance(node, dict) else None


def reference_errors(spec):
    """Selected semantic checks for fixtures, not complete G02-G07 qualification."""
    errors = []
    all_ids = [spec['project']['id']]
    for section in ('actors', 'imports', 'sources', 'environments', 'flags', 'nodes', 'edges', 'bindings', 'context_assets'):
        all_ids.extend(x['id'] for x in spec[section])
    all_ids.extend(x['id'] for x in spec['approval']['keys'])
    if len(all_ids) != len(set(all_ids)):
        errors.append('DUPLICATE_ID')
    nodes = {x['id']: x for x in spec['nodes']}
    actors = {x['id'] for x in spec['actors']}
    sources = {x['id'] for x in spec['sources']}
    envs = {x['id'] for x in spec['environments']}
    bindings = {x['id']: x for x in spec['bindings']}
    flags = {x['id']: x for x in spec['flags']}
    units = spec['project']['weight_minor_units']
    release = spec['release']
    for section, prefix in [('actors', 'ACTOR'), ('sources', 'SRC'), ('environments', 'ENV'), ('flags', 'FLAG'),
                            ('edges', 'EDGE'), ('bindings', 'BIND'), ('context_assets', 'ASSET'), ('imports', 'IMP')]:
        if any(not x['id'].startswith(prefix + '-') for x in spec[section]):
            errors.append('WRONG_PREFIX')
    # AX-M-020: who may approve the next release, with which key and method, and how many per risk band.
    approval = spec['approval']
    actor_types = {x['id']: x['type'] for x in spec['actors']}
    if any(not key['id'].startswith('KEY-') for key in approval['keys']):
        errors.append('WRONG_PREFIX')
    material = [key['public_key'] for key in approval['keys']]
    if len(material) != len(set(material)):
        errors.append('DUPLICATE_APPROVAL_KEY')
    for key in approval['keys']:
        if key['actor_id'] not in actors:
            errors.append('UNKNOWN_ACTOR')
        elif key['attests'] and actor_types[key['actor_id']] != 'service':
            errors.append('ATTESTOR_NOT_SERVICE')
        if not valid_public_key(key['algorithm'], key['public_key']):
            errors.append('INVALID_APPROVAL_KEY')
    for band in BANDS:
        if not set(approval['policy'][band]['methods']) <= {key['method'] for key in approval['keys']}:
            errors.append('UNKNOWN_APPROVAL_METHOD')
        elif len(eligible_approvers(spec, band)) < approval['policy'][band]['approvers']:
            errors.append('UNSATISFIABLE_APPROVAL_POLICY')
    # AX-M-021: an import pins one release of another specification; an export is an active public object.
    providers = [item['project_id'] for item in spec['imports']]
    if spec['project']['id'] in providers:
        errors.append('SELF_IMPORT')
    if len(providers) != len(set(providers)):
        errors.append('DUPLICATE_IMPORT')
    for item in spec['imports']:
        used = [use['external_id'] for use in item['uses']]
        if len(used) != len(set(used)):
            errors.append('DUPLICATE_IMPORT')
        if any(nodes.get(local, {}).get('status') in (None, 'retired') for use in item['uses'] for local in use['local_ids']):
            errors.append('UNKNOWN_IMPORT_USER')
    for exported in spec['exports']:
        node = nodes.get(exported)
        if node is None or node['status'] != 'active' or node['kind'] not in EXPORTABLE:
            errors.append('INVALID_EXPORT')
    if not spec['project']['id'].startswith('PROJECT-'):
        errors.append('WRONG_PREFIX')
    for env in spec['environments']:
        try:
            check_environment(env['schema'])
        except (ValueError, KeyError, TypeError, SchemaError):
            errors.append('INVALID_ENVIRONMENT_SCHEMA')
            continue
        annotated = {}
        for annotation in env['units']:
            if nodes.get(annotation['term_id'], {}).get('kind') != 'Term':
                errors.append('UNKNOWN_UNIT_TERM')
            leaf = annotated_leaf(env['schema'], annotation['pointer'])
            if leaf is None or leaf.get('type') != 'integer':
                errors.append('UNIT_ANNOTATION')
            if annotated.setdefault(annotation['pointer'], annotation['term_id']) != annotation['term_id']:
                errors.append('UNIT_ANNOTATION')
    active = {n['kind'] for n in spec['nodes'] if n['status'] == 'active'}
    if spec['project']['mode'] == 'product' and not {'Goal', 'Requirement'} <= active:
        errors.append('EMPTY_BASELINE')
    if spec['project']['owner'] not in actors:
        errors.append('UNKNOWN_OWNER')
    # AX-M-017: a release names the baseline it succeeds and is exactly one version step after it.
    if release['previous'] is None:
        if release['compatibility']:
            errors.append('COMPATIBILITY_WITHOUT_BASELINE')
    elif version_step(release['previous']['version'], release['version']) is None:
        errors.append('INVALID_VERSION_STEP')
    subjects = [entry['subject_id'] for entry in release['compatibility']]
    if len(subjects) != len(set(subjects)):
        errors.append('DUPLICATE_COMPATIBILITY_SUBJECT')
    for entry in release['compatibility']:
        decision = nodes.get(entry['decision_id'], {})
        if decision.get('kind') != 'Decision' or decision['status'] != 'active' or decision['data']['answer'] is None:
            errors.append('INVALID_COMPATIBILITY_DECISION')
        if entry['classification'] == 'breaking' and entry['migration'] is None:
            errors.append('MISSING_MIGRATION')
    # AX-M-019: flags are declared once, owned, introduced no later than this release and removed on schedule.
    keys = [flag['key'] for flag in spec['flags']]
    if len(keys) != len(set(keys)):
        errors.append('DUPLICATE_FLAG_KEY')
    governed = {n['data']['flag_id'] for n in spec['nodes'] if n['kind'] == 'Requirement' and n['status'] != 'retired'}
    for flag in spec['flags']:
        if flag['owner'] not in actors:
            errors.append('UNKNOWN_ACTOR')
        introduced = version_tuple(flag['introduced_in'])
        if introduced > version_tuple(release['version']):
            errors.append('FLAG_VERSION')
        if flag['remove_by'] is not None:
            if version_tuple(flag['remove_by']) <= introduced:
                errors.append('FLAG_VERSION')
            elif version_tuple(release['version']) >= version_tuple(flag['remove_by']):
                errors.append('STALE_FLAG')
        if flag['id'] not in governed:
            errors.append('UNUSED_FLAG')
    for n in nodes.values():
        if not n['id'].startswith(PREFIXES[n['kind']] + '-'):
            errors.append('WRONG_PREFIX')
        if n['owner'] not in actors or n['created_by'] not in actors:
            errors.append('UNKNOWN_ACTOR')
        if not set(n['source_ids']).issubset(sources):
            errors.append('UNKNOWN_SOURCE')
        data = n['data']
        if 'environment_id' in data and data['environment_id'] is not None and data['environment_id'] not in envs:
            errors.append('UNKNOWN_ENVIRONMENT')
        if n['kind'] == 'TestCase':
            for sid in data['witness_scenario_ids']:
                if nodes.get(sid, {}).get('kind') != 'Scenario':
                    errors.append('UNKNOWN_SCENARIO')
            named = [entry['flag_id'] for entry in data['flag_states']]
            if not set(named) <= set(flags):
                errors.append('UNKNOWN_FLAG')
            if len(named) != len(set(named)):
                errors.append('FLAG_STATE_CONFLICT')
        if n['kind'] == 'Scenario':
            for expected in data['constraint_expectations']:
                if nodes.get(expected['constraint_id'], {}).get('kind') != 'Constraint':
                    errors.append('UNKNOWN_CONSTRAINT')
        if n['kind'] == 'Requirement' and data['flag_id'] is not None and data['flag_id'] not in flags:
            errors.append('UNKNOWN_FLAG')
        if n['kind'] == 'Requirement' and n['status'] != 'retired':
            populated = (bool(data['conditions']), data['trigger'] is not None, data['feature'] is not None)
            if populated != PATTERN_FIELDS[data['pattern']]:
                errors.append('PATTERN_FIELDS')
            # AX-M-018: a weight is 1 to 100 points in declared minor units, and the risk label is its band.
            if not units <= data['weight_minor'] <= 100 * units:
                errors.append('WEIGHT_RANGE')
            elif weight_band(data['weight_minor'], units) != data['risk']:
                errors.append('RISK_BAND_MISMATCH')
            if data['pattern'] == 'optional' and data['flag_id'] is None:
                errors.append('OPTIONAL_WITHOUT_FLAG')
        if n['kind'] == 'Constraint' and n['status'] != 'retired':
            try:
                bounds = [None if data[f] is None else utc_instant(data[f]) for f in ('effective_from', 'effective_until')]
                if None not in bounds and bounds[0] >= bounds[1]:
                    errors.append('INVALID_WINDOW')
            except ValueError:
                errors.append('INVALID_WINDOW')
            if data['expression'] is not None and literal_collection(data['expression']):
                errors.append('LITERAL_COLLECTION')
        if n['kind'] == 'Constraint':
            review = data['predicate_role'] == 'review'
            if review:
                if data['representation'] != 'review_protocol' or data['expression'] is not None or data['review_protocol'] is None:
                    errors.append('INCONSISTENT_REVIEW')
            elif data['representation'] != 'bcir' or data['expression'] is None or data['environment_id'] is None or data['review_protocol'] is not None:
                errors.append('INCONSISTENT_BCIR')
            bid = data['enforcement_binding_id']
            if bid is not None and (bid not in bindings or bindings[bid]['node_id'] != n['id'] or bindings[bid]['kind'] != 'enforcement'):
                errors.append('INVALID_ENFORCEMENT_BINDING')
        if n['kind'] == 'StateModel':
            states = [s['name'] for s in data['states']]
            transitions = data['transitions']
            if len(states) != len(set(states)) or data['initial'] not in states:
                errors.append('INVALID_STATES')
            tids = [t['id'] for t in transitions]
            if len(tids) != len(set(tids)):
                errors.append('DUPLICATE_TRANSITION')
            if any(not tid.startswith('TRN-') for tid in tids):
                errors.append('WRONG_PREFIX')
            # AX-G-005 topology: guards are ignored, so this is reachability of the drawing, not of behavior.
            terminal = {s['name'] for s in data['states'] if s['terminal']}
            if any(t['from'] in terminal for t in transitions):
                errors.append('TERMINAL_HAS_EXIT')
            reached, frontier = {data['initial']}, [data['initial']]
            while frontier:
                state = frontier.pop()
                for t in transitions:
                    if t['from'] == state and t['to'] not in reached:
                        reached.add(t['to'])
                        frontier.append(t['to'])
            if data['initial'] in states and not set(states) <= reached:
                errors.append('UNREACHABLE_STATE')
            for t in transitions:
                if t['from'] not in states or t['to'] not in states:
                    errors.append('UNKNOWN_STATE')
                if t['guard_id'] is not None:
                    guard = nodes.get(t['guard_id'], {})
                    if guard.get('kind') != 'Constraint':
                        errors.append('UNKNOWN_GUARD')
                    elif (guard['data']['representation'] != 'bcir'
                          or guard['data']['environment_id'] != data['environment_id']):
                        errors.append('INCOMPATIBLE_GUARD')
    triples = [(e['from'], e['relation'], e['to']) for e in spec['edges']]
    if len(triples) != len(set(triples)):
        errors.append('DUPLICATE_EDGE')
    adjacency = {nid: [] for nid, n in nodes.items() if n['kind'] == 'Requirement'}
    for edge in spec['edges']:
        a, b = nodes.get(edge['from']), nodes.get(edge['to'])
        if a is None or b is None:
            errors.append('UNKNOWN_TARGET')
            continue
        types = RELATIONS.get(edge['relation'])
        if types is None or a['kind'] not in types[0] or b['kind'] not in types[1]:
            errors.append('WRONG_EDGE_TYPE')
            continue
        if a['status'] == 'active' and b['status'] == 'retired':
            errors.append('ACTIVE_TO_RETIRED')
        if edge['relation'] == 'depends_on' and a['status'] == b['status'] == 'active':
            adjacency[a['id']].append(b['id'])
    indegrees = dict.fromkeys(adjacency, 0)
    for targets in adjacency.values():
        for target in targets:
            indegrees[target] += 1
    ready = deque(sorted(nid for nid, count in indegrees.items() if count == 0))
    visited = 0
    while ready:
        nid = ready.popleft()
        visited += 1
        for other in adjacency[nid]:
            indegrees[other] -= 1
            if indegrees[other] == 0:
                ready.append(other)
    if visited != len(adjacency):
        errors.append('DEPENDENCY_CYCLE')
    outgoing = {}
    for edge in spec['edges']:
        outgoing.setdefault((edge['from'], edge['relation']), set()).add(edge['to'])
    def active_targets(nid, relation):
        return {t for t in outgoing.get((nid, relation), ()) if nodes.get(t, {}).get('status') == 'active'}
    for n in nodes.values():
        if n['status'] != 'active':
            continue
        # AX-G-003: the goal or requirement on the other end must itself be active.
        if n['kind'] == 'Requirement':
            if not n['source_ids'] or (n['data']['priority'] == 'must' and not active_targets(n['id'], 'satisfies')):
                errors.append('REQUIREMENT_PROVENANCE')
            flag_id = n['data']['flag_id']
            if flag_id in flags and n['data']['priority'] == 'must':
                # AX-G-007: a flagged must requirement is verified with its flag on and with it off.
                states = {entry['state'] for test_id, test in nodes.items()
                          if test['kind'] == 'TestCase' and test['status'] == 'active'
                          and n['id'] in outgoing.get((test_id, 'verifies'), ())
                          for entry in test['data']['flag_states'] if entry['flag_id'] == flag_id}
                if states != {'enabled', 'disabled'}:
                    errors.append('FLAG_STATE_UNTESTED')
        if n['kind'] == 'Constraint' and not active_targets(n['id'], 'formalizes'):
            errors.append('UNLINKED_CONSTRAINT')
        if n['kind'] == 'TestCase':
            # AX-G-007: a cited scenario illustrates a requirement this test verifies.
            verified = outgoing.get((n['id'], 'verifies'), set())
            for sid in n['data']['witness_scenario_ids']:
                if sid in nodes and not verified & outgoing.get((sid, 'illustrates'), set()):
                    errors.append('SCENARIO_NOT_ILLUSTRATING')
    for b in spec['bindings']:
        path = PurePosixPath(b['path'])
        if b['node_id'] not in nodes:
            errors.append('UNKNOWN_BINDING_NODE')
        elif nodes[b['node_id']]['kind'] not in BINDING_TARGETS[b['kind']]:
            errors.append('WRONG_BINDING_TARGET')
        if path.is_absolute() or '..' in path.parts or '\\' in b['path'] or ':' in b['path'] or '\x00' in b['path']:
            errors.append('UNSAFE_BINDING_PATH')
    for asset in spec['context_assets']:
        if not set(asset['supports']).issubset(nodes) or not set(asset['source_ids']).issubset(sources) or not set(asset['allowed_roles']).issubset(actors):
            errors.append('UNKNOWN_ASSET_REFERENCE')
        if any(nodes.get(nid, {}).get('kind') not in {'Goal', 'Term', 'Requirement', 'Constraint', 'StateModel', 'Decision'} for nid in asset['supports']):
            errors.append('WRONG_ASSET_TARGET_KIND')
        if asset['binding_id'] is not None and asset['binding_id'] not in bindings:
            errors.append('UNKNOWN_ASSET_BINDING')
        if asset['locator'].startswith('node:') and asset['locator'][5:] not in nodes:
            errors.append('UNKNOWN_ASSET_LOCATOR')
        if asset['locator'].startswith('binding:'):
            # AX-X-002: the locator names a declared binding, and a supplied binding_id agrees with it.
            if asset['locator'][8:] not in bindings:
                errors.append('UNKNOWN_ASSET_LOCATOR')
            elif asset['binding_id'] is not None and asset['binding_id'] != asset['locator'][8:]:
                errors.append('ASSET_BINDING_MISMATCH')
    return sorted(set(errors))


def resolve_symbol(path, symbol):
    """AX-M-014: True when a Python file declares `name` or `Class.member`. Parses the file; runs nothing."""
    scope = ast.parse(path.read_text()).body
    for name in symbol.split('.'):
        found = [node for node in scope
                 if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
        if not found:
            return False
        scope = found[0].body
    return True


def check_example_evidence(spec, executed_ids, root=None):
    """G09/G10 for the worked example: required bindings resolve and every implemented TestCase was executed."""
    root = root or ROOT
    nodes = {n['id']: n for n in spec['nodes']}
    bound_tests, resolved, covered = {}, 0, set()
    for binding in spec['bindings']:
        if binding['expected_resolution'] != 'must_resolve':
            continue
        require(binding['language'] == 'python' and binding['symbol'] is not None,
                f"{binding['id']}: only Python symbols are resolved by this check")
        path = root / binding['path']
        require(path.resolve().is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(),
                f"{binding['id']}: path does not resolve inside the package")
        require(resolve_symbol(path, binding['symbol']), f"{binding['id']}: symbol {binding['symbol']} not found")
        resolved += 1
        if binding['kind'] == 'test':
            prefix = f"{PurePosixPath(binding['path']).stem}.{binding['symbol']}."
            ran = [item for item in executed_ids if item.startswith(prefix)]
            require(ran, f"{binding['id']}: no executed test under {binding['symbol']}")
            bound_tests[binding['node_id']] = ran
            covered.update(ran)
    for node in nodes.values():
        if node['kind'] == 'TestCase' and node['status'] == 'active':
            require(node['data']['state'] == 'implemented' and node['id'] in bound_tests,
                    f"{node['id']}: an active TestCase has no executed, bound test")
    require(covered == set(executed_ids), 'An executed test belongs to no TestCase binding')
    return resolved, len(bound_tests)


def check_environment(schema):
    allowed = {'type', 'properties', 'required', 'additionalProperties', 'items', 'enum',
               'minimum', 'maximum', 'minItems', 'maxItems', 'minLength', 'maxLength', 'description'}
    require(isinstance(schema, dict), 'Environment schema must be an object')
    # Validate keyword shapes before traversing them, once for the whole schema.
    Draft202012Validator.check_schema(schema)

    def shape(current):
        require(isinstance(current, dict), 'Environment schema must be an object')
        require(set(current).issubset(allowed), 'Unsupported environment keyword')
        t = current.get('type')
        require(t in {'object', 'array', 'integer', 'boolean', 'string'}, 'Explicit environment type required')
        if t == 'object':
            require(current.get('additionalProperties') is False, 'Environment object must be closed')
            require(set(current.get('required', [])) == set(current.get('properties', {})), 'Every property required')
            for child in current.get('properties', {}).values():
                shape(child)
        elif t == 'array':
            require(type(current.get('maxItems')) is int and 0 <= current['maxItems'] <= 10000, 'Array bound')
            shape(current.get('items'))
        elif t == 'integer':
            require(type(current.get('minimum')) is int and type(current.get('maximum')) is int, 'Integer bounds')
            require(-SAFE <= current['minimum'] <= current['maximum'] <= SAFE, 'Safe bounds')
        elif t == 'string':
            require(type(current.get('maxLength')) is int and current['maxLength'] >= 0, 'String bound')
    shape(schema)


class BudgetExceeded(ValueError):
    pass


class MissingObservation(ValueError):
    pass


class ReferenceEvaluator:
    """Eager reference subset for supplied fixtures; no static unit/type compiler."""
    def __init__(self, max_steps=1000000):
        self.steps = 0
        self.max_steps = max_steps

    def tick(self):
        self.steps += 1
        if self.steps > self.max_steps:
            raise BudgetExceeded('Reference work budget exhausted')

    @staticmethod
    def integer(value):
        require(type(value) is int and abs(value) <= SAFE, 'Expected safe integer')
        return value

    @staticmethod
    def boolean(value):
        require(type(value) is bool, 'Expected boolean')
        return value

    def evaluate(self, expression, environment):
        self.steps = 0
        count = 0
        def preflight(e, depth=0):
            nonlocal count
            count += 1
            require(depth <= 24 and count <= 2000, 'Reference expression shape budget')
            if e['kind'] == 'apply':
                children = e['arguments']
            elif e['kind'] == 'aggregate':
                require(e['collection']['kind'] == 'path', 'A collection is a declared array reached by a path')
                children = [e['collection'], e['filter'], e['projection']]
            elif e['kind'] == 'quantifier':
                require(e['collection']['kind'] == 'path', 'A collection is a declared array reached by a path')
                children = [e['collection'], e['predicate']]
            else:
                require(e['kind'] in {'literal', 'path'}, 'Unknown expression kind')
                children = []
            for child in children:
                preflight(child, depth + 1)
        preflight(expression)
        return self.visit(expression, {'env': environment}, 0)

    def visit(self, e, scope, depth):
        self.tick()
        require(depth <= 24, 'Reference expression depth')
        kind = e['kind']
        if kind == 'literal':
            return e['value']
        if kind == 'path':
            require(e['pointer'] == '' or e['pointer'].startswith('/'), 'Invalid JSON Pointer')
            require(re.search(r'~(?![01])', e['pointer']) is None, 'Invalid JSON Pointer escape')
            if e['root'] not in scope:
                raise ValueError('Unbound root')
            value = scope[e['root']]
            for token in e['pointer'].split('/')[1:] if e['pointer'] else []:
                token = token.replace('~1', '/').replace('~0', '~')
                if not isinstance(value, dict) or token not in value:
                    raise MissingObservation('Missing observation path')
                value = value[token]
            return value
        if kind in {'aggregate', 'quantifier'}:
            require(e['bind'] != 'env' and e['bind'] not in scope, 'Variable shadowing')
            items = self.visit(e['collection'], scope, depth + 1)
            require(isinstance(items, list) and len(items) <= 10000, 'Bounded collection required')
            values = []
            for item in items:
                self.tick()
                nested = dict(scope, **{e['bind']: item})
                if kind == 'quantifier':
                    values.append(self.boolean(self.visit(e['predicate'], nested, depth + 1)))
                elif self.boolean(self.visit(e['filter'], nested, depth + 1)):
                    values.append(self.integer(self.visit(e['projection'], nested, depth + 1)))
            op = e['operator']
            if kind == 'quantifier':
                require(op in {'all', 'exists'}, 'Unknown quantifier')
                return all(values) if op == 'all' else any(values)
            require(op in {'sum', 'count'}, 'Unknown aggregate')
            if op == 'count':
                require(e['projection'] == {'kind': 'literal', 'value': 1} and type(e['projection']['value']) is int, 'Count projection')
                return len(values)
            total = 0
            for value in values:
                total = self.integer(total + value)
            return total
        require(kind == 'apply', 'Unknown expression kind')
        op = e['operator']
        args = [self.visit(a, scope, depth + 1) for a in e['arguments']]
        require(len(args) >= 2 if op in {'and', 'or'} else len(args) == (1 if op == 'not' else 2), 'Operator arity')
        if op in {'and', 'or', 'not', 'implies'}:
            args = [self.boolean(a) for a in args]
            if op == 'and': return all(args)
            if op == 'or': return any(args)
            if op == 'not': return not args[0]
            return not args[0] or args[1]
        a, b = args
        if op in {'eq', 'ne'}:
            require(type(a) is type(b) and type(a) in {str, int, bool}, 'Scalar equality types')
            return (a == b) if op == 'eq' else (a != b)
        if op == 'in':
            require(type(a) in {str, int, bool} and isinstance(b, list) and all(type(x) is type(a) for x in b), 'Membership types')
            return a in b
        a, b = self.integer(a), self.integer(b)
        if op == 'lt': return a < b
        if op == 'le': return a <= b
        if op == 'gt': return a > b
        if op == 'ge': return a >= b
        if op == 'add': return self.integer(a + b)
        if op == 'sub': return self.integer(a - b)
        if op == 'mul': return self.integer(a * b)
        raise ValueError('Unknown operator')


def mutate(baseline, mutation):
    require(mutation['op'] in {'add', 'replace', 'remove', 'append'}, 'Unknown fixture mutation')
    require(mutation['path'].startswith('/') and re.search(r'~(?![01])', mutation['path']) is None,
            'Invalid mutation pointer')
    result = copy.deepcopy(baseline)
    parts = [p.replace('~1', '/').replace('~0', '~') for p in mutation['path'].split('/')[1:]]
    target = result
    def index(container, token):
        if isinstance(container, list):
            require(re.fullmatch(r'0|[1-9][0-9]*', token) is not None, 'Invalid mutation array index')
            require(int(token) < len(container), 'Mutation array index out of range')
            return int(token)
        require(isinstance(container, dict), 'Mutation traverses a scalar')
        return token
    for part in parts[:-1]:
        target = target[index(target, part)]
    key = index(target, parts[-1])
    exists = (0 <= key < len(target)) if isinstance(target, list) else key in target
    if mutation['op'] in {'replace', 'remove', 'append'}:
        require(exists, 'Mutation target does not exist')
    else:
        # add creates a member; overwriting one is replace, and growing an array is append.
        require(isinstance(target, dict) and not exists, 'Add target must be a new object member')
    if mutation['op'] == 'remove':
        del target[key]
    elif mutation['op'] == 'append':
        require(isinstance(target[key], list), 'Append target must be an array')
        target[key].append(copy.deepcopy(mutation['value']))
    else:
        target[key] = copy.deepcopy(mutation['value'])
    return result


def check_observation_corpus(baseline, observations):
    require(observations['format'] == 'axiomspec-observation-fixtures/0.1'
            and observations['synthetic'] is True, 'Observation corpus format/provenance')
    nodes = {n['id']: n for n in baseline['nodes']}
    envs = {e['id']: e for e in baseline['environments']}
    expected_scenarios = {n['id'] for n in baseline['nodes'] if n['kind'] == 'Scenario'}
    seen = [c['scenario_id'] for c in observations['cases']]
    require(expected_scenarios and set(seen) == expected_scenarios and len(seen) == len(set(seen)),
            'Observation coverage differs from canonical scenarios')
    count = 0
    for case in observations['cases']:
        scenario = nodes[case['scenario_id']]['data']
        eid = case['environment_id']
        require(eid == scenario['environment_id'], 'Scenario environment mismatch')
        require(case['environment'] == scenario['given'], 'Fixture and canonical scenario differ')
        pairs = scenario['constraint_expectations']
        declared = {e['constraint_id']: e['expected'] for e in pairs}
        require(len(declared) == len(pairs), 'Duplicate scenario expectation')
        required = {n['id'] for n in baseline['nodes'] if n['kind'] == 'Constraint'
                    and n['status'] == 'active' and n['data']['representation'] == 'bcir'
                    and n['data']['environment_id'] == eid}
        require(set(declared) == required and case['expected'] == declared,
                'Missing, extra or inconsistent reference expectations')
        make_validator(envs[eid]['schema']).validate(case['environment'])
        for cid, expected in sorted(case['expected'].items()):
            constraint = nodes[cid]['data']
            result = ReferenceEvaluator().evaluate(constraint['expression'], case['environment'])
            require(type(expected) is bool and type(result) is bool and result is expected,
                    f"{case['scenario_id']} {cid}: {result} != {expected}")
            if scenario['intent'] == 'witness' and constraint['classification']['strength'] == 'hard' and constraint['predicate_role'] == 'invariant':
                require(result is True, 'Witness violates required invariant')
            count += 1
    return len(seen), count


def check_vector_corpus(baseline, vectors, validator):
    diagnostics = {'V-006': 'UNKNOWN_TARGET', 'V-007': 'WRONG_EDGE_TYPE',
                   'V-008': 'DUPLICATE_ID', 'V-009': 'UNKNOWN_ACTOR', 'V-010': 'DEPENDENCY_CYCLE',
                   'V-011': 'WEIGHT_RANGE', 'V-012': 'RISK_BAND_MISMATCH', 'V-013': 'UNKNOWN_FLAG',
                   'V-014': 'FLAG_STATE_UNTESTED', 'V-015': 'STALE_FLAG', 'V-016': 'INVALID_VERSION_STEP',
                   'V-017': 'MISSING_MIGRATION', 'V-018': 'OPTIONAL_WITHOUT_FLAG',
                   'V-019': 'UNKNOWN_APPROVAL_METHOD', 'V-020': 'UNSATISFIABLE_APPROVAL_POLICY', 'V-021': 'INVALID_EXPORT',
                   'V-022': 'UNKNOWN_IMPORT_USER', 'V-023': 'ATTESTOR_NOT_SERVICE'}
    executable = len(diagnostics) + 5
    required = {f'V-{i:03d}' for i in range(1, executable + 1)} | {f'V-{i:03d}' for i in range(101, 131)}
    require({v['id'] for v in vectors} == required and len(vectors) == len(required), 'Conformance corpus coverage differs from v0.3')
    for vector in vectors:
        require(set(vector) == {'id', 'purpose', 'layer', 'mutation', 'expected_schema_valid',
                                'expected_gate', 'expected_outcome'}, 'Invalid vector fields')
        require(type(vector['purpose']) is str and bool(vector['purpose'].strip()), 'Vector purpose required')
        require(vector['expected_gate'] in {f'G{i:02d}' for i in range(1, 15)}
                and vector['expected_outcome'] in {'pass', 'fail', 'unknown', 'error', 'not_applicable'},
                'Invalid expected gate or outcome')
        if vector['id'] >= 'V-101':
            require(vector['layer'] == 'future_runtime' and vector['mutation'] is None
                    and vector['expected_schema_valid'] is None,
                    'Future product vector must remain unexecuted')
            continue
        is_schema = vector['id'] <= 'V-005'
        expected = ('schema', 'error', False) if is_schema else ('references', 'fail', True)
        actual = (vector['layer'], vector['expected_outcome'], vector['expected_schema_valid'])
        gates = {'G01'} if is_schema else {'G02', 'G04', 'G07'}
        require(actual == expected and vector['expected_gate'] in gates and type(vector['expected_schema_valid']) is bool,
                f"{vector['id']} gate/outcome contract differs")
        candidate = mutate(baseline, vector['mutation'])
        require(validator.is_valid(candidate) == vector['expected_schema_valid'], f"{vector['id']} schema expectation")
        if not is_schema:
            require(diagnostics[vector['id']] in reference_errors(candidate), f"{vector['id']} expected diagnostic not observed")
    return executable, 30


def update_rule_index():
    rows, ids = [], set()
    for path in sorted((ROOT / 'docs').glob('*.md')):
        for line in path.read_text().splitlines():
            match = re.match(r'### (AX-[A-Z]+-\d{3}) — (.+)$', line)
            if match:
                rid, title = match.groups()
                require(rid not in ids, f'Duplicate rule: {rid}')
                ids.add(rid)
                rows.append(f'| {rid} | {title} | [{path.stem}](docs/{path.name}) |')
    content = '# Rule index\n\nGenerated from normative headings. The linked documents define each rule.\n\n| ID | Subject | Contract |\n|---|---|---|\n'
    write_atomic(ROOT / 'RULE_INDEX.md', content + '\n'.join(rows) + '\n')
    return len(ids)


def input_manifest():
    entries = []
    for path in package_files():
        relative = path.relative_to(ROOT).as_posix()
        if not relative.startswith('validation/') and relative != 'VALIDATION.md':
            raw = path.read_bytes()
            entries.append(dict(path=relative, sha256=digest(raw), bytes=len(raw)))
    return dict(format='axiomspec-package-manifest/0.1', entries=entries,
                exclusions=['validation/**', 'VALIDATION.md', '**/__pycache__/**'])


def require_unchanged_inputs(before):
    after = input_manifest()
    require(after == before, 'Package inputs changed during verification; rerun on a stable working tree')
    return after


def main():
    package_files()  # Reject symlinks before any input document is opened.
    rule_count = update_rule_index()
    initial_inputs = input_manifest()
    spec_schema, report_schema = read('schemas/spec.schema.json'), read('schemas/report.schema.json')
    baseline = read('examples/refund-ledger/spec.json')
    observations = read('examples/refund-ledger/observations.json')
    # The vector corpus deliberately contains an invalid floating-point revision.
    vectors = read('fixtures/conformance.json', fixture_values=True)['vectors']
    validator = make_validator(spec_schema, check_formats=True)
    nodes = {n['id']: n for n in baseline['nodes']}
    envs = {e['id']: e for e in baseline['environments']}
    checks = []
    stats = {}

    def check(cid, action):
        # Reporting boundary: exceptions are recorded as errors, never suppressed as success.
        try:
            message = action()
            status = 'pass'
        except (ValueError, AssertionError) as exc:
            status, message = 'fail', str(exc)
        except Exception as exc:
            status, message = 'error', f'{type(exc).__name__}: {exc}'
        checks.append(dict(id=cid, gate='PKG', status=status, required=True,
                           subject_id=None, pointer='', message=message or cid,
                           evidence=[], limitations=[]))

    def schemas():
        Draft202012Validator.check_schema(spec_schema)
        Draft202012Validator.check_schema(report_schema)
        for relative in ['schemas/execution.schema.json', 'schemas/croa-readiness.schema.json', 'schemas/approvals.schema.json', 'schemas/graph.schema.json']:
            Draft202012Validator.check_schema(read(relative))
        validator.validate(baseline)
        return 'Six schema documents valid under Draft 2020-12; example shape valid.'
    check('PKG.SCHEMAS', schemas)

    def references():
        require(not reference_errors(baseline), repr(reference_errors(baseline)))
        return f"Selected reference checks passed: {len(nodes)} nodes, {len(baseline['edges'])} edges. No completeness claim."
    check('PKG.REFERENCES', references)

    def receipt_check():
        count = validate_receipt(ROOT, read('review/regression-run.json'))
        stats['regression_tests_recorded'] = count
        return f'{count} test IDs in a current, successful local receipt; inputs/toolchain/output match. Producer remains untrusted.'
    check('PKG.REGRESSION_RECEIPT', receipt_check)

    def environments():
        for env in envs.values():
            check_environment(env['schema'])
        for node in nodes.values():
            if node['kind'] == 'Scenario':
                make_validator(envs[node['data']['environment_id']]['schema']).validate(node['data']['given'])
        return 'Restricted environment shapes and all scenario observations valid.'
    check('PKG.ENVIRONMENTS', environments)

    def observation_checks():
        scenarios, count = check_observation_corpus(baseline, observations)
        stats['observations'] = scenarios
        stats['boolean_expectations'] = count
        return f'{count} reference expectations checked across all {scenarios} synthetic observations. Fixtures, not application runs.'
    check('PKG.OBSERVATIONS', observation_checks)

    def mutation_checks():
        executed, pending = check_vector_corpus(baseline, vectors, validator)
        stats['mutations_executed'], stats['product_obligations_pending'] = executed, pending
        return f'{executed} mutations verified with expected diagnostics; {pending} future product obligations NOT executed.'
    check('PKG.NEGATIVE_FIXTURES', mutation_checks)

    croa_result = None
    def extensions():
        nonlocal croa_result
        execution = read('examples/refund-ledger/execution.json')
        make_validator(read('schemas/execution.schema.json')).validate(execution)
        record = read('examples/refund-ledger/croa-readiness.json')
        make_validator(read('schemas/croa-readiness.schema.json')).validate(record)
        croa_result = assess_inputs(baseline, record, digest(canonical(baseline)))
        require(croa_result['input_status'] == 'incomplete' and len(croa_result['missing_scores']) == 37,
                'The illustrative CROA fixture must remain explicitly unassessed')
        require(all(row['state'] == 'unknown' for row in croa_result['findings']), 'Unknown inputs must not become scored facts')
        stats['croa_items'] = 37
        stats['croa_red_flag_rules'] = 13
        return 'Execution declaration and CROA input fixture valid; 37 unassessed items, 13 unknown findings. No execution authority or CROA conformance.'
    check('PKG.OPTIONAL_EXTENSIONS', extensions)

    def release():
        import release_diff
        previous = read('examples/refund-ledger/releases/1.0.0.json')
        validator.validate(previous)
        require(not reference_errors(previous), repr(reference_errors(previous)))
        comparison = release_diff.compare(previous, baseline)
        require(comparison['status'] == 'pass', repr(comparison['errors']))
        stats['release_changes'] = len(comparison['changes'])
        stats['release_step'] = comparison['required_step']
        stats['release_risk_score'] = comparison['risk']['score']
        return (f"Reference G14 comparison {comparison['baseline']['version']} -> {comparison['candidate']['version']}: "
                f"{len(comparison['changes'])} changes, required step {comparison['required_step']}, "
                f"change risk score {comparison['risk']['score']} points. Classification is mechanical, not a compatibility proof.")
    check('PKG.RELEASE', release)

    def approval_check():
        import approvals
        previous = read('examples/refund-ledger/releases/1.0.0.json')
        identity = read('examples/identity-adapter/spec.json')
        ledger_approvals = read('examples/refund-ledger/approvals.json')
        cases = [('ledger 1.0.0', previous, read('examples/refund-ledger/releases/1.0.0.approvals.json'), None),
                 ('ledger 1.1.0', baseline, ledger_approvals, previous),
                 ('identity 1.0.0', identity, read('examples/identity-adapter/approvals.json'), None)]
        signatures = 0
        for label, spec, document, governing in cases:
            validator.validate(spec)
            report = approvals.verify(spec, document, governing)
            require(report['status'] == 'pass', f"{label}: {report['errors']!r}")
            signatures += sum(entry['valid'] for entry in report['approvals'])
        altered = copy.deepcopy(baseline)
        altered['project']['name'] += ' (altered)'
        require(approvals.verify(altered, ledger_approvals, previous)['status'] == 'fail', 'Approvals accepted for altered content')
        require(approvals.verify(baseline, ledger_approvals, None)['status'] == 'unknown', 'Approvals decided without the governing release')
        stats['approval_signatures_verified'] = signatures
        return (f'{signatures} approval signatures on {len(cases)} releases verify against the keys the governing release declares, '
                'with the approvers its policy requires per band (reference G12). The keys are fictional and derived from '
                'public labels; no authenticator hardware and no identity binding was involved.')
    check('PKG.APPROVALS', approval_check)

    def store_check():
        import release_store
        report = release_store.verify(release_store.load([str(ROOT / 'examples')]))
        require(report['status'] == 'pass', repr(report['errors'] or 'incomplete store'))
        resolved = sum(i['state'] == 'resolved' for r in report['releases'] for i in r['imports'])
        stats.update(store_releases=len(report['releases']), store_imports_resolved=resolved)
        return (f"{len(report['releases'])} releases of {len(report['projects'])} projects verify as one store from their files alone: "
                f'chain links, approvals and {resolved} pinned import. No index, log or clock is consulted.')
    check('PKG.RELEASE_STORE', store_check)

    def service_contract():
        import graph_index, queries
        document, listed = read('api/openapi.json'), read('api/mcp-tools.json')['tools']
        require(document['openapi'].startswith('3.1'), 'The service contract is an OpenAPI 3.1 document')
        components = document['components']['schemas']
        for schema in components.values():
            Draft202012Validator.check_schema(schema)
        operations = {operation['operationId']: operation for path in document['paths'].values() for operation in path.values()}
        require(len(operations) == sum(len(path) for path in document['paths'].values()), 'Operation IDs are unique')
        for tool in listed:
            operation = operations.get(tool['operation_id'], {})
            require(operation.get('x-mcp-tool') == tool['name'] and tool['output'] in components
                    and set(tool['modes']) == set(operation['x-axiom-modes']), f"Tool {tool['name']} differs from its operation")
            Draft202012Validator.check_schema(tool['input_schema'])
        require(sorted(o['x-mcp-tool'] for o in operations.values() if 'x-mcp-tool' in o) == sorted(t['name'] for t in listed),
                'Every operation offered as a tool is listed, and no other')
        graph_schema = read('schemas/graph.schema.json')
        Draft202012Validator.check_schema(graph_schema)
        annotations = graph_index.scan(ROOT, ['examples/refund-ledger'])
        require(not graph_index.check(baseline, annotations), 'An annotation of the example names an unknown or retired object')
        index = graph_index.build(baseline, annotations)
        make_validator(graph_schema).validate(index)
        require(graph_index.dumps(index) == (ROOT / 'examples/refund-ledger/axiom-graph.json').read_text(),
                'The committed graph index is not the one the example yields; rebuild it')
        snapshot = queries.Snapshot(baseline, annotations, ROOT)
        # The worked example is copied by readers: it carries no gap that its own query reports.
        for phase in ('design', 'implementation'):
            missing = [f"{gap['code']} {gap['id']}" for gap in queries.gaps(snapshot, phase)['items']]
            require(not missing, f"The worked example has {phase} gaps: {', '.join(missing)}")
        validators = {name: queries.contract_validator(name) for name in ('NodeView', 'ContextPage', 'TracePage', 'GapsPage', 'GraphIndex')}
        validators['GraphIndex'].validate(index)
        answers = 0
        for node in baseline['nodes']:
            if node['kind'] != 'Requirement':
                continue
            for detail in ('brief', 'full'):
                validators['NodeView'].validate(queries.lookup(snapshot, node['id'], detail))
                answers += 1
            for scope in ('direct', 'change'):
                cursor = None
                while True:
                    page = queries.context(snapshot, [node['id']], scope, cursor=cursor)
                    validators['ContextPage'].validate(page)
                    require(len(canonical(page)) <= queries.MAX_BYTES, 'A context page exceeds its budget')
                    answers += 1
                    cursor = page['next_cursor']
                    if cursor is None:
                        require(page['complete'], 'A context did not complete')
                        break
            validators['TracePage'].validate(queries.trace(snapshot, object_id=node['id']))
            answers += 1
        for phase in ('design', 'implementation'):
            validators['GapsPage'].validate(queries.gaps(snapshot, phase))
            answers += 1
        stats.update(service_operations=len(operations), service_tools=len(listed), service_answers_validated=answers,
                     example_annotations=sum(len(a['ids']) for a in annotations))
        return (f'{len(operations)} operations and {len(listed)} MCP tools agree; {answers} reference answers on the example validate '
                f"against the contract and stay within budget; the committed graph index is current with "
                f"{stats['example_annotations']} annotated IDs. Reference queries, not a qualified service.")
    check('PKG.SERVICE_CONTRACT', service_contract)

    def example_tests():
        executed = validate_example_receipt(ROOT, read(EXAMPLE_RECEIPT))
        resolved, cases = check_example_evidence(baseline, executed)
        stats.update(example_tests_executed=len(executed), example_bindings_resolved=resolved, example_test_cases_covered=cases)
        return (f'{len(executed)} example application tests executed on current inputs cover all {cases} active TestCases; '
                f'{resolved} required bindings resolve. Local SQLite reference implementation, untrusted producer.')
    check('PKG.EXAMPLE_TESTS', example_tests)

    def self_checks():
        count = 0
        def rejected(action, error=ValueError):
            nonlocal count
            try:
                action()
            except error:
                count += 1
            else:
                raise ValueError('Expected rejection not observed')
        for raw in (b'{"x":1,"x":2}', b'{"x":1.0}', b'{"x":NaN}', b'{"x":9007199254740992}', b'{"x":"\\ud800"}'):
            rejected(lambda raw=raw: strict_json(raw))
        lit = lambda x: dict(kind='literal', value=x)
        app = lambda op, *args: dict(kind='apply', operator=op, arguments=list(args))
        rejected(lambda: ReferenceEvaluator().evaluate(app('add', lit(True), lit(1)), {}))
        rejected(lambda: ReferenceEvaluator().evaluate(app('eq', lit(True), lit(1)), {}))
        rejected(lambda: ReferenceEvaluator().evaluate(app('add', lit(SAFE), lit(1)), {}))
        rejected(lambda: ReferenceEvaluator(max_steps=1).evaluate(app('and', lit(True), lit(True)), {}), BudgetExceeded)
        rejected(lambda: ReferenceEvaluator().evaluate(dict(kind='path', root='env', pointer='/absent'), {}), MissingObservation)
        rejected(lambda: ReferenceEvaluator().evaluate(app('or', lit(True), app('add', lit(False), lit(2))), {}))
        rejected(lambda: ReferenceEvaluator().evaluate(app('and', *[lit(True) for _ in range(2000)]), {}))
        deep = lit(True)
        for _ in range(26):
            deep = app('not', deep)
        rejected(lambda: ReferenceEvaluator().evaluate(deep, {}))
        aggregate = nodes['CON-001']['data']['expression']['arguments'][0]
        env = copy.deepcopy(observations['cases'][0]['environment'])
        item = copy.deepcopy(env['state']['refunds'][0])
        env['state']['refunds'] = [item, copy.deepcopy(item)]
        require(ReferenceEvaluator().evaluate(aggregate, env) == 2 * item['amount_minor'], 'Duplicate amounts lost')
        count += 1
        empty = dict(kind='path', root='env', pointer='/items')
        for operator, expected in [('all', True), ('exists', False)]:
            e = dict(kind='quantifier', operator=operator, bind='x', collection=empty, predicate=lit(True))
            require(ReferenceEvaluator().evaluate(e, {'items': []}) is expected, 'Empty collection semantics')
            count += 1
        rejected(lambda: ReferenceEvaluator().evaluate(
            dict(kind='quantifier', operator='all', bind='x', collection=lit([]), predicate=lit(True)), {}))
        stats['qa_self_checks'] = count
        return f'{count} targeted QA parser/evaluator self-checks passed; no full static typing qualification.'
    check('PKG.QA_SELF_CHECKS', self_checks)

    def editorial():
        stats['normative_rules'] = rule_count
        links, examples = 0, 0
        for path in package_files():
            if path.suffix != '.md':
                continue
            if path == ROOT / 'VALIDATION.md':
                continue  # Generated output checked separately from input documents.
            content = path.read_text()
            require(sum(line.startswith('```') for line in content.splitlines()) % 2 == 0, f'Unclosed fence {path}')
            for block in re.findall(r'```json\s*\n(.*?)\n```', content, re.S):
                strict_json(block.encode())
                examples += 1
            for dest in re.findall(r'\[[^\]]+\]\(([^)]+)\)', content):
                if dest.startswith(('https://', 'http://', 'mailto:', '#')):
                    continue
                check_local_link(path, dest)
                links += 1
        research = (ROOT / 'docs/01_FOUNDATIONS.md').read_text()
        cited = set(re.findall(r'\[R-(\d{2})\]', research))
        registered = set(re.findall(r'^\| R-(\d{2}) \|', research, re.M))
        require(cited.issubset(registered) and len(registered) == 26, 'Research reference registry')
        stats.update(local_links=links, json_blocks=examples)
        return f"{links} local link targets, {examples} JSON blocks and {stats['normative_rules']} unique normative rule headings checked. External URLs not revalidated by this script."
    check('PKG.EDITORIAL', editorial)

    manifest = require_unchanged_inputs(initial_inputs)
    toolchain = runtime_toolchain(ROOT)
    toolchain['jsonschema'] = toolchain['dependencies']['jsonschema']
    configuration = dict(format='axiomspec-package-config/0.1', profile='AX-CORE-0.3',
                         bounds=BOUNDS, json_depth_limit=128, corpus_version='0.3',
                         observation_coverage='all_canonical_scenarios_and_bcir_constraints',
                         application_test_execution='worked_example_only', external_schema_retrieval=False,
                         regression_receipt='required_matching_inputs_toolchain_and_output',
                         input_change_policy='reject_detected_changes')
    config_text = json.dumps(configuration, ensure_ascii=False, indent=2) + '\n'
    limitations = [
        'Artifact QA only. The full product-phase engine, static type/unit compiler, an access-controlled query engine and general test adapters are not implemented.',
        f"{stats.get('product_obligations_pending', 30)} future product obligations are descriptions, not executed tests.",
        'The worked example runs its own tests on a local SQLite reference implementation. That is not a production store, and no other application was tested.',
        'Release comparison classifies changes mechanically by ID; API compatibility and data migration are not examined.',
        'Approval signatures are checked against declared keys. Nothing binds a key to a person, and the example keys are fictional.',
        'Local untrusted runner; no runtime isolation or production approval.',
        'Reference evaluation is not proof of business completeness, formal equivalence or all executions.'
    ]
    checks.sort(key=lambda c: c['id'])
    status = 'error' if any(c['status'] == 'error' for c in checks) else ('fail' if any(c['status'] != 'pass' for c in checks) else 'pass')
    report = dict(format='axiomspec-report/0.4', scope='package', status=status,
                  profile='AX-CORE-0.3', requested_phase='package',
                  available_capabilities=['strict_json', 'shape_validation', 'local_schema_resolution', 'selected_reference_checks', 'reference_fixture_evaluation', 'editorial_checks', 'optional_declaration_checks', 'croa_guide_red_flag_calculation', 'local_receipt_consistency', 'input_manifest_change_detection', 'reference_release_comparison', 'reference_approval_verification', 'reference_graph_index', 'reference_bounded_queries', 'reference_release_store', 'specification_parts', 'format_migration_0_1', 'format_migration_0_2', 'example_python_binding_resolution', 'example_application_tests', 'specification_file_checker', 'markdown_reading_view'],
                  unsupported_capabilities=['static_type_unit_compiler', 'access_controlled_queries', 'code_call_analysis', 'general_binding_resolution', 'product_application_tests', 'identity_binding_of_approval_keys', 'authenticator_attestation', 'croa_deployment_assessment', 'croa_weighted_scorecard'],
                  configuration=dict(path='validation/package-config.json', sha256=digest(config_text.encode('utf-8'))),
                  subject=dict(spec_sha256=digest(canonical(baseline)), source_tree_sha256=digest(canonical(manifest)),
                               policy_sha256=None, toolchain_sha256=digest(canonical(toolchain)), observations_sha256=digest(canonical(observations))),
                  runner=dict(name='qa/check_package.py', version=EDITION, trust='untrusted_local'),
                  checks=checks, bounds=BOUNDS,
                  metadata=dict(evaluated_at=datetime.now(timezone.utc).isoformat(), attempt='local-package-qa'),
                  limitations=limitations)
    make_validator(report_schema, check_formats=True).validate(report)
    output = ROOT / 'validation'
    output.mkdir(exist_ok=True)
    write_atomic(output / 'package-config.json', config_text)
    write_atomic(output / 'croa-input-review.json', json.dumps(croa_result if croa_result is not None else croa_input_error(), ensure_ascii=False, indent=2) + '\n')
    for name, value in [('package-manifest.json', manifest), ('package-statistics.json', dict(stats, toolchain=toolchain)), ('package-report.json', report)]:
        write_atomic(output / name, json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    lines = [f'# Package validation: {status}', '', f"Run: {report['metadata']['evaluated_at']}.", '',
             '**Scope: design package. No product or example-application acceptance is asserted.**', '',
             f"Python {toolchain['python']}; jsonschema {toolchain['jsonschema']}; untrusted local runner.", '',
             '## Results', '']
    lines.extend(f"- `{c['id']}` : **{c['status']}** — {c['message']}" for c in checks)
    lines += ['', '## Limits', ''] + [f'- {l}' for l in limitations]
    lines += ['', '## Reproduce', '', 'Run `python3 qa/run_checks.py` from this directory with [requirements-qa.txt](qa/requirements-qa.txt). This replays tests before checking their receipt and the package.', '',
              '[Report](validation/package-report.json) · [Input manifest](validation/package-manifest.json) · [Statistics](validation/package-statistics.json).', '',
              'The manifest records exact input digests. Validation outputs are excluded to avoid circularity. A filename or commit alone is not an attestation.', '']
    write_atomic(ROOT / 'VALIDATION.md', '\n'.join(lines))
    print(json.dumps(dict(status=status, scope='package', **stats), ensure_ascii=False))
    for c in checks:
        if c['status'] != 'pass':
            print(c['id'] + ': ' + c['message'], file=sys.stderr)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    try:
        exit_code = main()
    except Exception as exc:
        # Final CLI boundary: never leave an old green report as the current result.
        message = f'{type(exc).__name__}: package QA could not complete; inspect the local input.'
        report = dict(format='axiomspec-report/0.4', scope='package', status='error',
                      profile='AX-CORE-0.3', requested_phase='package',
                      available_capabilities=[], unsupported_capabilities=['package_qa_incomplete'], configuration=None,
                      subject={name: None for name in ['spec_sha256', 'source_tree_sha256', 'policy_sha256', 'toolchain_sha256', 'observations_sha256']},
                      runner=dict(name='qa/check_package.py', version=EDITION, trust='untrusted_local'),
                      checks=[dict(id='PKG.INPUT_OR_PIPELINE_ERROR', gate='PKG', status='error', required=True,
                                   subject_id=None, pointer='', message=message, evidence=[], limitations=[])],
                      bounds=BOUNDS, metadata=dict(evaluated_at=datetime.now(timezone.utc).isoformat(), attempt='local-package-qa'),
                      limitations=['Incomplete QA. This emergency report may not have been validated against a damaged report schema.'])
        failures = [
            (ROOT / 'validation/package-report.json', json.dumps(report, indent=2) + '\n'),
            (ROOT / 'validation/croa-input-review.json', json.dumps(croa_input_error(), indent=2) + '\n'),
            (ROOT / 'VALIDATION.md', '# Package validation: error\n\n' + message + '\n\n[Current report](validation/package-report.json). Older manifests and statistics do not describe this attempt.\n')]
        for path, body in failures:
            try:
                write_atomic(path, body)
            except (OSError, ValueError):
                print(f'Cannot publish current diagnostic at {path.relative_to(ROOT)}; do not reuse an older result.', file=sys.stderr)
        print(message, file=sys.stderr)
        exit_code = 1
    sys.exit(exit_code)
