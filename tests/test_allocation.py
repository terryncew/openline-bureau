import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

from bureau.adapters import adapt, UnsupportedReceiptFormat
from bureau.adapters.exchange import assess
from bureau.allocation import choose, comparison
from bureau.allocation_demo import run, trial_result, PROTOCOL, seal
from bureau.server import Handler
from bureau.store import Store

WALLET = Path(os.environ.get('OPENLINE_WALLET_REPO', '/workspace/openline-wallet'))


class AllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / 'mixed'
        cls.result = run(WALLET, cls.out)
        cls.packet = json.loads((cls.out / 'history.json').read_text())
        cls.buyer = json.loads((cls.out / 'trust.json').read_text())['trusted_buyer']

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def setUp(self):
        self.store = Store(':memory:')
        self.prov = {'source_repo': 'terryncew/openline-wallet', 'source_path': 'selected/history.json'}
        self.records = adapt(self.packet, self.prov)
        self.store.ingest_many(self.records)

    def tearDown(self): self.store.close()

    def rows(self): return comparison(self.store, trusted_buyers=[self.buyer])['workers']

    def test_sources_unchanged_and_export_minimizes(self):
        from exchange.kernel import Exchange
        from exchange.evidence import export_selected
        x = Exchange(self.out / 'exchange')
        before = hashlib.sha256((x.chome / 'jobs.json').read_bytes()).hexdigest()
        packet = export_selected(x, [self.packet['jobs'][0]['job_id']])
        self.assertEqual(before, hashlib.sha256((x.chome / 'jobs.json').read_bytes()).hexdigest())
        serialized = json.dumps(packet)
        self.assertNotIn('input_path', serialized)
        self.assertNotIn('private_key', serialized)
        self.assertNotIn('public historical digest', serialized)
        self.assertEqual(len(packet['jobs']), 1)

    def test_duplicate_ingestion_does_not_inflate(self):
        before = self.rows()
        stats = self.store.ingest_many(adapt(self.packet, self.prov))
        self.assertEqual(stats['inserted'], 0)
        self.assertEqual(before, self.rows())

    def test_requires_explicit_buyer_trust(self):
        rows = comparison(self.store)['workers']
        self.assertEqual(sum(r['accepted'] for r in rows), 0)
        self.assertTrue(all(r['accepted_fraction'] is None for r in rows))

    def test_tampered_and_unsigned_cannot_be_success(self):
        for modification in ('signature', 'record'):
            job = copy.deepcopy(self.packet['jobs'][0])
            if modification == 'signature': job['verdict']['signature'] = {}
            else: job['submission']['record']['word_count'] += 1
            self.assertFalse(assess(job, [self.buyer])['accepted'])
        with self.assertRaises(UnsupportedReceiptFormat): adapt({'format': 'made-up'}, self.prov)

    def test_attacker_agent_cannot_claim_pinned_buyer(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from openline_wallet.crypto import sign_record, public_key_hex, principal_id
        job = copy.deepcopy(self.packet['jobs'][0])
        key = Ed25519PrivateKey.generate()
        job['agreement']['record']['agent'] = principal_id(public_key_hex(key))
        job['agreement']['signature'] = sign_record(job['agreement']['record'], key)
        v = job['verdict']['record']; v['verified_by'] = 'agent'
        v['agreement_hash'] = job['agreement']['signature']['payload_hash']
        job['verdict']['signature'] = sign_record(v, key)
        self.assertFalse(assess(job, [self.buyer])['accepted'])

    def test_authorization_is_not_work_completion(self):
        job = copy.deepcopy(self.packet['jobs'][0])
        job['submission'] = job['verdict'] = job['settlement'] = None
        state = assess(job, [self.buyer])
        self.assertTrue(state['agreement']); self.assertFalse(state['accepted'])

    def test_conflicting_signed_agreements_do_not_double_count(self):
        from exchange.kernel import Exchange
        from openline_wallet.crypto import sign_record
        x = Exchange(self.out / 'exchange')
        job = copy.deepcopy(self.packet['jobs'][0])
        # Same original job identity with a second genuinely signed body.
        job['agreement']['record']['nonce'] = 'conflicting-history'
        job['agreement']['signature'] = sign_record(job['agreement']['record'], x.commission_mod._load_key(x.chome, 'agent'))
        self.store.ingest_many(adapt({**self.packet, 'jobs': [job]}, self.prov))
        row = next(r for r in self.rows() if r['profile']['seller_name'] == 'Seller A')
        self.assertEqual(row['accepted'], 2)
        self.assertEqual(len(row['unresolved_jobs']), 1)

    def test_malformed_signer_and_wrong_schema_fail_closed(self):
        job = copy.deepcopy(self.packet['jobs'][0])
        job['verdict']['signature']['signature']['public_key'] = 'invalid'
        self.assertFalse(assess(job, [self.buyer])['accepted'])
        job['verdict']['record']['schema'] = 'commission.verdict.v99'
        self.assertFalse(assess(job, [self.buyer])['accepted'])

    def test_missing_attempt_counts_not_zero_failures(self):
        for row in self.rows():
            self.assertIsNone(row['attempt_count'])
            self.assertIsNone(row['unobserved_failure_count'])
        cold = next(r for r in self.rows() if r['profile']['seller_name'] == 'Seller C')
        self.assertIsNone(cold['accepted_fraction'])
        self.assertEqual(cold['ranking_status'], 'cannot yet be ranked reliably')

    def test_rejected_results_and_simulation_stay_separate(self):
        b = next(r for r in self.rows() if r['profile']['seller_name'] == 'Seller B')
        self.assertEqual((b['accepted'], b['rejected']), (0, 3))
        self.assertEqual(b['real_payment'], 'NOT ESTABLISHED — all settlement is simulated')
        for j in self.packet['jobs'][3:]: self.assertFalse(assess(j, [self.buyer])['settled'])

    def test_missing_settlement_keeps_cost_unknown(self):
        job = copy.deepcopy(self.packet['jobs'][0]); job['settlement'] = None
        s = Store(':memory:')
        try:
            s.ingest_many(adapt({**self.packet, 'jobs': [job]}, self.prov))
            row = next(r for r in comparison(s, trusted_buyers=[self.buyer])['workers'] if r['profile']['seller_name'] == 'Seller A')
            self.assertEqual(row['accepted'], 1)
            self.assertIsNone(row['observed_simulated_cost'])
        finally: s.close()

    def test_receipt_drilldowns_and_original_identities(self):
        a = next(r for r in self.rows() if r['profile']['seller_name'] == 'Seller A')
        self.assertEqual((a['accepted'], len(a['accepted_receipt_ids'])), (3, 3))
        for rid in a['receipt_ids']:
            rec = self.store.get(rid)
            self.assertEqual(rec['actor'], a['worker_id'])
            self.assertEqual(rec['principal'], self.buyer)
            self.assertTrue(rec['unmapped']['source_sha256'])
            self.assertEqual(rec['raw']['job']['job_id'], rec['unmapped']['original_job_id'])

    def test_heldout_outcomes_not_selection_inputs(self):
        selected = json.loads((self.out / 'selections.json').read_text())
        self.assertEqual(selected['protocol_sha256'], seal(PROTOCOL))
        self.assertEqual(selected['history_sha256'], seal(self.packet))
        ids = {j['job_id'] for j in self.packet['jobs']}
        self.assertFalse(ids & {r['job_id'] for r in self.result['rows']})
        with self.assertRaises(TypeError): choose(self.packet['profiles'], future_outcomes=[])
        for task in range(4):
            pair = [r for r in self.result['rows'] if r['task'] == f'heldout-{task}']
            self.assertEqual(pair[0]['task_content_sha256'], pair[1]['task_content_sha256'])

    def test_bureau_advantage_can_include_worse_choice(self):
        self.assertEqual(self.result['verdict'], 'ADVANTAGE')
        self.assertEqual(self.result['bureau_worse_tasks'], ['heldout-3'])
        self.assertEqual(self.result['completion_delta'], .5)

    def test_bureau_can_lose_after_history_drift(self):
        result = run(WALLET, Path(self.tmp.name) / 'reversal', scenario='reversal')
        self.assertEqual(result['verdict'], 'NO_ADVANTAGE')
        self.assertEqual(result['completion_delta'], -1)
        self.assertEqual(len(result['bureau_worse_tasks']), 4)

    def test_sparse_history_is_inconclusive_and_uses_control(self):
        result = run(WALLET, Path(self.tmp.name) / 'sparse', sparse=True)
        self.assertEqual(result['verdict'], 'INCONCLUSIVE')
        self.assertEqual(result['completion_delta'], 0)
        choices = json.loads((Path(self.tmp.name) / 'sparse/selections.json').read_text())['choices']
        self.assertEqual(choices['control'], choices['bureau'])

    def test_feedback_updates_and_pending_is_unresolved(self):
        before = json.loads((self.out / 'comparison-before.json').read_text())
        after = json.loads((self.out / 'comparison-after.json').read_text())
        self.assertGreater(sum(r['comparable_verified_jobs'] for r in after['workers']),
                           sum(r['comparable_verified_jobs'] for r in before['workers']))
        cold = next(r for r in after['workers'] if r['profile']['seller_name'] == 'Seller C')
        self.assertEqual(cold['comparable_verified_jobs'], 0)
        self.assertEqual(len(cold['unresolved_jobs']), 1)

    def test_unknown_outcomes_force_inconclusive(self):
        rows = copy.deepcopy(self.result['rows']); rows[0]['accepted'] = rows[0]['rejected'] = False
        self.assertEqual(trial_result(rows)['verdict'], 'INCONCLUSIVE')

    def test_http_comparison_ui_and_receipt_routes(self):
        server = HTTPServer(('127.0.0.1', 0), Handler)
        server.store = self.store; server.trusted_buyers = [self.buyer]
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base + '/api/workers') as r:
                self.assertEqual(sum(row['accepted'] for row in json.load(r)['workers']), 3)
            for path in ('/', '/ui/app.js', '/api/overview', '/api/ledger', '/api/timeline', '/api/incidents', '/api/coverage', '/api/facets'):
                with urllib.request.urlopen(base + path) as r: self.assertEqual(r.status, 200)
            with urllib.request.urlopen(base + '/api/receipt/' + self.records[0]['receipt_id']) as r:
                self.assertEqual(json.load(r)['record']['receipt_id'], self.records[0]['receipt_id'])
        finally: server.shutdown(); thread.join(); server.server_close()


if __name__ == '__main__': unittest.main()
