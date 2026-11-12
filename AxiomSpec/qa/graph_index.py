#!/usr/bin/env python3
"""The graph index of one release and the requirement annotations in its code (AX-V-001, AX-V-002).

The index is what a coding agent is given instead of the specification: every object by ID, kind and title,
every declared link, and where each requirement is implemented and tested. It is written one record per
line, so a search for an ID or a file path returns exactly the lines that matter.

An annotation is the token `@req` followed by one or more IDs, in a comment or docstring of a source file:

    # @req REQ-004 CON-005

A colon or an opening parenthesis may follow the token, and the IDs are separated by spaces or commas. The
token with no ID after it is reported as malformed, never skipped: a silent miss would tell an agent that
no requirement concerns the code. So is an ID of the release that follows other words on the same line
(`@req REQ-004 and CON-005`), because it was meant to be part of the annotation and was not read.

A repository that contains other code which mentions the token, such as a copy of this package, leaves it
out of the scan with `--exclude`.

The index is derived. It never replaces the specification, and an annotation is a declared link: it says
where an author placed a requirement, not that the code satisfies it.
"""
import ast
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tokenize

from check_package import canonical, digest, strict_json
import release_diff

FORMAT = 'axiomspec-graph/0.1'
# The token, not part of a longer word or of an address such as name@req.example.
TOKEN = re.compile(r'(?<![\w@])@req\b(?![.\-/])')
ANNOTATION = re.compile(r'@req[:(]?((?:[ \t,]*\b[A-Z][A-Z0-9_]*-[0-9]{3,6}\b)+)')
ID = re.compile(r'[A-Z][A-Z0-9_]*-[0-9]{3,6}')
SOURCE_SUFFIXES = {'.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.kt', '.scala', '.cs',
                   '.c', '.cc', '.cpp', '.h', '.hpp', '.swift', '.rb', '.php', '.sql', '.sh'}
# Folders never descended into below a scanned path. A scanned path is always read, whatever its own name:
# a source folder called `build` is scanned by naming it.
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


def python_annotation_lines(text):
    """Keep comments and actual module/class/function docstrings at their original line and column.

    During an incomplete edit only tokenized comments are available: ordinary strings are never promoted
    to docstrings just because the file does not parse.
    """
    lines = text.split('\n')  # the lines Python counts: a form feed or U+2028 does not end one
    kept = [[' '] * len(line) for line in lines]

    def keep(start, end):
        for number in range(start[0], end[0] + 1):
            left = start[1] if number == start[0] else 0
            right = end[1] if number == end[0] else len(lines[number - 1])
            kept[number - 1][left:right] = lines[number - 1][left:right]

    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                keep(token.start, token.end)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # retain comments already identified before the incomplete token
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return [''.join(line) for line in kept]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                value = first.value
                # AST columns are UTF-8 byte offsets; tokenize and Python strings use characters.
                column = lambda row, offset: len(lines[row - 1].encode('utf-8')[:offset].decode('utf-8'))
                keep((value.lineno, column(value.lineno, value.col_offset)),
                     (value.end_lineno, column(value.end_lineno, value.end_col_offset)))
    return [''.join(line) for line in kept]


def source_files(root, include=('.',), exclude=()):
    """The source files under the scanned paths, sorted. A path that does not exist is an error, not an empty scan.

    Nothing at or below an excluded path is read, whatever names it.
    """
    root = Path(root).resolve()
    excluded = [(root / entry).resolve() for entry in exclude]
    left_out = lambda path: any(path == other or other in path.parents for other in excluded)
    found = set()
    for entry in include:
        start = (root / entry).resolve()
        if not start.is_relative_to(root):
            raise ValueError('Scan path escapes the repository root')
        if not start.exists():
            raise ValueError(f'Scan path does not exist: {entry}')
        if left_out(start):
            continue
        if start.is_file():
            found.add(start)
            continue
        for directory, folders, names in os.walk(start):
            here = Path(directory)
            folders[:] = sorted(folder for folder in folders if folder not in SKIPPED_DIRECTORIES and not left_out(here / folder))
            for name in names:
                path = here / name
                if path.suffix in SOURCE_SUFFIXES and path.is_file() and not path.is_symlink() and not left_out(path):
                    found.add(path)
    return root, sorted(found)


def signature(root, include=('.',), exclude=()):
    """What a scan would read, without reading it: a rescan is needed only when this changes."""
    root, found = source_files(root, include, exclude)
    state = []
    for path in found:
        status = path.stat()
        state.append((path.relative_to(root).as_posix(), status.st_size, status.st_mtime_ns))
    return tuple(state)


def scan(root, include=('.',), exclude=()):
    """Every annotation under `root`, as (path, line, symbol, ids, rest) records sorted by path and line.

    Paths are relative to `root`, with forward slashes. Symbols are resolved for Python; elsewhere the
    file and line are the location. The token with no ID after it yields a record with no IDs, and `rest`
    holds what looks like an ID further along the line: `check` reports both.
    """
    root, files = source_files(root, include, exclude)
    found = []
    for path in files:
        if path.stat().st_size > MAX_SOURCE_BYTES:
            continue
        # A BOM would make ast reject the file. A byte that is not UTF-8, such as an accent in a cp1252
        # comment, becomes U+FFFD: skipping the file would lose every annotation in it without a word.
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        if '@req' not in text:
            continue
        lines = text.split('\n')  # read_text already turned \r\n and \r into \n
        python = path.suffix in {'.py', '.pyi'}
        spans = python_symbols(text) if python else []
        annotation_lines = python_annotation_lines(text) if python else lines
        for number, line in enumerate(annotation_lines, 1):
            tokens = list(TOKEN.finditer(line))
            for position, token in enumerate(tokens):
                match = ANNOTATION.match(line, token.start())
                end = tokens[position + 1].start() if position + 1 < len(tokens) else len(line)
                found.append(dict(path=path.relative_to(root).as_posix(), line=number,
                                  symbol=symbol_at(spans, lines, number),
                                  ids=ID.findall(match.group(1)) if match else [],
                                  rest=ID.findall(line[match.end():end]) if match else []))
    return found


def check(spec, annotations):
    """An annotation names at least one object, each held by the release and not retired."""
    nodes = {node['id']: node for node in spec['nodes']}
    others = {item['id'] for section in ('actors', 'imports', 'sources', 'environments', 'flags', 'edges', 'bindings',
                                         'context_assets') for item in spec[section]}
    problems = []
    for annotation in annotations:
        if not annotation['ids']:
            problems.append(dict(code='MALFORMED_ANNOTATION', subject_id=None, path=annotation['path'], line=annotation['line'],
                                 message=f"{annotation['path']}:{annotation['line']} has @req with no ID after it. "
                                         'Write @req REQ-004, with IDs separated by spaces or commas.'))
        # An ID of this release further along the line was meant to be annotated and was not read.
        unread = [target for target in annotation.get('rest', []) if target in nodes or target in others]
        if unread:
            problems.append(dict(code='MALFORMED_ANNOTATION', subject_id=unread[0], path=annotation['path'], line=annotation['line'],
                                 message=f"{annotation['path']}:{annotation['line']} names {', '.join(unread)} after other words, "
                                         'so it was not read. Separate IDs by spaces or commas only.'))
        for target in annotation['ids']:
            status = nodes.get(target, {}).get('status')
            if status in (None, 'retired'):
                code = 'UNKNOWN_ANNOTATION_ID' if status is None else 'RETIRED_ANNOTATION_ID'
                problems.append(dict(code=code, subject_id=target, path=annotation['path'], line=annotation['line'],
                                     message=f"{annotation['path']}:{annotation['line']} names {target}, which this release "
                                             + ('has retired.' if status is not None else 'does not hold.' if target not in others
                                                else 'holds, but not as a node. Annotate a requirement, a constraint or another node.')))
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
        rest, repo, include, exclude = arguments[2:], None, [], []
        while rest:
            if rest[0] == '--repo' and len(rest) > 1:
                repo, rest = rest[1], rest[2:]
            elif rest[0] in ('--include', '--exclude') and len(rest) > 1:
                (include if rest[0] == '--include' else exclude).append(rest[1])
                rest = rest[2:]
            else:
                break
        if not rest:
            annotations = scan(repo, include or ('.',), exclude) if repo else []
            problems = check(spec, annotations)
            for problem in problems:
                print(f"{problem['code']}: {problem['message']}", file=sys.stderr)
            sys.stdout.write(dumps(build(spec, annotations)))
            return 2 if problems else 0
    print('Usage: python3 qa/graph_index.py build <spec.json> [--repo <directory> [--include <path>]... [--exclude <path>]...]',
          file=sys.stderr)
    return 4


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(4)
