#!/usr/bin/env python3
"""Declared migration axiomspec/0.2 -> axiomspec/0.3 (AX-L-005).

Reads a 0.2 specification, writes a 0.3 candidate to a new path and prints what a person must still decide.
It never overwrites its source and decides no policy: the approval policy it writes asks for no approver in
any band and declares no key, which is valid, visible and almost certainly not what the organization wants.

A migrated release has a new digest. When the source names a baseline, pass the migrated baseline so that
`release.previous` names it; otherwise the candidate keeps a digest that no 0.3 file has.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

SOURCE, TARGET = ('axiomspec/0.2', 'AX-CORE-0.2'), ('axiomspec/0.3', 'AX-CORE-0.3')
BANDS = ('low', 'medium', 'high', 'critical')


def canonical_digest(document):
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def migrate(source, migrated_baseline=None):
    """Return (candidate, decisions). `source` is left untouched."""
    if (source.get('format'), source.get('profile')) != SOURCE:
        raise ValueError('Unsupported source format: expected axiomspec/0.2 with AX-CORE-0.2')
    old = copy.deepcopy(source)
    project = old['project']['id']
    decisions = [
        dict(subject_id=project, field='approval.policy',
             reason='Placeholder: no approver is required in any band. Set the number and the accepted methods per band.'),
        dict(subject_id=project, field='approval.keys',
             reason='No key is declared. Declare the keys of the approvers, or of the service that attests for them.'),
        dict(subject_id=project, field='exports',
             reason='Nothing is exported. List the requirements, constraints, terms and state models others may rely on.')]
    release = old['release']
    if release['previous'] is not None:
        if migrated_baseline is None:
            decisions.append(dict(subject_id=project, field='release.previous.spec_sha256',
                                  reason='Still the digest of the 0.2 baseline. Migrate the baseline and name its new digest.'))
        elif migrated_baseline['release']['version'] != release['previous']['version']:
            raise ValueError('The migrated baseline is not the version this release names')
        else:
            release['previous']['spec_sha256'] = canonical_digest(migrated_baseline)
    candidate = dict(format=TARGET[0], profile=TARGET[1], release=release, project=old['project'], actors=old['actors'],
                     approval=dict(policy={band: dict(approvers=0, methods=[]) for band in BANDS}, keys=[]),
                     imports=[], exports=[], sources=old['sources'], environments=old['environments'],
                     flags=old['flags'], nodes=old['nodes'], edges=old['edges'], bindings=old['bindings'],
                     context_assets=old['context_assets'])
    return candidate, decisions


def main(arguments):
    if len(arguments) not in (2, 3):
        print('Usage: python3 qa/migrate_0_2.py <source-0.2.json> <new-candidate-0.3.json> [<migrated-baseline-0.3.json>]',
              file=sys.stderr)
        return 2
    source_path, target_path = Path(arguments[0]), Path(arguments[1])
    if target_path.exists():
        print('Refusing to overwrite an existing file; choose a new candidate path.', file=sys.stderr)
        return 2
    baseline = json.loads(Path(arguments[2]).read_text()) if len(arguments) == 3 else None
    candidate, decisions = migrate(json.loads(source_path.read_text()), baseline)
    target_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(source=SOURCE[0], target=TARGET[0], candidate=str(target_path),
                          decisions_required=decisions), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
