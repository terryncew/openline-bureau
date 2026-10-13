import json
import tempfile
import unittest
from pathlib import Path

from bureau.beta_trial import exhibit, RECORDED


class BetaTrialTests(unittest.TestCase):
    def test_frozen_losses_sparse_and_cost_disadvantage_remain_visible(self):
        result = exhibit()
        mixed, reversal, sparse = result['scenarios']
        self.assertEqual(mixed['completion_delta'], 0.5)
        self.assertLess(mixed['conditions']['bureau']['accepted_per_settled_sim_usd'],
                        mixed['conditions']['control']['accepted_per_settled_sim_usd'])
        self.assertEqual(mixed['bureau_worse_tasks'], ['heldout-3'])
        self.assertEqual(reversal['completion_delta'], -1)
        self.assertEqual(len(reversal['bureau_worse_tasks']), 4)
        self.assertEqual(sparse['verdict'], 'INCONCLUSIVE')
        self.assertTrue(all(s['synthetic'] and not s['real_payment'] for s in result['scenarios']))

    def test_tampered_recorded_results_fail_closed(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'recorded'
            shutil.copytree(RECORDED, copy)
            file = copy / 'reversal/experiment.json'
            payload = json.loads(file.read_text())
            payload['verdict'] = 'ADVANTAGE'
            file.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                exhibit(copy)
