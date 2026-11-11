"""Format 0.2: weights in minor units, feature flags, releases and their comparison (gate G14).

Each case changes one thing on the reference ledger and expects one named result. The comparison cases
derive a candidate from release 1.0.0 of the ledger, so a classification is always checked against a real
baseline and never against a hand-written expectation of the whole report.
"""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    module_spec = importlib.util.spec_from_file_location(f'format02_{name}', ROOT / f'qa/{name}.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


qa, diff, migration, run_checks = load('check_package'), load('release_diff'), load('migrate_0_1'), load('run_checks')
migration_0_2 = load('migrate_0_2')
SPEC, BASE = 'examples/refund-ledger/spec.json', 'examples/refund-ledger/releases/1.0.0.json'


class Ledger(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read(SPEC)

    def node(self, node_id, spec=None):
        return next(n for n in (spec or self.spec)['nodes'] if n['id'] == node_id)

    def errors(self):
        return qa.reference_errors(self.spec)


class WeightsInMinorUnits(Ledger):
    def test_weight_is_one_to_one_hundred_points_in_the_declared_units(self):
        # The ledger declares 10 minor units per point: 10 is 1.0 point and 1000 is 100.0 points.
        for weight, risk, expected in [(10, 'low', []), (1000, 'critical', []), (9, 'low', ['WEIGHT_RANGE']),
                                       (1001, 'critical', ['WEIGHT_RANGE'])]:
            with self.subTest(weight=weight):
                self.node('REQ-001')['data'].update(weight_minor=weight, risk=risk)
                self.assertEqual(self.errors(), expected)

    def test_risk_label_is_the_band_of_the_weight(self):
        edges = [(250, 'low'), (251, 'medium'), (500, 'medium'), (501, 'high'), (750, 'high'), (751, 'critical')]
        for weight, band in edges:
            for label in ('low', 'medium', 'high', 'critical'):
                with self.subTest(weight=weight, label=label):
                    self.node('REQ-001')['data'].update(weight_minor=weight, risk=label)
                    self.assertEqual(self.errors(), [] if label == band else ['RISK_BAND_MISMATCH'])

    def test_same_weights_are_valid_in_each_unit(self):
        # 1 unit: 70 is 70 points. 1000 units: 70000 is 70 points. The value, not the integer, carries the meaning.
        validator = qa.make_validator(qa.read('schemas/spec.schema.json'))
        for units in (1, 10, 100, 1000):
            with self.subTest(units=units):
                spec = qa.read(SPEC)
                spec['project']['weight_minor_units'] = units
                for node in spec['nodes']:
                    if node['kind'] == 'Requirement':
                        node['data']['weight_minor'] = node['data']['weight_minor'] * units // 10
                self.assertTrue(validator.is_valid(spec))
                self.assertEqual(qa.reference_errors(spec), [])
        self.node('REQ-004', spec)['data']['weight_minor'] = 100001  # 100.001 points at 1000 units per point
        self.assertEqual(qa.reference_errors(spec), ['WEIGHT_RANGE'])
        self.assertEqual(qa.weight_band(25001, 1000), 'medium')
        self.assertEqual(qa.weight_band(26, 1), qa.weight_band(260, 10))
        self.assertEqual(qa.weight_band(25, 1), 'low')
        self.assertEqual(qa.weight_band(2501, 100), 'medium')

    def test_schema_bounds_the_fields(self):
        validator = qa.make_validator(qa.read('schemas/spec.schema.json'))
        for mutate in [lambda s: s['project'].update(weight_minor_units=5),
                       lambda s: self.node('REQ-001', s)['data'].update(weight_minor=0),
                       lambda s: self.node('REQ-001', s)['data'].pop('weight_minor'),
                       lambda s: s['release'].update(version='1.1'),
                       lambda s: s['release'].update(version='01.1.0'),
                       lambda s: s['flags'][0].update(state='rollout'),
                       lambda s: s.pop('flags')]:
            spec = qa.read(SPEC)
            self.assertTrue(validator.is_valid(spec))
            mutate(spec)
            self.assertFalse(validator.is_valid(spec))


class FeatureFlags(Ledger):
    def test_reference_to_an_undeclared_flag(self):
        self.node('REQ-001')['data']['flag_id'] = 'FLAG-999'
        self.assertEqual(self.errors(), ['UNKNOWN_FLAG'])
        self.spec = qa.read(SPEC)
        self.node('TEST-001')['data']['flag_states'] = [dict(flag_id='FLAG-999', state='enabled')]
        self.assertEqual(self.errors(), ['UNKNOWN_FLAG'])

    def test_optional_requirement_names_its_flag(self):
        self.node('REQ-010')['data']['flag_id'] = None
        self.assertEqual(self.errors(), ['OPTIONAL_WITHOUT_FLAG', 'UNUSED_FLAG'])

    def test_flagged_must_requirement_is_tested_in_both_states(self):
        for test_id in ('TEST-019', 'TEST-020'):
            with self.subTest(removed=test_id):
                self.spec = qa.read(SPEC)
                self.node(test_id)['data']['flag_states'] = []
                self.assertEqual(self.errors(), ['FLAG_STATE_UNTESTED'])
        self.spec = qa.read(SPEC)
        self.node('TEST-020')['status'] = 'draft'  # a draft test covers nothing
        self.assertEqual(self.errors(), ['FLAG_STATE_UNTESTED'])
        self.spec = qa.read(SPEC)
        self.node('REQ-010')['data']['priority'] = 'should'  # the obligation follows must requirements
        self.node('TEST-020')['data']['flag_states'] = []
        self.assertEqual(self.errors(), [])

    def test_one_test_states_one_state_per_flag(self):
        self.node('TEST-019')['data']['flag_states'].append(dict(flag_id='FLAG-001', state='disabled'))
        self.assertEqual(self.errors(), ['FLAG_STATE_CONFLICT'])

    def test_flag_registry_rules(self):
        flag = self.spec['flags'][0]
        cases = [(dict(introduced_in='1.2.0'), ['FLAG_VERSION']),                      # later than this release
                 (dict(introduced_in='1.1.0', remove_by='1.1.0'), ['FLAG_VERSION']),   # removed no later than introduced
                 (dict(introduced_in='1.0.0', remove_by='1.1.0'), ['STALE_FLAG']),     # this release reached the target
                 (dict(introduced_in='0.9.0', remove_by='1.0.5'), ['STALE_FLAG']),
                 (dict(remove_by=None), []),
                 (dict(remove_by='1.10.0'), []),                                       # compared as numbers, not text
                 (dict(owner='ACTOR-999'), ['UNKNOWN_ACTOR'])]
        for change, expected in cases:
            with self.subTest(change=change):
                self.spec['flags'][0] = dict(flag, **change)
                self.assertEqual(self.errors(), expected)
        self.spec['flags'] = [flag, dict(flag, id='FLAG-002', key='second_flag')]
        self.assertEqual(self.errors(), ['UNUSED_FLAG'])
        self.spec['flags'] = [flag, dict(flag, id='FLAG-002')]
        self.assertEqual(self.errors(), ['DUPLICATE_FLAG_KEY', 'UNUSED_FLAG'])
        self.spec['flags'] = [dict(flag, id='REQ-777')]
        self.assertIn('WRONG_PREFIX', self.errors())


class ReleaseDeclaration(Ledger):
    def test_version_is_one_step_after_the_named_baseline(self):
        for previous, version, step in [('1.0.0', '1.0.1', 'patch'), ('1.0.0', '1.1.0', 'minor'), ('1.0.0', '2.0.0', 'major'),
                                        ('1.9.3', '1.10.0', 'minor'), ('1.0.0', '1.2.0', None), ('1.0.0', '1.0.0', None),
                                        ('1.0.0', '0.9.0', None), ('1.0.0', '2.1.0', None), ('1.0.0', '1.1.1', None)]:
            with self.subTest(previous=previous, version=version):
                self.assertEqual(qa.version_step(previous, version), step)
        self.spec['release']['version'] = '1.2.0'
        self.assertEqual(self.errors(), ['INVALID_VERSION_STEP'])

    def test_first_release_has_nothing_to_be_compatible_with(self):
        self.spec['release']['previous'] = None
        self.assertEqual(self.errors(), ['COMPATIBILITY_WITHOUT_BASELINE'])
        self.spec['release']['compatibility'] = []
        self.assertEqual(self.errors(), [])

    def test_compatibility_entry_rests_on_an_answered_active_decision(self):
        entry = self.spec['release']['compatibility'][0]
        for decision in ('DEC-999', 'REQ-001'):
            entry['decision_id'] = decision
            self.assertEqual(self.errors(), ['INVALID_COMPATIBILITY_DECISION'])
        entry['decision_id'] = 'DEC-004'
        for change in (dict(status='draft'), dict(status='retired')):
            self.spec = qa.read(SPEC)
            self.node('DEC-004').update(change)
            self.assertIn('INVALID_COMPATIBILITY_DECISION', self.errors())
        self.spec = qa.read(SPEC)
        self.node('DEC-004')['data']['answer'] = None
        self.assertEqual(self.errors(), ['INVALID_COMPATIBILITY_DECISION'])

    def test_acknowledged_break_states_its_migration(self):
        entry = self.spec['release']['compatibility'][0]
        entry['classification'] = 'breaking'
        self.assertEqual(self.errors(), ['MISSING_MIGRATION'])
        entry['migration'] = 'Re-run the cancellation suite; no stored data changes.'
        self.assertEqual(self.errors(), [])
        self.spec['release']['compatibility'].append(copy.deepcopy(entry))
        self.assertEqual(self.errors(), ['DUPLICATE_COMPATIBILITY_SUBJECT'])


class ReleaseComparison(unittest.TestCase):
    """G14 on candidates derived from release 1.0.0 of the ledger."""

    def setUp(self):
        self.base = qa.read(BASE)

    def candidate(self, version='1.0.1', base=None):
        base = base or self.base
        candidate = copy.deepcopy(base)
        candidate['release'] = dict(version=version, compatibility=[],
                                    previous=dict(version=base['release']['version'], spec_sha256=qa.digest(qa.canonical(base))))
        return candidate

    @staticmethod
    def node(spec, node_id):
        return next(n for n in spec['nodes'] if n['id'] == node_id)

    def edit(self, spec, node_id, **data):
        node = self.node(spec, node_id)
        node['revision'] += 1
        node['data'].update(data)
        return node

    def accept(self, spec, subject_id, classification='breaking'):
        spec['release']['compatibility'].append(dict(
            subject_id=subject_id, classification=classification, decision_id='DEC-001',
            migration='Stated for the test.' if classification == 'breaking' else None))

    def codes(self, report):
        return [e['code'] for e in report['errors']]

    def level(self, report, subject_id):
        return next(c['level'] for c in report['changes'] if c['subject_id'] == subject_id)

    def test_ledger_release_1_1_0_is_a_minor_step_with_three_recorded_overrides(self):
        report = diff.compare(self.base, qa.read(SPEC))
        self.assertEqual((report['status'], report['declared_step'], report['required_step']), ('pass', 'minor', 'minor'))
        overridden = {c['subject_id']: c['accepted_as'] for c in report['changes'] if c['breaking_candidate']}
        self.assertEqual(overridden, dict.fromkeys(('CON-009', 'CON-010', 'CON-011'), 'compatible'))
        self.assertEqual(report['counts']['major'], 0)
        self.assertEqual(report['risk']['weight_minor_units'], 10)
        self.assertEqual(report['risk']['unmapped_changes'], [])
        # Without the recorded decision the same release does not pass.
        candidate = qa.read(SPEC)
        candidate['release']['compatibility'] = []
        # Unacknowledged, the three candidates also count as breaking, so the minor step is too small.
        self.assertEqual(set(self.codes(diff.compare(self.base, candidate))), {'UNACKNOWLEDGED_BREAKING', 'VERSION_BUMP_TOO_SMALL'})

    def test_unchanged_content_requires_no_step_and_scores_zero(self):
        report = diff.compare(self.base, self.candidate())
        self.assertEqual((report['status'], report['required_step'], report['changes']), ('pass', 'none', []))
        self.assertEqual((report['risk']['score_minor'], report['risk']['score'], report['risk']['exposure_permille']), (0, '0.000', 0))
        self.assertEqual(diff.compare(self.base, self.candidate()), report)  # deterministic body

    def test_candidate_names_its_baseline_by_version_and_digest(self):
        for change in (dict(previous=None), dict(previous=dict(version='1.0.0', spec_sha256='0' * 64)),
                       dict(previous=dict(version='0.9.9', spec_sha256=qa.digest(qa.canonical(self.base))))):
            candidate = self.candidate()
            candidate['release'].update(change)
            self.assertIn('BASELINE_MISMATCH', self.codes(diff.compare(self.base, candidate)))
        other = self.candidate()
        other['project']['id'] = 'PROJECT-002'
        self.assertIn('PROJECT_CHANGED', self.codes(diff.compare(self.base, other)))
        with self.assertRaisesRegex(ValueError, 'migrate an older baseline'):
            diff.compare(dict(self.base, format='axiomspec/0.1'), self.candidate())

    def test_identity_and_revision_rules(self):
        removed = self.candidate()
        removed['nodes'] = [n for n in removed['nodes'] if n['id'] != 'SCN-001']
        self.assertIn('REMOVED_ID', self.codes(diff.compare(self.base, removed)))
        retyped = self.candidate()
        self.node(retyped, 'ASM-001').update(kind='Risk')
        self.assertIn('KIND_CHANGED', self.codes(diff.compare(self.base, retyped)))
        silent = self.candidate()
        self.node(silent, 'GOAL-001')['title'] = 'Renamed without a revision'
        self.assertEqual(self.codes(diff.compare(self.base, silent)), ['REVISION_NOT_INCREASED'])
        lowered = self.candidate()
        self.node(self.base, 'GOAL-001')['revision'] = 3
        lowered = self.candidate()
        self.node(lowered, 'GOAL-001')['revision'] = 2
        self.assertIn('REVISION_DECREASED', self.codes(diff.compare(self.base, lowered)))

    def test_retired_id_is_never_brought_back(self):
        self.node(self.base, 'ASM-001')['status'] = 'retired'
        revived = self.candidate()
        self.node(revived, 'ASM-001').update(status='active', revision=2)
        self.assertIn('RETIRED_REUSED', self.codes(diff.compare(self.base, revived)))

    def classify(self, change, base=None):
        candidate = self.candidate(base=base)
        subject = change(candidate)
        return self.level(diff.compare(base or self.base, candidate), subject)

    def test_requirement_changes(self):
        def renamed(c):
            node = self.node(c, 'REQ-001'); node['revision'] += 1; node['title'] = 'Refuse an excess reservation'
            return 'REQ-001'
        def retired(c):
            node = self.node(c, 'REQ-007'); node['revision'] += 1; node['status'] = 'retired'
            return 'REQ-007'
        def added(status):
            def change(c):
                node = copy.deepcopy(self.node(c, 'REQ-001')); node.update(id='REQ-900', status=status)
                c['nodes'].append(node)
                return 'REQ-900'
            return change
        cases = [(renamed, 'patch'),
                 (lambda c: self.edit(c, 'REQ-001', response='reject it and record why')['id'], 'major'),
                 (lambda c: self.edit(c, 'REQ-001', trigger='a reservation exceeds the capacity')['id'], 'major'),
                 (lambda c: self.edit(c, 'REQ-001', priority='should')['id'], 'major'),
                 (lambda c: self.edit(c, 'REQ-001', weight_minor=740)['id'], 'patch'),
                 (lambda c: self.edit(c, 'REQ-001', category='data')['id'], 'patch'),
                 (retired, 'major'), (added('active'), 'minor'), (added('draft'), 'patch')]
        for change, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.classify(change), expected)
        # A statement change on a requirement that is not a must is an addition-level change.
        self.node(self.base, 'REQ-007')['data']['priority'] = 'should'
        self.assertEqual(self.classify(lambda c: self.edit(c, 'REQ-007', response='record the outcome')['id']), 'minor')
        self.assertEqual(self.classify(lambda c: self.edit(c, 'REQ-007', priority='must')['id']), 'minor')

    def test_constraint_changes(self):
        tighter = copy.deepcopy(self.node(self.base, 'CON-002')['data']['expression'])
        def added(formalizes):
            def change(c):
                node = copy.deepcopy(self.node(c, 'CON-003')); node['id'] = 'CON-900'
                c['nodes'].append(node)
                if formalizes == 'new':
                    requirement = copy.deepcopy(self.node(c, 'REQ-001')); requirement['id'] = 'REQ-900'
                    c['nodes'].append(requirement)
                c['edges'].append(dict(id='EDGE-9000', relation='formalizes', origin='declared', rationale='test',
                                       **{'from': 'CON-900', 'to': 'REQ-900' if formalizes == 'new' else 'REQ-001'}))
                return 'CON-900'
            return change
        def retired(c):
            node = self.node(c, 'CON-003'); node['revision'] += 1; node['status'] = 'retired'
            return 'CON-003'
        cases = [(lambda c: self.edit(c, 'CON-001', expression=tighter)['id'], 'major'),      # tighter or looser: not decidable here
                 (lambda c: self.edit(c, 'CON-001', effective_until='2027-01-01T00:00:00Z')['id'], 'major'),
                 (lambda c: self.edit(c, 'CON-006', review_protocol='A different reviewer protocol.')['id'], 'minor'),  # soft
                 (lambda c: self.edit(c, 'CON-001', roles=['verification'])['id'], 'patch'),
                 (retired, 'major'),
                 (added('existing'), 'major'),   # a new hard rule on a requirement the baseline already had
                 (added('new'), 'minor')]        # a new hard rule that only concerns a new requirement
        for change, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.classify(change), expected)

    def test_model_term_and_decision_changes(self):
        model = self.node(self.base, 'MODEL-001')['data']
        fewer = [t for t in model['transitions'] if t['id'] != 'TRN-002']
        more_states = model['states'] + [dict(name='expired', terminal=True)]
        more_moves = model['transitions'] + [dict(id='TRN-005', event='expire', guard_id=None, effect_ref=None,
                                                  **{'from': 'reserved', 'to': 'expired'})]
        cases = [(lambda c: self.edit(c, 'MODEL-001', transitions=fewer)['id'], 'major'),
                 (lambda c: self.edit(c, 'MODEL-001', initial='reserved')['id'], 'major'),
                 (lambda c: self.edit(c, 'MODEL-001', states=more_states, transitions=more_moves)['id'], 'minor'),
                 (lambda c: self.edit(c, 'TERM-001', unit='EUR_millicent')['id'], 'major'),
                 (lambda c: self.edit(c, 'TERM-001', definition='A non-negative integer number of cents.')['id'], 'minor'),
                 (lambda c: self.edit(c, 'TERM-001', aliases=['cent'])['id'], 'patch'),
                 (lambda c: self.edit(c, 'DEC-001', answer='Only committed')['id'], 'minor'),
                 (lambda c: self.edit(c, 'GOAL-001', success_measure='Measured weekly.')['id'], 'minor'),
                 (lambda c: self.edit(c, 'TEST-001', negative=False)['id'], 'patch'),
                 (lambda c: self.edit(c, 'SCN-001', expected='Refuse it.')['id'], 'patch')]
        for change, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.classify(change), expected)

    def test_environment_changes(self):
        def env(change):
            def apply(c):
                change(next(e for e in c['environments'] if e['id'] == 'ENV-001'))
                return 'ENV-001'
            return apply
        state = lambda e: e['schema']['properties']['state']['properties']
        def add_property(e):
            state(e)['note'] = dict(type='string', maxLength=10)
            e['schema']['properties']['state']['required'].append('note')
        def add_environment(c):
            c['environments'].append(dict(copy.deepcopy(c['environments'][0]), id='ENV-900'))
            return 'ENV-900'
        def remove_environment(c):
            c['environments'] = [e for e in c['environments'] if e['id'] != 'ENV-002']
            return 'ENV-002'
        cases = [(env(lambda e: state(e)['captured_minor'].update(maximum=200000000)), 'minor'),   # accepts more
                 (env(lambda e: state(e)['captured_minor'].update(maximum=1000)), 'major'),        # rejects what was valid
                 (env(lambda e: state(e)['captured_minor'].update(minimum=1)), 'major'),
                 (env(lambda e: state(e)['refunds'].update(maxItems=2000)), 'minor'),
                 (env(lambda e: state(e)['currency'].update(enum=['EUR', 'USD'])), 'minor'),
                 (env(lambda e: state(e)['refunds']['items']['properties']['status'].update(enum=['reserved', 'committed', 'released'])), 'major'),
                 (env(add_property), 'major'),                                                     # every property is required
                 (env(lambda e: state(e)['tenant_id'].update(type='integer', minimum=0, maximum=9)), 'major'),
                 (env(lambda e: e['units'].pop()), 'major'),
                 (env(lambda e: e.update(title='One ledger observation')), 'patch'),
                 (add_environment, 'minor'), (remove_environment, 'major')]
        for change, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.classify(change), expected)
        number = dict(type='integer', minimum=0, maximum=10)
        self.assertEqual(diff.schema_change(number, dict(number, description='text only')), 'same')
        self.assertEqual(diff.schema_change(dict(number, enum=[1, 2]), number), 'widened')
        self.assertEqual(diff.schema_change(number, dict(number, enum=[1, 2])), 'breaking')

    def test_flag_changes(self):
        flag = dict(id='FLAG-001', key='report', title='Report', state='enabled', owner='ACTOR-001',
                    introduced_in='1.0.0', remove_by=None)
        on = copy.deepcopy(self.base)
        on['flags'] = [flag]
        off = copy.deepcopy(self.base)
        off['flags'] = [dict(flag, state='disabled')]
        def set_flag(**change):
            def apply(c):
                c['flags'][0].update(change)
                return 'FLAG-001'
            return apply
        def remove(c):
            c['flags'] = []
            return 'FLAG-001'
        def add(c):
            c['flags'].append(dict(flag))
            return 'FLAG-001'
        def gate(c):
            self.edit(c, 'REQ-008', flag_id='FLAG-001')
            return 'REQ-008'
        for base, change, expected in [(on, set_flag(state='disabled'), 'major'),   # behavior that was on is off
                                       (off, set_flag(state='enabled'), 'minor'),
                                       (on, set_flag(key='capacity_report'), 'major'),
                                       (on, set_flag(remove_by='2.0.0'), 'patch'),
                                       (on, remove, 'patch'), (self.base, add, 'minor'),
                                       (off, gate, 'major'),                         # an active requirement goes dark
                                       (on, gate, 'minor')]:
            with self.subTest(expected=expected):
                self.assertEqual(self.classify(change, base), expected)

    def test_traceability_changes_are_patches_and_an_actor_change_is_unmapped(self):
        candidate = self.candidate()
        candidate['edges'][0]['rationale'] = 'Reworded.'
        candidate['bindings'][0]['symbol'] = 'RefundLedger'
        candidate['actors'][0]['name'] = 'Product owner'
        report = diff.compare(self.base, candidate)
        self.assertEqual((report['status'], report['required_step'], report['counts']), ('pass', 'patch', dict(major=0, minor=0, patch=3)))
        self.assertEqual(report['risk']['unmapped_changes'], ['ACTOR-001'])

    def test_declared_step_covers_the_required_one(self):
        addition = lambda c: c['nodes'].append(dict(copy.deepcopy(self.node(c, 'REQ-001')), id='REQ-900'))
        for version, expected in [('1.0.1', ['VERSION_BUMP_TOO_SMALL']), ('1.1.0', []), ('2.0.0', [])]:
            candidate = self.candidate(version)
            addition(candidate)
            self.assertEqual(self.codes(diff.compare(self.base, candidate)), expected)
        skipped = self.candidate('1.2.0')
        self.assertEqual(self.codes(diff.compare(self.base, skipped)), ['INVALID_VERSION_STEP'])

    def test_breaking_candidate_is_acknowledged_or_overridden_on_record(self):
        def broken(version, classification=None):
            candidate = self.candidate(version)
            self.edit(candidate, 'REQ-001', response='reject it and record why')
            if classification:
                self.accept(candidate, 'REQ-001', classification)
            return diff.compare(self.base, candidate)
        self.assertEqual(self.codes(broken('2.0.0')), ['UNACKNOWLEDGED_BREAKING'])
        self.assertEqual(self.codes(broken('2.0.0', 'breaking')), [])
        self.assertEqual(self.codes(broken('1.1.0', 'breaking')), ['VERSION_BUMP_TOO_SMALL'])
        overridden = broken('1.1.0', 'compatible')
        self.assertEqual((self.codes(overridden), overridden['required_step']), ([], 'minor'))
        self.assertEqual(self.codes(broken('1.0.1', 'compatible')), ['VERSION_BUMP_TOO_SMALL'])  # an override is not free
        unused = self.candidate()
        self.accept(unused, 'REQ-001')
        self.assertEqual(self.codes(diff.compare(self.base, unused)), ['UNUSED_COMPATIBILITY_ENTRY'])

    def test_change_risk_score_is_weight_times_factor_in_minor_units(self):
        # REQ-001 weighs 700 at 10 minor units per point: 70.0 points.
        breaking = self.candidate('2.0.0')
        self.edit(breaking, 'REQ-001', response='reject it and record why')
        self.accept(breaking, 'REQ-001')
        risk = diff.compare(self.base, breaking)['risk']
        self.assertEqual(risk['requirements'], [dict(id='REQ-001', weight_minor=700, factor_percent=100, reach='direct')])
        self.assertEqual((risk['score_minor'], risk['score_minor_units'], risk['score']), (70000, 1000, '70.000'))
        self.assertEqual(risk['total_weight_minor'], 5125)
        self.assertEqual(risk['exposure_permille'], 70000 * 1000 // (5125 * 100))
        # The same change accepted as compatible counts as an addition: half.
        compatible = self.candidate('1.1.0')
        self.edit(compatible, 'REQ-001', response='reject it and record why')
        self.accept(compatible, 'REQ-001', 'compatible')
        self.assertEqual(diff.compare(self.base, compatible)['risk']['score'], '35.000')
        # A test edit reaches the requirements it verifies at the patch factor: (600 + 600) x 10%.
        patch = self.candidate()
        self.edit(patch, 'TEST-004', negative=False)
        risk = diff.compare(self.base, patch)['risk']
        self.assertEqual([(r['id'], r['factor_percent']) for r in risk['requirements']], [('REQ-002', 10), ('REQ-003', 10)])
        self.assertEqual(risk['score'], '12.000')

    def test_dependents_are_reached_at_a_capped_factor(self):
        for document in (self.base,):
            document['edges'].append(dict(id='EDGE-9001', relation='depends_on', origin='declared', rationale='test',
                                          **{'from': 'REQ-002', 'to': 'REQ-001'}))
            document['edges'].append(dict(id='EDGE-9002', relation='depends_on', origin='declared', rationale='test',
                                          **{'from': 'REQ-003', 'to': 'REQ-002'}))
        breaking = self.candidate('2.0.0')
        self.edit(breaking, 'REQ-001', response='reject it and record why')
        self.accept(breaking, 'REQ-001')
        reached = {r['id']: (r['factor_percent'], r['reach']) for r in diff.compare(self.base, breaking)['risk']['requirements']}
        self.assertEqual(reached, {'REQ-001': (100, 'direct'), 'REQ-002': (25, 'dependency'), 'REQ-003': (25, 'dependency')})
        patch = self.candidate()
        self.edit(patch, 'REQ-001', category='data')
        reached = {r['id']: r['factor_percent'] for r in diff.compare(self.base, patch)['risk']['requirements']}
        self.assertEqual(reached, {'REQ-001': 10, 'REQ-002': 10, 'REQ-003': 10})  # never above its source

    def test_score_is_the_same_value_in_finer_units(self):
        coarse = self.candidate('2.0.0')
        self.edit(coarse, 'REQ-004', response='deny it')
        self.accept(coarse, 'REQ-004')
        fine = copy.deepcopy(coarse)
        fine['project']['weight_minor_units'] = 100
        for node in fine['nodes']:
            if node['kind'] == 'Requirement':
                node['data']['weight_minor'] *= 10
                node['revision'] = self.node(self.base, node['id'])['revision'] + 1
        a, b = diff.compare(self.base, coarse)['risk'], diff.compare(self.base, fine)['risk']
        self.assertEqual((a['weight_minor_units'], b['weight_minor_units']), (10, 100))
        self.assertEqual(next(r for r in b['requirements'] if r['id'] == 'REQ-004'),
                         dict(id='REQ-004', weight_minor=9500, factor_percent=100, reach='direct'))
        # REQ-004 at 100%: 95 points in both. The finer candidate also edits every other weight field: 10% each.
        self.assertEqual(a['score'], '95.000')
        others = sum(n['data']['weight_minor'] for n in self.base['nodes'] if n['kind'] == 'Requirement') - 950
        self.assertEqual(b['score_minor'], 9500 * 100 + others * 10 * 10)
        self.assertEqual(b['score_minor_units'], 10000)
        finest = copy.deepcopy(coarse)
        finest['project']['weight_minor_units'] = 1000
        for node in finest['nodes']:
            if node['kind'] == 'Requirement':
                node['data']['weight_minor'] *= 100
                node['revision'] = self.node(self.base, node['id'])['revision'] + 1
        c = diff.compare(self.base, finest)['risk']
        self.assertEqual((c['weight_minor_units'], c['score_minor_units']), (1000, 100000))
        self.assertEqual((c['score_minor'], c['exposure_permille']), (b['score_minor'] * 10, b['exposure_permille']))

    def test_command_line_reports_pass_fail_and_input_errors(self):
        import contextlib, io
        def run(*arguments):
            with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                return diff.main(list(arguments)), out.getvalue()
        code, out = run(str(ROOT / BASE), str(ROOT / SPEC))
        self.assertEqual((code, json.loads(out)['status']), (0, 'pass'))
        self.assertEqual(run(str(ROOT / SPEC), str(ROOT / BASE))[0], 2)   # reversed: not its baseline
        self.assertEqual(run(str(ROOT / BASE))[0], 4)
        self.assertEqual(run(str(ROOT / BASE), str(ROOT / 'README.md'))[0], 4)


class Migration(unittest.TestCase):
    def source(self):
        """Release 1.0.0 of the ledger written back in format 0.1."""
        old = qa.read(BASE)
        for key in ('release', 'flags', 'approval', 'imports', 'exports'):
            del old[key]
        del old['project']['weight_minor_units']
        for node in old['nodes']:
            for field in ('weight_minor', 'flag_id', 'flag_states'):
                node['data'].pop(field, None)
        old.update(format='axiomspec/0.1', profile='AX-CORE-0.1')
        return old

    def test_candidate_is_valid_and_the_source_is_untouched(self):
        source = self.source()
        before = copy.deepcopy(source)
        candidate, decisions = migration.migrate(source, '1.0.0', 10)
        self.assertEqual(source, before)
        self.assertEqual((candidate['format'], candidate['profile']), ('axiomspec/0.2', 'AX-CORE-0.2'))
        candidate, later = migration_0_2.migrate(candidate)  # 0.1 reaches the current format in two declared steps
        self.assertEqual([d['field'] for d in later], ['approval.policy', 'approval.keys', 'exports'])
        self.assertTrue(qa.make_validator(qa.read('schemas/spec.schema.json')).is_valid(candidate))
        self.assertEqual(qa.reference_errors(candidate), [])
        self.assertEqual(candidate['release'], dict(version='1.0.0', previous=None, compatibility=[]))
        weights = {n['id']: n['data']['weight_minor'] for n in candidate['nodes'] if n['kind'] == 'Requirement'}
        self.assertEqual((weights['REQ-004'], weights['REQ-007'], weights['REQ-001']), (1000, 500, 750))  # top of each band
        # Every placeholder weight is listed for review; none is presented as decided.
        self.assertEqual(sorted(d['subject_id'] for d in decisions), sorted(weights))
        # With reviewed weights restored, the candidate is release 1.0.0 exactly.
        reviewed = qa.read(BASE)
        for node, original in zip(candidate['nodes'], reviewed['nodes']):
            if node['kind'] == 'Requirement':
                node['data']['weight_minor'] = original['data']['weight_minor']
        candidate['approval'] = reviewed['approval']  # and with the approval policy and keys decided
        self.assertEqual(qa.canonical(candidate), qa.canonical(reviewed))

    def test_optional_requirement_gets_a_flag_to_review(self):
        source = self.source()
        requirement = next(n for n in source['nodes'] if n['id'] == 'REQ-007')
        requirement['data'].update(pattern='optional', trigger=None, feature='auditing is enabled')
        candidate, decisions = migration.migrate(source, '1.0.0')
        self.assertEqual(candidate['flags'], [dict(id='FLAG-001', key='flag_001', title='auditing is enabled', state='enabled',
                                                   owner='ACTOR-001', introduced_in='1.0.0', remove_by=None)])
        self.assertEqual(next(n for n in candidate['nodes'] if n['id'] == 'REQ-007')['data']['flag_id'], 'FLAG-001')
        self.assertIn('FLAG-001', [d['subject_id'] for d in decisions])
        # The migration decides nothing about tests: the missing flag-state coverage stays a visible failure.
        self.assertEqual(qa.reference_errors(migration_0_2.migrate(candidate)[0]), ['FLAG_STATE_UNTESTED'])

    def test_unsupported_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported source format'):
            migration.migrate(qa.read(BASE), '1.0.0')
        with self.assertRaisesRegex(ValueError, '1, 10, 100 or 1000'):
            migration.migrate(self.source(), '1.0.0', 5)

    def test_command_line_never_overwrites(self):
        import contextlib, io
        with tempfile.TemporaryDirectory(prefix='axiomspec-migrate-') as directory:
            source, target = Path(directory) / 'old.json', Path(directory) / 'new.json'
            source.write_text(json.dumps(self.source()))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(migration.main([str(source), str(target), '1.0.0', '10']), 0)
                written = target.read_text()
                self.assertEqual(migration.main([str(source), str(target), '1.0.0', '10']), 2)
                self.assertEqual(migration.main([str(source), str(source), '1.0.0']), 2)
            self.assertEqual(target.read_text(), written)
            self.assertEqual(json.loads(source.read_text())['format'], 'axiomspec/0.1')


class ExampleEvidence(unittest.TestCase):
    """The worked example's bindings resolve and its TestCases were executed (G09, G10)."""

    def setUp(self):
        self.spec = qa.read(SPEC)
        self.ids = [f"test_ledger.{b['symbol']}.test_case" for b in self.spec['bindings'] if b['kind'] == 'test']

    def test_every_unflagged_requirement_has_a_scenario_a_hard_predicate_and_a_test_citing_a_scenario(self):
        # The audit requirement (REQ-007) had an executed test and no scenario until edition 0.5.1.
        nodes = {n['id']: n for n in self.spec['nodes']}
        linked = lambda relation, target: [e['from'] for e in self.spec['edges'] if (e['relation'], e['to']) == (relation, target)]
        for requirement in (n for n in nodes.values() if n['kind'] == 'Requirement' and n['data']['flag_id'] is None):
            with self.subTest(requirement=requirement['id']):
                self.assertTrue(linked('illustrates', requirement['id']))
                self.assertTrue(any(nodes[c]['data']['classification']['strength'] == 'hard'
                                    for c in linked('formalizes', requirement['id'])))
                self.assertTrue(any(nodes[t]['data']['witness_scenario_ids'] for t in linked('verifies', requirement['id'])))

    def test_audit_predicate_fails_on_each_way_of_recording_too_much_or_too_little(self):
        attempt = dict(operation_id='op-1', operation='reserve', outcome='denied')
        expression = next(n for n in self.spec['nodes'] if n['id'] == 'CON-011')['data']['expression']
        holds = lambda rows: qa.ReferenceEvaluator().evaluate(expression, dict(attempt=attempt, added=rows))
        self.assertTrue(holds([dict(attempt)]))
        self.assertFalse(holds([]))
        self.assertFalse(holds([dict(attempt), dict(attempt)]))
        for field in attempt:
            self.assertFalse(holds([dict(attempt, **{field: attempt[field] + ' Bearer s3cr3t'})]))

    def test_symbols_are_resolved_by_parsing(self):
        app = ROOT / 'examples/refund-ledger/app/ledger.py'
        for symbol, expected in [('Ledger', True), ('Ledger.reserve', True), ('authorize', True), ('Ledger.snapshot', True),
                                 ('Ledger.missing', False), ('reserve', False), ('ledger', False)]:
            with self.subTest(symbol=symbol):
                self.assertIs(qa.resolve_symbol(app, symbol), expected)

    def test_every_active_test_case_is_bound_resolved_and_executed(self):
        resolved, cases = qa.check_example_evidence(self.spec, self.ids)
        self.assertEqual((resolved, cases), (len(self.spec['bindings']), 20))

    def test_missing_unbound_or_unresolved_tests_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no executed test under Test007'):
            qa.check_example_evidence(self.spec, [i for i in self.ids if 'Test007' not in i])
        with self.assertRaisesRegex(ValueError, 'belongs to no TestCase binding'):
            qa.check_example_evidence(self.spec, self.ids + ['test_ledger.Unbound.test_case'])
        renamed = copy.deepcopy(self.spec)
        renamed['bindings'][0]['symbol'] = 'LedgerThatDoesNotExist'
        with self.assertRaisesRegex(ValueError, 'BIND-001: symbol'):
            qa.check_example_evidence(renamed, self.ids)
        escaping = copy.deepcopy(self.spec)
        escaping['bindings'][0]['path'] = '../outside.py'
        with self.assertRaisesRegex(ValueError, 'does not resolve inside the package'):
            qa.check_example_evidence(escaping, self.ids)
        planned = copy.deepcopy(self.spec)
        next(n for n in planned['nodes'] if n['id'] == 'TEST-003')['data']['state'] = 'planned'
        with self.assertRaisesRegex(ValueError, 'TEST-003'):
            qa.check_example_evidence(planned, self.ids)
        unbound = copy.deepcopy(self.spec)
        unbound['bindings'] = [b for b in unbound['bindings'] if b['node_id'] != 'TEST-003']
        with self.assertRaisesRegex(ValueError, 'TEST-003'):
            qa.check_example_evidence(unbound, [i for i in self.ids if 'Test003' not in i])

    def test_receipt_is_bound_to_the_inputs_it_executed(self):
        with tempfile.TemporaryDirectory(prefix='axiomspec-example-') as directory:
            root = Path(directory)
            for folder in ('examples/refund-ledger/app', 'examples/refund-ledger/tests'):
                shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('examples/refund-ledger/spec.json', 'qa/check_package.py', 'qa/requirements-qa.txt'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / name, root / name)
            output = root / run_checks.EXAMPLE_OUTPUT
            output.parent.mkdir()
            output.write_text('raw output')
            def receipt():
                return dict(format='axiomspec-test-receipt/0.1', scope='example_application', edition=run_checks.EDITION,
                            status='pass', exit_code=0, command=run_checks.EXAMPLE_COMMAND,
                            runner=dict(name='unittest', trust='untrusted_local'), inputs=run_checks.example_manifest(root),
                            toolchain=run_checks.toolchain(root),
                            tests=dict(test_ids=['a', 'b'], tests_run=2, failures=0, errors=0, skipped=0,
                                       expected_failures=0, unexpected_successes=0),
                            raw_output=dict(path=run_checks.EXAMPLE_OUTPUT, sha256=run_checks.sha(output)))
            good = receipt()
            self.assertEqual(run_checks.validate_example_receipt(root, good), ['a', 'b'])
            for change, message in [(dict(status='fail'), 'successful run'), (dict(exit_code=1), 'successful run'),
                                    (dict(edition='0.4.0'), 'outdated'), (dict(scope='package_checker'), 'outdated'),
                                    (dict(tests=dict(good['tests'], skipped=1)), 'skipped'),
                                    (dict(tests=dict(good['tests'], test_ids=['a', 'a'])), 'duplicate'),
                                    (dict(tests=dict(good['tests'], test_ids=[], tests_run=0)), 'Missing'),
                                    (dict(runner=dict(name='unittest', trust='trusted_adapter')), 'runner mismatch')]:
                with self.subTest(change=list(change)), self.assertRaisesRegex(ValueError, message):
                    run_checks.validate_example_receipt(root, dict(good, **change))
            with (root / 'examples/refund-ledger/app/ledger.py').open('a') as stream:
                stream.write('\n# edited after the run\n')
            with self.assertRaisesRegex(ValueError, 'Stale example test receipt'):
                run_checks.validate_example_receipt(root, good)
            fresh = receipt()
            output.write_text('different output')
            with self.assertRaisesRegex(ValueError, 'raw-output digest'):
                run_checks.validate_example_receipt(root, fresh)


if __name__ == '__main__':
    unittest.main()
