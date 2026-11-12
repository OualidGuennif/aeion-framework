#!/usr/bin/env python3
"""Reference queries over one release: the operations of the service interface (AX-V-003 to AX-V-008).

Each function reads an immutable snapshot and returns a bounded, deterministic answer. The HTTP service and
the MCP tools are transports over these functions and add no behavior of their own.

    lookup    one object, its statement and its links                       (AX-K-003)
    context   what binds the given objects (scope direct), or everything a change
              to them must take into view (scope change: AX-K-007, AX-K-010)
    trace     the requirements behind a file or symbol, or the code behind a requirement
    gaps      what is missing before a phase                                (AX-K-005)
    propose   a candidate release from a baseline and a short list of edits

Selection follows declared links and annotations only. Nothing here is learned, ranked or approximate.
"""
import base64
import copy
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from check_package import canonical, digest, make_validator, reference_errors, resolve_symbol
import graph_index
import release_diff

ROOT = Path(__file__).resolve().parents[1]
MAX_ITEMS, MAX_BYTES, MIN_BYTES = 100, 32768, 4096
KIND_ORDER = ['Requirement', 'Goal', 'Term', 'Constraint', 'StateModel', 'Decision', 'Assumption', 'Risk', 'Control',
              'Scenario', 'TestCase', 'Component', 'Environment', 'Flag', 'Import', 'Binding', 'Actor', 'Source',
              'ContextAsset', 'ApprovalKey']
EDIT_SECTIONS = ('nodes', 'edges', 'bindings', 'environments', 'flags', 'actors', 'sources', 'context_assets', 'imports')
REMOVABLE = ('edges', 'bindings', 'flags', 'context_assets', 'imports', 'environments')
SETTABLE = ('exports', 'approval', 'compatibility')


@lru_cache(maxsize=1)
def spec_validator():
    return make_validator(json.loads((ROOT / 'schemas/spec.schema.json').read_text()))


def contract_validator(name):
    """A validator for one response schema of the service contract (api/openapi.json)."""
    document = json.loads((ROOT / 'api/openapi.json').read_text())
    registry = Registry().with_resource('urn:axiomspec:openapi', Resource(contents=document, specification=DRAFT202012))
    return Draft202012Validator({'$ref': f'urn:axiomspec:openapi#/components/schemas/{name}'}, registry=registry)


class QueryError(ValueError):
    """A request that cannot be answered. `status` is the HTTP status the service reports."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def statement(node):
    """AX-M-006: the sentence a requirement's structured fields render to."""
    data = node['data']
    while_, when = ' and '.join(data['conditions']), data['trigger']
    opening = dict(ubiquitous='', event=f'When {when}, ', state=f'While {while_}, ',
                   unwanted=f'If {when}, then ', optional=f"Where {data['feature']}, ",
                   composite=f'While {while_}, when {when}, ')[data['pattern']]
    sentence = f"{opening}the {data['subject']} shall {data['response']}."
    return sentence[0].upper() + sentence[1:]


class Snapshot:
    """One release with the annotations of one state of its code, indexed once. Every answer names the release digest.

    `state` also covers the annotations. A cursor is bound to it, so a page is never continued across a rescan
    of the code.
    """

    def __init__(self, spec, annotations=(), repository=None):
        self.spec, self.digest = spec, digest(canonical(spec))
        self.state = digest(canonical([self.digest, list(annotations)]))
        self.index = release_diff.Index(spec)
        self.nodes = self.index.nodes
        self.annotations = list(annotations)
        self.repository = Path(repository) if repository else None
        self.graph = graph_index.build(spec, self.annotations)
        self.objects = {}  # every identified object that is not a node: id -> (kind, content)
        for section, kind in (('environments', 'Environment'), ('flags', 'Flag'), ('imports', 'Import'),
                              ('bindings', 'Binding'), ('actors', 'Actor'), ('sources', 'Source'),
                              ('context_assets', 'ContextAsset')):
            for item in spec[section]:
                self.objects[item['id']] = (kind, item)
        for key in spec['approval']['keys']:
            self.objects[key['id']] = ('ApprovalKey', key)
        self.links = {}
        for edge in spec['edges']:
            self.links.setdefault(edge['from'], []).append((edge['relation'], 'out', edge['to']))
            self.links.setdefault(edge['to'], []).append((edge['relation'], 'in', edge['from']))
        self.traces = {}
        for trace in self.graph['traces']:
            for target in {trace['node_id'], *trace['requirement_ids']}:
                self.traces.setdefault(target, []).append(trace)

    def kind(self, object_id):
        return self.nodes[object_id]['kind'] if object_id in self.nodes else self.objects[object_id][0]

    def content(self, object_id):
        return self.nodes[object_id] if object_id in self.nodes else self.objects[object_id][1]

    def holds(self, object_id):
        return object_id in self.nodes or object_id in self.objects

    def summary(self, requirement_id):
        node = self.nodes[requirement_id]
        return dict(id=node['id'], title=node['title'], status=node['status'], priority=node['data']['priority'],
                    risk=node['data']['risk'], weight_minor=node['data']['weight_minor'])


def query_digest(name, parameters):
    return digest(canonical(dict(query=name, parameters=parameters)))


def page(snapshot, name, parameters, items, budget_bytes=MAX_BYTES, cursor=None, analysis_limits=()):
    """AX-K-006: the bounded response envelope. An item is never cut; one that cannot fit is named in `omissions`."""
    if type(budget_bytes) is not int or not MIN_BYTES <= budget_bytes <= MAX_BYTES:
        raise QueryError('INVALID_PARAMETER', f'budget_bytes is an integer from {MIN_BYTES} to {MAX_BYTES}')
    identity = query_digest(name, parameters)
    # A context reads the release alone, so its pages survive a rescan of the code; the other queries read the code too.
    bound_to = snapshot.digest if name == 'context' else snapshot.state
    position = 0
    if cursor is not None:
        try:
            padded = cursor + '=' * (-len(cursor) % 4)
            bound = json.loads(base64.urlsafe_b64decode(padded.encode('ascii')))
            position = bound['position']
            valid = (bound['snapshot'], bound['query']) == (bound_to, identity) and type(position) is int
        except (ValueError, KeyError, TypeError):
            valid = False
        if not valid or not 0 < position <= len(items):
            raise QueryError('INVALID_CURSOR', 'The cursor does not belong to this snapshot and query')
    envelope = dict(snapshot_id=snapshot.digest, query_digest=identity, items=[], returned_count=0,
                    total_visible_count=len(items), complete=False, next_cursor=None, omissions=[],
                    analysis_limits=list(analysis_limits))
    # Reserve room for the longest cursor and counters, so the finished envelope stays within the budget.
    reserve = len(canonical(dict(envelope, next_cursor='x' * 240, returned_count=MAX_ITEMS, total_visible_count=10 ** 9)))
    used = reserve
    while position < len(items) and len(envelope['items']) < MAX_ITEMS:
        item = items[position]
        size = len(canonical(item)) + 1
        if size > budget_bytes - reserve:
            envelope['omissions'].append(dict(id=item.get('id'), reason='exceeds_budget', bytes=size))
            used += 160
        elif used + size > budget_bytes:
            break
        else:
            envelope['items'].append(item)
            used += size
        position += 1
    envelope['returned_count'] = len(envelope['items'])
    if position < len(items):
        bound = canonical(dict(snapshot=bound_to, query=identity, position=position))
        envelope['next_cursor'] = base64.urlsafe_b64encode(bound).rstrip(b'=').decode('ascii')
    # Complete means the whole answer was deliverable at this budget, not only this page.
    oversized = any(len(canonical(item)) + 1 > budget_bytes - reserve for item in items)
    envelope['complete'] = position == len(items) and not oversized
    return envelope


def lookup(snapshot, object_id, detail='brief'):
    """AX-K-003: one object with its links and where it is implemented. An unknown ID is not_found, never a guess."""
    if detail not in ('brief', 'full'):
        raise QueryError('INVALID_PARAMETER', 'detail is brief or full')
    if not snapshot.holds(object_id):
        raise QueryError('NOT_FOUND', f'{object_id} is not in this snapshot', 404)
    kind, content = snapshot.kind(object_id), snapshot.content(object_id)
    title = lambda other: snapshot.content(other).get('title') or snapshot.content(other).get('name')
    links = [dict(relation=relation, direction=direction, id=other, kind=snapshot.kind(other), title=title(other))
             for relation, direction, other in snapshot.links.get(object_id, []) if snapshot.holds(other)]
    links.sort(key=lambda link: (link['relation'], link['direction'], link['id']))
    # Two links to one place (a constraint and its requirement on the same line) are one place to read.
    places = list(dict.fromkeys((t['path'], t['line'], t['symbol'], t['kind'], t['origin'])
                                for t in snapshot.traces.get(object_id, [])))
    view = dict(snapshot_id=snapshot.digest, query_digest=query_digest('lookup', dict(id=object_id, detail=detail)),
                id=object_id, kind=kind, status=content.get('status'), title=content.get('title') or content.get('name'),
                statement=None, requirement=None, links=links[:MAX_ITEMS], links_total=len(links),
                traces=[dict(zip(('path', 'line', 'symbol', 'kind', 'origin'), place)) for place in places[:MAX_ITEMS]],
                content=None, complete=len(links) <= MAX_ITEMS and len(places) <= MAX_ITEMS)
    if kind == 'Requirement':
        view['statement'] = statement(content)
        view['requirement'] = dict(snapshot.summary(object_id), flag_id=content['data']['flag_id'],
                                   verification_mode=content['data']['verification_mode'])
    if detail == 'full':
        view['content'] = content
    return view


def closure(snapshot, seeds):
    """AX-K-010: the conservative closure of a change. Returns (selected IDs, seed requirements, unmapped seeds)."""
    spec, index, nodes = snapshot.spec, snapshot.index, snapshot.nodes
    active = lambda node_id: nodes[node_id]['status'] == 'active'
    requirements, unmapped = set(), []
    for seed in seeds:  # 1. seeds
        reached = index.requirements(seed)
        if not reached:
            unmapped.append(seed)
        requirements |= reached or set()
    seeded = set(requirements)
    rules = {n['id'] for n in spec['nodes'] if n['kind'] == 'Constraint' and active(n['id'])
             and n['data']['scope'] == 'project' and n['data']['classification']['strength'] == 'hard'}
    for rule in rules:  # 2. requirements under hard project rules, then dependencies to a fixed point
        requirements |= index.out[(rule, 'formalizes')]
    pending = list(requirements)
    while pending:
        current = pending.pop()
        for other in index.out[(current, 'depends_on')] | index.inc[(current, 'depends_on')]:
            if other not in requirements:
                requirements.add(other)
                pending.append(other)
    requirements = {r for r in requirements if r in nodes and (active(r) or r in seeded)}
    selected = set(requirements) | rules | {seed for seed in seeds if seed in nodes}
    for edge in spec['edges']:  # 3. endpoints incident to these requirements
        if edge['from'] in requirements and edge['to'] in nodes:
            selected.add(edge['to'])
        if edge['to'] in requirements and edge['from'] in nodes:
            selected.add(edge['from'])
    changed = True
    while changed:  # 4 and 5. technical dependencies, to a fixed point; never back to unrelated requirements
        before = len(selected)
        for node_id in list(selected):
            node, kind = nodes[node_id], nodes[node_id]['kind']
            if kind == 'Constraint':
                selected |= index.out[(node_id, 'uses_term')] | index.out[(node_id, 'assumes')] | index.inc[(node_id, 'governs')]
            elif kind == 'TestCase':
                selected |= set(node['data']['witness_scenario_ids']) | index.out[(node_id, 'checks')]
            elif kind == 'Scenario':
                selected |= {e['constraint_id'] for e in node['data']['constraint_expectations']}
            elif kind == 'StateModel':
                selected |= {t['guard_id'] for t in node['data']['transitions'] if t['guard_id'] is not None}
        selected = {s for s in selected if s in nodes}
        changed = len(selected) != before
    selected = {s for s in selected if active(s) or s in seeds or s in seeded}
    support = set()  # 6. what the selected objects refer to
    for node_id in selected:
        node = nodes[node_id]
        support |= {node['owner'], node['created_by'], *node['source_ids']}
        if node['data'].get('environment_id'):
            support.add(node['data']['environment_id'])
        if node['kind'] == 'Requirement' and node['data']['flag_id']:
            support.add(node['data']['flag_id'])
    support |= {b['id'] for b in spec['bindings'] if b['node_id'] in selected}
    for asset in spec['context_assets']:
        if set(asset['supports']) & selected:
            support |= {asset['id'], *asset['source_ids']}
    support |= {item['id'] for item in spec['imports'] if any(set(use['local_ids']) & selected for use in item['uses'])}
    support |= {seed for seed in seeds if seed in snapshot.objects}
    return selected | {s for s in support if snapshot.holds(s)}, seeded, unmapped


def direct(snapshot, seeds):
    """AX-V-005: what the seed requirements mean and what binds them, without the examples and tests of a change.

    Per requirement: its goals, terms, assumptions, controls, dependencies, risks, models and governing decisions;
    the constraints that formalize it; every hard project rule; and, for each constraint, its terms, assumptions,
    decisions and environment. Scenarios, tests and components are named by the requirement's links, not included.
    """
    spec, index, nodes = snapshot.spec, snapshot.index, snapshot.nodes
    requirements, unmapped = set(), []
    for seed in seeds:
        reached = index.requirements(seed)
        if not reached:
            unmapped.append(seed)
        requirements |= reached or set()
    seeded = set(requirements)
    selected = set(requirements) | {seed for seed in seeds if seed in nodes}
    for requirement in requirements:
        for relation in ('satisfies', 'uses_term', 'assumes', 'realizes', 'depends_on'):
            selected |= index.out[(requirement, relation)]
        for relation in ('formalizes', 'models', 'governs', 'threatens', 'depends_on'):
            selected |= index.inc[(requirement, relation)]
    selected |= {n['id'] for n in spec['nodes'] if n['kind'] == 'Constraint' and n['status'] == 'active'
                 and n['data']['scope'] == 'project' and n['data']['classification']['strength'] == 'hard'}
    changed = True
    while changed:
        before = len(selected)
        for node_id in [s for s in selected if s in nodes]:
            if nodes[node_id]['kind'] == 'Constraint':
                selected |= index.out[(node_id, 'uses_term')] | index.out[(node_id, 'assumes')] | index.inc[(node_id, 'governs')]
            elif nodes[node_id]['kind'] == 'StateModel':
                selected |= {t['guard_id'] for t in nodes[node_id]['data']['transitions'] if t['guard_id'] is not None}
        changed = len(selected) != before
    selected = {s for s in selected if s in nodes and (nodes[s]['status'] == 'active' or s in seeds or s in seeded)}
    support = set()
    for node_id in selected:
        data = nodes[node_id]['data']
        if data.get('environment_id'):
            support.add(data['environment_id'])
        if nodes[node_id]['kind'] == 'Requirement' and data['flag_id']:
            support.add(data['flag_id'])
    support |= {b['id'] for b in spec['bindings'] if b['node_id'] in selected}
    support |= {item['id'] for item in spec['imports'] if any(set(use['local_ids']) & selected for use in item['uses'])}
    support |= {seed for seed in seeds if seed in snapshot.objects}
    return selected | {s for s in support if snapshot.holds(s)}, seeded, unmapped


def context(snapshot, ids, scope='direct', budget_bytes=MAX_BYTES, cursor=None):
    """The context of `ids`, in pages. Nothing a scope requires is dropped to fit a budget.

    scope `direct` answers "what does this requirement demand and what rules bind it" (AX-V-005).
    scope `change` is the mandatory context of a change (AX-K-007): the conservative closure of AX-K-010.
    """
    if scope not in ('direct', 'change'):
        raise QueryError('INVALID_PARAMETER', 'scope is direct or change')
    ids = sorted(set(ids))
    if not ids:
        raise QueryError('INVALID_PARAMETER', 'ids names at least one object')
    missing = [i for i in ids if not snapshot.holds(i)]
    if missing:
        raise QueryError('NOT_FOUND', f"{', '.join(missing)} not in this snapshot", 404)
    selected, seeded, unmapped = (closure if scope == 'change' else direct)(snapshot, ids)
    order = lambda object_id: (KIND_ORDER.index(snapshot.kind(object_id)), object_id)
    items = []
    for object_id in sorted(selected, key=order):
        item = dict(id=object_id, kind=snapshot.kind(object_id),
                    role='seed' if object_id in ids or object_id in seeded else 'required',
                    statement=statement(snapshot.nodes[object_id]) if snapshot.kind(object_id) == 'Requirement' else None,
                    links=sorted([relation, direction, other] for relation, direction, other
                                 in snapshot.links.get(object_id, []) if other in selected),
                    content=snapshot.content(object_id))
        items.append(item)
    limits = ['Selection follows declared links only; an undeclared dependency is not found.']
    if scope == 'direct':
        limits.append('Scope direct is not the mandatory context of a change: scenarios, tests and the requirements '
                      'under project rules are left out. Use scope change before changing behavior.')
    if unmapped:
        limits.append(f"No requirement is declared for: {', '.join(unmapped)}. Impact coverage is not complete.")
    return page(snapshot, 'context', dict(ids=ids, scope=scope), items, budget_bytes, cursor, limits)


def trace(snapshot, path=None, symbol=None, object_id=None, budget_bytes=MAX_BYTES, cursor=None):
    """The requirements behind a file or symbol, or the code and tests behind an object. Declared links only."""
    if (path is None) == (object_id is None) or (symbol is not None and path is None):
        raise QueryError('INVALID_PARAMETER', 'Give either path, with an optional symbol, or id')
    if object_id is not None and not snapshot.holds(object_id):
        raise QueryError('NOT_FOUND', f'{object_id} is not in this snapshot', 404)
    rows = []
    for row in snapshot.graph['traces']:
        if object_id is not None:
            keep = object_id == row['node_id'] or object_id in row['requirement_ids']
        else:
            keep = row['path'] == path and (symbol is None or row['symbol'] is None or row['symbol'] == symbol
                                            or symbol.startswith(row['symbol'] + '.') or row['symbol'].startswith(symbol + '.'))
        if keep:
            rows.append(dict(row, requirements=[snapshot.summary(r) for r in row['requirement_ids'] if r in snapshot.nodes]))
    limits = ['A trace is a declared link or an annotation. It does not show that the code satisfies the requirement.']
    return page(snapshot, 'trace', dict(path=path, symbol=symbol, id=object_id), rows, budget_bytes, cursor, limits)


def gaps(snapshot, phase='design', budget_bytes=MAX_BYTES, cursor=None):
    """AX-K-005: what is missing before a phase, each with its gate and subject. Never a score."""
    if phase not in ('design', 'implementation'):
        raise QueryError('INVALID_PARAMETER', 'phase is design or implementation')
    spec, index, nodes = snapshot.spec, snapshot.index, snapshot.nodes
    found = []

    def gap(gate, code, subject_id, message):
        found.append(dict(id=subject_id, gate=gate, code=code, message=message))

    for code in sorted(set(reference_errors(spec))):
        gap('G02', code, None, 'A reference rule of the canonical model fails.')
    live = lambda ids: [i for i in ids if i in nodes and nodes[i]['status'] == 'active']
    for node in spec['nodes']:
        if node['status'] != 'active':
            continue
        data = node['data']
        if node['kind'] == 'Decision' and data['blocking'] and data['answer'] is None:
            gap('G04', 'OPEN_DECISION', node['id'], 'A blocking decision has no answer.')
        if node['kind'] == 'Assumption' and data['blocking'] and data['state'] != 'validated':
            gap('G04', 'UNVALIDATED_ASSUMPTION', node['id'], 'A blocking assumption is not validated.')
        if node['kind'] == 'Requirement' and data['priority'] == 'must':
            if data['verification_mode'] != 'manual' and not live(index.inc[(node['id'], 'illustrates')]):
                gap('G06', 'MISSING_SCENARIO', node['id'], 'No active scenario illustrates this must requirement.')
            if not live(index.inc[(node['id'], 'verifies')]):
                gap('G07', 'MISSING_TEST', node['id'], 'No active test case verifies this must requirement.')
            if phase == 'implementation' and not any(t['kind'] in ('code', 'enforcement') for t in snapshot.traces.get(node['id'], [])):
                gap('G09', 'UNTRACED_REQUIREMENT', node['id'], 'No binding or annotation places this must requirement in code.')
    if phase == 'implementation':
        for binding in spec['bindings']:
            if binding['expected_resolution'] == 'planned':
                gap('G09', 'PLANNED_BINDING', binding['id'], 'The binding is planned, not required to resolve.')
            elif snapshot.repository is not None and binding['language'] == 'python':
                target = snapshot.repository / binding['path']
                try:
                    inside = target.resolve().is_relative_to(snapshot.repository.resolve())
                    resolved = inside and target.is_file() and resolve_symbol(target, binding['symbol'])
                    reason = f"{binding['path']} does not define {binding['symbol']}."
                except (SyntaxError, ValueError, OSError):
                    # A file being edited may not parse. That is a gap to report, not a failure of the query.
                    resolved, reason = False, f"{binding['path']} cannot be parsed, so {binding['symbol']} is not resolved."
                if not resolved:
                    gap('G09', 'UNRESOLVED_BINDING', binding['id'], reason)
        for problem in graph_index.check(spec, snapshot.annotations):
            gap('G09', problem['code'], problem['subject_id'], problem['message'])
    found.sort(key=lambda g: (g['gate'], g['code'], g['id'] or '', g['message']))
    limits = ['Executed tests, evidence freshness, approvals (G12) and the release comparison (G14) are not examined here.']
    if phase == 'implementation' and snapshot.repository is None:
        limits.append('No repository was supplied: bindings were not resolved against code.')
    return page(snapshot, 'gaps', dict(phase=phase), found, budget_bytes, cursor, limits)


def propose(baseline, version, operations):
    """A candidate release: `baseline` with the edits applied, named as its successor and checked.

    Edits address objects by ID, never by position. A changed node takes the next revision; a node is retired,
    never removed. The result is a function of the inputs, so the same request always yields the same digest.
    This function writes nothing: `held` is false here, and a service sets it when it keeps the candidate.
    """
    if not isinstance(version, str):
        raise QueryError('INVALID_PARAMETER', 'version is a string such as 1.2.0')
    spec = copy.deepcopy(baseline)
    spec['release'] = dict(version=version, compatibility=[],
                           previous=dict(version=baseline['release']['version'], spec_sha256=digest(canonical(baseline))))
    revisions = {node['id']: node for node in baseline['nodes']}
    if not isinstance(operations, list) or not operations:
        raise QueryError('INVALID_PARAMETER', 'operations is a non-empty list')
    for number, operation in enumerate(operations):
        fail = lambda message: QueryError('INVALID_PARAMETER', f'operation {number}: {message}')
        kind = operation.get('op') if isinstance(operation, dict) else None
        if kind == 'put':
            section, item = operation.get('section'), operation.get('item')
            if section not in EDIT_SECTIONS or not isinstance(item, dict) or not isinstance(item.get('id'), str):
                raise fail('put needs a section and an item with an id')
            item = copy.deepcopy(item)
            if section == 'nodes':
                old = revisions.get(item['id'])
                same = old is not None and {k: v for k, v in old.items() if k != 'revision'} == {k: v for k, v in item.items() if k != 'revision'}
                item['revision'] = 1 if old is None else old['revision'] + (0 if same else 1)
            rows = spec[section]
            position = next((i for i, row in enumerate(rows) if row['id'] == item['id']), None)
            if position is None:
                rows.append(item)
            else:
                rows[position] = item
        elif kind == 'retire':
            node = next((n for n in spec['nodes'] if n['id'] == operation.get('id')), None)
            if node is None:
                raise fail('retire names a node of the baseline')
            if node['status'] != 'retired':
                node['status'] = 'retired'
                node['revision'] = revisions.get(node['id'], node)['revision'] + (1 if node['id'] in revisions else 0)
        elif kind == 'remove':
            section = operation.get('section')
            if section not in REMOVABLE:
                raise fail(f"remove applies to {', '.join(REMOVABLE)}; a node is retired")
            kept = [row for row in spec[section] if row['id'] != operation.get('id')]
            if len(kept) == len(spec[section]):
                raise fail('remove names an object of that section')
            spec[section] = kept
        elif kind == 'set':
            field = operation.get('field')
            if field not in SETTABLE or 'value' not in operation:
                raise fail(f"set applies to {', '.join(SETTABLE)}")
            if field == 'compatibility':
                spec['release']['compatibility'] = operation['value']
            else:
                spec[field] = operation['value']
        else:
            raise fail('op is put, retire, remove or set')
    schema_errors = sorted(f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message[:200]}" for e in spec_validator().iter_errors(spec))[:50]
    references = sorted(set(reference_errors(spec))) if not schema_errors else []
    comparison = release_diff.compare(baseline, spec) if not schema_errors else None
    acceptable = not schema_errors and not references and comparison['status'] == 'pass'
    return dict(spec_sha256=digest(canonical(spec)), version=version,
                baseline=dict(version=baseline['release']['version'], spec_sha256=digest(canonical(baseline))),
                status='pass' if acceptable else 'fail', held=False, schema_errors=schema_errors, reference_errors=references,
                comparison=None if comparison is None else {k: comparison[k] for k in
                    ('status', 'declared_step', 'required_step', 'counts', 'errors', 'risk')},
                candidate=spec)
