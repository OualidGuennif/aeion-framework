#!/usr/bin/env python3
"""Declared migration axiomspec/0.1 -> axiomspec/0.2 (AX-L-005).

Reads a 0.1 specification, writes a 0.2 candidate to a new path and prints what a person must still decide.
It never overwrites its source, and it decides no business policy: weights and flag states are placeholders
derived from what the source already said, listed for review.
"""
import copy
import json
from pathlib import Path
import sys

SOURCE, TARGET = ('axiomspec/0.1', 'AX-CORE-0.1'), ('axiomspec/0.2', 'AX-CORE-0.2')
# Top of each risk band (AX-M-018): the highest weight the existing label still agrees with.
BAND_TOP = dict(low=25, medium=50, high=75, critical=100)


def migrate(source, version, weight_minor_units=1):
    """Return (candidate, decisions). `source` is left untouched."""
    if (source.get('format'), source.get('profile')) != SOURCE:
        raise ValueError('Unsupported source format: expected axiomspec/0.1 with AX-CORE-0.1')
    if weight_minor_units not in (1, 10, 100, 1000):
        raise ValueError('weight_minor_units is 1, 10, 100 or 1000')
    old = copy.deepcopy(source)
    decisions, flags, by_feature = [], [], {}
    project = dict(old['project'], weight_minor_units=weight_minor_units)
    used = {int(item['id'].split('-')[1]) for section in ('actors', 'sources', 'environments', 'nodes', 'edges',
            'bindings', 'context_assets') for item in old[section] if item['id'].startswith('FLAG-')}
    for node in old['nodes']:
        data = node['data']
        if node['kind'] == 'Requirement':
            data['weight_minor'] = BAND_TOP[data['risk']] * weight_minor_units
            data['flag_id'] = None
            decisions.append(dict(subject_id=node['id'], field='weight_minor',
                                  reason=f"Placeholder from risk '{data['risk']}'; set the reviewed weight."))
            if data['pattern'] == 'optional' and node['status'] != 'retired':
                feature = data['feature']
                if feature not in by_feature:
                    number = max(used | {0}) + 1
                    used.add(number)
                    flag_id = f'FLAG-{number:03d}'
                    by_feature[feature] = flag_id
                    flags.append(dict(id=flag_id, key=f'flag_{number:03d}', title=feature[:256], state='enabled',
                                      owner=node['owner'], introduced_in=version, remove_by=None))
                    decisions.append(dict(subject_id=flag_id, field='key, state, remove_by',
                                          reason='Created from an optional requirement; name it, confirm its state '
                                                 'and set a removal target.'))
                data['flag_id'] = by_feature[feature]
        if node['kind'] == 'TestCase':
            data['flag_states'] = []
    candidate = dict(format=TARGET[0], profile=TARGET[1],
                     release=dict(version=version, previous=None, compatibility=[]),
                     project=project, actors=old['actors'], sources=old['sources'],
                     environments=old['environments'], flags=flags, nodes=old['nodes'], edges=old['edges'],
                     bindings=old['bindings'], context_assets=old['context_assets'])
    if flags:
        decisions.append(dict(subject_id=project['id'], field='flag coverage',
                              reason='A flagged must requirement needs a test in each flag state (AX-G-007).'))
    return candidate, decisions


def main(arguments):
    if len(arguments) not in (3, 4):
        print('Usage: python3 qa/migrate_0_1.py <source-0.1.json> <new-candidate-0.2.json> <version> [1|10|100|1000]',
              file=sys.stderr)
        return 2
    source_path, target_path, version = Path(arguments[0]), Path(arguments[1]), arguments[2]
    if target_path.exists():
        print('Refusing to overwrite an existing file; choose a new candidate path.', file=sys.stderr)
        return 2
    candidate, decisions = migrate(json.loads(source_path.read_text()), version,
                                   int(arguments[3]) if len(arguments) == 4 else 1)
    target_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(source=SOURCE[0], target=TARGET[0], candidate=str(target_path),
                          decisions_required=decisions), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
