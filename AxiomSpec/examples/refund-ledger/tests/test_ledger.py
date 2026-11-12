"""Executed tests of the reference ledger. One class per TestCase in ../spec.json, bound by class name.

Every expectation comes from a requirement, a decision or a scenario of the specification. Where the
specification states a predicate, the test evaluates that predicate on observations read back from the store,
so the formula and the implementation are checked against each other, not against the test author's memory.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import threading
import unittest

EXAMPLE = Path(__file__).resolve().parents[1]
PACKAGE = EXAMPLE.parents[1]
sys.path[:0] = [str(EXAMPLE / 'app'), str(PACKAGE / 'qa')]

import check_package as qa  # noqa: E402  reference evaluator and schema validation
from ledger import FLAG_REMAINING, Ledger, Principal, authorize, fits, handle  # noqa: E402

SPEC = qa.read('examples/refund-ledger/spec.json')
NODES = {n['id']: n for n in SPEC['nodes']}
ENVIRONMENTS = {e['id']: e for e in SPEC['environments']}
TENANT, PAYMENT = 'tenant-demo', 'pay-demo'
OWNER, STRANGER, UNVERIFIED = Principal(True, TENANT), Principal(True, 'tenant-other'), Principal(False, TENANT)


def holds(constraint_id, observation):
    """Evaluate a specification predicate on an observation that fits its declared environment."""
    data = NODES[constraint_id]['data']
    qa.make_validator(ENVIRONMENTS[data['environment_id']]['schema']).validate(observation)
    return qa.ReferenceEvaluator().evaluate(data['expression'], observation)


class NonAtomicLedger(Ledger):
    """Mutant: capacity check and write are separate autocommitted statements."""

    @contextmanager
    def transaction(self):
        yield


class LedgerCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='refund-ledger-')
        self.addCleanup(directory.cleanup)
        self.path = str(Path(directory.name) / 'ledger.sqlite3')
        self.ledger = self.open()
        self.ledger.open_payment(TENANT, PAYMENT, 1000)

    def open(self, cls=Ledger, **options):
        ledger = cls(self.path, **options)
        self.addCleanup(ledger.close)
        return ledger

    def snapshot_observation(self, key='k', amount=1, principal=OWNER, request_tenant=TENANT, resource_tenant=TENANT):
        """ENV-001: the ledger, one request and the authentication result."""
        return dict(state=dict(tenant_id=resource_tenant, payment_id=PAYMENT, currency='EUR', **self.ledger.snapshot(PAYMENT)),
                    input=dict(tenant_id=request_tenant, key=key, amount_minor=amount),
                    auth=dict(verified=principal.verified, tenant_id=principal.tenant_id))

    def attempt(self, key, amount, principal=OWNER, tenant=TENANT):
        """Reserve through the store and assert both ENV-002 predicates on what was really written."""
        before = self.ledger.snapshot(PAYMENT)
        result = self.ledger.reserve(principal, tenant, PAYMENT, key, amount)
        observation = dict(before=before, after=self.ledger.snapshot(PAYMENT),
                           request=dict(key=key, amount_minor=amount, outcome=result.outcome))
        self.assertTrue(holds('CON-007', observation), observation)
        self.assertTrue(holds('CON-008', observation), observation)
        return result

    def command(self, kind, record_id, principal=OWNER, tenant=TENANT):
        """Cancel or commit through the store and assert both ENV-003 predicates."""
        before = self.ledger.snapshot(PAYMENT)
        result = self.ledger.command(kind, principal, tenant, PAYMENT, record_id)
        observation = dict(before=before, after=self.ledger.snapshot(PAYMENT),
                           command=dict(kind=kind, record_id=record_id, outcome=result.outcome))
        self.assertTrue(holds('CON-009', observation), observation)
        self.assertTrue(holds('CON-010', observation), observation)
        return result

    def raw_row(self, key, amount, status):
        self.ledger.connection.execute(
            'INSERT INTO refunds(payment_id, key, amount_minor, status) VALUES (?, ?, ?, ?)', (PAYMENT, key, amount, status))

    def statuses(self):
        return {r['key']: r['status'] for r in self.ledger.snapshot(PAYMENT)['refunds']}


class Test001CapacityAggregation(LedgerCase):
    def test_reserved_and_committed_consume_and_released_does_not(self):
        self.attempt('a', 300)
        self.command('commit', self.attempt('b', 400).record_id)
        self.command('cancel', self.attempt('c', 200).record_id)
        self.assertEqual(self.statuses(), dict(a='reserved', b='committed', c='released'))
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 700)
        self.assertTrue(holds('CON-001', self.snapshot_observation()))

    def test_over_consumed_state_is_detected(self):
        # SCN-002: such a state cannot be reached through the API, so it is written directly.
        self.raw_row('a', 600, 'reserved')
        self.raw_row('b', 401, 'committed')
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 1001)
        self.assertFalse(holds('CON-001', self.snapshot_observation()))


class Test002AdmissionGuard(LedgerCase):
    def test_guard_agrees_with_the_specified_formula_at_the_boundaries(self):
        self.raw_row('held', 600, 'reserved')
        for amount, expected in [(400, True), (401, False), (1, True), (0, False)]:
            with self.subTest(amount=amount):
                self.assertIs(fits(1000, 600, amount), expected)
                self.assertIs(holds('CON-002', self.snapshot_observation(amount=amount)), expected)
        self.assertIs(fits(1000, 600, -1), False)
        self.assertIs(fits(1000, 0, 1000), True)
        self.assertIs(fits(1000, 0, 1001), False)


class Test003PositiveAmounts(LedgerCase):
    def test_zero_and_negative_requests_are_refused_without_a_record(self):
        self.assertEqual(self.attempt('zero', 0).outcome, 'rejected')
        self.assertEqual(self.ledger.reserve(OWNER, TENANT, PAYMENT, 'negative', -5).outcome, 'rejected')
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'], [])
        self.assertEqual(self.attempt('one', 1).outcome, 'reserved')
        self.assertTrue(holds('CON-003', self.snapshot_observation()))

    def test_zero_amount_row_is_detected(self):
        self.raw_row('zero', 0, 'reserved')  # SCN-004
        self.assertFalse(holds('CON-003', self.snapshot_observation()))


class Test004DuplicateKeys(LedgerCase):
    def test_store_refuses_a_second_row_for_one_key(self):
        self.attempt('a', 100)
        with self.assertRaises(sqlite3.IntegrityError):
            self.raw_row('a', 100, 'reserved')
        self.assertTrue(holds('CON-004', self.snapshot_observation()))

    def test_duplicate_observation_is_detected(self):
        self.assertFalse(holds('CON-004', NODES['SCN-005']['data']['given']))


class Test005PrincipalGuard(LedgerCase):
    def test_guard_agrees_with_the_specified_formula(self):
        cases = [(OWNER, TENANT, TENANT, True), (UNVERIFIED, TENANT, TENANT, False),
                 (OWNER, 'tenant-other', TENANT, False),        # SCN-006: request names another tenant
                 (STRANGER, 'tenant-other', TENANT, False)]     # SCN-009: the ledger belongs to another tenant
        for principal, request_tenant, resource_tenant, expected in cases:
            with self.subTest(principal=principal, request=request_tenant):
                self.assertIs(authorize(principal, request_tenant, resource_tenant), expected)
                observation = self.snapshot_observation(principal=principal, request_tenant=request_tenant,
                                                        resource_tenant=resource_tenant)
                self.assertIs(holds('CON-005', observation), expected)
        self.assertIs(authorize(OWNER, TENANT, None), False)  # unknown payment


class Test006CapacityProperty(LedgerCase):
    def test_seeded_sequences_keep_the_invariants_after_every_operation(self):
        seen = set()
        for seed in range(5):
            source = random.Random(7000 + seed)
            self.ledger.connection.execute('DELETE FROM refunds WHERE payment_id = ?', (PAYMENT,))
            for _ in range(120):
                choice = source.random()
                if choice < 0.6:
                    result = self.attempt(f'k{source.randrange(25)}', source.choice([0, 50, 100, 200, 400]))
                else:
                    rows = self.ledger.snapshot(PAYMENT)['refunds']
                    record = source.choice(rows)['id'] if rows and source.random() < 0.9 else 'r-999999'
                    result = self.command(source.choice(['cancel', 'commit']), record)
                seen.add(result.outcome)
                self.assertLessEqual(self.ledger.consumed_minor(PAYMENT), 1000)
                observation = self.snapshot_observation()
                for constraint in ('CON-001', 'CON-003', 'CON-004'):
                    self.assertTrue(holds(constraint, observation), (seed, constraint))
        # The sequences are not vacuous: every outcome of both operations occurred.
        self.assertEqual(seen, {'reserved', 'rejected', 'replayed', 'conflict', 'released', 'committed',
                                'repeated', 'refused', 'not_found'})


class Test007ConcurrentReservations(LedgerCase):
    def interleave(self, first):
        """Run a second reservation inside the first one's critical section, after its capacity check."""
        second, inside = self.open(), []
        first.hooks['after_check'] = lambda: inside.append(second.reserve(OWNER, TENANT, PAYMENT, 'b', 600))
        outer = first.reserve(OWNER, TENANT, PAYMENT, 'a', 600)
        return outer, inside[0], second

    def test_second_writer_inside_the_critical_section_is_turned_away(self):
        outer, inner, second = self.interleave(self.ledger)
        self.assertEqual((outer.outcome, inner.outcome), ('reserved', 'busy'))
        self.assertEqual(second.reserve(OWNER, TENANT, PAYMENT, 'b', 600).outcome, 'rejected')
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 600)
        self.assertTrue(holds('CON-001', self.snapshot_observation()))

    def test_a_reader_blocking_commit_rolls_back_and_the_connection_can_retry(self):
        reader = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(reader.close)
        reader.execute('BEGIN')
        reader.execute('SELECT * FROM payments').fetchall()
        try:
            # The writer can begin and insert; the reader blocks its commit.
            self.assertEqual(self.ledger.reserve(OWNER, TENANT, PAYMENT, 'a', 600).outcome, 'busy')
            self.assertFalse(self.ledger.connection.in_transaction)
            self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'], [])
            self.assertEqual(self.ledger.audit_events(), [])
        finally:
            reader.rollback()
        self.assertEqual(self.attempt('a', 600).outcome, 'reserved')
        self.assertEqual(self.open().reserve(OWNER, TENANT, PAYMENT, 'b', 400).outcome, 'reserved')
        self.assertEqual(len(self.ledger.audit_events()), 2)

    def test_same_interleaving_overbooks_a_non_atomic_ledger(self):
        # Test effectiveness: without one transaction around check and write, this test must fail.
        outer, inner, _ = self.interleave(self.open(NonAtomicLedger))
        self.assertEqual((outer.outcome, inner.outcome), ('reserved', 'reserved'))
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 1200)
        self.assertFalse(holds('CON-001', self.snapshot_observation()))

    def test_two_threads_admit_exactly_one(self):
        barrier, outcomes = threading.Barrier(2), []

        def worker(key):
            ledger = Ledger(self.path, timeout=30.0)
            try:
                barrier.wait(timeout=30)
                outcomes.append(ledger.reserve(OWNER, TENANT, PAYMENT, key, 600).outcome)
            finally:
                ledger.close()
        threads = [threading.Thread(target=worker, args=(key,)) for key in ('a', 'b')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertEqual(sorted(outcomes), ['rejected', 'reserved'])
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 600)


class Test008IdenticalRetry(LedgerCase):
    def test_retry_returns_the_same_record_and_adds_nothing(self):
        first = self.attempt('a', 400)
        again = self.attempt('a', 400)
        self.assertEqual((first.outcome, again.outcome), ('reserved', 'replayed'))
        self.assertEqual(again.record_id, first.record_id)
        self.assertEqual(len(self.ledger.snapshot(PAYMENT)['refunds']), 1)

    def test_retry_after_a_lost_response_finds_the_persisted_record(self):
        def lose_response():
            raise ConnectionError('response lost after commit')
        self.ledger.hooks['after_commit'] = lose_response
        with self.assertRaises(ConnectionError):
            self.ledger.reserve(OWNER, TENANT, PAYMENT, 'a', 400)
        del self.ledger.hooks['after_commit']
        self.assertEqual(self.attempt('a', 400).outcome, 'replayed')
        self.assertEqual(len(self.ledger.snapshot(PAYMENT)['refunds']), 1)


class Test009ConflictingRetry(LedgerCase):
    def test_conflicting_payload_is_refused_and_the_original_is_intact(self):
        first = self.attempt('a', 400)
        self.assertEqual(self.attempt('a', 500).outcome, 'conflict')
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'],
                         [dict(id=first.record_id, key='a', amount_minor=400, status='reserved')])


class EntrypointCase(LedgerCase):
    def send(self, principal=OWNER, **request):
        request = dict(dict(tenant_id=TENANT, payment_id=PAYMENT, operation_id='op-1'), **request)
        return handle(self.ledger, principal, request)


class Test010EntrypointReserveCommit(EntrypointCase):
    def test_reserve_commit_and_refuse_within_capacity(self):
        before = self.ledger.snapshot(PAYMENT)
        reserved = self.send(operation='reserve', key='a', amount_minor=600)
        middle = self.ledger.snapshot(PAYMENT)
        self.assertTrue(holds('CON-008', dict(before=before, after=middle,
                                              request=dict(key='a', amount_minor=600, outcome=reserved['outcome']))))
        committed = self.send(operation='commit', record_id=reserved['record_id'])
        self.assertTrue(holds('CON-010', dict(before=middle, after=self.ledger.snapshot(PAYMENT),
                                              command=dict(kind='commit', record_id=reserved['record_id'],
                                                           outcome=committed['outcome']))))
        self.assertEqual((reserved['outcome'], committed['outcome']), ('reserved', 'committed'))
        self.assertEqual(self.send(operation='reserve', key='b', amount_minor=401), dict(outcome='rejected'))
        self.assertEqual(self.send(operation='reserve', key='b', amount_minor=400)['outcome'], 'reserved')
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 1000)

    def test_malformed_request_reaches_no_operation(self):
        for request in [dict(operation='reserve', key='a', amount_minor='600'), dict(operation='reserve', key='a', amount_minor=True),
                        dict(operation='erase'), dict(operation='commit'),
                        dict(operation='reserve', key='a', amount_minor=600, operation_id='x' * 65)]:
            with self.subTest(request=request):
                self.assertEqual(self.send(**request), dict(outcome='invalid'))
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'], [])
        self.assertEqual(self.ledger.audit_events(), [])


class Test011CrossTenant(EntrypointCase):
    def test_other_tenants_are_denied_and_learn_nothing(self):
        record = self.attempt('a', 600).record_id
        before = self.ledger.snapshot(PAYMENT)
        callers = [(STRANGER, 'tenant-other'),  # SCN-009: caller and request agree, the ledger is someone else's
                   (STRANGER, TENANT),          # SCN-006: caller's tenant differs from the requested tenant
                   (UNVERIFIED, TENANT)]        # SCN-008
        requests = [dict(operation='reserve', key='x', amount_minor=100), dict(operation='reserve', key='a', amount_minor=600),
                    dict(operation='cancel', record_id=record), dict(operation='commit', record_id=record),
                    dict(operation='remaining')]
        self.ledger.flags[FLAG_REMAINING] = True
        for principal, tenant in callers:
            for request in requests:
                with self.subTest(principal=principal, tenant=tenant, request=request):
                    self.assertEqual(self.send(principal, tenant_id=tenant, **request), dict(outcome='denied'))
        self.assertEqual(self.ledger.snapshot(PAYMENT), before)
        # A payment that does not exist answers exactly like one owned by another tenant.
        self.assertEqual(self.send(STRANGER, tenant_id='tenant-other', payment_id='pay-missing', operation='remaining'),
                         self.send(STRANGER, tenant_id='tenant-other', operation='remaining'))

    def test_denied_attempts_satisfy_the_before_after_predicates(self):
        record = self.attempt('a', 600).record_id
        self.assertEqual(self.attempt('x', 100, STRANGER, 'tenant-other').outcome, 'denied')
        self.assertEqual(self.command('cancel', record, STRANGER, 'tenant-other').outcome, 'denied')


class Test012Cancellation(LedgerCase):
    def test_cancellation_releases_capacity_once_and_keeps_the_key(self):
        record = self.attempt('a', 700).record_id
        self.assertEqual(self.attempt('b', 400).outcome, 'rejected')
        self.assertEqual(self.command('cancel', record).outcome, 'released')
        self.assertEqual(self.attempt('b', 400).outcome, 'reserved')        # the capacity is available again
        replay = self.attempt('a', 700)                                      # the key is still held by the released record
        self.assertEqual((replay.outcome, replay.record_id), ('replayed', record))
        self.assertEqual(self.command('cancel', record).outcome, 'repeated')  # SCN-024
        self.assertEqual(self.statuses(), dict(a='released', b='reserved'))
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 400)


class Test013AuditContent(EntrypointCase):
    def audited(self, principal=OWNER, **request):
        """Send one request and require CON-011 of the audit rows it added."""
        known = len(self.ledger.audit_events())
        result = self.send(principal, **request)
        attempt = dict(operation_id=request['operation_id'], operation=request['operation'], outcome=result['outcome'])
        self.assertTrue(holds('CON-011', dict(attempt=attempt, added=self.ledger.audit_events()[known:])), attempt)
        return result

    def test_audit_rows_hold_identifier_kind_and_outcome_only(self):
        secret, body = 'Bearer s3cr3t-token-91', 'free text with card 4111111111111111'
        extra = dict(credential=secret, note=body)
        first = self.audited(operation='reserve', key='key-437', amount_minor=437, operation_id='op-1', **extra)
        self.audited(STRANGER, operation='reserve', key='key-438', amount_minor=438, operation_id='op-2', **extra)
        before = self.ledger.snapshot(PAYMENT)
        replay = self.audited(operation='reserve', key='key-437', amount_minor=437, operation_id='op-3', **extra)
        self.assertEqual(replay['outcome'], 'replayed')
        self.assertEqual(self.ledger.snapshot(PAYMENT), before)  # auditing a replay changes no business state
        events = self.ledger.audit_events()
        self.assertEqual(events, [dict(operation_id='op-1', operation='reserve', outcome='reserved'),
                                  dict(operation_id='op-2', operation='reserve', outcome='denied'),
                                  dict(operation_id='op-3', operation='reserve', outcome='replayed')])
        stored = json.dumps(self.ledger.connection.execute('SELECT * FROM audit').fetchall())
        for forbidden in (secret, 's3cr3t', body, '4111111111111111', 'key-437', '437', TENANT):
            self.assertNotIn(forbidden, stored)
        for request in (dict(operation='commit', record_id=first['record_id']), dict(operation='remaining'),
                        dict(operation='cancel', record_id='r-9'), dict(operation='reserve', key='big', amount_minor=10**6)):
            self.audited(operation_id='op-' + request['operation'], **request, **extra)

    def test_copied_credential_copied_body_and_missing_row_are_detected(self):
        for scenario in ('SCN-029', 'SCN-030', 'SCN-031'):
            with self.subTest(scenario=scenario):
                self.assertFalse(holds('CON-011', NODES[scenario]['data']['given']))


class Test014Restart(LedgerCase):
    def test_retry_after_restart_finds_the_record(self):
        first = self.ledger.reserve(OWNER, TENANT, PAYMENT, 'a', 400)
        self.ledger.close()
        self.ledger = self.open()
        again = self.attempt('a', 400)
        self.assertEqual((again.outcome, again.record_id), ('replayed', first.record_id))
        self.assertEqual(len(self.ledger.snapshot(PAYMENT)['refunds']), 1)

    def test_crash_before_commit_leaves_nothing_and_the_retry_is_admitted(self):
        def crash():
            raise RuntimeError('process stopped between check and commit')
        self.ledger.hooks['after_check'] = crash
        with self.assertRaises(RuntimeError):
            self.ledger.reserve(OWNER, TENANT, PAYMENT, 'a', 400)
        self.ledger.close()
        self.ledger = self.open()
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'], [])
        self.assertEqual(self.ledger.audit_events(), [])
        self.assertEqual(self.attempt('a', 400).outcome, 'reserved')


class Test015NewKeyAdmitted(LedgerCase):
    def test_new_key_is_admitted_beside_an_existing_record(self):
        first = self.attempt('a', 600)
        second = self.attempt('c', 300)  # SCN-015
        self.assertEqual(second.outcome, 'reserved')
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'],
                         [dict(id=first.record_id, key='a', amount_minor=600, status='reserved'),
                          dict(id=second.record_id, key='c', amount_minor=300, status='reserved')])


class Test016OwnTenantServed(EntrypointCase):
    def test_verified_principal_of_the_ledger_tenant_is_served(self):
        served = self.send(operation='reserve', key='a', amount_minor=400)  # SCN-003
        self.assertEqual(served['outcome'], 'reserved')
        self.assertEqual(self.ledger.snapshot(PAYMENT)['refunds'],
                         [dict(id=served['record_id'], key='a', amount_minor=400, status='reserved')])
        self.assertEqual(self.send(STRANGER, operation='reserve', key='b', amount_minor=400), dict(outcome='denied'))


class Test017InapplicableCommand(LedgerCase):
    def test_commands_that_do_not_apply_change_nothing(self):
        committed, released = self.attempt('a', 300).record_id, self.attempt('b', 300).record_id
        self.command('commit', committed)
        self.command('cancel', released)
        before = self.ledger.snapshot(PAYMENT)
        cases = [('cancel', committed, 'refused'),    # SCN-022
                 ('commit', released, 'refused'),
                 ('commit', committed, 'repeated'),
                 ('commit', 'r-999', 'not_found'),    # SCN-025
                 ('cancel', 'not-an-id', 'not_found'),
                 # Only the spelling the ledger issues names a record: other digits, a leading zero or a
                 # number SQLite cannot hold used to raise an error or reach r-1.
                 ('commit', 'r-²', 'not_found'), ('commit', 'r-' + '9' * 30, 'not_found'),
                 ('commit', 'r-١', 'not_found'), ('commit', 'r-01', 'not_found')]
        for kind, record, expected in cases:
            with self.subTest(kind=kind, record=record):
                self.assertEqual(self.command(kind, record).outcome, expected)
        self.assertEqual(self.ledger.snapshot(PAYMENT), before)

    def test_refusal_that_moved_a_terminal_record_is_detected(self):
        self.assertFalse(holds('CON-009', NODES['SCN-023']['data']['given']))


class Test018ApplicableCommand(LedgerCase):
    def test_commands_on_reserved_records_apply(self):
        first, second = self.attempt('a', 300).record_id, self.attempt('b', 300).record_id
        self.assertEqual(self.command('cancel', first).outcome, 'released')    # SCN-018
        self.assertEqual(self.command('commit', second).outcome, 'committed')  # SCN-020
        self.assertEqual(self.statuses(), dict(a='released', b='committed'))
        self.assertEqual(self.ledger.consumed_minor(PAYMENT), 300)


class FlagCase(EntrypointCase):
    def test_flag_is_the_one_the_specification_declares(self):
        flag = next(f for f in SPEC['flags'] if f['id'] == NODES['REQ-010']['data']['flag_id'])
        self.assertEqual(flag['key'], FLAG_REMAINING)
        self.assertIs(self.open().flags[FLAG_REMAINING], flag['state'] == 'enabled')  # the default follows the release

    def report(self):
        """Ask for the report as the owner and require CON-012 of the answer, the flag and the ledger read back."""
        answer = self.send(operation='remaining')
        state = self.ledger.snapshot(PAYMENT)
        consumed = sum(r['amount_minor'] for r in state['refunds'] if r['status'] in ('reserved', 'committed'))
        self.assertTrue(holds('CON-012', dict(flag_enabled=self.ledger.flags[FLAG_REMAINING], captured_minor=state['captured_minor'],
                                              consumed_minor=consumed, reported='remaining_minor' in answer,
                                              remaining_minor=answer.get('remaining_minor', 0))), answer)
        return answer


class Test019RemainingReportOn(FlagCase):
    def test_remaining_capacity_is_reported(self):
        self.ledger.flags[FLAG_REMAINING] = True
        record = self.attempt('a', 600).record_id
        self.assertEqual(self.report(), dict(outcome='reported', remaining_minor=400))
        self.command('cancel', record)
        self.assertEqual(self.report(), dict(outcome='reported', remaining_minor=1000))
        self.assertEqual(self.send(STRANGER, operation='remaining'), dict(outcome='denied'))


class Test020RemainingReportOff(FlagCase):
    def test_report_is_unavailable_and_discloses_nothing(self):
        self.attempt('a', 600)
        before = self.ledger.snapshot(PAYMENT)
        self.assertEqual(self.report(), dict(outcome='unavailable'))
        self.assertEqual(self.ledger.snapshot(PAYMENT), before)


del LedgerCase, EntrypointCase, FlagCase  # base classes are not test cases


if __name__ == '__main__':
    unittest.main()
