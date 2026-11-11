#!/usr/bin/env python3
"""A release store: any set of release and approval files, verified without shared state (AX-L-010, AX-L-011).

A store is a set of immutable files named by content: a release by the digest of its canonical form, an
approval file by the release it approves. There is no index, no log, no ordering service and no clock.
Any two stores merge by taking the union of their files, and the verdict below is a function of the set
alone: the order in which files arrived, or which replica supplied them, cannot change it.

What a missing file causes is an `unknown`, never a wrong answer. What two conflicting files cause is a
reported fork with a deterministic preferred head, never a corrupted store. Every release carries its own
status, so one failed or unreadable file does not withhold the verdict on the others.
"""
import json
from pathlib import Path
import sys

import approvals as approval_check
from check_package import (BOUNDS, canonical, digest, make_validator, reference_errors, strict_json,
                           version_tuple)
import release_diff
import spec_parts

ROOT = Path(__file__).resolve().parents[1]
LEVELS = release_diff.LEVELS


class Store:
    def __init__(self):
        self.releases = {}   # canonical digest -> specification
        self.paths = {}      # canonical digest -> sorted list of file names that held it
        self.approvals = {}  # release digest -> merged approvals document
        self.rejected = []   # files that claim a store format and are not valid

    def add_release(self, spec, name):
        key = digest(canonical(spec))
        self.releases[key] = spec
        self.paths.setdefault(key, []).append(name)

    def add_approvals(self, document):
        held = self.approvals.get(document['spec_sha256'])
        self.approvals[document['spec_sha256']] = approval_check.merge(held, document) if held else approval_check.merge(document, document)


def load(paths):
    """Read every JSON file under the given files and directories. Files of other formats are ignored."""
    spec_validator = make_validator(json.loads((ROOT / 'schemas/spec.schema.json').read_text()))
    approvals_validator = make_validator(json.loads((ROOT / 'schemas/approvals.schema.json').read_text()))
    store = Store()
    files = []
    for path in map(Path, paths):
        files += sorted(p for p in path.rglob('*.json') if p.is_file() and not p.is_symlink()) if path.is_dir() else [path]
    for file in files:
        name = file.as_posix()
        try:
            with file.open('rb') as source:
                document = strict_json(source.read(BOUNDS['max_input_bytes'] + 1))
        except ValueError:
            continue  # not strict JSON within bounds: not a store file
        kind = document.get('format') if isinstance(document, dict) else None
        try:
            if kind == release_diff.FORMAT:
                spec_validator.validate(document)
                store.add_release(document, name)
            elif kind == spec_parts.MANIFEST:
                spec = spec_parts.read(file)
                spec_validator.validate(spec)
                store.add_release(spec, name)
            elif kind == approval_check.FORMAT:
                approvals_validator.validate(document)
                store.add_approvals(document)
        except Exception as exc:
            store.rejected.append(dict(path=name, reason=f'{type(exc).__name__}: {str(exc)[:200]}'))
    return store


def head_order(item):
    """Greatest version first; between equal versions the smaller digest, so every replica prefers the same one."""
    key, spec = item
    return tuple(-part for part in version_tuple(spec['release']['version'])), key


def verify(store):
    """Return the deterministic verdict on a store: pass, fail or incomplete."""
    releases, errors = [], []

    def error(code, subject, message):
        errors.append(dict(code=code, subject=subject, message=message))

    successors = {}
    for key, spec in store.releases.items():
        previous = spec['release']['previous']
        if previous is not None:
            successors.setdefault(previous['spec_sha256'], []).append(key)
    for key in sorted(store.releases):
        spec = store.releases[key]
        previous = spec['release']['previous']
        entry = dict(project_id=spec['project']['id'], version=spec['release']['version'], spec_sha256=key,
                     status='pass', files=sorted(store.paths[key]), link='genesis' if previous is None else 'unknown',
                     comparison=None, approvals='unknown', imports=[])
        known = len(errors)
        found = sorted(set(reference_errors(spec)))
        if found:
            error('REFERENCE_ERRORS', key, ', '.join(found))
        baseline = store.releases.get(previous['spec_sha256']) if previous is not None else None
        if previous is not None and baseline is not None:
            comparison = release_diff.compare(baseline, spec)
            entry['link'], entry['comparison'] = 'present', comparison['status']
            for problem in comparison['errors']:
                error(problem['code'], key, problem['message'])
        if previous is None or baseline is not None:
            document = store.approvals.get(key) or approval_check.empty(spec)
            check = approval_check.verify(spec, document, baseline)
            entry['approvals'] = check['status']
            entry['approvals_set_aside'] = len(check['rejected'])
            for problem in check['errors']:
                error(problem['code'], key, problem['message'])
        for item in spec['imports']:
            provider = store.releases.get(item['spec_sha256'])
            state = 'unresolved'
            if provider is not None:
                state = 'resolved'
                if (provider['project']['id'], provider['release']['version']) != (item['project_id'], item['version']):
                    state = 'mismatch'
                    error('IMPORT_PIN_MISMATCH', key, f"{item['id']}: the pinned digest is another project or version.")
                missing = sorted({use['external_id'] for use in item['uses']} - set(provider['exports']))
                if missing:
                    state = 'not_exported'
                    error('NOT_EXPORTED', key, f"{item['id']}: the pinned release does not export {', '.join(missing)}.")
            entry['imports'].append(dict(id=item['id'], project_id=item['project_id'], version=item['version'], state=state))
        if len(errors) > known:
            entry['status'] = 'fail'
        elif entry['link'] == 'unknown' or entry['approvals'] == 'unknown' or any(i['state'] == 'unresolved' for i in entry['imports']):
            entry['status'] = 'unknown'
        releases.append(entry)

    projects = []
    for project_id in sorted({spec['project']['id'] for spec in store.releases.values()}):
        members = {key: spec for key, spec in store.releases.items() if spec['project']['id'] == project_id}
        heads = sorted(((key, spec) for key, spec in members.items()
                        if not any(successor in members for successor in successors.get(key, []))), key=head_order)
        top = heads[0][1]['release']['version']
        tied = [key for key, spec in heads if spec['release']['version'] == top]
        if len(tied) > 1:
            error('FORKED_HEAD', project_id,
                  f'{len(tied)} different releases claim version {top}. Each stays verifiable by its digest; '
                  'a later release that names one of them settles the fork.')
        projects.append(dict(project_id=project_id, releases=len(members),
                             head=dict(version=top, spec_sha256=heads[0][0]), tied_heads=tied if len(tied) > 1 else [],
                             orphaned_heads=[key for key, spec in heads if spec['release']['version'] != top]))
    open_ends = bool(store.rejected) or any(r['status'] == 'unknown' for r in releases)
    return dict(format='axiomspec-store-check/0.1', status='fail' if errors else 'incomplete' if open_ends else 'pass',
                releases=releases, projects=projects, errors=sorted(errors, key=lambda e: (e['code'], e['subject'], e['message'])),
                rejected_files=sorted(store.rejected, key=lambda r: r['path']),
                limitations=['The verdict covers the files supplied. A release whose baseline or provider is absent is unknown, not accepted.',
                             'A fork is reported when two releases hold the highest version of a project. Settling it is a decision; the store never deletes a file.',
                             'Nothing here says a store is complete or current: an absent newer release cannot be detected from the files present.'])


def heads(store):
    """The preferred head of each project: digest -> specification."""
    report = verify(store)
    return {p['head']['spec_sha256']: store.releases[p['head']['spec_sha256']] for p in report['projects']}


def impact(store, baseline, candidate):
    """AX-L-011: which specifications in the store a provider's step from `baseline` to `candidate` reaches.

    A use is reached at the highest level of any change whose subject it is or whose declared links lead to it.
    A reached local requirement scores as a dependent does within one specification (AX-L-009): its weight
    times the smaller of the dependent cap and the factor of that level.
    """
    comparison = release_diff.compare(baseline, candidate)
    provider = candidate['project']['id']
    level = {}
    indexes = (release_diff.Index(baseline), release_diff.Index(candidate))
    for change in comparison['changes']:
        touched = {change['subject_id']}
        for index in indexes:
            touched |= index.requirements(change['subject_id']) or set()
        for subject in touched:
            if LEVELS[change['level']] > LEVELS[level.get(subject, 'none')]:
                level[subject] = change['level']
    withdrawn = set(baseline['exports']) - set(candidate['exports'])
    consumers = []
    for key, spec in sorted(heads(store).items()):
        if spec['project']['id'] == provider:
            continue
        index = release_diff.Index(spec)
        units = spec['project']['weight_minor_units']
        for item in spec['imports']:
            if item['project_id'] != provider:
                continue
            uses, factor = [], {}
            for use in item['uses']:
                reached = 'major' if use['external_id'] in withdrawn else level.get(use['external_id'])
                if reached is None:
                    continue
                uses.append(dict(external_id=use['external_id'], level=reached, local_ids=use['local_ids']))
                percent = min(release_diff.DEPENDENT_CAP_PERCENT, release_diff.FACTOR_PERCENT[reached])
                for local in use['local_ids']:
                    for rid in index.requirements(local) or set():
                        if index.nodes[rid]['status'] == 'active':
                            factor[rid] = max(factor.get(rid, 0), percent)
            score_minor = sum(index.nodes[rid]['data']['weight_minor'] * percent for rid, percent in factor.items())
            score_units = units * 100
            consumers.append(dict(
                project_id=spec['project']['id'], version=spec['release']['version'], spec_sha256=key,
                import_id=item['id'], pinned_version=item['version'],
                pinned_to_baseline=item['spec_sha256'] == digest(canonical(baseline)),
                uses=uses,
                requirements=[dict(id=rid, weight_minor=index.nodes[rid]['data']['weight_minor'], factor_percent=factor[rid])
                              for rid in sorted(factor)],
                score_minor=score_minor, score_minor_units=score_units,
                score=f'{score_minor // score_units}.{score_minor % score_units:0{len(str(score_units)) - 1}d}'))
    return dict(format='axiomspec-impact/0.1', provider=dict(project_id=provider, baseline=baseline['release']['version'],
                                                             candidate=candidate['release']['version']),
                comparison=comparison['status'], required_step=comparison['required_step'], consumers=consumers,
                limitations=['Only the preferred head of each project in the supplied store is examined.',
                             'A consumer pinned to a release other than this baseline is reached by this step and by every step before it; compare from its pin for the full effect.',
                             'Only declared uses are followed. An undeclared dependency on the provider is not found.'])


def main(arguments):
    load_one = lambda name: strict_json(Path(name).read_bytes())
    if len(arguments) >= 2 and arguments[0] == 'verify':
        report = verify(load(arguments[1:]))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return {'pass': 0, 'fail': 2, 'incomplete': 3}[report['status']]
    if len(arguments) >= 4 and arguments[0] == 'impact':
        print(json.dumps(impact(load(arguments[3:]), load_one(arguments[1]), load_one(arguments[2])), ensure_ascii=False, indent=2))
        return 0
    print('Usage: python3 qa/release_store.py verify <file-or-directory>...\n'
          '       python3 qa/release_store.py impact <provider-baseline.json> <provider-candidate.json> <file-or-directory>...',
          file=sys.stderr)
    return 4


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(4)
