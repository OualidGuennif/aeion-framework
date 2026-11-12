"""The behavior behind both transports: a release store and the snapshots read from it.

Every specification operation of the contract (AxiomSpec/api/openapi.json) is one method call here.
HTTP and MCP translate those calls; transport limits and health probes stay in the application layer.

Nothing is kept between requests except files. Files are named by their content and never rewritten, so a
write by one process cannot undo a write by another, and before each request the service takes in the
files that appeared since the last one: a second process on the same directory answers the same.
"""
import os
import errno
from itertools import islice
from pathlib import Path
import shutil
import sys
import tempfile
import threading

PACKAGE = Path(__file__).resolve().parents[2] / 'AxiomSpec'
sys.path.insert(0, str(PACKAGE / 'qa'))

import approvals  # noqa: E402
import graph_index  # noqa: E402
import queries  # noqa: E402
import release_diff  # noqa: E402
import release_store  # noqa: E402
import spec_parts  # noqa: E402
from check_package import BOUNDS, canonical, digest as digest_of, reference_errors, strict_json  # noqa: E402
from queries import QueryError  # noqa: E402
from run_checks import EDITION  # noqa: E402

MODES = ('sandbox', 'organization')
READ = ('listSnapshots', 'getIndex', 'lookup', 'context', 'trace', 'gaps')
ORGANIZATION = ('getProject', 'getRelease', 'putRelease', 'getApprovals', 'putApprovals', 'getVerdict', 'getStatement',
                'compare', 'impact', 'propose')
MAX_BODY_BYTES = BOUNDS['max_input_bytes']  # one file of the store: what is accepted must be readable back
UMASK = os.umask(0)
os.umask(UMASK)


def not_found(what):
    return QueryError('NOT_FOUND', what, 404)


class Service:
    def __init__(self, store_paths, mode='sandbox', snapshot=None, repository=None, include=('.',), exclude=(), lock_timeout=1):
        if mode not in MODES:
            raise ValueError('mode is sandbox or organization')
        self.mode, self.paths = mode, [Path(path).resolve() for path in store_paths]
        if lock_timeout < 0:
            raise ValueError('lock_timeout must not be negative')
        self.lock_timeout = lock_timeout
        self.repository, self.include, self.exclude = repository, tuple(include), tuple(exclude)
        self.lock = threading.RLock()  # one operation at a time: the store is replaced as a whole when it changes
        self.store, self.seen = release_store.Store(), {}
        self.snapshots, self.report = {}, None
        self.refresh()
        self.only, self.reads_code = None, False
        self.annotations, self.scanned = [], None
        if mode == 'sandbox':
            held = sorted(self.store.releases)
            if snapshot is None and len(held) != 1:
                raise ValueError('Sandbox mode serves one snapshot: name its digest, or supply a store that holds one release')
            self.only = snapshot or held[0]
            if self.only not in self.store.releases:
                raise ValueError('The named snapshot is not in the store')
            if repository is not None:
                # Scanned now, so a path that does not exist stops the service instead of serving an empty index.
                self.reads_code = True
                self.scanned = graph_index.signature(repository, self.include, self.exclude)
                self.annotations = graph_index.scan(repository, self.include, self.exclude)

    def refresh(self):
        """Take in the store files that appeared since the last request.

        A file never changes once written, so reading the new ones is all it takes to agree with another
        process. A new file may be what a rejected one was waiting for (the missing part of a release), so
        the rejected files are read again with it, and only those. A file that changed or went away rebuilds
        the store from what is there.
        """
        listed = release_store.listing(self.paths)
        for dependencies in self.store.dependencies.values():
            for name in dependencies:
                file = Path(name)
                if file not in listed:
                    try:
                        state = file.stat()
                        listed[file] = (state.st_size, state.st_mtime_ns)
                    except OSError:
                        listed[file] = None
        present = {file: state for file, state in listed.items() if state is not None}
        new = [file for file in present if file not in self.seen]
        changed = any(present.get(file) != state for file, state in self.seen.items())
        if changed:
            self.store, self.seen, new = release_store.Store(), {}, list(present)
        elif new and self.store.rejected:
            again = [Path(rejected['path']) for rejected in self.store.rejected]
            self.store.rejected = []
            new += [file for file in again if file in present]
        for file in new:
            try:
                release_store.add_file(self.store, file)
            except OSError:
                continue  # gone since it was listed; the next request sees what is there
            self.seen[file] = present[file]
            for name in self.store.dependencies.get(file.as_posix(), []):
                dependency = Path(name)
                if dependency not in self.seen:
                    try:
                        state = dependency.stat()
                        self.seen[dependency] = (state.st_size, state.st_mtime_ns)
                    except OSError:
                        pass  # a missing part stays watched and will be retried when it arrives
        if new or changed:
            self.report = None

    # -- reading ---------------------------------------------------------------------------------------------

    def resolve(self, name):
        """The digest a path names. `current` stands for the one snapshot of a sandbox service."""
        if not isinstance(name, str):
            raise QueryError('INVALID_PARAMETER', 'A release is named by its digest')
        if name == 'current':
            if self.only is None:
                raise not_found('`current` names the snapshot of a service that serves exactly one; name a digest')
            return self.only
        if self.only is not None and name != self.only:
            raise not_found('This service serves one snapshot, and it is not that one')
        if name not in self.store.releases:
            raise not_found(f'No release with digest {name} is held')
        return name

    def release(self, name):
        return self.store.releases[self.resolve(name)]

    def checked_release(self, name):
        spec = self.release(name)
        problems = reference_errors(spec)
        if problems:
            raise QueryError('INVALID_DOCUMENT', 'The release has invalid references: ' + ', '.join(problems), 422)
        return spec

    def snapshot(self, name, code=True):
        """The snapshot a digest names. `code` is false for a query that reads the release alone: the code is not looked at."""
        key = self.resolve(name)
        local = self.reads_code and key == self.only
        if local and code:
            try:
                state = graph_index.signature(self.repository, self.include, self.exclude)
                if state != self.scanned:  # the code changed: read its annotations again
                    self.annotations, self.scanned = graph_index.scan(self.repository, self.include, self.exclude), state
                    self.snapshots.pop(key, None)
            except (ValueError, OSError) as exc:
                raise QueryError('CODE_UNAVAILABLE', 'The current code scan is unavailable; retry after restoring '
                                 'the included paths and read access.', 503) from exc
        if key not in self.snapshots:
            self.snapshots[key] = queries.Snapshot(self.checked_release(key), self.annotations if local else [],
                                                   self.repository if local else None, self.scanned if local else None)
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

    def governing(self, spec):
        """The release whose policy and keys govern the approvals of `spec`, or None when it is not held."""
        previous = spec['release']['previous']
        return spec if previous is None else self.store.releases.get(previous['spec_sha256'])

    # -- the operations of the contract ----------------------------------------------------------------------

    def call(self, operation, **arguments):
        if operation not in READ + ORGANIZATION:
            raise not_found(f'Unknown operation {operation}')
        if operation in ORGANIZATION and self.mode != 'organization':
            raise QueryError('READ_ONLY', 'This service is read-only: it serves one snapshot to a sandbox', 404)
        if not self.lock.acquire(timeout=self.lock_timeout):
            raise QueryError('STORE_BUSY', 'This worker is processing another operation; retry with backoff.', 503)
        try:
            # New files cannot change a held immutable read. Avoid a directory scan on the hot path;
            # inventories, approvals, verdicts and writes still refresh, and a missing digest refreshes once.
            pinned = operation in ('getIndex', 'lookup', 'context', 'trace', 'gaps', 'getRelease')
            held = self.unchanged(arguments.get('digest')) if pinned else False
            compared = operation == 'compare' and all(self.unchanged(arguments.get(name)) for name in ('baseline', 'candidate'))
            if self.mode == 'organization' and not ((pinned and held) or compared):
                if not self.ready():
                    raise QueryError('STORAGE_UNAVAILABLE', 'The configured store is not accessible.', 503)
                self.refresh()
            return getattr(self, '_' + operation)(**arguments)
        except OSError as exc:
            raise QueryError('STORAGE_UNAVAILABLE', 'The store operation could not complete; retry after restoring storage.', 503) from exc
        finally:
            self.lock.release()

    def unchanged(self, key):
        """Check only the source(s) of this digest, rather than listing unrelated releases."""
        for name in self.store.paths.get(key, []):
            try:
                for source in self.store.dependencies[name]:
                    file = Path(source)
                    state = file.stat()
                    if (state.st_size, state.st_mtime_ns) != self.seen.get(file):
                        break
                else:
                    return True
            except OSError:
                continue
        return False

    def ready(self):
        """A cheap access probe, independent of the operation lock; not a full store-verification claim."""
        if not self.paths or not all(path.exists() and os.access(path, os.R_OK | (os.X_OK if path.is_dir() else 0)) for path in self.paths):
            return False
        directory = next((path for path in self.paths if path.is_dir()), None)
        return self.mode != 'organization' or directory is None or os.access(directory, os.W_OK | os.X_OK)

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
        return queries.context(self.snapshot(digest, code=False), ids, scope, budget_bytes, cursor)

    def _trace(self, digest='current', path=None, symbol=None, id=None, budget_bytes=queries.MAX_BYTES, cursor=None):
        return queries.trace(self.snapshot(digest), path, symbol, id, budget_bytes, cursor)

    def _gaps(self, digest='current', phase='design', budget_bytes=queries.MAX_BYTES, cursor=None):
        return queries.gaps(self.snapshot(digest), phase, budget_bytes, cursor)

    def _getProject(self, project_id):
        report = self.verify()
        project = next((p for p in report['projects'] if p['project_id'] == project_id), None)
        if project is None:
            raise not_found(f'No release of {project_id} is held')
        releases = sorted((dict(version=r['version'], spec_sha256=r['spec_sha256'], status=r['status'])
                           for r in report['releases'] if r['project_id'] == project_id),
                          key=lambda r: (release_store.version_tuple(r['version']), r['spec_sha256']))
        return dict(project_id=project_id, releases=releases, head=project['head'], accepted_head=project['accepted_head'],
                    tied_heads=project['tied_heads'], orphaned_heads=project['orphaned_heads'])

    def _getRelease(self, digest):
        return self.release(digest)

    def _getApprovals(self, digest):
        """The approvals of a release that count. Without the release that governs them, all that were offered."""
        key = self.resolve(digest)
        spec = self.store.releases[key]
        held = self.store.approvals_of(key) or approvals.empty(spec)
        governing = self.governing(spec)
        return held if governing is None else dict(held, approvals=approvals.counted(spec, held, governing))

    def _getVerdict(self, digest):
        return self.verdict(self.resolve(digest))

    def _getStatement(self, digest, actor, key):
        spec = self.release(digest)
        governing = self.governing(spec)
        if governing is None:
            raise not_found('The baseline that governs this release is not held')
        declared = next((k for k in governing['approval']['keys'] if k['id'] == key), None)
        if declared is None:
            raise not_found(f'The governing release declares no key {key}')
        if actor not in {a['id'] for a in governing['actors']}:
            raise not_found(f'The governing release declares no actor {actor}')
        message = approvals.statement(spec, actor, declared['id'], declared['method'])
        return dict(statement=message.decode('utf-8'), sha256=digest_of(message), webauthn_challenge=approvals.challenge(message))

    def _compare(self, baseline, candidate):
        return release_diff.compare(self.checked_release(baseline), self.checked_release(candidate))

    def _impact(self, baseline, candidate):
        before, after = self.checked_release(baseline), self.checked_release(candidate)
        return release_store.impact(self.store, before, after, self.verify())

    def _propose(self, baseline, version, operations):
        result = queries.propose(self.checked_release(baseline), version, operations)
        if result['status'] == 'pass':
            # Only a candidate that passes its own checks enters the store. A refused one is returned to its
            # author and leaves the store, its heads and its verdict as they were.
            result['held'] = self.hold(result['candidate']) in self.store.releases
        return result

    def _putRelease(self, digest, body):
        try:
            named = digest_of(canonical(body)) if isinstance(body, dict) else None
        except ValueError:
            named = None
        if named != digest:
            raise QueryError('DIGEST_MISMATCH', 'The body is not the release this digest names', 409)
        spec_validator, _ = release_store.validators()
        problems = sorted(error.message[:200] for error in islice(spec_validator.iter_errors(body), 5))
        if problems:
            raise QueryError('INVALID_DOCUMENT', '; '.join(problems[:5]), 422)
        self.hold(body)
        return self.verdict(digest)

    def _putApprovals(self, digest, body):
        key = self.resolve(digest)
        _, approvals_validator = release_store.validators()
        problems = sorted(error.message[:200] for error in islice(approvals_validator.iter_errors(body), 5))
        if problems:
            raise QueryError('INVALID_DOCUMENT', '; '.join(problems[:5]), 422)
        spec = self.store.releases[key]
        if (body['spec_sha256'], body['project_id'], body['version']) != (key, spec['project']['id'], spec['release']['version']):
            raise QueryError('DIGEST_MISMATCH', 'The approvals name another release', 409)
        document, governing = body, self.governing(spec)
        if governing is not None:
            # With the governing release at hand, only approvals that verify are kept. Without it they are
            # kept as offered, and the verdict sets aside what does not verify once the baseline arrives.
            kept = approvals.counted(spec, body, governing)
            if body['approvals'] and not kept:
                raise QueryError('NO_VALID_APPROVAL', 'No approval in the body verifies under the governing release', 422)
            document = dict(body, approvals=kept)
        document = approvals.merge(document, document)
        if document['approvals']:
            raw = self.readable(document)
            # Named by its own content: two processes that receive different approvals write different files,
            # and the store reads their union.
            self.place(self.directory() / f'{key}.approvals.{digest_of(raw)}.json', raw)
            self.refresh()
        return self.verdict(key)

    # -- writing ---------------------------------------------------------------------------------------------

    def directory(self):
        directory = next((path for path in self.paths if path.is_dir()), None)
        if directory is None:
            raise QueryError('READ_ONLY', 'The store has no directory to write to', 404)
        return directory

    @staticmethod
    def readable(document):
        """The bytes the store holds for a document, refused unless the store reads exactly them back.

        Canonical form with `format` moved first: a copy cut short still says what it was, so the store
        reports it as a broken file instead of ignoring it as a file of another format.
        """
        try:
            rest = {name: value for name, value in document.items() if name != 'format'}
            raw = canonical({'format': document['format']})[:-1] + b',' + canonical(rest)[1:]
            strict_json(raw)
        except ValueError as exc:
            raise QueryError('INVALID_DOCUMENT', f'The store cannot hold this document: {exc}', 422)
        return raw

    def hold(self, spec):
        """Keep a release under its digest: one canonical file, or parts when it exceeds one file (AX-M-022)."""
        key = digest_of(canonical(spec))
        if key in self.store.releases:
            for name in self.store.paths[key]:
                for source in self.store.dependencies[name]:
                    with Path(source).open('rb') as stream:
                        os.fsync(stream.fileno())
                self.sync_directory(Path(name).parent)
                if len(self.store.dependencies[name]) > 1:
                    self.sync_directory(Path(name).parent.parent)
            return key
        directory = self.directory()
        if len(canonical(spec)) <= MAX_BODY_BYTES:
            self.place(directory / f'{key}.json', self.readable(spec))
        else:
            try:
                for part in spec_parts.split(spec):
                    strict_json(canonical(part))
                staging = Path(tempfile.mkdtemp(dir=directory, prefix='.incoming-'))
                try:
                    spec_parts.write(spec, staging / 'parts', stem=key)
                    for file in (staging / 'parts').iterdir():
                        with file.open('rb') as stream:
                            os.fsync(stream.fileno())
                    self.sync_directory(staging / 'parts')
                    try:
                        os.rename(staging / 'parts', directory / f'{key}.parts')
                    except OSError as exc:
                        if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                            raise
                    self.sync_directory(directory)
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
            except ValueError as exc:
                raise QueryError('INVALID_DOCUMENT', f'The store cannot hold this document: {exc}', 422)
        self.refresh()
        if key not in self.store.releases:  # the write did not land, or the store rejected what was written
            raise QueryError('INTERNAL_ERROR', 'The store did not keep the release', 500)
        return key

    @staticmethod
    def sync_directory(directory):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def place(path, raw):
        """Write one content-named file atomically. A reader sees the whole file or none of it.

        A file that already holds these bytes is left alone: rewriting it would change its modification time
        and make every process that shares the store read the whole store again.
        """
        try:
            if path.read_bytes() == raw:
                with path.open('rb') as stream:
                    os.fsync(stream.fileno())
                Service.sync_directory(path.parent)
                return
        except OSError:
            pass
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('wb', dir=path.parent, prefix='.incoming-', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fchmod(stream.fileno(), 0o666 & ~UMASK)
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # complete publication without overwriting another writer
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise QueryError('STORE_CONFLICT', 'A content-named file already holds different bytes.', 409)
            Service.sync_directory(path.parent)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
