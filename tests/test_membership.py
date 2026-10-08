import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from bureau.membership import Sharing, proposal, FIELDS
from bureau.membership_demo import run
from bureau.store import Store

WALLET=Path(os.environ.get('OPENLINE_WALLET_REPO','/workspace/openline-wallet'))
sys.path.insert(0,str(WALLET/'demo/agent-exchange-001'))
from exchange.kernel import Exchange
from exchange.evidence import export_selected
from openline_wallet.crypto import sign_record


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.x=Exchange(Path(self.tmp.name)/'x');self.x.bootstrap()
        self.store=Store(':memory:');self.sharing=Sharing(self.store);self.listing=self.x.registry.all()[0]
        self.input=Path(self.tmp.name)/'input.txt';self.input.write_text('{"nonce":"membership-test"}\npublic digest\n')
        self.body=proposal(self.x,self.listing,self.input);self.buyer=self.x.principal('owner')
        self.worker=self.listing['seller_id']

    def tearDown(self):self.store.close();self.tmp.cleanup()

    def signatures(self,body):
        return {self.buyer:sign_record(body,self.x.commission_mod._load_key(self.x.chome,'owner')),
                self.worker:sign_record(body,self.x.commission_mod._load_key(self.x.chome,self.listing['identity']))}

    def register(self):return self.sharing.register(self.x,self.body,self.signatures(self.body))

    def perform(self,wrong=False):
        job=self.x.commission(self.listing,input_path=str(self.input));self.x.deliver(job,self.listing['identity'],wrong_input=wrong)
        self.x.adjudicate(job);return job,export_selected(self.x,[job])

    def test_private_default_and_registration_before_work(self):
        self.assertEqual(self.body['sharing']['visibility'],'private');aid=self.register()
        row=self.store.db.execute('SELECT * FROM sharing_jobs').fetchone()
        self.assertTrue(row['registered_at']);self.assertEqual(row['agreement_id'],aid)
        self.assertEqual(self.x.read_json('jobs.json'),{})
        job,_=self.perform();self.assertEqual(job,self.body['eligible_job']['job_id'])

    def test_versioned_exact_party_signatures_required(self):
        for bad in ('version','missing_signature','mutated_scope'):
            body=copy.deepcopy(self.body);signatures=self.signatures(body)
            if bad=='version':body['version']=2
            elif bad=='missing_signature':signatures.pop(self.worker)
            else:body['sharing']['analysis_audience']=['outsider']
            with self.assertRaises(ValueError):self.sharing.register(self.x,body,signatures)

    def test_cannot_register_after_commission(self):
        self.perform()
        with self.assertRaises(ValueError):self.register()

    def test_private_receipts_and_analysis_cannot_be_published(self):
        self.register();job,packet=self.perform();self.sharing.report(packet)
        with self.assertRaises(PermissionError):self.sharing.export_report(job,self.buyer,'public')
        with self.assertRaises(PermissionError):self.sharing.analysis(self.buyer,'public')
        self.assertEqual(self.sharing.export_report(job,self.buyer)['jobs'],packet['jobs'])

    def test_outside_audience_cannot_receive_evidence(self):
        self.register();job,packet=self.perform();self.sharing.report(packet)
        outsider=self.x.registry.all()[2]['seller_id']
        with self.assertRaises(PermissionError):self.sharing.export_report(job,outsider)
        with self.assertRaises(PermissionError):self.sharing.analysis(outsider)

    def test_explicit_public_scope_is_required_and_supported(self):
        self.body['sharing']={'visibility':'public','receipt_audience':['public'],'analysis_audience':['public']}
        self.register();job,packet=self.perform();self.sharing.report(packet)
        self.assertEqual(self.sharing.export_report(job,self.buyer,'public')['jobs'],packet['jobs'])
        self.assertEqual(self.sharing.analysis(self.buyer,'public')['accepted_fraction'],1)

    def test_all_registered_jobs_count_and_missing_failure_is_unknown(self):
        self.register();self.perform(wrong=True)  # deliberately omit every result from sharing
        analysis=self.sharing.analysis(self.buyer)
        self.assertEqual(analysis['registered_eligible_jobs'],1)
        self.assertIsNone(analysis['accepted_fraction'])
        self.assertEqual(analysis['incomplete_jobs'],[self.body['eligible_job']['job_id']])
        self.assertEqual(analysis['workers'][0]['reporting_status'],'INCOMPLETE')

    def test_failure_reporting_never_becomes_success(self):
        self.register();job,packet=self.perform(wrong=True);self.sharing.report(packet)
        analysis=self.sharing.analysis(self.buyer)
        self.assertEqual(analysis['accepted_fraction'],0)
        self.assertEqual(analysis['workers'][0]['rejected'],1)
        self.assertIsNone(analysis['workers'][0]['work_attempt_count'])

    def test_partial_outcome_and_missing_settlement_remain_incomplete(self):
        self.register();job=self.x.commission(self.listing,input_path=str(self.input))
        self.sharing.report(export_selected(self.x,[job]));self.assertIsNone(self.sharing.analysis(self.buyer)['accepted_fraction'])
        self.x.deliver(job,self.listing['identity']);self.x.receiver.check(job)  # accepted, not yet settled
        self.sharing.report(export_selected(self.x,[job]));self.assertIsNone(self.sharing.analysis(self.buyer)['accepted_fraction'])
        self.x.settlement.settle(job);self.sharing.report(export_selected(self.x,[job]))
        self.assertEqual(self.sharing.analysis(self.buyer)['accepted_fraction'],1)

    def test_permitted_fields_cannot_expand_to_prompts_or_credentials(self):
        for field in ('prompt','private_key','credentials','customer_data'):
            body=copy.deepcopy(self.body);body['permitted_receipt_fields']['commission.result.v1'].append(field)
            with self.assertRaises(ValueError):self.sharing.register(self.x,body,self.signatures(body))

    def test_subset_field_permission_refuses_whole_original_receipt(self):
        self.body['permitted_receipt_fields']['commission.agreement.v1'].remove('deliverable')
        self.register();_,packet=self.perform()
        with self.assertRaises(PermissionError):self.sharing.report(packet)
        self.assertIn('deliverable',FIELDS['commission.agreement.v1'])  # no shared mutable defaults

    def test_extra_private_data_in_signature_metadata_is_refused(self):
        self.register();_,packet=self.perform()
        packet['jobs'][0]['verdict']['signature']['signature']['private_key']='fixture-never-export'
        with self.assertRaises(PermissionError):self.sharing.report(packet)

    def test_original_evidence_and_public_ledger_preserved(self):
        self.register();job,packet=self.perform();source=(self.x.chome/'jobs.json').read_bytes()
        self.sharing.report(packet);self.sharing.report(packet)
        self.assertEqual(source,(self.x.chome/'jobs.json').read_bytes())
        self.assertEqual(self.sharing.export_report(job,self.buyer)['jobs'],packet['jobs'])
        self.assertEqual(self.store.count(),0)  # existing public HTTP ledger cannot expose private reports
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM sharing_reports').fetchone()[0],1)

    def test_scope_and_report_cannot_be_silently_rewritten(self):
        self.register();changed=copy.deepcopy(self.body);changed['sharing']['visibility']='public'
        with self.assertRaises(ValueError):self.sharing.register(self.x,changed,self.signatures(changed))
        job,packet=self.perform();self.sharing.report(packet)
        packet['jobs'][0]['verdict']=None
        with self.assertRaises(ValueError):self.sharing.report(packet)

    def test_nonmember_protocol_still_works_in_demo(self):
        report=run(WALLET,Path(self.tmp.name)/'demo')
        self.assertEqual(report['nonparticipant']['protocol_transaction'],'accepted')
        self.assertEqual(report['nonparticipant']['shared_analysis'],'DENIED_NOT_PARTICIPATING')
        self.assertIsNone(report['omitted_failure']['accepted_fraction'])
        self.assertEqual(report['completed_reporting']['accepted_fraction'],.5)
        self.assertEqual(report['public_export'],'DENIED_PRIVATE_SCOPE')
