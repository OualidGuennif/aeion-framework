"""Format 0.3: approval policy and signatures (G12), the release store, imports, impact and multi-file specs.

The approval cases sign with fictional keys derived from public labels (qa/fictional_keys.py); the passkey
cases simulate an authenticator. They exercise the verification rules, not any hardware or identity system.
"""
import base64
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
import approvals  # noqa: E402
import check_package as qa  # noqa: E402
import fictional_keys as fk  # noqa: E402
import migrate_0_2  # noqa: E402
import release_diff as diff  # noqa: E402
import release_store  # noqa: E402
import spec_parts  # noqa: E402

LEDGER = 'examples/refund-ledger/'
BANDS = ('low', 'medium', 'high', 'critical')
PASSKEYS = [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')]


def node(spec, nid):
    return next(n for n in spec['nodes'] if n['id'] == nid)


def codes(report, field='errors'):
    return sorted(e['code'] for e in report[field])


class Examples(unittest.TestCase):
    def setUp(self):
        self.base = qa.read(LEDGER + 'releases/1.0.0.json')
        self.spec = qa.read(LEDGER + 'spec.json')
        self.identity = qa.read('examples/identity-adapter/spec.json')
        self.base_approvals = qa.read(LEDGER + 'releases/1.0.0.approvals.json')
        self.spec_approvals = qa.read(LEDGER + 'approvals.json')

    def successor(self, baseline, version, edit=lambda spec: None):
        """A next release of `baseline`: named by digest, with one edit applied."""
        spec = copy.deepcopy(baseline)
        spec['release'] = dict(version=version, compatibility=[],
                               previous=dict(version=baseline['release']['version'], spec_sha256=qa.digest(qa.canonical(baseline))))
        edit(spec)
        return spec

    def retitle(self, nid):
        def edit(spec):
            target = node(spec, nid)
            target['title'] += ' (reworded)'
            target['revision'] += 1
        return edit

    def with_policy(self, spec, **bands):
        spec = copy.deepcopy(spec)
        for band, (count, methods) in bands.items():
            spec['approval']['policy'][band] = dict(approvers=count, methods=list(methods))
        return spec

    def add_attestor(self, spec):
        spec = copy.deepcopy(spec)
        spec['actors'].append(dict(id='ACTOR-009', name='Approval service', type='service', binding_status='asserted'))
        spec['approval']['keys'].append(dict(id='KEY-009', actor_id='ACTOR-009', method='sso_mfa', algorithm='ed25519',
                                             public_key=fk.public_key('ed25519', 'PROJECT-001/KEY-009'), attests=True))
        return spec


class ApprovalPolicy(Examples):
    """AX-M-020: the policy is the organization's; the format only requires that it is stated and satisfiable."""

    def test_any_number_of_approvers_is_a_valid_policy_when_keys_can_supply_it(self):
        for counts in [(0, 0, 0, 0), (1, 1, 1, 1), (0, 1, 2, 2), (2, 0, 0, 0)]:
            with self.subTest(counts=counts):
                spec = self.with_policy(self.base, **{band: (count, []) for band, count in zip(BANDS, counts)})
                self.assertEqual(qa.reference_errors(spec), [])
        spec = self.with_policy(self.base, **{band: (0, []) for band in BANDS})
        spec['approval']['keys'] = []
        self.assertEqual(qa.reference_errors(spec), [])  # no approver, no key: stated, valid, visible
        self.assertEqual(qa.reference_errors(self.with_policy(self.base, low=(7, []))), ['UNSATISFIABLE_APPROVAL_POLICY'])

    def test_seven_approvers_are_satisfiable_through_an_attesting_service(self):
        spec = self.add_attestor(self.base)
        for number in range(10, 16):
            spec['actors'].append(dict(id=f'ACTOR-0{number}', name=f'Reviewer {number}', type='human_role', binding_status='asserted'))
        spec = self.with_policy(spec, critical=(7, ['sso_mfa']))
        self.assertEqual(qa.reference_errors(spec), [])
        self.assertEqual(len(qa.eligible_approvers(spec, 'critical')), 9)  # every actor that is not a service
        self.assertEqual(len(qa.eligible_approvers(self.with_policy(spec, critical=(7, ['device_passkey'])), 'critical')), 2)

    def test_each_structural_rule(self):
        cases = [
            ('UNKNOWN_APPROVAL_METHOD', lambda s: s['approval']['policy']['high'].update(methods=['email_link'])),
            ('UNSATISFIABLE_APPROVAL_POLICY', lambda s: s['approval']['policy']['critical'].update(approvers=3)),
            ('DUPLICATE_APPROVAL_KEY', lambda s: s['approval']['keys'][1].update(public_key=s['approval']['keys'][0]['public_key'])),
            ('INVALID_APPROVAL_KEY', lambda s: s['approval']['keys'][0].update(algorithm='ed25519')),
            ('INVALID_APPROVAL_KEY', lambda s: s['approval']['keys'][0].update(public_key=base64.b64encode(b'\x02' + bytes(64)).decode())),
            ('ATTESTOR_NOT_SERVICE', lambda s: s['approval']['keys'][0].update(attests=True)),
            ('UNKNOWN_ACTOR', lambda s: s['approval']['keys'][0].update(actor_id='ACTOR-999')),
            ('WRONG_PREFIX', lambda s: s['approval']['keys'][0].update(id='SIGNER-001')),
            ('DUPLICATE_ID', lambda s: s['approval']['keys'][1].update(id='KEY-001'))]
        for expected, mutate in cases:
            with self.subTest(expected=expected):
                spec = copy.deepcopy(self.base)
                mutate(spec)
                self.assertIn(expected, qa.reference_errors(spec))

    def test_schema_requires_all_four_bands_and_bounds_the_fields(self):
        validator = qa.make_validator(qa.read('schemas/spec.schema.json'))
        for mutate in [lambda s: s['approval']['policy'].pop('low'), lambda s: s.pop('approval'),
                       lambda s: s['approval']['policy']['low'].update(approvers=-1),
                       lambda s: s['approval']['policy']['low'].update(approvers=129),
                       lambda s: s['approval']['keys'][0].update(algorithm='rsa'),
                       lambda s: s['approval']['keys'][0].update(method='Device Passkey'),
                       lambda s: s.pop('imports'), lambda s: s.pop('exports')]:
            spec = copy.deepcopy(self.base)
            self.assertTrue(validator.is_valid(spec))
            mutate(spec)
            self.assertFalse(validator.is_valid(spec))


class ApprovalVerification(Examples):
    """AX-G-014: the verdict needs the release, its approvals and its baseline, and nothing else."""

    def test_the_three_example_releases_have_the_approvers_their_policy_requires(self):
        first = approvals.verify(self.base, self.base_approvals)
        self.assertEqual((first['status'], first['governed_by']['version']), ('pass', '1.0.0'))
        self.assertEqual([r['band'] for r in first['required']], list(BANDS))  # a first release reaches every requirement
        second = approvals.verify(self.spec, self.spec_approvals, self.base)
        self.assertEqual((second['status'], second['governed_by']['version']), ('pass', '1.0.0'))
        critical = next(r for r in second['required'] if r['band'] == 'critical')
        self.assertEqual((critical['approvers'], critical['valid_approvers'], critical['because']),
                         (2, ['ACTOR-001', 'ACTOR-003'], ['REQ-004']))
        identity = approvals.verify(self.identity, qa.read('examples/identity-adapter/approvals.json'))
        self.assertEqual(identity['status'], 'pass')
        self.assertEqual(identity['approvals'], [dict(actor_id='ACTOR-001', key_id='KEY-001', method='sso_mfa', valid=True)])

    def test_without_the_governing_release_the_answer_is_unknown_not_fail(self):
        for baseline in (None, self.spec):
            report = approvals.verify(self.spec, self.spec_approvals, baseline)
            self.assertEqual((report['status'], codes(report)), ('unknown', ['BASELINE_REQUIRED']))

    def test_altered_content_and_replayed_approvals_do_not_count(self):
        altered = copy.deepcopy(self.spec)
        altered['project']['name'] += ' (altered)'
        report = approvals.verify(altered, self.spec_approvals, self.base)
        self.assertEqual((report['status'], codes(report, 'rejected')), ('fail', ['APPROVALS_FOR_OTHER_RELEASE']))
        # The approvals of 1.0.0 relabelled as approvals of 1.1.0: each signature names another digest.
        replayed = dict(self.spec_approvals, approvals=self.base_approvals['approvals'])
        report = approvals.verify(self.spec, replayed, self.base)
        self.assertEqual((report['status'], codes(report, 'rejected')), ('fail', ['INVALID_SIGNATURE'] * 2))
        self.assertIn('INSUFFICIENT_APPROVALS', codes(report))

    def test_one_approver_short_fails_only_the_band_that_needs_two(self):
        short = dict(self.spec_approvals, approvals=self.spec_approvals['approvals'][:1])
        report = approvals.verify(self.spec, short, self.base)
        self.assertEqual((report['status'], codes(report)), ('fail', ['INSUFFICIENT_APPROVALS']))
        self.assertIn('critical band needs 2', report['errors'][0]['message'])

    def test_a_policy_of_zero_approvers_passes_with_no_approval(self):
        open_base = self.with_policy(self.base, **{band: (0, []) for band in BANDS})
        candidate = self.successor(open_base, '1.0.1', self.retitle('REQ-004'))
        report = approvals.verify(candidate, approvals.empty(candidate), open_base)
        self.assertEqual((report['status'], report['approvals']), ('pass', []))
        self.assertEqual({r['band']: r['approvers'] for r in report['required']}, dict(low=0, critical=0))

    def test_a_policy_of_seven_approvers_is_not_met_by_two(self):
        strict = self.add_attestor(self.base)
        for number in range(10, 16):
            strict['actors'].append(dict(id=f'ACTOR-0{number}', name=f'Reviewer {number}', type='human_role', binding_status='asserted'))
        strict = self.with_policy(strict, low=(7, []))
        candidate = self.successor(strict, '1.0.1', self.retitle('REQ-007'))
        two = fk.approvals_for(candidate, strict, PASSKEYS)
        self.assertEqual(codes(approvals.verify(candidate, two, strict)), ['INSUFFICIENT_APPROVALS'])
        people = [a['id'] for a in strict['actors'] if a['type'] != 'service'][:7]
        seven = fk.approvals_for(candidate, strict, [(actor, 'KEY-009') for actor in people])
        self.assertEqual(approvals.verify(candidate, seven, strict)['status'], 'pass')

    def test_only_the_bands_a_release_reaches_are_required(self):
        candidate = self.successor(self.spec, '1.1.1', self.retitle('REQ-010'))
        low = approvals.verify(candidate, approvals.empty(candidate), self.spec)
        self.assertEqual(([r['band'] for r in low['required']], low['status']), (['low'], 'pass'))  # REQ-010 is low: no approver
        medium = self.successor(self.spec, '1.1.1', self.retitle('REQ-007'))
        report = approvals.verify(medium, approvals.empty(medium), self.spec)
        self.assertEqual(([r['band'] for r in report['required']], codes(report)), (['low', 'medium'], ['INSUFFICIENT_APPROVALS']))
        one = fk.approvals_for(medium, self.spec, PASSKEYS[:1])
        self.assertEqual(approvals.verify(medium, one, self.spec)['status'], 'pass')
        critical = self.successor(self.spec, '1.1.1', self.retitle('REQ-004'))
        self.assertEqual(approvals.verify(critical, fk.approvals_for(critical, self.spec, PASSKEYS[:1]), self.spec)['status'], 'fail')
        self.assertEqual(approvals.verify(critical, fk.approvals_for(critical, self.spec, PASSKEYS), self.spec)['status'], 'pass')

    def test_a_band_counts_only_the_methods_it_accepts(self):
        governing = self.add_attestor(self.base)
        candidate = self.successor(governing, '1.0.1', self.retitle('REQ-004'))
        attested = fk.approvals_for(candidate, governing, [('ACTOR-001', 'KEY-009'), ('ACTOR-003', 'KEY-009')])
        report = approvals.verify(candidate, attested, governing)
        self.assertEqual(codes(report), ['INSUFFICIENT_APPROVALS'])  # critical accepts device_passkey only
        self.assertEqual({a['method'] for a in report['approvals']}, {'sso_mfa'})
        accepting = self.with_policy(governing, critical=(2, ['device_passkey', 'sso_mfa']))
        candidate = self.successor(accepting, '1.0.1', self.retitle('REQ-004'))
        mixed = fk.approvals_for(candidate, accepting, [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-009')])
        self.assertEqual(approvals.verify(candidate, mixed, accepting)['status'], 'pass')
        # One person approving twice, by passkey and through the service, is one approver.
        twice = fk.approvals_for(candidate, accepting, [('ACTOR-001', 'KEY-001'), ('ACTOR-001', 'KEY-009')])
        self.assertEqual(codes(approvals.verify(candidate, twice, accepting)), ['INSUFFICIENT_APPROVALS'])

    def test_who_may_sign_for_whom(self):
        governing = self.add_attestor(self.base)
        candidate = self.successor(governing, '1.0.1', self.retitle('REQ-007'))
        def rejected(signers, label=None):
            document = approvals.empty(candidate)
            document['approvals'] = [fk.approve(candidate, governing, actor, key, label) for actor, key in signers]
            return codes(approvals.verify(candidate, document, governing), 'rejected')
        self.assertEqual(rejected([('ACTOR-003', 'KEY-001')]), ['APPROVER_MISMATCH'])   # a personal key for someone else
        self.assertEqual(rejected([('ACTOR-009', 'KEY-009')]), ['APPROVER_MISMATCH'])   # a service vouching for a service
        self.assertEqual(rejected([('ACTOR-777', 'KEY-009')]), ['APPROVER_MISMATCH'])   # an actor nobody declared
        self.assertEqual(rejected([('ACTOR-001', 'KEY-001')], 'another private key'), ['INVALID_SIGNATURE'])
        self.assertEqual(rejected([('ACTOR-002', 'KEY-009')]), [])                      # any declared non-service actor
        stranger = copy.deepcopy(governing)
        stranger['approval']['keys'].append(dict(governing['approval']['keys'][0], id='KEY-050'))
        document = approvals.empty(candidate)
        document['approvals'] = [fk.approve(candidate, stranger, 'ACTOR-001', 'KEY-050', 'PROJECT-001/KEY-001')]
        self.assertEqual(codes(approvals.verify(candidate, document, governing), 'rejected'), ['UNKNOWN_APPROVAL_KEY'])

    def test_a_passkey_assertion_needs_the_right_challenge_and_a_verified_user(self):
        candidate = self.successor(self.base, '1.0.1', self.retitle('REQ-007'))
        good = fk.approve(candidate, self.base, 'ACTOR-001', 'KEY-001')
        key = self.base['approval']['keys'][0]
        message = approvals.statement(candidate, 'ACTOR-001', 'KEY-001', 'device_passkey')
        self.assertTrue(approvals.signature_valid(key, message, good))
        self.assertFalse(approvals.signature_valid(key, message, fk.approve(candidate, self.base, 'ACTOR-001', 'KEY-001', user_verified=False)))
        other = approvals.statement(self.base, 'ACTOR-001', 'KEY-001', 'device_passkey')
        self.assertFalse(approvals.signature_valid(key, other, good))  # an assertion for another release
        self.assertFalse(approvals.signature_valid(key, approvals.statement(candidate, 'ACTOR-001', 'KEY-001', 'sso_mfa'), good))
        client = json.loads(base64.b64decode(good['client_data_json']))
        registration = dict(good, client_data_json=base64.b64encode(json.dumps(dict(client, type='webauthn.create')).encode()).decode())
        self.assertFalse(approvals.signature_valid(key, message, registration))
        for field in ('signature', 'authenticator_data', 'client_data_json'):
            self.assertFalse(approvals.signature_valid(key, message, dict(good, **{field: 'AAAA'})))
            self.assertFalse(approvals.signature_valid(key, message, dict(good, **{field: 'not base64'})))
        self.assertFalse(approvals.signature_valid(key, message, dict(good, authenticator_data=None, client_data_json=None)))
        self.assertEqual(json.loads(message)['spec_sha256'], qa.digest(qa.canonical(candidate)))

    def test_keys_rotate_through_the_chain_without_a_clock(self):
        # 1.0.1 adds a third key. It changes who may approve, so it needs every band of the release before it.
        def add_key(spec):
            spec['actors'].append(dict(id='ACTOR-005', name='New reviewer', type='human_role', binding_status='asserted'))
            spec['approval']['keys'].append(dict(id='KEY-005', actor_id='ACTOR-005', method='device_passkey', algorithm='webauthn-es256',
                                                 public_key=fk.public_key('webauthn-es256', 'PROJECT-001/KEY-005'), attests=False))
        rotated = self.successor(self.base, '1.0.1', add_key)
        report = approvals.verify(rotated, fk.approvals_for(rotated, self.base, PASSKEYS), self.base)
        self.assertEqual(([r['band'] for r in report['required']], report['status']), (list(BANDS), 'pass'))
        self.assertIn('actors, approval policy or keys changed', report['required'][3]['because'])
        # The new key cannot approve the release that introduces it: the baseline governs.
        own = approvals.empty(rotated)
        own['approvals'] = [fk.approve(rotated, rotated, 'ACTOR-005', 'KEY-005')] + fk.approvals_for(rotated, self.base, PASSKEYS[:1])['approvals']
        self.assertEqual(codes(approvals.verify(rotated, own, self.base), 'rejected'), ['UNKNOWN_APPROVAL_KEY'])
        self.assertEqual(approvals.verify(rotated, own, self.base)['status'], 'fail')
        # From the next release on it counts.
        def drop_first(spec):
            spec['approval']['keys'] = [k for k in spec['approval']['keys'] if k['id'] != 'KEY-001']
            self.retitle('REQ-004')(spec)
        revoked = self.successor(rotated, '1.0.2', drop_first)
        signed = fk.approvals_for(revoked, rotated, [('ACTOR-005', 'KEY-005'), ('ACTOR-003', 'KEY-002')])
        self.assertEqual(approvals.verify(revoked, signed, rotated)['status'], 'pass')
        # KEY-001 is gone after 1.0.2. It no longer approves 1.0.3, and 1.0.1, which it approved, still verifies.
        later = self.successor(revoked, '1.0.3', self.retitle('REQ-004'))
        stale = fk.approvals_for(later, rotated, PASSKEYS)
        self.assertEqual(codes(approvals.verify(later, stale, revoked), 'rejected'), ['UNKNOWN_APPROVAL_KEY'])
        self.assertEqual(approvals.verify(rotated, fk.approvals_for(rotated, self.base, PASSKEYS), self.base)['status'], 'pass')

    def test_a_damaged_fragment_never_blocks_a_release_that_has_its_approvers(self):
        garbage = dict(self.spec_approvals['approvals'][0], actor_id='ACTOR-002')
        forged = dict(self.spec_approvals['approvals'][1], signature=base64.b64encode(bytes(70)).decode(), key_id='KEY-001', actor_id='ACTOR-001')
        polluted = dict(self.spec_approvals, approvals=self.spec_approvals['approvals'] + [garbage, forged])
        report = approvals.verify(self.spec, polluted, self.base)
        self.assertEqual((report['status'], codes(report, 'rejected')), ('pass', ['APPROVER_MISMATCH', 'INVALID_SIGNATURE']))

    def test_merge_is_a_union_and_order_never_matters(self):
        first, second = (dict(self.spec_approvals, approvals=[a]) for a in self.spec_approvals['approvals'])
        merged = approvals.merge(first, second)
        self.assertEqual(merged, approvals.merge(second, first))
        self.assertEqual(merged, approvals.merge(merged, first))
        self.assertEqual(merged, approvals.merge(approvals.merge(first, approvals.empty(self.spec)), second))
        self.assertEqual(approvals.verify(self.spec, merged, self.base)['status'], 'pass')
        self.assertEqual(approvals.verify(self.spec, first, self.base)['status'], 'fail')
        resigned = fk.approvals_for(self.spec, self.base, PASSKEYS)  # ECDSA signatures differ on every signing
        self.assertEqual(approvals.merge(merged, resigned), approvals.merge(resigned, merged))
        # Both signings of each approver are kept: a merge never chooses between two approvals of one key.
        both = approvals.merge(merged, resigned)
        self.assertEqual(len(both['approvals']), 4)
        self.assertEqual([r['valid_approvers'] for r in approvals.verify(self.spec, both, self.base)['required']][0], ['ACTOR-001', 'ACTOR-003'])
        reversed_order = dict(merged, approvals=merged['approvals'][::-1])
        self.assertEqual(approvals.verify(self.spec, reversed_order, self.base), approvals.verify(self.spec, merged, self.base))
        with self.assertRaisesRegex(ValueError, 'different releases'):
            approvals.merge(self.spec_approvals, self.base_approvals)

    def test_command_line(self):
        import contextlib, io
        def run(*arguments):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                return approvals.main(list(arguments)), out.getvalue()
        spec, base = str(ROOT / LEDGER / 'spec.json'), str(ROOT / LEDGER / 'releases/1.0.0.json')
        self.assertEqual(run('verify', spec, str(ROOT / LEDGER / 'approvals.json'), base)[0], 0)
        self.assertEqual(run('verify', spec, str(ROOT / LEDGER / 'approvals.json'))[0], 3)
        self.assertEqual(run('verify', base, str(ROOT / LEDGER / 'approvals.json'))[0], 2)
        self.assertEqual(run('verify', spec, str(ROOT / 'README.md'))[0], 4)
        code, text = run('statement', base, 'ACTOR-001', 'KEY-001')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['webauthn_challenge'],
                         approvals.challenge(approvals.statement(self.base, 'ACTOR-001', 'KEY-001', 'device_passkey')))
        self.assertEqual(run('statement', base, 'ACTOR-001', 'KEY-999')[0], 4)
        self.assertEqual(run()[0], 4)


class ImportsAndExports(Examples):
    """AX-M-021 and their classification in the release comparison."""

    def test_structural_rules(self):
        cases = [
            ('SELF_IMPORT', lambda s: s['imports'][0].update(project_id='PROJECT-001')),
            ('DUPLICATE_IMPORT', lambda s: s['imports'].append(dict(s['imports'][0], id='IMP-002'))),
            ('DUPLICATE_IMPORT', lambda s: s['imports'][0]['uses'].append(dict(s['imports'][0]['uses'][0]))),
            ('UNKNOWN_IMPORT_USER', lambda s: s['imports'][0]['uses'][0].update(local_ids=['REQ-999'])),
            ('WRONG_PREFIX', lambda s: s['imports'][0].update(id='DEP-001')),
            ('INVALID_EXPORT', lambda s: s.update(exports=['REQ-999'])),
            ('INVALID_EXPORT', lambda s: s.update(exports=['TEST-001'])),
            ('INVALID_EXPORT', lambda s: (s.update(exports=['REQ-010']), node(s, 'REQ-010').update(status='retired')))]
        for expected, mutate in cases:
            with self.subTest(expected=expected):
                spec = copy.deepcopy(self.spec)
                mutate(spec)
                self.assertIn(expected, qa.reference_errors(spec))
        exporting = copy.deepcopy(self.spec)
        exporting['exports'] = ['REQ-004', 'CON-005', 'TERM-005', 'MODEL-001']
        self.assertEqual(qa.reference_errors(exporting), [])

    def level(self, baseline, edit, subject):
        report = diff.compare(baseline, self.successor(baseline, '2.0.0', edit))
        return next(c['level'] for c in report['changes'] if c['subject_id'] == subject)

    def test_import_and_export_changes_are_classified(self):
        added = next(c for c in diff.compare(self.base, self.spec)['changes'] if c['subject_id'] == 'IMP-001')
        self.assertEqual((added['kind'], added['change'], added['level']), ('Import', 'added', 'minor'))
        pin = lambda version, digest='0' * 64: lambda s: s['imports'][0].update(version=version, spec_sha256=digest)
        self.assertEqual(self.level(self.spec, pin('2.0.0'), 'IMP-001'), 'major')
        self.assertEqual(self.level(self.spec, pin('1.1.0'), 'IMP-001'), 'minor')
        self.assertEqual(self.level(self.spec, pin('1.0.1'), 'IMP-001'), 'patch')
        self.assertEqual(self.level(self.spec, pin('1.0.0'), 'IMP-001'), 'minor')  # same version, other content
        self.assertEqual(self.level(self.spec, lambda s: s['imports'][0]['uses'][0].update(rationale='Reworded.'), 'IMP-001'), 'patch')
        self.assertEqual(self.level(self.spec, lambda s: s['imports'].clear(), 'IMP-001'), 'minor')
        back = copy.deepcopy(self.spec)
        back['imports'][0]['version'] = '1.2.0'
        self.assertEqual(self.level(back, pin('1.1.0'), 'IMP-001'), 'major')
        self.assertEqual(self.level(self.spec, lambda s: s.update(exports=['REQ-004']), 'REQ-004'), 'minor')
        exporting = copy.deepcopy(self.spec)
        exporting['exports'] = ['REQ-004']
        self.assertEqual(self.level(exporting, lambda s: s.update(exports=[]), 'REQ-004'), 'major')

    def test_an_import_reaches_the_requirements_that_use_it(self):
        candidate = self.successor(self.spec, '1.2.0', lambda s: s['imports'][0].update(version='1.1.0', spec_sha256='1' * 64))
        risk = diff.compare(self.spec, candidate)['risk']
        self.assertEqual(risk['unmapped_changes'], [])
        self.assertIn(dict(id='REQ-004', weight_minor=950, factor_percent=50, reach='direct'), risk['requirements'])

    def test_governance_changes_are_recorded_and_reach_no_requirement(self):
        def edit(spec):
            spec['approval']['policy']['low']['approvers'] = 1
            spec['approval']['keys'][1]['method'] = 'security_key'
        report = diff.compare(self.spec, self.successor(self.spec, '1.1.1', edit))
        changed = {c['subject_id']: (c['kind'], c['level']) for c in report['changes']}
        self.assertEqual(changed, {'KEY-002': ('ApprovalKey', 'patch'), 'PROJECT-001': ('Project', 'patch')})
        self.assertEqual((report['status'], report['risk']['unmapped_changes']), ('pass', ['KEY-002', 'PROJECT-001']))


class ReleaseStore(Examples):
    """AX-L-010: the verdict is a function of the set of files, whatever their order or origin."""

    def store(self, *documents):
        store = release_store.Store()
        for position, document in enumerate(documents):
            if document['format'] == approvals.FORMAT:
                store.add_approvals(document)
            else:
                store.add_release(document, f'file-{position}')
        return store

    def everything(self):
        return [self.base, self.base_approvals, self.spec, self.spec_approvals, self.identity,
                qa.read('examples/identity-adapter/approvals.json')]

    def verdict(self, *documents):
        report = release_store.verify(self.store(*documents))
        for release in report['releases']:
            release.pop('files')
        return report

    def test_the_example_directory_is_a_complete_store(self):
        report = release_store.verify(release_store.load([str(ROOT / 'examples')]))
        self.assertEqual((report['status'], report['errors'], report['rejected_files']), ('pass', [], []))
        self.assertEqual([(r['project_id'], r['version'], r['status'], r['link'], r['approvals']) for r in report['releases']],
                         sorted([('PROJECT-001', '1.0.0', 'pass', 'genesis', 'pass'), ('PROJECT-001', '1.1.0', 'pass', 'present', 'pass'),
                                 ('PROJECT-002', '1.0.0', 'pass', 'genesis', 'pass')],
                                key=lambda row: next(r['spec_sha256'] for r in report['releases'] if (r['project_id'], r['version']) == row[:2])))
        self.assertEqual([(p['project_id'], p['head']['version'], p['tied_heads'], p['orphaned_heads']) for p in report['projects']],
                         [('PROJECT-001', '1.1.0', [], []), ('PROJECT-002', '1.0.0', [], [])])

    def test_every_arrival_order_gives_the_same_verdict(self):
        documents = self.everything()
        expected = self.verdict(*documents)
        for order in itertools.islice(itertools.permutations(documents), 0, 720, 37):
            self.assertEqual(self.verdict(*order), expected)
        self.assertEqual(self.verdict(*documents, *documents), expected)  # a file received twice changes nothing

    def test_a_missing_file_is_unknown_and_its_arrival_completes_the_verdict(self):
        without_baseline = self.verdict(self.spec, self.spec_approvals, self.identity, qa.read('examples/identity-adapter/approvals.json'))
        self.assertEqual((without_baseline['status'], without_baseline['errors']), ('incomplete', []))
        ledger = next(r for r in without_baseline['releases'] if r['project_id'] == 'PROJECT-001')
        self.assertEqual((ledger['status'], ledger['link'], ledger['approvals']), ('unknown', 'unknown', 'unknown'))
        without_provider = self.verdict(self.base, self.base_approvals, self.spec, self.spec_approvals)
        head = next(r for r in without_provider['releases'] if r['version'] == '1.1.0')
        self.assertEqual((without_provider['status'], head['status'], head['imports'][0]['state']), ('incomplete', 'unknown', 'unresolved'))
        self.assertEqual(next(r for r in without_provider['releases'] if r['version'] == '1.0.0')['status'], 'pass')
        self.assertEqual(self.verdict(*self.everything())['status'], 'pass')

    def test_a_release_without_its_approvals_fails_alone(self):
        report = self.verdict(self.base, self.base_approvals, self.spec, self.identity, qa.read('examples/identity-adapter/approvals.json'))
        self.assertEqual({(r['version'], r['project_id']): r['status'] for r in report['releases']},
                         {('1.0.0', 'PROJECT-001'): 'pass', ('1.1.0', 'PROJECT-001'): 'fail', ('1.0.0', 'PROJECT-002'): 'pass'})
        self.assertEqual(codes(report), ['INSUFFICIENT_APPROVALS'] * 3)  # medium, high and critical; low asks for none

    def test_two_replicas_merge_by_union(self):
        half = [dict(self.spec_approvals, approvals=[a]) for a in self.spec_approvals['approvals']]
        common = [self.base, self.base_approvals, self.spec, self.identity, qa.read('examples/identity-adapter/approvals.json')]
        east, west = self.verdict(*common, half[0]), self.verdict(*common, half[1])
        self.assertEqual((east['status'], west['status']), ('fail', 'fail'))  # each replica holds one of two approvals
        self.assertEqual(self.verdict(*common, half[0], half[1]), self.verdict(*common, half[1], half[0]))
        self.assertEqual(self.verdict(*common, half[0], half[1])['status'], 'pass')

    def fork(self):
        left = self.successor(self.spec, '1.1.1', self.retitle('REQ-010'))
        right = self.successor(self.spec, '1.1.1', self.retitle('REQ-009'))
        signed = lambda spec, governing: fk.approvals_for(spec, governing, PASSKEYS)
        return left, right, signed

    def test_a_fork_is_reported_identically_everywhere_and_corrupts_nothing(self):
        left, right, signed = self.fork()
        documents = self.everything() + [left, signed(left, self.spec), right, signed(right, self.spec)]
        report = self.verdict(*documents)
        self.assertEqual((report['status'], codes(report)), ('fail', ['FORKED_HEAD']))
        project = report['projects'][0]
        digests = sorted(qa.digest(qa.canonical(spec)) for spec in (left, right))
        self.assertEqual((project['head'], project['tied_heads']), (dict(version='1.1.1', spec_sha256=digests[0]), digests))
        self.assertEqual(self.verdict(*documents[::-1]), report)
        # Each side is still a fully verified release, and everything before the fork is untouched.
        self.assertEqual({r['status'] for r in report['releases']}, {'pass'})

    def test_a_later_release_settles_the_fork_without_deleting_anything(self):
        left, right, signed = self.fork()
        chosen = self.successor(right, '1.1.2', self.retitle('REQ-008'))
        documents = self.everything() + [left, signed(left, self.spec), right, signed(right, self.spec), chosen, signed(chosen, right)]
        report = self.verdict(*documents)
        self.assertEqual((report['status'], report['errors']), ('pass', []))
        project = report['projects'][0]
        self.assertEqual((project['head']['version'], project['tied_heads'], project['orphaned_heads']),
                         ('1.1.2', [], [qa.digest(qa.canonical(left))]))
        self.assertEqual(len(report['releases']), 6)

    def test_a_pin_must_name_what_it_holds_and_only_what_is_exported(self):
        wrong_version = copy.deepcopy(self.spec)
        wrong_version['imports'][0]['version'] = '1.0.1'
        report = self.verdict(self.base, wrong_version, self.identity)
        self.assertIn('IMPORT_PIN_MISMATCH', codes(report))
        private = copy.deepcopy(self.identity)
        private['exports'] = ['TERM-001']
        consumer = copy.deepcopy(self.spec)
        consumer['imports'][0]['spec_sha256'] = qa.digest(qa.canonical(private))
        self.assertIn('NOT_EXPORTED', codes(self.verdict(self.base, consumer, private)))

    def test_files_on_disk_unreadable_or_foreign_files_withhold_nothing(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-store-') as directory:
            root = Path(directory)
            for position, document in enumerate(self.everything()):
                (root / f'{position}.json').write_text(json.dumps(document))
            (root / 'notes.json').write_text('{"format": "something-else/1.0"}')
            (root / 'float.json').write_text('{"x": 1.5}')
            (root / 'not-json.json').write_text('{"x": ')
            self.assertEqual(release_store.verify(release_store.load([directory]))['status'], 'pass')
            damaged = copy.deepcopy(self.spec)
            del damaged['nodes']
            (root / 'damaged.json').write_text(json.dumps(damaged))
            report = release_store.verify(release_store.load([directory]))
            self.assertEqual((report['status'], report['errors'], len(report['rejected_files'])), ('incomplete', [], 1))
            self.assertEqual({r['status'] for r in report['releases']}, {'pass'})

    def test_command_line(self):
        import contextlib, io
        def run(*arguments):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return release_store.main(list(arguments))
        self.assertEqual(run('verify', str(ROOT / 'examples')), 0)
        self.assertEqual(run('verify', str(ROOT / LEDGER / 'spec.json'), str(ROOT / LEDGER / 'approvals.json')), 3)
        self.assertEqual(run('impact', str(ROOT / LEDGER / 'releases/1.0.0.json'), str(ROOT / LEDGER / 'spec.json'), str(ROOT / 'examples')), 0)
        self.assertEqual(run(), 4)


class Impact(Examples):
    """AX-L-011: a provider's step is followed into the specifications that declare a use of it."""

    def consumers(self, edit, version='1.1.0'):
        candidate = self.successor(self.identity, version, edit)
        store = ReleaseStore.store(self, self.base, self.spec, self.identity)
        return release_store.impact(store, self.identity, candidate)

    def test_a_breaking_provider_change_reaches_the_consumer_requirement_at_the_dependent_cap(self):
        def edit(spec):
            target = node(spec, 'REQ-001')
            target['data']['response'] = 'return a principal marked verified for any credential'
            target['revision'] += 1
        report = self.consumers(edit, '2.0.0')
        self.assertEqual((report['required_step'], report['comparison']), ('major', 'fail'))  # nobody acknowledged the break
        consumer, = report['consumers']
        self.assertEqual((consumer['project_id'], consumer['version'], consumer['pinned_version'], consumer['pinned_to_baseline']),
                         ('PROJECT-001', '1.1.0', '1.0.0', True))
        self.assertEqual(consumer['uses'], [dict(external_id='REQ-001', level='major', local_ids=['REQ-004'])])
        self.assertEqual(consumer['requirements'], [dict(id='REQ-004', weight_minor=950, factor_percent=25)])
        self.assertEqual((consumer['score_minor'], consumer['score_minor_units'], consumer['score']), (23750, 1000, '23.750'))

    def test_a_term_change_reaches_through_the_consumer_term(self):
        def edit(spec):
            target = node(spec, 'TERM-001')
            target['data']['definition'] += ' The tenant is never empty.'
            target['revision'] += 1
        consumer, = self.consumers(edit)['consumers']
        self.assertEqual([(u['external_id'], u['level']) for u in consumer['uses']], [('REQ-001', 'minor'), ('TERM-001', 'minor')])
        users = sorted(e['from'] for e in self.spec['edges'] if (e['relation'], e['to']) == ('uses_term', 'TERM-005')
                       and node(self.spec, e['from'])['kind'] == 'Requirement')
        self.assertEqual(sorted(r['id'] for r in consumer['requirements']), sorted(set(users) | {'REQ-004'}))
        self.assertTrue(all(r['factor_percent'] == 25 for r in consumer['requirements']))

    def test_a_withdrawn_export_is_breaking_for_its_users_and_an_unrelated_change_reaches_nobody(self):
        consumer, = self.consumers(lambda s: s.update(exports=['REQ-001']), '2.0.0')['consumers']
        self.assertIn(dict(external_id='TERM-001', level='major', local_ids=['TERM-005']), consumer['uses'])
        consumer, = self.consumers(self.retitle('GOAL-001'))['consumers']
        self.assertEqual([u['external_id'] for u in consumer['uses']], ['REQ-001'])  # the goal is reached through REQ-001
        def unrelated(spec):
            spec['nodes'].append(dict(node(spec, 'GOAL-001'), id='GOAL-002', title='Another goal'))
        self.assertEqual(self.consumers(unrelated)['consumers'][0]['uses'], [])
        self.assertEqual(release_store.impact(ReleaseStore.store(self, self.identity), self.identity,
                                              self.successor(self.identity, '1.0.1', self.retitle('GOAL-001')))['consumers'], [])


class Parts(Examples):
    """AX-M-022: a specification in several files is the same specification."""

    def test_split_and_join_keep_the_digest(self):
        for budget in (20000, 60000, spec_parts.PART_BUDGET):
            with self.subTest(budget=budget):
                parts = spec_parts.split(self.spec, budget)
                self.assertTrue(all(len(qa.canonical(p)) <= budget for p in parts))
                files = {f'p{i}.json': json.dumps(p).encode() for i, p in enumerate(parts)}
                manifest = dict(format=spec_parts.MANIFEST, spec_sha256=qa.digest(qa.canonical(self.spec)),
                                parts=[dict(path=name, sha256=qa.digest(raw)) for name, raw in files.items()])
                joined = spec_parts.join(manifest, files.__getitem__)
                self.assertEqual(qa.canonical(joined), qa.canonical(self.spec))
                self.assertEqual(list(joined), list(self.spec))
        self.assertGreater(len(spec_parts.split(self.spec, 20000)), 5)
        self.assertEqual(len(spec_parts.split(self.spec)), 1)

    def test_a_store_reads_parts_as_the_release_they_are(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-parts-') as directory:
            root = Path(directory)
            manifest = spec_parts.write(self.spec, root / 'ledger-1.1.0', budget=30000)
            self.assertEqual(qa.canonical(spec_parts.read(manifest)), qa.canonical(self.spec))
            for position, document in enumerate([self.base, self.base_approvals, self.spec_approvals, self.identity]):
                (root / f'{position}.json').write_text(json.dumps(document))
            report = release_store.verify(release_store.load([directory]))
            head = next(r for r in report['releases'] if r['version'] == '1.1.0')
            # The approvals were made for the single file; they hold for the parts because the digest is the same.
            self.assertEqual((head['status'], head['approvals'], head['spec_sha256']), ('pass', 'pass', qa.digest(qa.canonical(self.spec))))
            with self.assertRaisesRegex(ValueError, 'not empty'):
                spec_parts.write(self.spec, root / 'ledger-1.1.0')

    def test_damaged_or_escaping_parts_are_refused(self):
        parts = spec_parts.split(self.spec, 60000)
        files = {f'p{i}.json': json.dumps(p).encode() for i, p in enumerate(parts)}
        entries = [dict(path=name, sha256=qa.digest(raw)) for name, raw in files.items()]
        good = dict(format=spec_parts.MANIFEST, spec_sha256=qa.digest(qa.canonical(self.spec)), parts=entries)
        cases = [
            ('Part digest differs', good, dict(files, **{'p1.json': files['p1.json'] + b' '})),
            ('differs from the manifest digest', dict(good, parts=entries[:-1]), files),
            ('differs from the manifest digest', dict(good, parts=entries + entries[-1:]), files),
            ('Root field repeated', dict(good, parts=entries[:1] + entries), files),
            ('must stay beside the manifest', dict(good, parts=[dict(entries[0], path='../p0.json')] + entries[1:]), files),
            ('Part count out of bounds', dict(good, parts=[]), files),
            ('Not a parts manifest', dict(good, format='axiomspec-parts/9'), files)]
        for message, manifest, available in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    spec_parts.join(manifest, available.__getitem__)
        missing = dict(good, parts=entries[1:])
        with self.assertRaisesRegex(ValueError, 'A root field is missing'):
            spec_parts.join(missing, files.__getitem__)

    def test_a_specification_larger_than_one_file_is_checked_in_parts(self):
        big = copy.deepcopy(self.base)
        template, edge = node(big, 'REQ-001'), max(int(e['id'].split('-')[1]) for e in big['edges'])
        for number in range(3000):
            rid = f'REQ-{100000 + number}'
            big['nodes'].append(dict(copy.deepcopy(template), id=rid, title=f'Generated requirement {number}'))
            big['edges'].append(dict(id=f'EDGE-{edge + 1 + number}', relation='satisfies', origin='declared',
                                     rationale='Generated for the size test.', **{'from': rid, 'to': 'GOAL-001'}))
        size = len(json.dumps(big).encode())
        self.assertGreater(size, qa.BOUNDS['max_input_bytes'])
        started = time.perf_counter()
        self.assertEqual(qa.reference_errors(big), [])
        with tempfile.TemporaryDirectory(prefix='axiomspec-big-') as directory:
            manifest = spec_parts.write(big, Path(directory) / 'big')
            self.assertGreater(len(json.loads(manifest.read_text())['parts']), 1)
            joined = spec_parts.read(manifest)
        self.assertEqual(qa.digest(qa.canonical(joined)), qa.digest(qa.canonical(big)))
        report = approvals.verify(big, fk.approvals_for(big, big, PASSKEYS))
        self.assertEqual(report['status'], 'pass')
        self.assertLess(time.perf_counter() - started, 120)


class MigrationTo03(Examples):
    def source(self, document):
        old = copy.deepcopy(document)
        for key in ('approval', 'imports', 'exports'):
            del old[key]
        old.update(format='axiomspec/0.2', profile='AX-CORE-0.2')
        return old

    def test_candidate_is_valid_and_decides_no_policy(self):
        source = self.source(self.base)
        before = copy.deepcopy(source)
        candidate, decisions = migrate_0_2.migrate(source)
        self.assertEqual(source, before)
        self.assertTrue(qa.make_validator(qa.read('schemas/spec.schema.json')).is_valid(candidate))
        self.assertEqual(qa.reference_errors(candidate), [])
        self.assertEqual(candidate['approval'], dict(policy={band: dict(approvers=0, methods=[]) for band in BANDS}, keys=[]))
        self.assertEqual([d['field'] for d in decisions], ['approval.policy', 'approval.keys', 'exports'])
        candidate['approval'] = self.base['approval']
        self.assertEqual(qa.canonical(candidate), qa.canonical(self.base))

    def test_a_successor_names_the_migrated_baseline(self):
        alone, decisions = migrate_0_2.migrate(self.source(self.spec))
        self.assertIn('release.previous.spec_sha256', [d['field'] for d in decisions])
        self.assertEqual(alone['release']['previous'], self.spec['release']['previous'])
        chained, decisions = migrate_0_2.migrate(self.source(self.spec), self.base)
        self.assertNotIn('release.previous.spec_sha256', [d['field'] for d in decisions])
        self.assertEqual(chained['release']['previous']['spec_sha256'], qa.digest(qa.canonical(self.base)))
        self.assertEqual(migrate_0_2.canonical_digest(self.base), qa.digest(qa.canonical(self.base)))
        with self.assertRaisesRegex(ValueError, 'not the version'):
            migrate_0_2.migrate(self.source(self.spec), self.spec)
        with self.assertRaisesRegex(ValueError, 'Unsupported source format'):
            migrate_0_2.migrate(self.spec)

    def test_command_line_never_overwrites(self):
        import contextlib, io
        with tempfile.TemporaryDirectory(prefix='axiomspec-migrate-') as directory:
            source, target = Path(directory) / 'old.json', Path(directory) / 'new.json'
            source.write_text(json.dumps(self.source(self.base)))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(migrate_0_2.main([str(source), str(target)]), 0)
                self.assertEqual(migrate_0_2.main([str(source), str(target)]), 2)
                self.assertEqual(migrate_0_2.main([str(source)]), 2)
            self.assertEqual(json.loads(source.read_text())['format'], 'axiomspec/0.2')


if __name__ == '__main__':
    unittest.main()
