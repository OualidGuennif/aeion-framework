"""Reference implementation of the fictional refund ledger on SQLite.

It exists so the example's planned tests can run against a real store. It moves no money, calls no provider
and is not hardened for production. Requirement and constraint IDs refer to ../spec.json.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3

CONSUMING = ('reserved', 'committed')  # DEC-001
FLAG_REMAINING = 'remaining_capacity_report'  # FLAG-001


@dataclass(frozen=True)
class Principal:
    """TERM-005: established by an authentication adapter, never read from a request."""
    verified: bool
    tenant_id: str


@dataclass(frozen=True)
class Result:
    outcome: str
    record_id: str | None = None
    remaining_minor: int | None = None


def authorize(principal, request_tenant, resource_tenant):
    """CON-005: a verified principal whose tenant is both the requested and the owning tenant."""
    return (principal.verified is True and resource_tenant is not None
            and principal.tenant_id == request_tenant == resource_tenant)


def fits(captured_minor, consumed_minor, amount_minor):
    """CON-002: a positive amount within the remaining captured capacity."""
    return amount_minor > 0 and consumed_minor + amount_minor <= captured_minor


def record_outcome(connection, operation_id, operation, outcome):
    """REQ-007: the audit row holds an operation identifier, its kind and its outcome, and nothing else."""
    connection.execute('INSERT INTO audit(operation_id, operation, outcome) VALUES (?, ?, ?)',
                       (str(operation_id)[:64], operation, outcome))


class Ledger:
    """COMP-001. One connection per instance; every operation is one serialized transaction (CTRL-001)."""

    def __init__(self, path, flags=None, timeout=0.0):
        self.connection = sqlite3.connect(path, isolation_level=None, timeout=timeout)
        self.flags = {FLAG_REMAINING: False, **(flags or {})}
        self.hooks = {}  # test injection points: 'after_check', 'after_commit'
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS payments(
                payment_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, captured_minor INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS refunds(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT NOT NULL, key TEXT NOT NULL,
                amount_minor INTEGER NOT NULL, status TEXT NOT NULL, UNIQUE(payment_id, key));
            CREATE TABLE IF NOT EXISTS audit(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL, operation TEXT NOT NULL,
                outcome TEXT NOT NULL);''')

    def close(self):
        self.connection.close()

    def hook(self, name):
        if name in self.hooks:
            self.hooks[name]()

    @contextmanager
    def transaction(self):
        """Take the write lock before reading, so check and write cannot interleave with another writer."""
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise
        self.connection.execute('COMMIT')

    def open_payment(self, tenant_id, payment_id, captured_minor):
        self.connection.execute('INSERT INTO payments VALUES (?, ?, ?)', (payment_id, tenant_id, captured_minor))

    def resource(self, payment_id):
        return self.connection.execute('SELECT tenant_id, captured_minor FROM payments WHERE payment_id = ?',
                                       (payment_id,)).fetchone() or (None, None)

    def consumed_minor(self, payment_id):
        marks = ', '.join('?' for _ in CONSUMING)
        return self.connection.execute(
            f'SELECT COALESCE(SUM(amount_minor), 0) FROM refunds WHERE payment_id = ? AND status IN ({marks})',
            (payment_id, *CONSUMING)).fetchone()[0]

    def run(self, operation, operation_id, body):
        """One audited transaction. A held write lock yields `busy`: nothing was read or written."""
        try:
            with self.transaction():
                result = body()
                record_outcome(self.connection, operation_id, operation, result.outcome)
        except sqlite3.OperationalError as exc:
            if 'locked' in str(exc) or 'busy' in str(exc):
                return Result('busy')
            raise
        self.hook('after_commit')
        return result

    def reserve(self, principal, tenant_id, payment_id, key, amount_minor, operation_id='op'):
        def body():
            owner, captured = self.resource(payment_id)
            if not authorize(principal, tenant_id, owner):
                return Result('denied')  # REQ-004: before any ledger row is read
            existing = self.connection.execute(
                'SELECT seq, amount_minor FROM refunds WHERE payment_id = ? AND key = ?', (payment_id, key)).fetchone()
            if existing is not None:
                if existing[1] == amount_minor:
                    return Result('replayed', f'r-{existing[0]}')  # REQ-002
                return Result('conflict')  # REQ-003
            admitted = fits(captured, self.consumed_minor(payment_id), amount_minor)
            self.hook('after_check')
            if not admitted:
                return Result('rejected')  # REQ-001, DEC-002: no record is written
            cursor = self.connection.execute(
                "INSERT INTO refunds(payment_id, key, amount_minor, status) VALUES (?, ?, ?, 'reserved')",
                (payment_id, key, amount_minor))
            return Result('reserved', f'r-{cursor.lastrowid}')  # REQ-008
        return self.run('reserve', operation_id, body)

    def command(self, kind, principal, tenant_id, payment_id, record_id, operation_id='op'):
        target = dict(cancel='released', commit='committed')[kind]

        def body():
            owner, _ = self.resource(payment_id)
            if not authorize(principal, tenant_id, owner):
                return Result('denied')
            seq = record_id[2:] if isinstance(record_id, str) and record_id.startswith('r-') else ''
            row = self.connection.execute('SELECT status FROM refunds WHERE payment_id = ? AND seq = ?',
                                          (payment_id, int(seq) if seq.isdigit() else -1)).fetchone()
            if row is None:
                return Result('not_found')  # REQ-009
            if row[0] == 'reserved':
                self.connection.execute('UPDATE refunds SET status = ? WHERE seq = ?', (target, int(seq)))
                return Result(target, record_id)  # REQ-005, REQ-006
            return Result('repeated' if row[0] == target else 'refused', record_id)  # REQ-009, DEC-003
        return self.run(kind, operation_id, body)

    def cancel(self, principal, tenant_id, payment_id, record_id, operation_id='op'):
        return self.command('cancel', principal, tenant_id, payment_id, record_id, operation_id)

    def commit(self, principal, tenant_id, payment_id, record_id, operation_id='op'):
        return self.command('commit', principal, tenant_id, payment_id, record_id, operation_id)

    def remaining(self, principal, tenant_id, payment_id, operation_id='op'):
        """REQ-010, behind FLAG-001. With the flag off nothing is read and nothing is disclosed."""
        def body():
            if not self.flags[FLAG_REMAINING]:
                return Result('unavailable')
            owner, captured = self.resource(payment_id)
            if not authorize(principal, tenant_id, owner):
                return Result('denied')
            return Result('reported', remaining_minor=captured - self.consumed_minor(payment_id))
        return self.run('remaining', operation_id, body)

    def snapshot(self, payment_id):
        """Observation adapter: the ledger of one payment in the shape ENV-002 and ENV-003 declare."""
        captured = self.resource(payment_id)[1]
        rows = self.connection.execute(
            'SELECT seq, key, amount_minor, status FROM refunds WHERE payment_id = ? ORDER BY seq', (payment_id,))
        return dict(captured_minor=captured,
                    refunds=[dict(id=f'r-{seq}', key=key, amount_minor=amount, status=status)
                             for seq, key, amount, status in rows])

    def audit_events(self):
        return [dict(operation_id=a, operation=b, outcome=c) for a, b, c in
                self.connection.execute('SELECT operation_id, operation, outcome FROM audit ORDER BY seq')]


def handle(ledger, principal, request):
    """Public entrypoint: one command as a dict in, one result as a dict out. Unknown fields are ignored."""
    text = lambda name: isinstance(request.get(name), str) and 0 < len(request[name]) <= 256
    operation = request.get('operation')
    common = text('tenant_id') and text('payment_id') and text('operation_id')
    if operation == 'reserve' and common and text('key') and type(request.get('amount_minor')) is int:
        result = ledger.reserve(principal, request['tenant_id'], request['payment_id'], request['key'],
                                request['amount_minor'], request['operation_id'])
    elif operation in ('cancel', 'commit') and common and text('record_id'):
        result = ledger.command(operation, principal, request['tenant_id'], request['payment_id'],
                                request['record_id'], request['operation_id'])
    elif operation == 'remaining' and common:
        result = ledger.remaining(principal, request['tenant_id'], request['payment_id'], request['operation_id'])
    else:
        return dict(outcome='invalid')
    return {name: value for name, value in vars(result).items() if value is not None}
