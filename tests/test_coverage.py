import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch
from http.server import HTTPServer

from bureau.coverage import Coverage, ReceiverBoundary, envelope
from bureau.coverage_demo import prepare, outcomes, run
from bureau.server import Handler
from bureau.store import Store

WALLET = Path(os.environ.get('OPENLINE_WALLET_REPO', '/workspace/openline-wallet'))
NOW = 1800000110


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.x, self.listing, self.store, self.c, self.receiver, self.cid, self.events = prepare(WALLET, Path(self.tmp.name) / 'trial')
        self.buyer = self.x.principal('owner')
        self.cp = self.receiver.checkpoint()

    def tearDown(self):
        self.receiver.close()
        self.store.close()
        self.tmp.cleanup()

    def anchor(self):
        self.c.anchor(self.cid, self.cp, now=1800000100)

    def analysis(self, now=NOW):
        return self.c.analysis(self.cid, self.buyer, now=now)

    def signed(self, value, **changes):
        body = copy.deepcopy(value['record'])
        body.update(changes)
        return envelope(body, self.receiver.key)

    def test_admission_precedes_execution_and_checkpoint_precedes_outcomes(self):
        jobs = self.x.read_json('jobs.json')
        self.assertEqual(len(jobs), 8)
        self.assertTrue(all(not j.get('submission') and not j.get('verdict') and not j.get('settlement') for j in jobs.values()))
        self.assertEqual([e['record']['sequence'] for e in self.events], list(range(1, 9)))
        self.anchor()
        packets = outcomes(self.x, self.listing, self.events)
        self.c.report(self.cid, packets[0])
        self.assertEqual(self.analysis()['verified_outcomes'], 1)

    def test_complete_and_selective_have_same_trustworthy_denominator(self):
        self.anchor()
        packets = outcomes(self.x, self.listing, self.events)
        for p in packets[:2]:
            self.c.report(self.cid, p)
        b = self.analysis()
        self.assertEqual(b['reporting_coverage'], 2 / 8)
        self.assertEqual(len(b['missing_outcomes']), 6)
        self.assertIsNone(b['observed_completion_rate'])
        self.assertEqual(b['verified_failures'], 0)  # unreported failures remain unknown
        for p in packets[2:]:
            self.c.report(self.cid, p)
        a = self.analysis()
        self.assertEqual(a['observed_completion_rate'], 2 / 8)
        self.assertEqual(a['verified_failures'], 6)
        self.assertEqual(a['verified_successes'], 2)
        self.assertEqual(a['reporting_coverage'], 1)

    def test_genuine_successes_without_anchor_do_not_certify(self):
        packets = outcomes(self.x, self.listing, self.events)
        with self.assertRaises(ValueError):
            self.c.report(self.cid, packets[0])
        self.c.sharing.report(packets[0])
        self.assertIsNone(self.analysis()['observed_completion_rate'])
        with self.assertRaisesRegex(ValueError, 'after outcomes'):
            self.anchor()

    def test_duplicates_do_not_inflate_or_refresh(self):
        self.anchor()
        self.c.anchor(self.cid, self.cp, now=1800000110)
        self.assertEqual(self.store.db.execute('SELECT retained_at FROM coverage_checkpoints').fetchone()[0], 1800000100)
        for e in self.events:
            self.c.receive_admission(self.cid, e)
        p = outcomes(self.x, self.listing, self.events)[0]
        self.c.report(self.cid, p)
        self.c.report(self.cid, p)
        self.assertEqual(self.analysis()['reports_received'], 1)
        self.assertEqual(self.analysis()['eligible_jobs'], 8)

    def test_forged_signatures_and_fabricated_completion_are_refused(self):
        forged = copy.deepcopy(self.cp)
        forged['signature']['signature']['value'] = '0' * 128
        with self.assertRaises(ValueError):
            self.c.anchor(self.cid, forged, now=1800000100)
        self.anchor()
        packets = outcomes(self.x, self.listing, self.events)
        for phase in ('agreement', 'offer', 'submission', 'verdict', 'settlement'):
            fake = copy.deepcopy(packets[0])
            fake['jobs'][0][phase]['signature']['signature']['value'] = '0' * 128
            with self.assertRaises(ValueError):
                self.c.report(self.cid, fake)
        fabricated = copy.deepcopy(packets[2])
        fabricated['jobs'][0]['verdict']['record']['verdict'] = 'accepted'
        with self.assertRaises(ValueError):
            self.c.report(self.cid, fabricated)
        self.assertEqual(self.analysis()['verified_successes'], 0)

    def test_receiver_pin_and_changed_scope(self):
        row = self.store.db.execute('SELECT * FROM coverage_agreements').fetchone()
        body, signatures = json.loads(row['body']), json.loads(row['signatures'])
        with self.assertRaises(ValueError):
            Coverage(self.store).enroll(body, signatures)
        body['categories'].append('private_customer_service')
        with self.assertRaises(ValueError):
            self.c.enroll(body, signatures)
        changed = self.signed(self.events[0], category='other')
        with self.assertRaises(ValueError):
            self.c.receive_admission(self.cid, changed)
        with self.assertRaises(ValueError):
            self.c.anchor(self.cid, self.signed(self.cp, coverage_id='0' * 64), now=1800000100)

    def test_missing_registration_sequence_and_late_delivery(self):
        # Simulate an interrupted transport from the independent receiver log.
        self.store.db.execute('DELETE FROM coverage_admissions WHERE sequence=4')
        self.store.db.commit()
        self.anchor()
        a = self.analysis()
        self.assertEqual(a['missing_registration_sequences'], [4])
        self.assertEqual(a['eligible_jobs'], 8)
        self.assertIsNone(a['reporting_coverage'])
        self.c.receive_admission(self.cid, self.events[3])
        self.assertEqual(self.analysis()['missing_registration_sequences'], [])
        self.assertEqual(self.analysis()['reporting_coverage'], 0)

    def test_missing_registration_cannot_backfill_previously_disclosed_outcomes(self):
        self.store.db.execute('DELETE FROM coverage_admissions WHERE sequence=4')
        self.store.db.commit()
        packet = outcomes(self.x, self.listing, self.events)[3]
        self.c.sharing.report(packet)  # existing membership path, outside coverage
        self.anchor()
        with self.assertRaisesRegex(ValueError, 'before_registration_delivery'):
            self.c.receive_admission(self.cid, self.events[3])
        self.assertIn('CONFLICTING_SIGNED_EVIDENCE', self.analysis()['issues'])

    def test_receiver_journal_retry_is_stable_and_admission_failure_stays_unknown(self):
        p = Path(self.tmp.name) / 'new-input.txt'
        p.write_text('{"nonce":"interrupted-admission"}\nsynthetic fixture\n')
        with patch.object(self.x, 'commission', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                self.receiver.admit(self.listing, p, at=1800000009)
        self.assertEqual(self.analysis()['admissions_received'], 9)
        resumed = ReceiverBoundary(self.x, self.c, self.cid, Path(self.tmp.name) / 'trial/receiver-private.db')
        try:
            e = resumed.admit(self.listing, p, at=1800000010)
            self.assertEqual(e['record']['sequence'], 9)
            self.assertEqual(e['record']['admitted_at'], 1800000009)
            self.assertEqual(resumed.checkpoint()['record']['through_sequence'], 9)
        finally:
            resumed.close()

    def test_signed_checkpoint_with_missing_prefix_never_certifies(self):
        # A valid receiver signature cannot remove locally observed admissions.
        shortened = self.signed(self.cp, through_sequence=2, admission_hashes=self.cp['record']['admission_hashes'][:2])
        self.c.anchor(self.cid, shortened, now=1800000100)
        self.assertIn('REGISTRATION_COMMITMENT_MISMATCH', self.analysis()['issues'])
        self.assertIsNone(self.analysis()['reporting_coverage'])

    def test_stale_and_future_checkpoints(self):
        with self.assertRaises(ValueError):
            self.c.anchor(self.cid, self.cp, now=1800000099)
        self.anchor()
        for at in (1800000099, 1800000401):
            self.assertIn('STALE_OR_FUTURE_CHECKPOINT', self.analysis(at)['issues'])
            self.assertIsNone(self.analysis(at)['observed_completion_rate'])

    def test_signed_conflicts_quarantine_prior_assessment_and_survive_restart(self):
        self.anchor()
        conflict = self.signed(self.cp, through_sequence=2, admission_hashes=self.cp['record']['admission_hashes'][:2])
        with self.assertRaises(ValueError):
            self.c.anchor(self.cid, conflict, now=1800000100)
        reopened = Store(str(Path(self.tmp.name) / 'trial/bureau-private.db'))
        try:
            result = Coverage(reopened, [self.buyer]).analysis(self.cid, self.buyer, now=NOW)
            self.assertIn('CONFLICTING_SIGNED_EVIDENCE', result['issues'])
        finally:
            reopened.close()

    def test_duplicate_sequence_and_job_identity_conflict(self):
        for changes in ({'sequence': 2}, {'sequence': 9}):
            with self.assertRaises(ValueError):
                self.c.receive_admission(self.cid, self.signed(self.events[0], **changes))
        self.assertIn('CONFLICTING_SIGNED_EVIDENCE', self.analysis()['issues'])

    def test_commitment_mismatch_and_missing_registration_report(self):
        self.anchor()
        with self.assertRaises(ValueError):
            self.c.receive_admission(self.cid, self.signed(self.events[0], admitted_at=1800000050))
        self.store.db.execute('DELETE FROM coverage_admissions WHERE sequence=4')
        self.store.db.commit()
        p = outcomes(self.x, self.listing, self.events)[3]
        with self.assertRaisesRegex(ValueError, 'missing receiver registration'):
            self.c.report(self.cid, p)

    def test_unsettled_success_partial_report_and_interrupted_reporting(self):
        from exchange.evidence import export_selected
        self.anchor()
        job = self.events[0]['record']['job_id']
        self.c.report(self.cid, export_selected(self.x, [job]))
        self.assertEqual(self.analysis()['reports_received'], 1)
        self.assertEqual(self.analysis()['verified_outcomes'], 0)
        self.x.deliver(job, self.listing['identity'])
        self.x.receiver.check(job)
        self.c.report(self.cid, export_selected(self.x, [job]))
        self.assertEqual(self.analysis()['verified_outcomes'], 1)
        self.assertEqual(self.analysis()['settled_successes'], 0)
        self.assertIn(job, self.analysis()['missing_settlements'])
        self.assertNotIn(job, self.analysis()['missing_outcomes'])
        self.assertEqual(self.analysis()['verified_successes'], 1)
        self.x.settlement.settle(job)
        packet = export_selected(self.x, [job])
        self.c.report(self.cid, packet)
        self.assertNotIn(job, self.analysis()['missing_settlements'])
        erased = copy.deepcopy(packet)
        erased['jobs'][0]['settlement'] = None
        with self.assertRaises(ValueError):
            self.c.report(self.cid, erased)

    def test_private_fields_and_public_endpoints(self):
        self.anchor()
        packet = outcomes(self.x, self.listing, self.events)[0]
        for field in ('prompt', 'credentials', 'customer_data', 'input_path'):
            private = copy.deepcopy(packet)
            private['jobs'][0][field] = 'private'
            with self.assertRaises(ValueError):
                self.c.report(self.cid, private)
        self.c.report(self.cid, packet)
        self.assertEqual(self.store.count(), 0)
        self.assertNotIn('synthetic private customer fixture', json.dumps(packet))
        server = HTTPServer(('127.0.0.1', 0), Handler)
        # SQLite connections are thread-bound: use a separate empty public-store
        # connection in the serving thread against the same private database.
        db_path = str(Path(self.tmp.name) / 'trial/bureau-private.db')
        ready = threading.Event()
        def serve():
            public_store = Store(db_path)
            server.store = public_store
            ready.set()
            try:
                server.serve_forever(poll_interval=.01)
            finally:
                public_store.close()
        thread = threading.Thread(target=serve)
        thread.start()
        ready.wait(2)
        try:
            for path in ('/api/ledger', '/api/overview', '/api/timeline', '/api/incidents', '/api/coverage', '/api/facets', '/api/workers'):
                data = urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}{path}').read().decode()
                self.assertNotIn(self.cid, data)
                self.assertNotIn(self.events[0]['record']['job_id'], data)
                self.assertNotIn(self.buyer, data)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        with self.assertRaises(PermissionError):
            self.c.analysis(self.cid, 'nonmember', now=NOW)

    def test_signed_extra_fields_cannot_enter_coverage_store(self):
        for value, method in ((self.events[0], lambda e: self.c.receive_admission(self.cid, e)),
                              (self.cp, lambda e: self.c.anchor(self.cid, e, now=1800000100))):
            with self.assertRaises(ValueError):
                method(self.signed(value, customer_data='never store'))
            extra = copy.deepcopy(value)
            extra['signature']['signature']['credentials'] = 'never store'
            with self.assertRaises(ValueError):
                method(extra)

    def test_demo_preserves_suppression_counterexample_and_nonmember_protocol(self):
        result = run(WALLET, Path(self.tmp.name) / 'demonstration')
        self.assertEqual(result['finding'], 'PASS')
        self.assertEqual(result['suppression_counterexample']['actual_eligible_jobs'], 8)
        hidden = result['suppression_counterexample']['assessment']
        self.assertEqual(hidden['eligible_jobs'], 2)
        self.assertEqual(hidden['observed_completion_rate'], 1)
        self.assertEqual(hidden['global_completeness'], 'NOT ESTABLISHED')
        self.assertEqual(result['nonmember'], {'transaction': 'accepted', 'analysis_denied': True})
