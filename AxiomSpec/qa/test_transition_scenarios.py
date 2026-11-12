"""Edition 0.4.0: before/after observations, and three rules decided in that edition.

The transition predicates are cross-checked against direct calculations on seeded data,
as the snapshot predicates are in the third review.
"""
import copy
import importlib.util
from pathlib import Path
import random
import unittest

ROOT = Path(__file__).resolve().parents[1]
module_spec = importlib.util.spec_from_file_location('transition_checker', ROOT / 'qa/check_package.py')
qa = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(qa)

NON_ADMITTING = {'replayed', 'rejected', 'conflict', 'denied'}


class TransitionObservations(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')
        self.nodes = {n['id']: n for n in self.spec['nodes']}
        self.environment = next(e for e in self.spec['environments'] if e['id'] == 'ENV-002')

    def evaluate(self, constraint_id, observation):
        return qa.ReferenceEvaluator().evaluate(self.nodes[constraint_id]['data']['expression'], observation)

    def test_every_transition_scenario_states_both_assertions(self):
        scenarios = [n for n in self.spec['nodes'] if n['kind'] == 'Scenario' and n['data']['environment_id'] == 'ENV-002']
        self.assertEqual(len(scenarios), 9)
        for scenario in scenarios:
            declared = {e['constraint_id'] for e in scenario['data']['constraint_expectations']}
            self.assertEqual(declared, {'CON-007', 'CON-008'}, scenario['id'])
        # A corpus of witnesses only would not show that the predicates can fail.
        failing = {e['constraint_id'] for s in scenarios if s['data']['intent'] == 'counterexample'
                   for e in s['data']['constraint_expectations'] if e['expected'] is False}
        self.assertEqual(failing, {'CON-007', 'CON-008'})

    def test_one_changed_field_is_a_change(self):
        # CON-007 compares identity, key, status and amount of every earlier record, and the captured amount.
        given = copy.deepcopy(self.nodes['SCN-010']['data']['given'])
        self.assertIs(self.evaluate('CON-007', given), True)
        for field, value in [('id', 'r-z'), ('key', 'z'), ('status', 'released'), ('amount_minor', 601)]:
            with self.subTest(field=field):
                changed = copy.deepcopy(given)
                changed['after']['refunds'][0][field] = value
                self.assertIs(self.evaluate('CON-007', changed), False)
        changed = copy.deepcopy(given)
        changed['after']['captured_minor'] += 1
        self.assertIs(self.evaluate('CON-007', changed), False)
        changed = copy.deepcopy(given)
        del changed['after']['refunds'][1]
        self.assertIs(self.evaluate('CON-007', changed), False)

    def test_200_seeded_transitions_match_direct_domain_oracles(self):
        validator = qa.make_validator(self.environment['schema'])
        rng = random.Random(4018)
        outcomes = {'CON-007': set(), 'CON-008': set()}
        row = lambda i: dict(id=f'r{i}', key=f'k{i}', amount_minor=rng.randrange(1, 40), status=rng.choice(['reserved', 'committed', 'released']))
        for sample in range(200):
            before = [row(i) for i in range(rng.randrange(6))]
            after = copy.deepcopy(before)
            request = dict(key=f'k{rng.randrange(8)}', amount_minor=rng.randrange(1, 40),
                           outcome=rng.choice(['reserved', 'replayed', 'rejected', 'conflict', 'denied']))
            mutation = rng.choice(['none', 'none', 'admit', 'admit', 'wrong_amount', 'extra', 'drop', 'edit'])
            if mutation in {'admit', 'wrong_amount'}:
                after.append(dict(id='r-new', key=request['key'], status='reserved',
                                  amount_minor=request['amount_minor'] + (mutation == 'wrong_amount')))
            elif mutation == 'extra':
                after.append(dict(id='r-extra', key='other', amount_minor=1, status='rejected'))
            elif mutation == 'drop' and after:
                after.pop(rng.randrange(len(after)))
            elif mutation == 'edit' and after:
                after[rng.randrange(len(after))]['amount_minor'] += 1
            cap = rng.randrange(200)
            observation = dict(before=dict(captured_minor=cap, refunds=before),
                               after=dict(captured_minor=cap + rng.choice([0, 0, 0, 1]), refunds=after), request=request)
            validator.validate(observation)
            kept = all(b in after for b in before)
            unchanged = len(after) == len(before) and kept and observation['after']['captured_minor'] == cap
            admitted = (len(after) == len(before) + 1 and kept and any(
                a['key'] == request['key'] and a['status'] == 'reserved' and a['amount_minor'] == request['amount_minor'] for a in after))
            expected = {'CON-007': request['outcome'] not in NON_ADMITTING or unchanged,
                        'CON-008': request['outcome'] != 'reserved' or admitted}
            for constraint_id, value in expected.items():
                with self.subTest(sample=sample, constraint=constraint_id):
                    actual = self.evaluate(constraint_id, observation)
                    self.assertIs(actual, value)
                    outcomes[constraint_id].add(actual)
        self.assertTrue(all(values == {True, False} for values in outcomes.values()))


    def test_300_row_comparison_is_explicitly_unresolved_under_default_budget(self):
        # CON-007 compares every earlier record with every later one: quadratic, like CON-004.
        rows = [dict(id=f'r{i}', key=f'k{i}', amount_minor=1, status='reserved') for i in range(300)]
        observation = dict(before=dict(captured_minor=1000, refunds=rows), after=dict(captured_minor=1000, refunds=list(rows)),
                           request=dict(key='x', amount_minor=1, outcome='rejected'))
        qa.make_validator(self.environment['schema']).validate(observation)
        with self.assertRaises(qa.BudgetExceeded):
            self.evaluate('CON-007', observation)


class RulesDecidedIn040(unittest.TestCase):
    def setUp(self):
        self.spec = qa.read('examples/refund-ledger/spec.json')

    def test_literal_array_is_not_a_collection(self):
        # AX-C-005. Rejected by the evaluator and reported by the reference checks.
        lit = lambda value: dict(kind='literal', value=value)
        literal_loop = dict(kind='quantifier', operator='all', bind='x', collection=lit([1, 2]), predicate=lit(True))
        with self.assertRaisesRegex(ValueError, 'declared array'):
            qa.ReferenceEvaluator().evaluate(literal_loop, {})
        nested = dict(kind='apply', operator='and', arguments=[lit(True), dict(kind='aggregate', operator='count', bind='x',
                      collection=lit(['a']), filter=lit(True), projection=lit(1))])
        with self.assertRaisesRegex(ValueError, 'declared array'):
            qa.ReferenceEvaluator().evaluate(nested, {})
        next(n for n in self.spec['nodes'] if n['id'] == 'CON-003')['data']['expression']['collection'] = lit([])
        self.assertEqual(qa.reference_errors(self.spec), ['LITERAL_COLLECTION'])

    def test_array_field_of_a_bound_element_is_a_collection(self):
        inner = dict(kind='quantifier', operator='exists', bind='t', collection=dict(kind='path', root='o', pointer='/tags'),
                     predicate=dict(kind='apply', operator='eq', arguments=[dict(kind='path', root='t', pointer=''), dict(kind='literal', value='x')]))
        outer = dict(kind='quantifier', operator='all', bind='o', collection=dict(kind='path', root='env', pointer='/orders'), predicate=inner)
        self.assertIs(qa.ReferenceEvaluator().evaluate(outer, {'orders': [{'tags': ['x', 'y']}, {'tags': ['x']}]}), True)
        self.assertIs(qa.ReferenceEvaluator().evaluate(outer, {'orders': [{'tags': ['y']}]}), False)

    def test_binding_kind_fixes_the_node_kinds_it_may_name(self):
        # AX-M-014. BIND-001 is code on a Component; BIND-006 is a test on a TestCase.
        bindings = {b['id']: b for b in self.spec['bindings']}
        for binding_id, target, valid in [('BIND-001', 'CON-001', True), ('BIND-001', 'REQ-001', False),
                                           ('BIND-001', 'TEST-001', False), ('BIND-006', 'REQ-001', False),
                                           ('BIND-006', 'COMP-001', False), ('BIND-006', 'TEST-002', True)]:
            with self.subTest(binding=binding_id, target=target):
                original = bindings[binding_id]['node_id']
                bindings[binding_id]['node_id'] = target
                self.assertEqual(qa.reference_errors(self.spec), [] if valid else ['WRONG_BINDING_TARGET'])
                bindings[binding_id]['node_id'] = original

    def test_same_link_declared_twice_is_a_duplicate(self):
        # AX-M-010.
        self.spec['edges'].append(dict(self.spec['edges'][0], id='EDGE-999'))
        self.assertEqual(qa.reference_errors(self.spec), ['DUPLICATE_EDGE'])


if __name__ == '__main__':
    unittest.main()
