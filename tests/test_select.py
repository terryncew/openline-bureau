import copy
import unittest

from bureau.select import select_candidates


def fixture():
    # Pure rule fixtures; these are never published as marketplace records.
    caps = [{'id': name, 'version': '1', 'tasks': ['digest'],
             'price': {'amount': price, 'currency': 'USD', 'basis': 'task'}}
            for name, price in [('a', '20.00'), ('b', '10.00'), ('c', '30.00')]]
    evals = [{'capability_id': name, 'capability_version': '1', 'task': 'digest',
              'independence': 'SEPARATE_REVIEWED_CONTRIBUTOR',
              'outcome_verification': 'MAINTAINER_REPRODUCED',
              'method': 'exact digest v1', 'environment': 'isolated test',
              'sample': {'total': 4}} for name in ['a', 'b']]
    return {'format': 'openline.catalog.v1', 'synthetic': False,
            'capabilities': caps, 'evaluations': evals}


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.criteria = {'task': 'digest', 'budget': 25, 'currency': 'USD', 'basis': 'task', 'minEvaluations': 1}

    def test_cheapest_matching_baseline_not_an_authorization(self):
        result = select_candidates(self.data, self.criteria)
        self.assertEqual(result['baseline']['id'], 'b')
        self.assertEqual([c['id'] for c in result['eligible']], ['b', 'a'])
        self.assertIsNone(result['recommendation'])
        self.assertIn('human review', result['abstention'])

    def test_other_task_currency_unit_budget_cannot_share_performance(self):
        for key, value in [('task', 'unobserved-task'), ('currency', 'EUR'), ('basis', 'hour'), ('budget', 5)]:
            with self.subTest(key=key):
                result = select_candidates(self.data, {**self.criteria, key: value})
                self.assertIsNone(result['baseline'])
                self.assertEqual(result['eligible'], [])

    def test_self_reported_and_wrong_version_are_not_independent_evaluation(self):
        for edit in [{'independence': 'SELF_REPORTED'}, {'capability_version': '2'}, {'worker_id': 'some-worker'}]:
            data = copy.deepcopy(self.data)
            for e in data['evaluations']:
                e.update(edit)
            result = select_candidates(data, self.criteria)
            self.assertEqual(result['eligible'], [])
            self.assertIn('No candidate', result['abstention'])

    def test_evaluator_report_is_not_reproduced(self):
        self.data['evaluations'][0]['outcome_verification'] = 'EVALUATOR_REPORTED'
        result = select_candidates(self.data, self.criteria)
        self.assertIn('Abstaining', result['abstention'])

    def test_heterogeneous_conditions_and_synthetic_abstain(self):
        self.data['evaluations'][0]['sample']['total'] = 5
        self.assertIn('differ', select_candidates(self.data, self.criteria)['abstention'])
        self.data['synthetic'] = True
        self.assertIn('synthetic', select_candidates(self.data, self.criteria)['abstention'])

    def test_same_sample_size_on_different_data_cannot_be_compared(self):
        self.data['evaluations'][0]['sample']['dataset'] = 'Benchmark A'
        self.data['evaluations'][1]['sample']['dataset'] = 'Benchmark B'
        self.assertIn('datasets', select_candidates(self.data, self.criteria)['abstention'])

    def test_invalid_budget_does_not_become_unlimited(self):
        for value in ['bad', float('nan'), float('inf'), -1]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_candidates(self.data, {**self.criteria, 'budget': value})
