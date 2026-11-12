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
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sys

import approvals as approval_check
from check_package import (BOUNDS, canonical, digest, make_validator, reference_errors, strict_json,
                           version_tuple)
import release_diff
import spec_parts

ROOT = Path(__file__).resolve().parents[1]
LEVELS = release_diff.LEVELS
# A file that cannot be read as a store file and still says it is one is reported, never dropped in silence.
CLAIM = re.compile(rb'"format"\s*:\s*"axiomspec(?:-approvals|-parts)?/')


class Store:
    def __init__(self):
        self.releases = {}   # canonical digest -> specification
        self.paths = {}      # canonical digest -> sorted list of file names that held it
        self.approvals = {}  # (release digest, project id, version) -> merged approvals document
        self.approval_paths = {}  # the same key -> names of the files that held approvals under it
        self.rejected = []   # files that claim a store format and are not valid

    def add_release(self, spec, name):
        key = digest(canonical(spec))
        self.releases[key] = spec
        self.paths.setdefault(key, []).append(name)

    def add_approvals(self, document, name=None):
        # Keyed by the whole header: a file that names a release under another project or version is kept
        # apart, so it can neither block the true approvals nor depend on the order in which files are read.
        key = (document['spec_sha256'], document['project_id'], document['version'])
        held = self.approvals.get(key)
        self.approvals[key] = approval_check.merge(held, document) if held else approval_check.merge(document, document)
        self.approval_paths.setdefault(key, []).append(name)

    def approvals_of(self, key):
        """The merged approvals of the release held under `key`, or None."""
        spec = self.releases[key]
        return self.approvals.get((key, spec['project']['id'], spec['release']['version']))

    def misnamed_approvals(self):
        """Approval files that name a held release under another project or version: reported, never counted."""
        found = []
        for (key, project_id, version), names in self.approval_paths.items():
            spec = self.releases.get(key)
            if spec is not None and (project_id, version) != (spec['project']['id'], spec['release']['version']):
                found += [dict(path=name, reason=f'Approvals of {key} name {project_id} {version}, which that release is not')
                          for name in names]
        return found


@lru_cache(maxsize=1)
def validators():
    """The specification and approvals validators, compiled once."""
    return tuple(make_validator(json.loads((ROOT / f'schemas/{name}.schema.json').read_text()))
                 for name in ('spec', 'approvals'))


def listing(paths):
    """Every JSON file under the given files and directories: path -> (size, modification time).

    Symbolic links are not followed, and nothing is read below a name that starts with a dot: that is where
    a writer stages a file before it moves it into place. One pass over each directory, so a large store is
    listed at about one system call per file. A named file that is absent maps to None.
    """
    found = {}

    def walk(directory):
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith('.') or entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    walk(entry.path)
                elif entry.name.endswith('.json') and entry.is_file(follow_symlinks=False):
                    status = entry.stat(follow_symlinks=False)
                    found[Path(entry.path)] = (status.st_size, status.st_mtime_ns)

    for path in map(Path, paths):
        if path.is_dir():
            walk(path)
        else:
            try:
                status = path.stat()
                found[path] = (status.st_size, status.st_mtime_ns)
            except OSError:
                found[path] = None
    return found


def files(paths):
    """Every JSON file under the given files and directories, sorted."""
    return sorted(listing(paths))


def add_file(store, file):
    """Read one file into the store. A file of another format is ignored; a broken store file is rejected."""
    spec_validator, approvals_validator = validators()
    name = Path(file).as_posix()
    with Path(file).open('rb') as source:
        raw = source.read(BOUNDS['max_input_bytes'] + 1)
    try:
        document = strict_json(raw)
    except ValueError as exc:
        if CLAIM.search(raw):
            store.rejected.append(dict(path=name, reason=f'{type(exc).__name__}: {str(exc)[:200]}'))
        return  # otherwise not strict JSON within bounds: not a store file
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
            store.add_approvals(document, name)
    except Exception as exc:
        store.rejected.append(dict(path=name, reason=f'{type(exc).__name__}: {str(exc)[:200]}'))


def load(paths):
    """Read every JSON file under the given files and directories. Files of other formats are ignored."""
    store = Store()
    for file in files(paths):
        add_file(store, file)
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

    # Reference failures are known before comparing either end of a link. Comparison and risk traversal
    # require valid typed relations; a bad release must not make the entire store unverifiable.
    reference_problems = {key: sorted(set(reference_errors(spec))) for key, spec in store.releases.items()}
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
        found = reference_problems[key]
        if found:
            error('REFERENCE_ERRORS', key, ', '.join(found))
        baseline = store.releases.get(previous['spec_sha256']) if previous is not None else None
        comparison = None
        if previous is not None and baseline is not None:
            entry['link'] = 'present'
            if reference_problems[previous['spec_sha256']]:
                error('INVALID_BASELINE', key, 'The named baseline has invalid references; it cannot govern this release.')
            elif not found:
                comparison = release_diff.compare(baseline, spec)
                entry['comparison'] = comparison['status']
                for problem in comparison['errors']:
                    error(problem['code'], key, problem['message'])
        if not found and (previous is None or (baseline is not None and comparison is not None)):
            document = store.approvals_of(key) or approval_check.empty(spec)
            check = approval_check.verify(spec, document, baseline, comparison, validated=True)
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

    # A valid successor always has a numerically smaller baseline version. Resolve authority in that
    # order, without recursion or dependence on file arrival. Local approval details stay visible.
    by_digest = {entry['spec_sha256']: entry for entry in releases}
    for entry in sorted(releases, key=lambda r: (version_tuple(r['version']), r['spec_sha256'])):
        previous = store.releases[entry['spec_sha256']]['release']['previous']
        baseline_entry = by_digest.get(previous['spec_sha256']) if previous is not None else None
        if entry['status'] == 'fail' or baseline_entry is None:
            continue
        if baseline_entry['status'] == 'fail':
            entry['status'] = 'fail'
            error('BASELINE_NOT_ACCEPTED', entry['spec_sha256'],
                  f"The baseline {previous['spec_sha256']} does not pass its release chain.")
        elif baseline_entry['status'] == 'unknown':
            entry['status'] = 'unknown'

    passed = {entry['spec_sha256'] for entry in releases if entry['status'] == 'pass'}
    projects = []
    for project_id in sorted({spec['project']['id'] for spec in store.releases.values()}):
        members = {key: spec for key, spec in store.releases.items() if spec['project']['id'] == project_id}
        accepted = sorted(((key, spec) for key, spec in members.items() if key in passed), key=head_order)
        heads = sorted(((key, spec) for key, spec in members.items()
                        if not any(successor in members for successor in successors.get(key, []))), key=head_order)
        top = heads[0][1]['release']['version']
        tied = [key for key, spec in heads if spec['release']['version'] == top]
        if len(tied) > 1:
            error('FORKED_HEAD', project_id,
                  f'{len(tied)} different releases claim version {top}. Each stays verifiable by its digest; '
                  'a later release that names one of them settles the fork.')
        projects.append(dict(project_id=project_id, releases=len(members),
                             head=dict(version=top, spec_sha256=heads[0][0]),
                             accepted_head=dict(version=accepted[0][1]['release']['version'], spec_sha256=accepted[0][0]) if accepted else None,
                             tied_heads=tied if len(tied) > 1 else [],
                             orphaned_heads=[key for key, spec in heads if spec['release']['version'] != top]))
    rejected = store.rejected + store.misnamed_approvals()
    open_ends = bool(rejected) or any(r['status'] == 'unknown' for r in releases)
    return dict(format='axiomspec-store-check/0.2', status='fail' if errors else 'incomplete' if open_ends else 'pass',
                releases=releases, projects=projects, errors=sorted(errors, key=lambda e: (e['code'], e['subject'], e['message'])),
                rejected_files=sorted(rejected, key=lambda r: r['path']),
                limitations=['The verdict covers the files supplied. An absent baseline, ancestor or provider leaves a release unknown, not accepted.',
                             'A release passes only when its own checks and its baseline chain pass. Trust in a genesis still requires pinning its digest through a trusted channel.',
                             'A fork is reported when two releases hold the highest version of a project. Settling it is a decision; the store never deletes a file.',
                             'The head of a project is its highest version, whatever its status. The accepted head is its highest release that passes; it is null when none does.',
                             'Nothing here says a store is complete or current: an absent newer release cannot be detected from the files present.'])


def consumer_heads(store, report=None):
    """The release of each project that others are measured against: digest -> specification.

    It is the accepted head, the highest release that passes. A refused or unapproved release never stands
    for its project while an accepted one exists; the preferred head is used only when none passes.
    """
    report = report or verify(store)
    chosen = [(p['accepted_head'] or p['head'])['spec_sha256'] for p in report['projects']]
    return {key: store.releases[key] for key in chosen}


def impact(store, baseline, candidate, report=None):
    """AX-L-011: which specifications in the store a provider's step from `baseline` to `candidate` reaches.

    `report` is the verdict on the store when the caller already holds it.

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
    for key, spec in sorted(consumer_heads(store, report).items()):
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
                limitations=['Only one release of each project in the supplied store is examined: its accepted head, or its preferred head when no release passes.',
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
