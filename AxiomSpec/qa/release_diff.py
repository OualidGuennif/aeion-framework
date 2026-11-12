#!/usr/bin/env python3
"""Reference comparison of two releases of one specification: gate G14.

Given the baseline a candidate names in `release.previous`, it reports what changed by ID, whether identity
and revision rules were kept (AX-L-006), how each change is classified (AX-L-007), the version step that
classification requires (AX-L-008) and a change risk score from requirement weights (AX-L-009).

It reads two files and runs nothing. The classification is mechanical and conservative: it cannot tell a
tightened formula from a relaxed one, so either is a breaking candidate until a recorded decision says otherwise.
"""
from collections import defaultdict
import json
from pathlib import Path
import sys

from check_package import (canonical, digest, make_validator, read, reference_errors, strict_json,
                           version_step)

FORMAT = 'axiomspec/0.3'
LEVELS = dict(none=0, patch=1, minor=2, major=3)
FACTOR_PERCENT = dict(major=100, minor=50, patch=10)
DEPENDENT_CAP_PERCENT = 25
ORDER = dict(same=0, widened=1, breaking=2)


def schema_change(old, new):
    """Compare two restricted environment schemas: 'same', 'widened' or 'breaking'.

    Widened means every observation valid before is still valid. Anything else is breaking, including a
    property added to a closed object, because all properties are required.
    """
    if old.get('type') != new.get('type'):
        return 'breaking'

    def bound(key, lower, default=None):
        a, b = old.get(key, default), new.get(key, default)
        if a == b:
            return 'same'
        if a is None or b is None:
            return 'breaking'
        return 'widened' if (b < a if lower else b > a) else 'breaking'

    outcomes = []
    kind = old.get('type')
    if kind == 'object':
        if set(old.get('properties', {})) != set(new.get('properties', {})):
            return 'breaking'
        outcomes += [schema_change(old['properties'][name], new['properties'][name]) for name in old['properties']]
    elif kind == 'array':
        outcomes += [schema_change(old['items'], new['items']), bound('minItems', True, 0), bound('maxItems', False)]
    elif kind == 'integer':
        outcomes += [bound('minimum', True), bound('maximum', False)]
    elif kind == 'string':
        outcomes += [bound('minLength', True, 0), bound('maxLength', False)]
    before, after = old.get('enum'), new.get('enum')
    if before is None:
        if after is not None:
            outcomes.append('breaking')
    elif after is None:
        outcomes.append('widened')
    else:
        # JSON values include objects/arrays; canonical bytes also distinguish true from 1.
        before, after = {canonical(value) for value in before}, {canonical(value) for value in after}
        if before != after:
            outcomes.append('widened' if before <= after else 'breaking')
    return max(outcomes, key=ORDER.get, default='same')


class Index:
    """Declared links of one specification, used to find the requirements a change reaches."""

    def __init__(self, spec):
        self.spec = spec
        self.nodes = {n['id']: n for n in spec['nodes']}
        self.out, self.inc = defaultdict(set), defaultdict(set)
        for edge in spec['edges']:
            self.out[(edge['from'], edge['relation'])].add(edge['to'])
            self.inc[(edge['to'], edge['relation'])].add(edge['from'])
        self.by_id = {}
        for section, kind in (('environments', 'Environment'), ('flags', 'Flag'), ('edges', 'Edge'),
                              ('bindings', 'Binding'), ('context_assets', 'ContextAsset'),
                              ('actors', 'Actor'), ('sources', 'Source'), ('imports', 'Import')):
            for item in spec[section]:
                self.by_id[item['id']] = (kind, item)

    def requirements(self, subject_id):
        """AX-L-009 seeds: the requirements a changed object is declared to concern. None when unmapped."""
        node = self.nodes.get(subject_id)
        if node is not None:
            return self.of_node(node)
        kind, item = self.by_id.get(subject_id, (None, None))
        many = lambda ids: set().union(*[self.requirements(i) or set() for i in ids]) if ids else set()
        if kind == 'Environment':
            return many([n['id'] for n in self.nodes.values() if n['data'].get('environment_id') == subject_id])
        if kind == 'Flag':
            return {n['id'] for n in self.nodes.values() if n['kind'] == 'Requirement' and n['data']['flag_id'] == subject_id}
        if kind == 'Edge':
            return many([i for i in (item['from'], item['to']) if i in self.nodes])
        if kind == 'Binding':
            return many([item['node_id']] if item['node_id'] in self.nodes else [])
        if kind == 'ContextAsset':
            return many([i for i in item['supports'] if i in self.nodes])
        if kind == 'Import':
            return many([i for use in item['uses'] for i in use['local_ids'] if i in self.nodes])
        return None

    def of_node(self, node):
        nid, kind = node['id'], node['kind']
        many = lambda ids: set().union(*[self.of_node(self.nodes[i]) for i in ids if i in self.nodes]) if ids else set()
        if kind == 'Requirement':
            return {nid}
        direct = dict(Constraint='formalizes', Component='implements', TestCase='verifies',
                      Scenario='illustrates', StateModel='models')
        if kind in direct:
            return set(self.out[(nid, direct[kind])])
        if kind == 'Goal':
            return set(self.inc[(nid, 'satisfies')])
        if kind == 'Term':
            return many(self.inc[(nid, 'uses_term')])
        if kind == 'Decision':
            return many(self.out[(nid, 'governs')])
        if kind == 'Assumption':
            return many(self.inc[(nid, 'assumes')])
        if kind == 'Risk':
            return many(self.out[(nid, 'threatens')])
        if kind == 'Control':
            return set(self.inc[(nid, 'realizes')]) | many(self.out[(nid, 'mitigates')])
        return set()


def without(item, *keys):
    return {k: v for k, v in item.items() if k not in keys}


def compare(baseline, candidate):
    """Return the deterministic G14 comparison of two axiomspec/0.3 documents."""
    for document in (baseline, candidate):
        if document.get('format') != FORMAT:
            raise ValueError('Both releases must be axiomspec/0.3; migrate an older baseline first')
    errors, changes = [], {}

    def error(code, subject_id, message):
        errors.append(dict(code=code, subject_id=subject_id, message=message))

    def change(subject_id, kind, what, level, reason):
        record = changes.setdefault(subject_id, dict(subject_id=subject_id, kind=kind, change=what,
                                                     level='patch', reasons=[]))
        if LEVELS[level] > LEVELS[record['level']]:
            record['level'] = level
        record['reasons'].append(reason)

    old_index, new_index = Index(baseline), Index(candidate)
    old_nodes, new_nodes = old_index.nodes, new_index.nodes
    was_active = {i for i, n in old_nodes.items() if n['status'] == 'active'}

    # Release identity (AX-L-006).
    base_digest, cand_digest = digest(canonical(baseline)), digest(canonical(candidate))
    previous = candidate['release']['previous']
    if previous is None or previous != dict(version=baseline['release']['version'], spec_sha256=base_digest):
        error('BASELINE_MISMATCH', None, 'release.previous does not name this baseline by version and digest.')
    if baseline['project']['id'] != candidate['project']['id']:
        error('PROJECT_CHANGED', candidate['project']['id'], 'A release succeeds a baseline of the same project.')

    def activated_level(node):
        """Level of a node that is active now and was absent or not active before."""
        if node['kind'] in {'Scenario', 'TestCase', 'Component'}:
            return 'patch', 'verification or structure added'
        if (node['kind'] == 'Constraint' and node['data']['classification']['strength'] == 'hard'
                and new_index.out[(node['id'], 'formalizes')] & was_active):
            return 'major', 'a hard rule now applies to a requirement the baseline already had'
        return 'minor', 'added to the active model'

    withdrawn = dict(Requirement='major', StateModel='major', Term='minor', Goal='minor', Decision='minor',
                     Assumption='minor', Risk='minor', Control='minor')

    def live_changes(old, new):
        """Field-level classification for a node active in both releases."""
        a, b, kind = old['data'], new['data'], old['kind']
        found = []
        if kind == 'Requirement':
            statement = ('pattern', 'conditions', 'trigger', 'feature', 'subject', 'response')
            if any(a[f] != b[f] for f in statement):
                found.append(('major' if a['priority'] == 'must' else 'minor', 'the rendered statement changed'))
            if a['priority'] != b['priority']:
                if a['priority'] == 'must':
                    found.append(('major', 'no longer a must'))
                else:
                    found.append(('minor' if b['priority'] == 'must' else 'patch', 'priority changed'))
            if a['flag_id'] != b['flag_id']:
                states = {f['id']: f['state'] for f in candidate['flags']}
                before = {f['id']: f['state'] for f in baseline['flags']}.get(a['flag_id'], 'enabled')
                if states.get(b['flag_id'], 'enabled') == 'disabled' and before == 'enabled':
                    found.append(('major', 'now behind a disabled flag'))
                else:
                    found.append(('minor', 'flag changed'))
        elif kind == 'Constraint':
            watched = lambda d: (d['expression'], d['environment_id'], d['predicate_role'], d['representation'],
                                 d['review_protocol'], d['effective_from'], d['effective_until'], d['scope'],
                                 d['classification']['strength'])
            if watched(a) != watched(b):
                hard = a['classification']['strength'] == 'hard'
                found.append(('major' if hard else 'minor', 'the predicate, its environment, window, scope or strength changed'))
        elif kind == 'StateModel':
            states = lambda d: {s['name']: s['terminal'] for s in d['states']}
            moves = lambda d: {t['id']: (t['from'], t['to'], t['event'], t['guard_id']) for t in d['transitions']}
            if (a['environment_id'] != b['environment_id'] or a['initial'] != b['initial']
                    or any(states(b).get(name) != terminal for name, terminal in states(a).items())
                    or any(moves(b).get(tid) != move for tid, move in moves(a).items())):
                found.append(('major', 'a state or transition was removed or changed'))
            elif states(a) != states(b) or moves(a) != moves(b):
                found.append(('minor', 'a state or transition was added'))
        elif kind == 'Term':
            if a['unit'] != b['unit']:
                found.append(('major', 'the unit changed'))
            elif a['definition'] != b['definition']:
                found.append(('minor', 'the definition changed'))
        elif kind == 'Decision':
            if a['answer'] != b['answer']:
                found.append(('minor', 'the answer changed'))
        elif kind in {'Goal', 'Assumption', 'Risk', 'Control'}:
            if a != b:
                found.append(('minor', 'its content changed'))
        return found or [('patch', 'no change of meaning detected by the classifier')]

    for nid, old in sorted(old_nodes.items()):
        new = new_nodes.get(nid)
        if new is None:
            error('REMOVED_ID', nid, 'A node is retired, never deleted: its ID must stay reserved.')
            continue
        if new['kind'] != old['kind']:
            error('KIND_CHANGED', nid, 'An ID keeps its kind; a different object needs a new ID.')
            continue
        if new['revision'] < old['revision']:
            error('REVISION_DECREASED', nid, 'A revision never decreases.')
        if without(old, 'revision') == without(new, 'revision'):
            continue
        if new['revision'] <= old['revision']:
            error('REVISION_NOT_INCREASED', nid, 'Content changed without a higher revision.')
        before, after, kind = old['status'], new['status'], old['kind']
        if before == 'retired':
            if after != 'retired':
                error('RETIRED_REUSED', nid, 'A retired ID is never brought back.')
            change(nid, kind, 'changed', 'patch', 'historical record edited')
        elif before == 'active' and after != 'active':
            hard = kind == 'Constraint' and old['data']['classification']['strength'] == 'hard'
            level = 'major' if hard else withdrawn.get(kind, 'minor' if kind == 'Constraint' else 'patch')
            change(nid, kind, 'retired' if after == 'retired' else 'changed', level, 'withdrawn from the active model')
        elif before != 'active' and after == 'active':
            change(nid, kind, 'changed', *activated_level(new))
        elif before == after == 'active':
            for level, reason in live_changes(old, new):
                change(nid, kind, 'changed', level, reason)
        else:
            change(nid, kind, 'changed', 'patch', 'not active in either release')
    for nid, new in sorted(new_nodes.items()):
        if nid not in old_nodes:
            if new['status'] == 'active':
                change(nid, new['kind'], 'added', *activated_level(new))
            else:
                change(nid, new['kind'], 'added', 'patch', 'added but not active')

    def by_id(document, section):
        return {item['id']: item for item in document[section]}

    old_envs, new_envs = by_id(baseline, 'environments'), by_id(candidate, 'environments')
    for eid in sorted(set(old_envs) | set(new_envs)):
        old, new = old_envs.get(eid), new_envs.get(eid)
        if old is None:
            change(eid, 'Environment', 'added', 'minor', 'environment added')
        elif new is None:
            change(eid, 'Environment', 'removed', 'major', 'environment removed')
        elif old != new:
            shape = schema_change(old['schema'], new['schema'])
            units = lambda env: sorted((u['pointer'], u['term_id']) for u in env['units'])
            if shape == 'breaking':
                change(eid, 'Environment', 'changed', 'major', 'observations valid before may now be rejected')
            elif shape == 'widened':
                change(eid, 'Environment', 'changed', 'minor', 'the schema accepts more than before')
            if units(old) != units(new):
                change(eid, 'Environment', 'changed', 'major', 'unit annotations changed')
            change(eid, 'Environment', 'changed', 'patch', 'environment edited')

    old_flags, new_flags = by_id(baseline, 'flags'), by_id(candidate, 'flags')
    for fid in sorted(set(old_flags) | set(new_flags)):
        old, new = old_flags.get(fid), new_flags.get(fid)
        if old is None:
            change(fid, 'Flag', 'added', 'minor', 'flag added')
        elif new is None:
            change(fid, 'Flag', 'removed', 'patch', 'flag removed; its requirements are classified separately')
        elif old != new:
            if old['state'] == 'enabled' and new['state'] == 'disabled':
                change(fid, 'Flag', 'changed', 'major', 'behavior that was on is now off')
            elif old['state'] != new['state']:
                change(fid, 'Flag', 'changed', 'minor', 'behavior that was off is now on')
            if old['key'] != new['key']:
                change(fid, 'Flag', 'changed', 'major', 'the runtime key was renamed')
            change(fid, 'Flag', 'changed', 'patch', 'flag edited')

    for section, kind in (('edges', 'Edge'), ('bindings', 'Binding'), ('context_assets', 'ContextAsset'),
                          ('actors', 'Actor'), ('sources', 'Source')):
        old_items, new_items = by_id(baseline, section), by_id(candidate, section)
        for item_id in sorted(set(old_items) | set(new_items)):
            if item_id not in old_items:
                change(item_id, kind, 'added', 'patch', 'traceability or metadata added')
            elif item_id not in new_items:
                change(item_id, kind, 'removed', 'patch', 'traceability or metadata removed')
            elif old_items[item_id] != new_items[item_id]:
                change(item_id, kind, 'changed', 'patch', 'traceability or metadata edited')
    if baseline['project'] != candidate['project']:
        mode = baseline['project']['mode'] != candidate['project']['mode']
        change(candidate['project']['id'], 'Project', 'changed', 'minor' if mode else 'patch', 'project record edited')

    # Imports (AX-M-021): the provider's own version number says how far a pin moved.
    old_imports, new_imports = by_id(baseline, 'imports'), by_id(candidate, 'imports')
    for iid in sorted(set(old_imports) | set(new_imports)):
        old, new = old_imports.get(iid), new_imports.get(iid)
        if old is None:
            change(iid, 'Import', 'added', 'minor', 'now depends on another specification')
        elif new is None:
            change(iid, 'Import', 'removed', 'minor', 'no longer depends on that specification')
        elif old != new:
            a, b = (tuple(int(p) for p in item['version'].split('.')) for item in (old, new))
            if old['project_id'] != new['project_id'] or b < a or b[0] > a[0]:
                change(iid, 'Import', 'changed', 'major', 'the pin moved to another provider, backwards or across a major version')
            elif b[:2] > a[:2] or (a == b and old['spec_sha256'] != new['spec_sha256']):
                change(iid, 'Import', 'changed', 'minor', 'the pin moved to a later minor version or to other content')
            change(iid, 'Import', 'changed', 'patch', 'import edited')
    # Exports (AX-M-021): what other specifications may rely on.
    for nid in sorted(set(baseline['exports']) ^ set(candidate['exports'])):
        kind = (new_nodes.get(nid) or old_nodes.get(nid) or {}).get('kind', 'Node')
        if nid in baseline['exports']:
            change(nid, kind, 'changed', 'major', 'no longer exported')
        else:
            change(nid, kind, 'changed', 'minor', 'now exported')
    # Approval policy and keys (AX-M-020): governance, never a compatibility question.
    old_keys = {key['id']: key for key in baseline['approval']['keys']}
    new_keys = {key['id']: key for key in candidate['approval']['keys']}
    for kid in sorted(set(old_keys) | set(new_keys)):
        if old_keys.get(kid) != new_keys.get(kid):
            what = 'added' if kid not in old_keys else 'removed' if kid not in new_keys else 'changed'
            change(kid, 'ApprovalKey', what, 'patch', 'approval key ' + what)
    if baseline['approval']['policy'] != candidate['approval']['policy']:
        change(candidate['project']['id'], 'Project', 'changed', 'patch', 'approval policy changed')

    # Compatibility decisions (AX-L-007): every breaking candidate is acknowledged or overridden on record.
    entries = {entry['subject_id']: entry for entry in candidate['release']['compatibility']}
    for record in changes.values():
        record['breaking_candidate'] = record['level'] == 'major'
        record['accepted_as'] = None
        if record['breaking_candidate']:
            entry = entries.get(record['subject_id'])
            if entry is None:
                error('UNACKNOWLEDGED_BREAKING', record['subject_id'],
                      'A breaking candidate needs a release.compatibility entry backed by a decision.')
            else:
                record['accepted_as'] = entry['classification']
                if entry['classification'] == 'compatible':
                    record['level'] = 'minor'
    candidates = {r['subject_id'] for r in changes.values() if r['breaking_candidate']}
    for subject_id in sorted(set(entries) - candidates):
        error('UNUSED_COMPATIBILITY_ENTRY', subject_id, 'This entry matches no breaking candidate of this release.')

    # Version step (AX-L-008).
    required = max((r['level'] for r in changes.values()), key=LEVELS.get, default='none')
    declared = version_step(baseline['release']['version'], candidate['release']['version'])
    if declared is None:
        error('INVALID_VERSION_STEP', None, 'The version is not the next major, minor or patch after the baseline.')
    elif LEVELS[declared] < LEVELS[required]:
        error('VERSION_BUMP_TOO_SMALL', None, f'The changes require a {required} step; {declared} was declared.')

    # Change risk score (AX-L-009).
    units = max(baseline['project']['weight_minor_units'], candidate['project']['weight_minor_units'])
    weights, active = {}, set()
    for document in (baseline, candidate):
        scale = units // document['project']['weight_minor_units']
        for node in document['nodes']:
            if node['kind'] == 'Requirement':
                weights[node['id']] = max(weights.get(node['id'], 0), node['data']['weight_minor'] * scale)
                if node['status'] == 'active':
                    active.add(node['id'])
    factor, reach, unmapped = {}, {}, []
    for record in sorted(changes.values(), key=lambda r: r['subject_id']):
        reached = [index.requirements(record['subject_id']) for index in (old_index, new_index)]
        if all(r is None for r in reached):
            unmapped.append(record['subject_id'])
            continue
        for rid in set().union(*[r for r in reached if r]) & active:
            if FACTOR_PERCENT[record['level']] > factor.get(rid, 0):
                factor[rid], reach[rid] = FACTOR_PERCENT[record['level']], 'direct'
    neighbours = defaultdict(set)
    for index in (old_index, new_index):
        for (source, relation), targets in index.out.items():
            if relation == 'depends_on':
                for target in targets:
                    neighbours[source].add(target)
                    neighbours[target].add(source)
    pending = sorted(factor)
    while pending:
        rid = pending.pop()
        passed = min(DEPENDENT_CAP_PERCENT, factor[rid])
        for other in neighbours[rid] & active:
            if passed > factor.get(other, 0):
                factor[other], reach[other] = passed, 'dependency'
                pending.append(other)
    score_minor = sum(weights[rid] * factor[rid] for rid in factor)
    score_units = units * 100
    total = sum(weights[rid] for rid in active)
    digits = len(str(score_units)) - 1
    risk = dict(weight_minor_units=units, score_minor=score_minor, score_minor_units=score_units,
                score=f'{score_minor // score_units}.{score_minor % score_units:0{digits}d}',
                total_weight_minor=total,
                exposure_permille=score_minor * 1000 // (total * 100) if total else 0,
                requirements=[dict(id=rid, weight_minor=weights[rid], factor_percent=factor[rid], reach=reach[rid])
                              for rid in sorted(factor)],
                unmapped_changes=unmapped)

    ordered = sorted(changes.values(), key=lambda r: r['subject_id'])
    return dict(format='axiomspec-release-comparison/0.1', gate='G14',
                status='fail' if errors else 'pass',
                baseline=dict(version=baseline['release']['version'], spec_sha256=base_digest),
                candidate=dict(version=candidate['release']['version'], spec_sha256=cand_digest),
                declared_step=declared, required_step=required,
                counts={level: sum(r['level'] == level for r in ordered) for level in ('major', 'minor', 'patch')},
                errors=sorted(errors, key=lambda e: (e['code'], e['subject_id'] or '')),
                changes=ordered, risk=risk,
                limitations=['Mechanical classification by ID: it cannot judge whether a changed formula is tighter or looser.',
                             'The score ranks exposure from declared links and weights; it never changes a gate result.',
                             'API compatibility, data migration and mixed-version operation are verified on the product.'])


def main(arguments):
    if len(arguments) != 2:
        print('Usage: python3 qa/release_diff.py <baseline.json> <candidate.json>', file=sys.stderr)
        return 4
    try:
        validator = make_validator(read('schemas/spec.schema.json'), check_formats=True)
        documents = []
        for name in arguments:
            document = strict_json(Path(name).read_bytes())
            validator.validate(document)
            problems = reference_errors(document)
            if problems:
                raise ValueError(f'{name}: {problems}')
            documents.append(document)
        report = compare(*documents)
    except Exception as exc:  # CLI boundary: an unreadable input is an error, never a pass.
        print(f'{type(exc).__name__}: {str(exc)[:400]}', file=sys.stderr)
        return 4
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'pass' else 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
