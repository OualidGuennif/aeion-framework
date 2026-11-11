#!/usr/bin/env python3
"""The graph index of one release and the requirement annotations in its code (AX-V-001, AX-V-002).

The index is what a coding agent is given instead of the specification: every object by ID, kind and title,
every declared link, and where each requirement is implemented and tested. It is written one record per
line, so a search for an ID or a file path returns exactly the lines that matter.

An annotation is the token `@req` followed by one or more IDs, in a comment or docstring of a source file:

    # @req REQ-004 CON-005

The index is derived. It never replaces the specification, and an annotation is a declared link: it says
where an author placed a requirement, not that the code satisfies it.
"""
import ast
import json
from pathlib import Path, PurePosixPath
import re
import sys

from check_package import canonical, digest, strict_json
import release_diff

FORMAT = 'axiomspec-graph/0.1'
ANNOTATION = re.compile(r'@req\b((?:[ \t,]+[A-Z][A-Z0-9_]*-[0-9]{3,6})+)')
ID = re.compile(r'[A-Z][A-Z0-9_]*-[0-9]{3,6}')
SOURCE_SUFFIXES = {'.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.kt', '.scala', '.cs',
                   '.c', '.cc', '.cpp', '.h', '.hpp', '.swift', '.rb', '.php', '.sql', '.sh'}
SKIPPED_DIRECTORIES = {'.git', '.hg', '.venv', 'venv', 'node_modules', '__pycache__', 'dist', 'build', 'target', '.tox'}
MAX_SOURCE_BYTES = 1048576
SECTIONS = ('nodes', 'edges', 'traces', 'flags', 'imports', 'exports')


def is_test_path(path):
    """A file counts as a test by its name or folder; everything else is code."""
    parts = PurePosixPath(path).parts
    stem = PurePosixPath(path).stem
    return (any(part in {'test', 'tests', '__tests__', 'spec'} for part in parts[:-1])
            or stem.startswith('test_') or stem.endswith(('_test', '.test', '.spec')))


def python_symbols(text):
    """(first line, last line, qualified name) of every class and function, or [] when the file does not parse."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    spans = []

    def visit(parent, prefix):
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                first = min([child.lineno] + [d.lineno for d in child.decorator_list])
                spans.append((first, child.end_lineno, name))
                visit(child, name + '.')
            else:
                visit(child, prefix)
    visit(tree, '')
    return spans


def symbol_at(spans, lines, number):
    """The definition a comment block directly precedes, else the innermost one that contains the line."""
    if lines[number - 1].lstrip().startswith('#'):
        for first, _, name in sorted(spans):
            if first > number and all(not line.strip() or line.lstrip().startswith(('#', '@'))
                                      for line in lines[number:first - 1]):
                return name
    inside = [span for span in spans if span[0] <= number <= span[1]]
    return max(inside, key=lambda span: span[0])[2] if inside else None


def scan(root, include=('.',)):
    """Every annotation under `root`, as (path, line, symbol, ids) records sorted by path and line.

    Paths are relative to `root`, with forward slashes. Symbols are resolved for Python; elsewhere the
    file and line are the location.
    """
    root = Path(root).resolve()
    files = []
    for entry in include:
        start = (root / entry).resolve()
        if not start.is_relative_to(root):
            raise ValueError('Scan path escapes the repository root')
        if start.is_file():
            files.append(start)
            continue
        for path in sorted(start.rglob('*')):
            relative = path.relative_to(root)
            if (path.is_file() and not path.is_symlink() and path.suffix in SOURCE_SUFFIXES
                    and not SKIPPED_DIRECTORIES & set(relative.parts)):
                files.append(path)
    found = []
    for path in sorted(set(files)):
        if path.stat().st_size > MAX_SOURCE_BYTES:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if '@req' not in text:
            continue
        lines = text.splitlines()
        spans = python_symbols(text) if path.suffix in {'.py', '.pyi'} else []
        for number, line in enumerate(lines, 1):
            for match in ANNOTATION.finditer(line):
                found.append(dict(path=path.relative_to(root).as_posix(), line=number,
                                  symbol=symbol_at(spans, lines, number), ids=ID.findall(match.group(1))))
    return found


def check(spec, annotations):
    """An annotation names an object the release holds and has not retired."""
    nodes = {node['id']: node for node in spec['nodes']}
    problems = []
    for annotation in annotations:
        for target in annotation['ids']:
            status = nodes.get(target, {}).get('status')
            if status in (None, 'retired'):
                code = 'UNKNOWN_ANNOTATION_ID' if status is None else 'RETIRED_ANNOTATION_ID'
                problems.append(dict(code=code, subject_id=target, path=annotation['path'], line=annotation['line'],
                                     message=f"{annotation['path']}:{annotation['line']} names {target}, which this "
                                             f"release {'does not hold' if status is None else 'has retired'}."))
    return problems


def build(spec, annotations=()):
    """The index of one release. Deterministic: sorted, and a function of the release and the annotations."""
    index = release_diff.Index(spec)
    nodes = []
    for node in sorted(spec['nodes'], key=lambda n: n['id']):
        row = dict(id=node['id'], kind=node['kind'], status=node['status'], title=node['title'])
        if node['kind'] == 'Requirement':
            data = node['data']
            row.update(priority=data['priority'], risk=data['risk'], weight_minor=data['weight_minor'], flag_id=data['flag_id'])
        nodes.append(row)
    edges = [{'from': e['from'], 'relation': e['relation'], 'to': e['to']}
             for e in sorted(spec['edges'], key=lambda e: (e['from'], e['relation'], e['to'], e['id']))]
    traces = []
    for binding in spec['bindings']:
        traces.append(dict(path=binding['path'], line=None, symbol=binding['symbol'], kind=binding['kind'],
                           origin='binding', node_id=binding['node_id'],
                           requirement_ids=sorted(index.requirements(binding['node_id']) or [])))
    for annotation in annotations:
        for target in annotation['ids']:
            if target in index.nodes:
                traces.append(dict(path=annotation['path'], line=annotation['line'], symbol=annotation['symbol'],
                                   kind='test' if is_test_path(annotation['path']) else 'code', origin='annotation',
                                   node_id=target, requirement_ids=sorted(index.of_node(index.nodes[target]))))
    traces.sort(key=lambda t: (t['path'], t['line'] or 0, t['symbol'] or '', t['node_id'], t['origin'], t['kind']))
    return dict(format=FORMAT, project_id=spec['project']['id'], version=spec['release']['version'],
                spec_sha256=digest(canonical(spec)), weight_minor_units=spec['project']['weight_minor_units'],
                nodes=nodes, edges=edges, traces=traces,
                flags=[dict(id=f['id'], key=f['key'], state=f['state']) for f in sorted(spec['flags'], key=lambda f: f['id'])],
                imports=[dict(id=i['id'], project_id=i['project_id'], version=i['version'], spec_sha256=i['spec_sha256'])
                         for i in sorted(spec['imports'], key=lambda i: i['id'])],
                exports=sorted(spec['exports']))


def dumps(index):
    """The index as JSON with one record per line: valid JSON, and searchable with a line tool."""
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    lines = ['{']
    names = list(index)
    for position, name in enumerate(names):
        comma = '' if position == len(names) - 1 else ','
        if name in SECTIONS:
            rows = index[name]
            lines.append(f'{compact(name)}:[')
            lines.extend(compact(row) + (',' if number < len(rows) - 1 else '') for number, row in enumerate(rows))
            lines.append(']' + comma)
        else:
            lines.append(f'{compact(name)}:{compact(index[name])}{comma}')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def main(arguments):
    if len(arguments) >= 2 and arguments[0] == 'build':
        spec = strict_json(Path(arguments[1]).read_bytes())
        rest, repo, include = arguments[2:], None, []
        while rest:
            if rest[0] == '--repo' and len(rest) > 1:
                repo, rest = rest[1], rest[2:]
            elif rest[0] == '--include' and len(rest) > 1:
                include.append(rest[1])
                rest = rest[2:]
            else:
                break
        if not rest:
            annotations = scan(repo, include or ('.',)) if repo else []
            problems = check(spec, annotations)
            for problem in problems:
                print(f"{problem['code']}: {problem['message']}", file=sys.stderr)
            sys.stdout.write(dumps(build(spec, annotations)))
            return 2 if problems else 0
    print('Usage: python3 qa/graph_index.py build <spec.json> [--repo <directory> [--include <path>]...]', file=sys.stderr)
    return 4


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(4)
