"""The behavior behind both transports: a release store and the snapshots read from it.

Every operation of the contract (AxiomSpec/api/openapi.json) is one method call here. The HTTP routes and
the MCP tools only translate a request into `Service.call` and its result back. Nothing is kept between
requests except files: a second process on the same directory answers the same.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parents[2] / 'AxiomSpec'
sys.path.insert(0, str(PACKAGE / 'qa'))

import approvals  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_diff  # noqa: E402
import release_store  # noqa: E402
from check_package import canonical, digest as digest_of, make_validator  # noqa: E402
from queries import QueryError  # noqa: E402

MODES = ('sandbox', 'organization')
READ = ('listSnapshots', 'getIndex', 'lookup', 'context', 'trace', 'gaps')
ORGANIZATION = ('getProject', 'getRelease', 'putRelease', 'getApprovals', 'putApprovals', 'getVerdict', 'getStatement',
                'compare', 'impact', 'propose')


def not_found(what):
    return QueryError('NOT_FOUND', what, 404)


class Service:
    def __init__(self, store_paths, mode='sandbox', snapshot=None, repository=None, include=('.',)):
        if mode not in MODES:
            raise ValueError('mode is sandbox or organization')
        self.mode, self.paths = mode, [Path(path) for path in store_paths]
        self.repository, self.include = repository, tuple(include)
        self.schemas = {name: make_validator(json.loads((PACKAGE / f'schemas/{name}.schema.json').read_text()))
                        for name in ('spec', 'approvals')}
        self.load()
        self.only = None
        if mode == 'sandbox':
            held = sorted(self.store.releases)
            if snapshot is None and len(held) != 1:
                raise ValueError('Sandbox mode serves one snapshot: name its digest, or supply a store that holds one release')
            self.only = snapshot or held[0]
            if self.only not in self.store.releases:
                raise ValueError('The named snapshot is not in the store')

    def load(self):
        self.store = release_store.load([str(path) for path in self.paths])
        self.snapshots, self.report = {}, None

    # -- reading ---------------------------------------------------------------------------------------------

    def resolve(self, name):
        """The digest a path names. `current` stands for the one snapshot of a sandbox service."""
        if name == 'current':
            if self.only is None:
                raise not_found('`current` names the snapshot of a service that serves exactly one; name a digest')
            return self.only
        if self.only is not None and name != self.only:
            raise not_found('This service serves one snapshot, and it is not that one')
        if name not in self.store.releases and self.mode == 'organization':
            self.load()  # another replica may have added it
        if name not in self.store.releases:
            raise not_found(f'No release with digest {name} is held')
        return name

    def release(self, name):
        """The release a digest names. Resolving may reload the store, so it happens before the store is read."""
        key = self.resolve(name)
        return self.store.releases[key]

    def snapshot(self, name):
        key = self.resolve(name)
        if key not in self.snapshots:
            scanned = graph_index.scan(self.repository, self.include) if self.repository and key == self.only else []
            self.snapshots[key] = queries.Snapshot(self.store.releases[key], scanned, self.repository if key == self.only else None)
        return self.snapshots[key]

    def verify(self):
        if self.report is None:
            self.report = release_store.verify(self.store)
        return self.report

    def verdict(self, key):
        report = self.verify()
        entry = next(release for release in report['releases'] if release['spec_sha256'] == key)
        errors = [error for error in report['errors'] if error['subject'] == key]
        return dict({name: entry[name] for name in ('project_id', 'version', 'spec_sha256', 'status', 'link',
                                                    'comparison', 'approvals', 'imports')}, errors=errors)

    # -- the operations of the contract ----------------------------------------------------------------------

    def call(self, operation, **arguments):
        if operation not in READ + ORGANIZATION:
            raise not_found(f'Unknown operation {operation}')
        if operation in ORGANIZATION and self.mode != 'organization':
            raise QueryError('READ_ONLY', 'This service is read-only: it serves one snapshot to a sandbox', 404)
        return getattr(self, '_' + operation)(**arguments)

    def _listSnapshots(self):
        held = [self.only] if self.only else sorted(self.store.releases)
        rows = [dict(project_id=self.store.releases[key]['project']['id'],
                     version=self.store.releases[key]['release']['version'], spec_sha256=key) for key in held]
        return dict(mode=self.mode, snapshots=sorted(rows, key=lambda row: (row['project_id'], row['version'], row['spec_sha256'])))

    def _getIndex(self, digest='current'):
        return self.snapshot(digest).graph

    def _lookup(self, id, digest='current', detail='brief'):
        return queries.lookup(self.snapshot(digest), id, detail)

    def _context(self, ids, digest='current', scope='direct', budget_bytes=queries.MAX_BYTES, cursor=None):
        return queries.context(self.snapshot(digest), ids, scope, budget_bytes, cursor)

    def _trace(self, digest='current', path=None, symbol=None, id=None, budget_bytes=queries.MAX_BYTES, cursor=None):
        return queries.trace(self.snapshot(digest), path, symbol, id, budget_bytes, cursor)

    def _gaps(self, digest='current', phase='design', budget_bytes=queries.MAX_BYTES, cursor=None):
        return queries.gaps(self.snapshot(digest), phase, budget_bytes, cursor)

    def _getProject(self, project_id):
        report = self.verify()
        project = next((p for p in report['projects'] if p['project_id'] == project_id), None)
        if project is None:
            self.load()
            report = self.verify()
            project = next((p for p in report['projects'] if p['project_id'] == project_id), None)
        if project is None:
            raise not_found(f'No release of {project_id} is held')
        releases = sorted((dict(version=r['version'], spec_sha256=r['spec_sha256'], status=r['status'])
                           for r in report['releases'] if r['project_id'] == project_id),
                          key=lambda r: (release_store.version_tuple(r['version']), r['spec_sha256']))
        return dict(project_id=project_id, releases=releases, head=project['head'],
                    tied_heads=project['tied_heads'], orphaned_heads=project['orphaned_heads'])

    def _getRelease(self, digest):
        return self.release(digest)

    def _getApprovals(self, digest):
        key = self.resolve(digest)
        return self.store.approvals.get(key) or approvals.empty(self.store.releases[key])

    def _getVerdict(self, digest):
        return self.verdict(self.resolve(digest))

    def _getStatement(self, digest, actor, key):
        spec = self.release(digest)
        previous = spec['release']['previous']
        governing = spec if previous is None else self.store.releases.get(previous['spec_sha256'])
        if governing is None:
            raise not_found('The baseline that governs this release is not held')
        declared = next((k for k in governing['approval']['keys'] if k['id'] == key), None)
        if declared is None:
            raise not_found(f'The governing release declares no key {key}')
        message = approvals.statement(spec, actor, declared['id'], declared['method'])
        return dict(statement=message.decode('utf-8'), sha256=digest_of(message), webauthn_challenge=approvals.challenge(message))

    def _compare(self, baseline, candidate):
        return release_diff.compare(self.release(baseline), self.release(candidate))

    def _impact(self, baseline, candidate):
        before, after = self.release(baseline), self.release(candidate)
        return release_store.impact(self.store, before, after)

    def _propose(self, baseline, version, operations):
        result = queries.propose(self.release(baseline), version, operations)
        if not result['schema_errors']:
            self.hold(result['candidate'], f"{result['spec_sha256']}.json")
        return result

    def _putRelease(self, digest, body):
        if not isinstance(body, dict) or digest_of(canonical(body)) != digest:
            raise QueryError('DIGEST_MISMATCH', 'The body is not the release this digest names', 409)
        problems = sorted(error.message[:200] for error in self.schemas['spec'].iter_errors(body))
        if problems:
            raise QueryError('INVALID_DOCUMENT', '; '.join(problems[:5]), 422)
        self.hold(body, f'{digest}.json')
        return self.verdict(digest)

    def _putApprovals(self, digest, body):
        key = self.resolve(digest)
        problems = sorted(error.message[:200] for error in self.schemas['approvals'].iter_errors(body))
        if problems:
            raise QueryError('INVALID_DOCUMENT', '; '.join(problems[:5]), 422)
        spec = self.store.releases[key]
        if (body['spec_sha256'], body['project_id'], body['version']) != (key, spec['project']['id'], spec['release']['version']):
            raise QueryError('DIGEST_MISMATCH', 'The approvals name another release', 409)
        self.store.add_approvals(body)
        self.write(f'{key}.approvals.json', self.store.approvals[key])
        self.report = None
        return self.verdict(key)

    # -- writing ---------------------------------------------------------------------------------------------

    def hold(self, spec, name):
        key = digest_of(canonical(spec))
        if key not in self.store.releases:
            self.store.add_release(spec, name)
            self.write(name, spec)
            self.report = None

    def write(self, name, document):
        """Write one content-named file atomically into the first store directory."""
        directory = next((path for path in self.paths if path.is_dir()), None)
        if directory is None:
            raise QueryError('READ_ONLY', 'The store has no directory to write to', 404)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=directory, prefix='.incoming-', suffix='.tmp', delete=False) as stream:
            stream.write(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            temporary = stream.name
        os.replace(temporary, directory / name)
