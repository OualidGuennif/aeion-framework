#!/usr/bin/env python3
"""A specification stored as several files (AX-M-022).

One file is bounded at one megabyte. A larger specification is stored as parts under a manifest that names
each part by digest and the joined document by its canonical digest. Joining is deterministic, so the joined
digest, and with it every pin and every approval, is the same as for a single file.

Splitting changes storage, not meaning: IDs stay unique across the whole specification and every rule applies
to the joined document.
"""
import json
from pathlib import Path, PurePosixPath
import sys

from check_package import BOUNDS, canonical, digest, require, strict_json

MANIFEST, PART = 'axiomspec-parts/0.1', 'axiomspec-part/0.1'
FIELDS = ('format', 'profile', 'release', 'project', 'approval')
SECTIONS = ('actors', 'imports', 'exports', 'sources', 'environments', 'flags', 'nodes', 'edges', 'bindings',
            'context_assets')
MAX_PARTS = 256
PART_BUDGET = BOUNDS['max_input_bytes'] * 9 // 10


def split(spec, budget=PART_BUDGET):
    """Return the parts of `spec`, each serializing under `budget` bytes. The first carries the root fields."""
    require(set(spec) == set(FIELDS) | set(SECTIONS), 'Unexpected root fields')
    parts = [dict(format=PART, fields={name: spec[name] for name in FIELDS}, items={})]
    used = len(canonical(parts[0]))
    require(used <= budget, 'Root fields exceed one part')
    for section in SECTIONS:
        for item in spec[section]:
            size = len(canonical(item)) + len(section) + 8
            require(size <= budget, f'One {section} item exceeds one part')
            if used + size > budget:
                parts.append(dict(format=PART, fields={}, items={}))
                used = len(canonical(parts[-1]))
            parts[-1]['items'].setdefault(section, []).append(item)
            used += size
    require(len(parts) <= MAX_PARTS, 'Too many parts')
    return parts


def join(manifest, load):
    """Rebuild the specification a manifest names. `load(path)` returns the raw bytes of one part."""
    require(isinstance(manifest, dict) and manifest.get('format') == MANIFEST
            and isinstance(manifest.get('parts'), list), 'Not a parts manifest')
    require(1 <= len(manifest['parts']) <= MAX_PARTS, 'Part count out of bounds')
    spec = {section: [] for section in SECTIONS}
    for entry in manifest['parts']:
        require(isinstance(entry, dict) and isinstance(entry.get('path'), str) and entry['path']
                and isinstance(entry.get('sha256'), str), 'A part entry needs a path and SHA-256')
        lexical = PurePosixPath(entry['path'])
        require(not lexical.is_absolute() and '..' not in lexical.parts and '\\' not in entry['path'],
                'Part path must stay beside the manifest')
        raw = load(entry['path'])
        require(digest(raw) == entry['sha256'], f"Part digest differs: {entry['path']}")
        part = strict_json(raw)
        require(isinstance(part, dict) and part.get('format') == PART and set(part) == {'format', 'fields', 'items'},
                'Not a specification part')
        require(isinstance(part['fields'], dict) and isinstance(part['items'], dict), 'Part fields and items must be objects')
        for name, value in part['fields'].items():
            require(name in FIELDS and name not in spec, f'Root field repeated or unknown: {name}')
            spec[name] = value
        for section, items in part['items'].items():
            require(section in SECTIONS and isinstance(items, list), f'Unknown section: {section}')
            spec[section].extend(items)
    require(all(name in spec for name in FIELDS), 'A root field is missing from the parts')
    require(digest(canonical(spec)) == manifest['spec_sha256'], 'Joined specification differs from the manifest digest')
    return {name: spec[name] for name in FIELDS[:4] + ('actors', 'approval') + SECTIONS[1:]}


def write(spec, directory, stem='spec', budget=PART_BUDGET):
    """Write the parts and the manifest into a new or empty directory; return the manifest path."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    require(not any(directory.iterdir()), 'Refusing to write parts into a directory that is not empty')
    entries = []
    for number, part in enumerate(split(spec, budget), 1):
        raw = (json.dumps(part, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        require(len(raw) <= BOUNDS['max_input_bytes'], 'Part exceeds the input bound')
        name = f'{stem}.part-{number:03d}.json'
        (directory / name).write_bytes(raw)
        entries.append(dict(path=name, sha256=digest(raw), bytes=len(raw)))
    manifest = dict(format=MANIFEST, spec_sha256=digest(canonical(spec)), parts=entries)
    path = directory / f'{stem}.manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    return path


def read(manifest_path, dependencies=None):
    """Read and join the specification a manifest file names."""
    manifest_path = Path(manifest_path)
    with manifest_path.open('rb') as source:
        manifest = strict_json(source.read(BOUNDS['max_input_bytes'] + 1))
    base = manifest_path.parent.resolve()

    def load(relative):
        require(not (base / relative).is_symlink(), 'A part is a regular file, not a link')
        path = (base / relative).resolve()
        require(path.is_relative_to(base), 'Part path escapes the manifest directory')
        if dependencies is not None:
            dependencies.append(path.as_posix())
        with path.open('rb') as source:
            return source.read(BOUNDS['max_input_bytes'] + 1)
    return join(manifest, load)


def main(arguments):
    if len(arguments) == 3 and arguments[0] == 'split':
        spec = json.loads(Path(arguments[1]).read_text())
        print(write(spec, arguments[2]))
        return 0
    if len(arguments) == 3 and arguments[0] == 'join':
        if Path(arguments[2]).exists():
            print('Refusing to overwrite an existing file.', file=sys.stderr)
            return 4
        Path(arguments[2]).write_text(json.dumps(read(arguments[1]), ensure_ascii=False, indent=2) + '\n')
        return 0
    print('Usage: python3 qa/spec_parts.py split <spec.json> <new-directory>\n'
          '       python3 qa/spec_parts.py join <manifest.json> <new-spec.json>', file=sys.stderr)
    return 4


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except ValueError as exc:
        print(f'{exc}', file=sys.stderr)
        sys.exit(4)
