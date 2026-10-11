"""Verify retained historical evidence using public material only."""
import hashlib
import json
import sys
import unittest
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP))
from olp_gate.crypto import verify_olp_signature, verify_agent_receipt_signature
from olp_gate.gateway import verify_decision_receipt


class SmokeEvidenceTests(unittest.TestCase):
    def test_historical_hashes_signatures_chain_and_git_commit(self):
        root = EXP / 'evidence' / 'phase15-smoke'
        manifest = json.loads((root / 'manifest.json').read_text())
        for rel, expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((root / rel).read_bytes()).hexdigest(), expected, rel)
        key = manifest['local_receiver_public_key']
        permission = json.loads((root / 'permission.json').read_text())
        self.assertTrue(verify_decision_receipt(permission, [key])['valid'])
        inputs = json.loads((root / 'proof-inputs.json').read_text())
        for source in inputs['source_receipts']:
            method = source['proof']['verificationMethod']
            self.assertTrue(verify_agent_receipt_signature(
                source, manifest['local_source_public_keys'][method])[0])
        self.assertTrue(verify_olp_signature(inputs['outcome_receipt'])[0])
        receipts = [json.loads(p.read_text()) for p in (root / 'receipts').glob('*.json')]
        previous = None
        while receipts:
            successors = [r for r in receipts if
                          r['extensions']['autonomy']['previous_receipt_hash'] == previous]
            self.assertEqual(len(successors), 1)
            receipt = successors[0]
            self.assertEqual(receipt['signature']['public_key'], key)
            self.assertTrue(verify_olp_signature(receipt)[0])
            previous = receipt['payload_hash']
            receipts.remove(receipt)
        self.assertEqual(previous, manifest['receipt_head'])
        commit = (root / 'candidate-commit.txt').read_bytes()
        git_hash = hashlib.sha1(b'commit ' + str(len(commit)).encode() + b'\0' + commit).hexdigest()
        evidence = json.loads((root / 'evidence.json').read_text())
        self.assertEqual(git_hash, evidence['commit'])
        self.assertEqual(evidence['commit'], inputs['action']['settings']['commit'])
        self.assertEqual(hashlib.sha256((root / 'evidence.json').read_bytes()).hexdigest(),
                         inputs['action']['evidence_hashes'][0])


if __name__ == '__main__':
    unittest.main()
