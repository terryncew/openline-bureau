"""Public beta boundaries and evidence semantics, using only test-owned data."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from bureau.catalog import (CatalogError, Reader, assess_receipt, build_catalog,
                            export_artifacts, load_json, main, safe_url, validate_source)

ROOT = Path(__file__).resolve().parents[1]
RELEASE = {"authorized": True, "rights_confirmed": True, "contains_private_data": False}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def receipt():
    return {"receipt_version": "bureau.receipt.v0.1", "receipt_id": "test-only-receipt",
            "timestamp": "2026-01-01T00:00:00Z", "receiver": "synthetic-test-receiver",
            "action": {"type": "count_words"}, "decision": {"outcome": "OBSERVED"},
            "effect": {"observed": True}}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "catalog"
        self.root.mkdir()
        self.registry = load_json(ROOT / "catalog/reviewed.json")
        self.write("reviewed.json", self.registry)
        self.cap = load_json(ROOT / "catalog/templates/capability.json")
        self.cap.update(id="test-capability", name="Synthetic test-only capability", contributor_id="test-alice")
        self.ev = load_json(ROOT / "catalog/templates/evaluation.json")
        self.ev.update(id="test-evaluation", capability_id="test-capability", evaluator_id="test-bob")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, value):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def approve(self, rel, record):
        digest = hashlib.sha256((self.root / rel).read_bytes()).hexdigest()
        self.registry["reviews"] = [r for r in self.registry["reviews"] if r["path"] != rel]
        self.registry["reviews"].append({"path": rel, "record_sha256": digest,
                                       "github_author": record.get("contributor_id", record.get("evaluator_id")),
                                       "source_pr_url": "https://github.com/terryncew/openline-bureau/pull/123",
                                       "public_disclosure_reviewed": True,
                                       "evidence_sha256": {e["path"]: e["sha256"] for e in record.get("evidence", [])},
                                       "reproduction": None})
        self.write("reviewed.json", self.registry)
        return self.registry["reviews"][-1]

    def add_cap(self, approved=True):
        self.write("submissions/capabilities/test.json", self.cap)
        if approved:
            self.approve("submissions/capabilities/test.json", self.cap)

    def add_eval(self, approved=True):
        self.write("submissions/evaluations/test.json", self.ev)
        if approved:
            return self.approve("submissions/evaluations/test.json", self.ev)

    def evidence(self, payload=None, format="bureau.receipt.v0.1"):
        digest = self.write("evidence/test.json", payload or receipt())
        return {"path": "evidence/test.json", "sha256": digest, "format": format, "public_release": RELEASE}

    def reproduce(self, reviewer="test-carol"):
        review = self.registry["reviews"][-1]
        report = {"format": "openline.catalog.reproduction.v1", "evaluation_sha256": review["record_sha256"],
                  "reviewer": reviewer, "method": self.ev["method"], "environment": self.ev["environment"],
                  "sample": self.ev["sample"], "results_sha256": hashlib.sha256(canonical(self.ev["results"])).hexdigest(),
                  "public_release": RELEASE}
        digest = self.write("reproductions/test.json", report)
        review["reproduction"] = {"path": "reproductions/test.json", "sha256": digest}
        self.write("reviewed.json", self.registry)
        return report

    def test_default_catalog_empty_and_fixture_catalog_separate(self):
        catalog = build_catalog(ROOT / "catalog")
        fixture = build_catalog(ROOT / "catalog", fixtures=True)
        self.assertFalse(catalog["synthetic"])
        self.assertEqual(catalog["capabilities"], [])
        self.assertEqual(len(fixture["capabilities"]), 3)
        self.assertTrue(all(c["evidence_summary"]["label"] == "SYNTHETIC" for c in fixture["capabilities"]))
        self.assertFalse(fixture["policy"]["payment_processing"])
        self.assertTrue(all(not c["inquiry"]["accepts_inquiries"] for c in fixture["capabilities"]))

    def test_pending_validation_never_publishes(self):
        self.add_cap(approved=False)
        pending = validate_source(self.root, pending=True)
        self.assertFalse(pending["capabilities"][0]["publication"]["reviewed"])
        self.assertEqual(build_catalog(self.root)["capabilities"], [])
        self.assertEqual(main(["build", "--source", str(self.root), "--pending"]), 1)

    def test_reviewed_self_report_is_useful_without_receipts(self):
        self.add_cap()
        catalog = build_catalog(self.root)
        c = catalog["capabilities"][0]
        self.assertEqual(c["evidence_summary"]["label"], "SELF_REPORTED")
        self.assertIn("Supporting receipts", c["evidence_summary"]["missing"])
        self.assertEqual(c["price"], None)
        self.assertEqual(c["record_url"], "submissions/capabilities/test.json")
        self.assertNotIn("trust_score", c)

    def test_distinct_reviewed_contributor_report_not_outcome_verification(self):
        self.add_cap()
        self.add_eval()
        catalog = build_catalog(self.root)
        self.assertEqual(catalog["evaluations"][0]["independence"], "SEPARATE_REVIEWED_CONTRIBUTOR")
        self.assertEqual(catalog["evaluations"][0]["outcome_verification"], "EVALUATOR_REPORTED")
        self.assertEqual(catalog["capabilities"][0]["evidence_summary"]["label"], "INDEPENDENTLY_REPORTED")

    def test_same_reviewed_account_cannot_evaluate_independently(self):
        self.ev["evaluator_id"] = "TEST-ALICE"
        self.add_cap()
        self.add_eval()
        catalog = build_catalog(self.root)
        self.assertEqual(catalog["evaluations"][0]["independence"], "NOT_INDEPENDENT")
        self.assertEqual(catalog["capabilities"][0]["evidence_summary"]["label"], "SELF_REPORTED")

    def test_exact_reproduction_and_distinct_reviewer(self):
        self.add_cap()
        self.add_eval()
        self.reproduce()
        catalog = build_catalog(self.root)
        self.assertEqual(catalog["capabilities"][0]["evidence_summary"]["label"], "INDEPENDENTLY_REPRODUCED")
        self.assertEqual(catalog["evaluations"][0]["reproduction"]["reviewer"], "test-carol")
        self.reproduce(reviewer="test-alice")
        with self.assertRaises(CatalogError):
            build_catalog(self.root)

    def test_reproduction_must_bind_context_and_results(self):
        self.add_cap()
        self.add_eval()
        report = self.reproduce()
        for field in ("method", "environment", "results_sha256", "evaluation_sha256"):
            with self.subTest(field=field):
                changed = copy.deepcopy(report)
                changed[field] = "different" if field in ("method", "environment") else "0" * 64
                digest = self.write("reproductions/test.json", changed)
                self.registry["reviews"][-1]["reproduction"]["sha256"] = digest
                self.write("reviewed.json", self.registry)
                with self.assertRaises(CatalogError):
                    build_catalog(self.root)

    def test_approval_binds_record_author_and_every_evidence_hash(self):
        self.cap["evidence"] = [self.evidence()]
        self.add_cap()
        self.cap["summary"] += " modified after review"
        self.write("submissions/capabilities/test.json", self.cap)
        with self.assertRaises(CatalogError):
            build_catalog(self.root)
        self.approve("submissions/capabilities/test.json", self.cap)
        self.registry["reviews"][0]["github_author"] = "test-forged"
        self.write("reviewed.json", self.registry)
        with self.assertRaises(CatalogError):
            build_catalog(self.root)
        self.registry["reviews"][0]["github_author"] = "test-alice"
        self.registry["reviews"][0]["evidence_sha256"] = {}
        self.write("reviewed.json", self.registry)
        with self.assertRaises(CatalogError):
            build_catalog(self.root)

    def test_public_release_is_explicit_and_cannot_be_overridden(self):
        for field, value in (("authorized", False), ("rights_confirmed", False), ("contains_private_data", True)):
            with self.subTest(field=field):
                self.cap["public_release"] = {**RELEASE, field: value}
                self.add_cap()
                with self.assertRaises(CatalogError):
                    build_catalog(self.root)

    def test_claimed_verification_and_self_approval_fields_rejected(self):
        for field in ("verified", "reviewed", "trusted", "verification_status", "approval"):
            with self.subTest(field=field):
                self.cap[field] = True
                self.add_cap()
                with self.assertRaises(CatalogError):
                    build_catalog(self.root)
                del self.cap[field]

    def test_all_results_and_failures_required(self):
        self.add_cap()
        for mutation in (lambda e: e["sample"].update(passed=1),
                         lambda e: e["results"].append(copy.deepcopy(e["results"][0])),
                         lambda e: (e["sample"].update(failed=1, inconclusive=0), e["results"][0].update(outcome="FAIL"))):
            with self.subTest(mutation=mutation):
                self.ev = load_json(ROOT / "catalog/templates/evaluation.json")
                self.ev.update(id="test-evaluation", capability_id="test-capability", evaluator_id="test-bob")
                mutation(self.ev)
                self.add_eval()
                with self.assertRaises(CatalogError):
                    build_catalog(self.root)

    def test_evidence_format_and_byte_hash_fail_closed(self):
        descriptor = self.evidence()
        for field, value in (("format", "arbitrary.python.v1"), ("sha256", "0" * 64), ("path", "../private.json")):
            with self.subTest(field=field):
                self.cap["evidence"] = [{**descriptor, field: value}]
                self.add_cap()
                with self.assertRaises(CatalogError):
                    build_catalog(self.root)

    def test_unsigned_structural_receipt_is_not_authenticated_or_verified(self):
        verdict = assess_receipt(receipt(), "bureau.receipt.v0.1")
        self.assertEqual(verdict["cryptographic_authenticity"], "UNKNOWN")
        self.assertEqual(verdict["outcome_verification"], "NOT_ESTABLISHED")
        self.assertIn("EFFECT_OBSERVED", verdict["supported_claims"])

    def test_malformed_receipt_types_fail_without_crash(self):
        for field, value in (("receiver", 123), ("action", {"type": []}), ("decision", {"outcome": []}),
                             ("provenance", []), ("effect", {"observed": 1}), ("verified", True)):
            with self.subTest(field=field):
                payload = receipt()
                payload[field] = value
                with self.assertRaises(CatalogError):
                    assess_receipt(payload, "bureau.receipt.v0.1")

    def test_no_arbitrary_code_execution(self):
        marker = Path(self.tmp.name) / "executed"
        self.cap["summary"] = "__import__('pathlib').Path('" + str(marker) + "').touch()"
        self.add_cap()
        build_catalog(self.root)
        self.assertFalse(marker.exists())

    def test_source_symlinks_size_duplicate_keys_and_secrets_fail(self):
        p = self.root / "submissions/capabilities/test.json"
        p.parent.mkdir(parents=True)
        cases = ['{"id":"a","id":"b"}', '{"summary":"' + 'x' * (256 * 1024) + '"}',
                 '{"api_key":"do-not-print-test-secret"}', '{"summary":"ghp_' + 'x' * 32 + '"}']
        for content in cases:
            with self.subTest(content=content[:24]):
                p.write_text(content)
                with self.assertRaises(CatalogError):
                    Reader(self.root).read("submissions/capabilities/test.json")
        p.unlink()
        p.symlink_to(ROOT / "catalog/templates/capability.json")
        with self.assertRaises(CatalogError):
            build_catalog(self.root)

    def test_unsafe_urls_rejected_without_fetching(self):
        for u in ("http://example.org/x", "javascript:alert(1)", "https://user:password@example.org/x",
                  "https://127.0.0.1/x", "https://127.1/x", "https://0177.0.0.1/x", "https://0x7f.0x0.0x0.0x1/x",
                  "https://%31%32%37.0.0.1/x", "https://metadata.google.internal/x", "https://example.local/x",
                  "https://example.org/?access_token=test", "https://example.org/#token=test",
                  "https://example.org/?X-Amz-Credential=test", "https://example.org/?X-Amz-Signature=test"):
            with self.subTest(url=u):
                with self.assertRaises(CatalogError):
                    safe_url(u)
        self.assertEqual(safe_url("https://github.com/terryncew/openline-bureau#readme"), "https://github.com/terryncew/openline-bureau#readme")

    def test_price_inquiry_and_no_real_payment_policy(self):
        self.cap["price"] = {"amount": "12.50", "currency": "USD", "basis": "Quoted per document; negotiated separately."}
        self.cap["inquiry"]["accepts_inquiries"] = True
        self.add_cap()
        self.assertFalse(build_catalog(self.root)["capabilities"][0]["inquiry"]["accepts_inquiries"])
        self.registry["policy"]["inquiries_enabled"] = True
        self.write("reviewed.json", self.registry)
        catalog = build_catalog(self.root)
        self.assertTrue(catalog["capabilities"][0]["inquiry"]["accepts_inquiries"])
        self.assertFalse(catalog["policy"]["payment_processing"])

    def test_lineage_hashes_history_and_cycles(self):
        self.add_cap()
        original_hash = hashlib.sha256((self.root / "submissions/capabilities/test.json").read_bytes()).hexdigest()
        new = copy.deepcopy(self.cap)
        new["version"] = "1.1.0"
        new["lineage"] = [{"capability_id": self.cap["id"], "version": self.cap["version"], "record_sha256": original_hash, "relation": "improves"}]
        self.write("submissions/capabilities/test-1.1.0.json", new)
        self.approve("submissions/capabilities/test-1.1.0.json", new)
        self.assertEqual(len(build_catalog(self.root)["capabilities"]), 2)
        new["lineage"][0]["record_sha256"] = "0" * 64
        self.write("submissions/capabilities/test-1.1.0.json", new)
        self.approve("submissions/capabilities/test-1.1.0.json", new)
        with self.assertRaises(CatalogError):
            build_catalog(self.root)

    def test_export_only_approved_artifacts_and_remove_withdrawn_files(self):
        self.cap["evidence"] = [self.evidence()]
        self.add_cap()
        self.write("evidence/unapproved-private.json", {"not_for_publication": "test-only private marker"})
        out = Path(self.tmp.name) / "public/v1"
        export_artifacts(self.root, out)
        manifest = load_json(out / "artifacts.json")
        self.assertTrue((out / "evidence/test.json").is_file())
        self.assertFalse((out / "evidence/unapproved-private.json").exists())
        for artifact in manifest["artifacts"]:
            self.assertEqual(hashlib.sha256((out / artifact["path"]).read_bytes()).hexdigest(), artifact["sha256"])
        self.registry["reviews"] = []
        self.write("reviewed.json", self.registry)
        export_artifacts(self.root, out)
        self.assertFalse((out / "evidence/test.json").exists())
        self.assertFalse((out / "submissions/capabilities/test.json").exists())

    def test_deterministic_build(self):
        fixture = build_catalog(ROOT / "catalog", fixtures=True)
        self.assertEqual(fixture, build_catalog(ROOT / "catalog", fixtures=True))

    def test_published_json_schema(self):
        fixture = build_catalog(ROOT / "catalog", fixtures=True)
        try:
            import jsonschema
        except ImportError:
            self.skipTest("optional JSON Schema verifier missing")
        schema = Reader(ROOT / "catalog/schemas").read("catalog.schema.json", scan=False)[0]
        jsonschema.validate(fixture, schema)

    def test_worker_execution_evidence_never_promotes_capability_quality(self):
        worker = load_json(ROOT / "catalog/templates/worker.json")
        worker.update(id="test-worker", contributor_id="test-diana", capability_ids=[self.cap["id"]])
        self.cap["worker_id"] = worker["id"]
        self.ev["worker_id"] = worker["id"]
        self.write("submissions/workers/test.json", worker)
        self.approve("submissions/workers/test.json", worker)
        self.add_cap()
        self.add_eval()
        self.reproduce()
        catalog = build_catalog(self.root)
        self.assertEqual(catalog["capabilities"][0]["evidence_summary"]["label"], "SELF_REPORTED")
        self.assertEqual(catalog["capabilities"][0]["evidence_summary"]["independent_evaluation_count"], 0)
        self.assertEqual(catalog["workers"][0]["evidence_summary"]["label"], "INDEPENDENTLY_REPRODUCED")
        self.assertEqual(catalog["evaluations"][0]["scope"], "WORKER_EXECUTION")
        self.reproduce(reviewer="test-diana")
        with self.assertRaises(CatalogError):
            build_catalog(self.root)

    def test_missing_or_unpublished_prerequisites_cannot_publish(self):
        self.add_cap(approved=False)
        self.add_eval()
        with self.assertRaises(CatalogError):
            build_catalog(self.root)
        self.ev["capability_version"] = "9.0.0"
        self.add_eval()
        with self.assertRaises(CatalogError):
            validate_source(self.root, pending=True)

    def test_receipt_private_provenance_path_not_public(self):
        for ref in ("/home/user/private.json", "../private.json", "file:///tmp/token", "C:\\secret.json"):
            with self.subTest(ref=ref):
                payload = receipt()
                payload["provenance"] = {"system": "synthetic-test", "source_ref": ref}
                with self.assertRaises(CatalogError):
                    assess_receipt(payload, "bureau.receipt.v0.1")

    def crypto(self):
        try:
            from openline_wallet.crypto import sign_record, public_key_hex
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("Signed success cases require the installed trusted Wallet package")
        return sign_record, public_key_hex, Ed25519PrivateKey.generate()

    def gate_receipt(self, stopped=False):
        sign_record, public_key_hex, key = self.crypto()
        body = {"schema": "openline.gate.action_receipt.v1", "gate_id": "synthetic-test-gate",
                "gate_public_key": public_key_hex(key), "principal_id": "openline:principal:" + "1" * 64,
                "mandate_id": None if stopped else "test-mandate", "subject_id": None if stopped else "test-subject",
                "action": "synthetic-test-action", "decision": "STOPPED" if stopped else "ALLOWED",
                "reason_codes": ["MANDATE_NOT_FOUND"] if stopped else [],
                "presentation_hash": None if stopped else "2" * 64, "decided_at": "2026-01-01T00:00:00Z",
                "wallet_policy_authority": "NONE", "decision_authority": "RECEIVER_GATE"}
        return sign_record(body, key), sign_record, key

    def test_signed_receipt_authenticates_key_not_real_world_outcome(self):
        sign_record, _, key = self.crypto()
        original = receipt()
        payload = {"format": "openline.catalog.signed-receipt.v1", "receipt": original, "signed_record": sign_record(original, key)}
        verdict = assess_receipt(payload, payload["format"])
        self.assertEqual(verdict["cryptographic_authenticity"], "AUTHENTICATED_KEY")
        self.assertEqual(verdict["outcome_verification"], "NOT_ESTABLISHED")
        self.cap["evidence"] = [self.evidence(payload, payload["format"])]
        self.add_cap()
        self.assertEqual(build_catalog(self.root)["capabilities"][0]["evidence_summary"]["label"], "SELF_REPORTED")
        payload["receipt"] = copy.deepcopy(original)
        payload["receipt"]["effect"]["observed"] = False
        with self.assertRaises(CatalogError):
            assess_receipt(payload, payload["format"])

    def test_authentic_nullable_gate_refusal_matches_wallet_protocol(self):
        payload, _, _ = self.gate_receipt(stopped=True)
        from openline_wallet.wallet import _verify_gate_receipt
        _verify_gate_receipt(payload, principal=payload["principal_id"])
        verdict = assess_receipt(payload, "openline.gate.action_receipt.v1")
        self.assertEqual(verdict["cryptographic_authenticity"], "AUTHENTICATED_KEY")
        self.assertIn("mandate_id is unknown in this receiver receipt", verdict["missing_claims"])
        self.assertNotIn("EFFECT_OBSERVED", verdict["supported_claims"])

    def test_signed_gate_wrong_types_vocabulary_and_tamper_fail(self):
        payload, sign_record, key = self.gate_receipt()
        for field, value in (("decision", "COMMITTED"), ("action", None), ("gate_id", []), ("wallet_policy_authority", "OWNER")):
            with self.subTest(field=field):
                body = {k: v for k, v in payload.items() if k not in ("signature", "payload_hash")}
                body[field] = value
                with self.assertRaises(CatalogError):
                    assess_receipt(sign_record(body, key), "openline.gate.action_receipt.v1")
        payload["signature"]["value"] = "0" * 128
        with self.assertRaises(CatalogError):
            assess_receipt(payload, "openline.gate.action_receipt.v1")

    def test_signed_wallet_effect_preserves_refusal_and_rejects_contradiction(self):
        payload, sign_record, key = self.gate_receipt()
        body = {k: v for k, v in payload.items() if k not in ("signature", "payload_hash", "presentation_hash", "decided_at")}
        body.update(schema="openline.wallet.effect_receipt.v1", decision="STOPPED", reason_codes=["MANDATE_REVOKED"],
                    release="synthetic-test", effect_id="3" * 64, admission_receipt_hash="4" * 64,
                    frontier_receipt_hash="5" * 64, effect_applied=False, completed_at="2026-01-01T00:00:01Z")
        verdict = assess_receipt(sign_record(body, key), body["schema"])
        self.assertEqual(verdict["outcome_verification"], "NOT_ESTABLISHED")
        body["effect_applied"] = True
        with self.assertRaises(CatalogError):
            assess_receipt(sign_record(body, key), body["schema"])


if __name__ == "__main__":
    unittest.main()
