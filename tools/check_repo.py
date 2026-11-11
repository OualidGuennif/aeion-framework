#!/usr/bin/env python3
"""Check what the package QA cannot see: the root README and the playbooks.

The AxiomSpec package checks itself (AxiomSpec/qa/run_checks.py) and must stay
self-contained, so it never reads its parent folder. This script reuses the
package's checker functions on the files around it. It writes nothing.

Run from anywhere, with the package's QA dependencies installed:
    python3 tools/check_repo.py
"""
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'AxiomSpec' / 'qa'))
import check_package as qa  # noqa: E402
from run_checks import EDITION  # noqa: E402

# A link the playbook cites and the repository does not publish. Named here so that it
# stays one known exception instead of a reason to stop checking links.
UNPUBLISHED = {'../research/auto-ontology-comparison-2026-11-09.md'}
LINK = re.compile(r'\[[^\]]+\]\(([^)\s]+)\)')


def slug(heading):
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r'[^a-z0-9 \-]', '', heading.strip().lower()).replace(' ', '-')


def outside_fences(text):
    """The document without fenced blocks: a template inside a fence is an example, not a link."""
    kept, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith('```'):
            fenced = not fenced
        elif not fenced:
            kept.append(line)
    return '\n'.join(kept)


def check_document(path, validator):
    problems = []
    text = path.read_text(encoding='utf-8')
    if sum(line.lstrip().startswith('```') for line in text.splitlines()) % 2:
        return [f'{path.relative_to(REPO)}: unclosed code fence']
    prose = outside_fences(text)
    anchors = {slug(h) for h in re.findall(r'^#+ (.+)$', prose, re.M)}
    for destination in LINK.findall(prose):
        if destination.startswith(('https://', 'http://', 'mailto:')):
            continue
        if destination.startswith('#'):
            if destination[1:] not in anchors:
                problems.append(f'{path.relative_to(REPO)}: no heading for {destination}')
            continue
        if destination in UNPUBLISHED:
            if (path.parent / destination).exists():
                problems.append(f'{path.relative_to(REPO)}: {destination} now exists; remove it from UNPUBLISHED')
            continue
        try:
            qa.check_local_link(path, destination, root=REPO)
        except ValueError as error:
            problems.append(f'{path.relative_to(REPO)}: {error}')
    for block in re.findall(r'```json\s*\n(.*?)\n```', text, re.S):
        try:
            document = qa.strict_json(block.encode('utf-8'))
        except ValueError as error:
            problems.append(f'{path.relative_to(REPO)}: JSON example is not strict JSON ({error})')
            continue
        if isinstance(document, dict) and str(document.get('format', '')).startswith('axiomspec/'):
            # A specification printed in a guide is copied by readers: it must be one the package accepts.
            problems += [f'{path.relative_to(REPO)}: specification example: {e.message[:120]}'
                         for e in validator.iter_errors(document)]
            if validator.is_valid(document):
                problems += [f'{path.relative_to(REPO)}: specification example: {code}'
                             for code in qa.reference_errors(document)]
    return problems


def main():
    validator = qa.make_validator(qa.read('schemas/spec.schema.json'), check_formats=True)
    documents = [REPO / 'README.md', *sorted((REPO / 'playbooks').glob('*.md'))]
    problems = [problem for document in documents for problem in check_document(document, validator)]
    stated = set(re.findall(r'edition (\d+\.\d+\.\d+)', (REPO / 'README.md').read_text(encoding='utf-8')))
    if EDITION not in stated:
        problems.append(f'README.md: does not name the package edition {EDITION}')
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f'{len(documents)} documents checked around the package, edition {EDITION}: '
          f"{'no problem' if not problems else str(len(problems)) + ' problem(s)'}")
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
