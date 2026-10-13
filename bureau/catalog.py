"""Data-only, reviewed public capability catalog; no contributed code or URL fetches.

Review identity is a maintainer attestation, not authentication performed by this
compiler. Hashes bind the exact reviewed bytes. Receipt conformance, key
authenticity, independent reports and reproduced outcomes remain separate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import urlsplit, unquote, parse_qsl

FORMAT = "openline.catalog.v1"
REPOSITORY = "https://github.com/terryncew/openline-bureau"
MAX_FILE = 256 * 1024
MAX_FILES = 2000
MAX_TOTAL = 16 * 1024 * 1024
KINDS = {"capabilities": "openline.capability.v1", "workers": "openline.worker.v1",
         "evaluations": "openline.evaluation.v1"}
RECEIPT_FORMATS = {"bureau.receipt.v0.1", "openline.wallet.effect_receipt.v1",
                   "openline.gate.action_receipt.v1", "openline.catalog.signed-receipt.v1",
                   "openline.exchange.selected-evidence.v1"}
ID = re.compile(r"^[a-z][a-z0-9._-]{1,79}$")
AUTHOR = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[a-zA-Z0-9.-]+)?$")
SHA = re.compile(r"^[0-9a-f]{64}$")
SECRET = re.compile(r"(?:-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|"
                    r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|"
                    r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|\bAKIA[A-Z0-9]{16}\b)")
FORBIDDEN_KEYS = {"private_key", "privatekey", "api_key", "apikey", "password",
                  "access_token", "refresh_token", "client_secret", "authorization",
                  "cookie", "session_token", "environment_variables"}


class CatalogError(ValueError):
    """A bounded, safe validation error; never embeds contributed payload values."""


def fail(message):
    raise CatalogError(message)


def shape(value, required, optional=(), where="record"):
    if not isinstance(value, dict):
        fail(f"{where}: expected object")
    missing, unknown = set(required) - value.keys(), value.keys() - set(required) - set(optional)
    if missing or unknown:
        fail(f"{where}: missing or unsupported fields")


def text(value, where, limit=4000, pattern=None, empty=False):
    if (not isinstance(value, str) or len(value) > limit or
            (not empty and not value.strip()) or
            any(ord(c) < 32 and c not in "\n\t" for c in value) or
            (pattern and not pattern.fullmatch(value))):
        fail(f"{where}: invalid text")


def items(value, where, maximum=100, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        fail(f"{where}: invalid list length")


def strings(value, where, maximum=100, minimum=0, limit=1000):
    items(value, where, maximum, minimum)
    for v in value:
        text(v, where, limit)
    if len(set(value)) != len(value):
        fail(f"{where}: duplicate strings")


def public_release(value):
    shape(value, ("authorized", "rights_confirmed", "contains_private_data"), where="public_release")
    if (value["authorized"] is not True or value["rights_confirmed"] is not True
            or value["contains_private_data"] is not False):
        fail("public_release: explicit permission and absence of private data required")


def safe_url(value, *, inquiry=False, pr=False):
    text(value, "URL", 2048)
    try:
        u = urlsplit(value)
        host = u.hostname
        port = u.port
    except ValueError:
        fail("URL: malformed")
    decoded = unquote(value)
    sensitive_query = {"access_token", "token", "api_key", "apikey", "key", "password", "secret", "signature", "sig", "auth", "authorization", "credential", "credentials", "client_secret", "code", "jwt", "sas", "sv", "x-amz-credential", "x-amz-signature", "x-goog-credential", "x-goog-signature"}
    if any(k.casefold() in sensitive_query or any(x in k.casefold() for x in ("token", "secret", "password", "signature", "credential"))
           for k, _ in [*parse_qsl(u.query, keep_blank_values=True), *parse_qsl(u.fragment, keep_blank_values=True)]):
        fail("URL: credential-bearing or signed query links forbidden")
    if (u.scheme != "https" or not host or u.username or u.password or port not in (None, 443)
            or any(c.isspace() or ord(c) < 32 for c in decoded) or "\\" in decoded
            or host.endswith(".") or host.lower() in ("localhost", "metadata.google.internal")
            or host.lower().endswith((".local", ".internal", ".localhost"))
            or "." not in host or any(p in (".", "..") for p in decoded.split("/"))):
        fail("URL: only credential-free public HTTPS destinations allowed")
    labels = host.split(".")
    dns_label = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
    if (len(host) > 253 or any(not dns_label.fullmatch(label) for label in labels)
            or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9-]*", labels[-1])):
        fail("URL: only canonical public DNS hostnames allowed")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        fail("URL: IP addresses are not public contribution destinations")
    if inquiry and (u.netloc != "github.com" or u.path != "/terryncew/openline-bureau/issues/new"
                    or u.query or u.fragment):
        fail("inquiry URL: expected the configured public GitHub issue entrypoint")
    if pr and (u.netloc != "github.com" or not re.fullmatch(
            r"/terryncew/openline-bureau/pull/[1-9][0-9]*", u.path) or u.query or u.fragment):
        fail("review URL: expected a contribution pull request")
    return value


def safety_scan(value, depth=0):
    if depth > 24:
        fail("JSON nesting exceeds limit")
    if isinstance(value, dict):
        if len(value) > 1000:
            fail("JSON object exceeds limit")
        for k, v in value.items():
            text(k, "JSON key", 128)
            if k.lower() in FORBIDDEN_KEYS:
                fail("credential or private configuration field forbidden")
            safety_scan(v, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            fail("JSON array exceeds limit")
        for v in value:
            safety_scan(v, depth + 1)
    elif isinstance(value, str):
        text(value, "JSON string", 16000, empty=True)
        if SECRET.search(value):
            fail("possible credential material forbidden")
        # Every complete URL token is checked, including descriptive evidence.
        for u in re.findall(r"(?:[a-zA-Z][a-zA-Z0-9+.-]*://)[^\s<>\"']+", value):
            safe_url(u.rstrip(".,);]"))
    elif value is None or type(value) in (bool, int):
        pass
    elif type(value) is float:
        import math
        if not math.isfinite(value):
            fail("non-finite JSON number forbidden")
    else:
        fail("unsupported JSON value")


def relative_path(value, prefix=None):
    text(value, "path", 240)
    p = PurePosixPath(value)
    if (p.is_absolute() or "\\" in value or "%" in value or
            any(x in ("", ".", "..") for x in value.split("/")) or
            not re.fullmatch(r"[A-Za-z0-9._/-]+", value) or
            (prefix and not value.startswith(prefix + "/")) or p.suffix != ".json"):
        fail("path: expected bounded relative JSON path under permitted directory")
    return p


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            fail("duplicate JSON keys forbidden")
        out[k] = v
    return out


class Reader:
    def __init__(self, root):
        supplied = Path(root).absolute()
        # Reject symlinks even when they happen to resolve inside the source.
        for parent in [supplied, *supplied.parents]:
            if parent.is_symlink():
                fail("source directory symlink forbidden")
        if not supplied.is_dir():
            fail("source directory missing")
        self.root, self.cache, self.total = supplied, {}, 0

    def read(self, rel, *, scan=True):
        relative_path(rel)
        if rel in self.cache:
            return self.cache[rel]
        if len(self.cache) >= MAX_FILES:
            fail("catalog file count exceeds limit")
        target = self.root / rel
        for part in [target, *target.parents]:
            if part == self.root.parent:
                break
            if part.is_symlink():
                fail("symlink forbidden in contributed data")
        try:
            mode = target.stat().st_mode
            if not stat.S_ISREG(mode) or target.stat().st_size > MAX_FILE:
                fail("catalog source must be a bounded regular file")
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as handle:
                data = handle.read(MAX_FILE + 1)
        except OSError:
            fail("catalog source missing or unreadable")
        if len(data) > MAX_FILE:
            fail("catalog source exceeds size limit")
        self.total += len(data)
        if self.total > MAX_TOTAL:
            fail("catalog total bytes exceeds limit")
        try:
            payload = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates,
                                 parse_constant=lambda _: fail("invalid JSON constant"))
        except (ValueError, UnicodeError, RecursionError):
            fail("catalog source is not valid bounded UTF-8 JSON")
        if scan:
            safety_scan(payload)
        result = payload, hashlib.sha256(data).hexdigest()
        self.cache[rel] = result
        return result

    def submissions(self):
        result = []
        base = self.root / "submissions"
        if not base.exists():
            return result
        for directory, dirs, files in os.walk(base, followlinks=False):
            for child in [*dirs, *files]:
                p = Path(directory) / child
                if p.is_symlink():
                    fail("symlink forbidden in submissions")
            for name in sorted(files):
                if name == ".gitkeep":
                    continue
                p = Path(directory) / name
                rel = p.relative_to(self.root).as_posix()
                if len(p.relative_to(base).parts) != 2 or p.parent.name not in KINDS or p.suffix != ".json":
                    fail("submissions contain unsupported file or directory")
                result.append((p.parent.name, rel))
                if len(result) > MAX_FILES:
                    fail("catalog file count exceeds limit")
        return sorted(result)


def evidence_descriptor(item):
    shape(item, ("path", "sha256", "format", "public_release"), where="evidence")
    relative_path(item["path"], "evidence")
    text(item["sha256"], "evidence hash", 64, SHA)
    if item["format"] not in RECEIPT_FORMATS:
        fail("unsupported receipt format")
    public_release(item["public_release"])


def provenance(value):
    shape(value, ("source_url", "source_revision", "authors"), where="provenance")
    safe_url(value["source_url"])
    if value["source_revision"] is not None:
        text(value["source_revision"], "source_revision", 64, re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$"))
    strings(value["authors"], "authors", 30, 1, 200)


def inquiry(value):
    shape(value, ("url", "accepts_inquiries"), where="inquiry")
    safe_url(value["url"], inquiry=True)
    if type(value["accepts_inquiries"]) is not bool:
        fail("inquiry: accepts_inquiries must be boolean")


def sample(value):
    shape(value, ("dataset", "selection", "total", "passed", "failed", "inconclusive"), where="sample")
    text(value["dataset"], "dataset", 1000)
    text(value["selection"], "selection", 2000)
    for field in ("total", "passed", "failed", "inconclusive"):
        if type(value[field]) is not int or not 0 <= value[field] <= 1000:
            fail("sample: invalid bounded denominator")
    if value["total"] < 1 or sum(value[k] for k in ("passed", "failed", "inconclusive")) != value["total"]:
        fail("sample: results do not sum to denominator")


def validate_record(record, kind):
    common = ("format", "id", "public_release", "synthetic")
    if kind == "capabilities":
        shape(record, common + ("version", "name", "summary", "tasks", "contributor_id", "worker_id",
                               "provenance", "usage_terms", "price", "inquiry", "limitations", "lineage", "evidence"))
    elif kind == "workers":
        shape(record, common + ("name", "summary", "contributor_id", "capability_ids", "provenance", "inquiry", "limitations"))
    else:
        shape(record, common + ("capability_id", "capability_version", "worker_id", "evaluator_id", "task", "method",
                               "sample", "results", "failures", "limitations", "environment", "conflicts", "evidence"))
    if record["format"] != KINDS[kind]:
        fail("record format does not match submission directory")
    text(record["id"], "id", 80, ID)
    if type(record["synthetic"]) is not bool:
        fail("synthetic must be explicit boolean")
    public_release(record["public_release"])
    author = "evaluator_id" if kind == "evaluations" else "contributor_id"
    text(record[author], author, 39, AUTHOR)
    strings(record["limitations"], "limitations", 50, limit=2000)
    if kind != "evaluations":
        text(record["name"], "name", 120)
        text(record["summary"], "summary", 4000)
        provenance(record["provenance"])
        inquiry(record["inquiry"])
    if kind == "workers":
        strings(record["capability_ids"], "capability_ids", 100, 1, 80)
        for x in record["capability_ids"]:
            text(x, "capability id", 80, ID)
    else:
        if record["worker_id"] is not None:
            text(record["worker_id"], "worker_id", 80, ID)
        items(record["evidence"], "evidence", 100)
        for e in record["evidence"]:
            evidence_descriptor(e)
        if len({e["path"] for e in record["evidence"]}) != len(record["evidence"]):
            fail("duplicate evidence reference")
    if kind == "capabilities":
        text(record["version"], "version", 80, VERSION)
        strings(record["tasks"], "tasks", 30, 1, 100)
        shape(record["usage_terms"], ("license", "summary"), where="usage_terms")
        text(record["usage_terms"]["license"], "license", 200)
        text(record["usage_terms"]["summary"], "terms summary", 4000)
        if record["price"] is not None:
            p = record["price"]
            shape(p, ("amount", "currency", "basis"), where="price")
            text(p["amount"], "price amount", 20, re.compile(r"^(0|[1-9][0-9]{0,8})(?:\.[0-9]{1,4})?$"))
            text(p["currency"], "currency", 32, re.compile(r"^[A-Z]{3}$|^SIM_USD$"))
            if p["currency"] == "SIM_USD" and not record["synthetic"]:
                fail("simulated price requires synthetic label")
            text(p["basis"], "price basis", 500)
        items(record["lineage"], "lineage", 20)
        for link in record["lineage"]:
            shape(link, ("capability_id", "version", "record_sha256", "relation"), where="lineage")
            text(link["capability_id"], "lineage id", 80, ID)
            text(link["version"], "lineage version", 80, VERSION)
            text(link["record_sha256"], "lineage hash", 64, SHA)
            if link["relation"] not in ("improves", "derived_from", "evaluates"):
                fail("unsupported lineage relation")
    elif kind == "evaluations":
        text(record["capability_id"], "capability_id", 80, ID)
        text(record["capability_version"], "capability_version", 80, VERSION)
        for f in ("task", "method", "environment", "conflicts"):
            text(record[f], f, 4000)
        sample(record["sample"])
        items(record["results"], "results", 1000, 1)
        if len(record["results"]) != record["sample"]["total"]:
            fail("evaluation must expose every case in its declared denominator")
        counts = {"PASS": 0, "FAIL": 0, "INCONCLUSIVE": 0}
        ids = set()
        for result in record["results"]:
            shape(result, ("case_id", "outcome", "summary"), where="result")
            text(result["case_id"], "case_id", 100)
            text(result["summary"], "result summary", 2000)
            if result["outcome"] not in counts or result["case_id"] in ids:
                fail("evaluation result outcome invalid or case duplicated")
            counts[result["outcome"]] += 1
            ids.add(result["case_id"])
        if [counts[k] for k in ("PASS", "FAIL", "INCONCLUSIVE")] != [record["sample"][k] for k in ("passed", "failed", "inconclusive")]:
            fail("case outcomes disagree with declared sample")
        strings(record["failures"], "failures", 100, limit=2000)
        if record["sample"]["failed"] and not record["failures"]:
            fail("failed cases require documented failures")


def _wallet_signature(payload):
    if not isinstance(payload, dict):
        fail("signed receipt must be object")
    if not payload.get("signature"):
        return "UNKNOWN", None
    try:
        from openline_wallet.crypto import verify_record, principal_id
    except ImportError:
        fail("Wallet cryptographic verifier required for signed evidence")
    try:
        ok, _ = verify_record(payload)
    except Exception:
        fail("signed receipt authentication failed")
    if not ok:
        fail("signed receipt authentication failed")
    try:
        signer = principal_id(payload["signature"]["public_key"])
    except Exception:
        fail("signed receipt signer malformed")
    return "AUTHENTICATED_KEY", signer


def _bureau_shape(payload):
    shape(payload, ("receipt_version", "receipt_id", "timestamp", "receiver"),
          ("principal", "actor", "action", "authority", "decision", "effect", "parents", "provenance", "extensions"), where="Bureau public receipt profile")
    for key in ("receipt_id", "timestamp", "receiver", "principal", "actor"):
        if key in payload:
            text(payload[key], key, 1000)
    nested = {"action": ("type", "target", "action_id"),
              "authority": ("authority_id", "status", "issued_at", "revoked_at"),
              "decision": ("outcome", "reason"), "effect": ("effect_id", "observed", "observed_at"),
              "provenance": ("system", "hash", "signature", "source_ref")}
    for key, fields in nested.items():
        if key not in payload:
            continue
        shape(payload[key], (), fields, where=key)
        for field, value in payload[key].items():
            if field == "observed":
                if value is not None and type(value) is not bool:
                    fail("Bureau effect observation must be boolean or null")
            else:
                text(value, key + "." + field, 4000)
                if key == "provenance" and field == "source_ref":
                    if value.startswith("https://"):
                        safe_url(value)
                    elif (value.startswith(("/", "~")) or "\\" in value or "://" in value
                          or any(x in (".", "..") for x in value.split("/"))
                          or re.match(r"^[A-Za-z]:", value)):
                        fail("receipt provenance source_ref must not expose private filesystem paths")
                if field in ("issued_at", "revoked_at", "observed_at"):
                    from .conformance import _parse_ts
                    if _parse_ts(value) is None:
                        fail("Bureau receipt timestamp invalid")
    if "parents" in payload:
        strings(payload["parents"], "parents", 100, limit=1000)
    if "extensions" in payload and not isinstance(payload["extensions"], dict):
        fail("Bureau extensions must be an object")


def _wallet_shape(payload, declared_format):
    common = ("schema", "gate_id", "gate_public_key", "principal_id", "mandate_id", "subject_id", "action",
              "decision", "reason_codes", "wallet_policy_authority", "decision_authority", "payload_hash", "signature")
    effect = declared_format == "openline.wallet.effect_receipt.v1"
    extra = ("release", "effect_id", "admission_receipt_hash", "frontier_receipt_hash", "effect_applied", "completed_at") if effect else ("presentation_hash", "decided_at")
    shape(payload, common + extra, where="Wallet or gate receipt")
    if payload["schema"] != declared_format or payload["decision"] not in ("ALLOWED", "STOPPED"):
        fail("Wallet or gate receipt schema or decision unsupported")
    for key in ("gate_id", "mandate_id", "subject_id", "action") + (("release",) if effect else ()):
        if not effect and payload["decision"] == "STOPPED" and key in ("mandate_id", "subject_id") and payload[key] is None:
            continue
        text(payload[key], key, 500)
    for key in ("gate_public_key", "payload_hash") + (("effect_id", "admission_receipt_hash", "frontier_receipt_hash") if effect else ("presentation_hash",)):
        if not effect and payload["decision"] == "STOPPED" and key == "presentation_hash" and payload[key] is None:
            continue
        text(payload[key], key, 64, SHA)
    text(payload["principal_id"], "principal_id", 83, re.compile(r"^openline:principal:[0-9a-f]{64}$"))
    strings(payload["reason_codes"], "reason_codes", 100, limit=200)
    if payload["wallet_policy_authority"] != "NONE" or payload["decision_authority"] != "RECEIVER_GATE":
        fail("Wallet receipt authority semantics unsupported")
    if effect and (type(payload["effect_applied"]) is not bool or (payload["decision"] == "STOPPED" and payload["effect_applied"])):
        fail("Wallet effect receipt effect contradicts its receiver decision")
    from .conformance import _parse_ts
    if _parse_ts(payload["completed_at" if effect else "decided_at"]) is None:
        fail("Wallet receipt timestamp invalid")
    auth, signer = _wallet_signature(payload)
    if auth != "AUTHENTICATED_KEY" or payload["signature"].get("public_key") != payload["gate_public_key"]:
        fail("Wallet gate public key must match the authenticated signer")
    return auth, signer


def assess_receipt(payload, declared_format):
    """Revalidate formats; signatures authenticate a key, never an outcome."""
    safety_scan(payload)
    from . import conformance
    from .adapters import adapt
    auth, signer = "UNKNOWN", None
    claims, missing = [], []
    if declared_format == "openline.catalog.signed-receipt.v1":
        shape(payload, ("format", "receipt", "signed_record"), where="signed receipt")
        if payload["format"] != declared_format:
            fail("receipt format mismatch")
        auth, signer = _wallet_signature(payload["signed_record"])
        signed_body = {k: v for k, v in payload["signed_record"].items() if k not in ("payload_hash", "signature")}
        if auth != "AUTHENTICATED_KEY" or signed_body != payload["receipt"]:
            fail("signature does not bind exact receipt")
        payload = payload["receipt"]
        declared_format = "bureau.receipt.v0.1"
    if declared_format == "bureau.receipt.v0.1":
        if not isinstance(payload, dict) or payload.get("receipt_version") != declared_format:
            fail("receipt version mismatch")
        _bureau_shape(payload)
        try:
            verdict = conformance.validate(payload)
        except (TypeError, AttributeError, ValueError, KeyError):
            fail("malformed Bureau receipt")
        if verdict["status"] not in (conformance.VALID, conformance.CONFORMANT_NO_CLAIMS):
            fail("Bureau receipt conformance failed")
        claims, missing = verdict["supported_claims"], verdict["not_established"]
        status = verdict["status"]
    elif declared_format in ("openline.wallet.effect_receipt.v1", "openline.gate.action_receipt.v1"):
        auth, signer = _wallet_shape(payload, declared_format)
        try:
            normalized = adapt(payload, {"source_repo": "public-catalog", "source_path": "data-only"})
        except Exception:
            fail("Bureau receipt adapter failed")
        if not normalized:
            fail("receipt adapter produced no records")
        status = "STRUCTURALLY_VALID"
        claims = ["RECEIVER_DECISION_OBSERVED"]
        missing = ["independent outcome verification", "authority standing"]
        for key in ("mandate_id", "subject_id", "presentation_hash"):
            if key in payload and payload[key] is None:
                missing.append(key + " is unknown in this receiver receipt")
    elif declared_format == "openline.exchange.selected-evidence.v1":
        from .adapters import exchange
        shape(payload, ("format", "jobs"), ("source", "profiles"), where="Exchange evidence")
        if payload["format"] != declared_format:
            fail("Exchange receipt format mismatch")
        items(payload["jobs"], "Exchange jobs", 100, 1)
        authenticated = []
        for job in payload["jobs"]:
            if not isinstance(job, dict):
                fail("malformed Exchange job")
            for phase in ("offer", *exchange.PHASES):
                if phase not in job:
                    continue
                envelope = job[phase]
                shape(envelope, ("record", "signature"), where="Exchange envelope")
                schema = "commission.offer.v1" if phase == "offer" else exchange.PHASES[phase]
                if not isinstance(envelope["record"], dict) or envelope["record"].get("schema") != schema:
                    fail("Exchange phase schema mismatch")
                phase_auth, _ = _wallet_signature(envelope["signature"])
                body = {k: v for k, v in envelope["signature"].items() if k not in ("payload_hash", "signature")}
                if phase_auth != "AUTHENTICATED_KEY" or body != envelope["record"]:
                    fail("Exchange signed envelope does not bind record")
                authenticated.append(True)
            state = exchange.assess(job, trusted_buyers=())
            if not state["agreement"] or not state["offer"]:
                fail("Exchange evidence has no authenticated supported agreement and offer")
        try:
            normalized = exchange.adapt(payload, {"source_repo": "public-catalog", "source_path": "data-only"})
        except Exception:
            fail("Exchange receipt adaptation failed")
        if not normalized:
            fail("Exchange evidence produced no receipts")
        status, auth = "STRUCTURALLY_VALID", "AUTHENTICATED_KEY" if authenticated else "UNKNOWN"
        claims = ["SIGNED_EXCHANGE_RECORDS_OBSERVED"]
        missing = ["independent outcome verification", "buyer trust policy", "real payment: Exchange selected evidence is simulated"]
    else:
        fail("unsupported receipt format")
    return {"status": status, "cryptographic_authenticity": auth, "signer_principal": signer,
            "supported_claims": claims, "missing_claims": missing,
            "outcome_verification": "NOT_ESTABLISHED",
            "authenticity_limit": "A valid signature binds a key to bytes; it does not verify the reported outcome or legal identity."}


def load_registry(reader):
    registry, _ = reader.read("reviewed.json")
    shape(registry, ("format", "policy", "reviews"), where="trusted review registry")
    if registry["format"] != "openline.catalog.reviews.v1":
        fail("review registry version unsupported")
    policy = registry["policy"]
    shape(policy, ("repository_url", "contribution_url", "catalog_url", "inquiries_enabled"), where="catalog policy")
    if policy["repository_url"] != REPOSITORY or policy["contribution_url"] != REPOSITORY + "/compare":
        fail("catalog contribution repository does not match configured repository")
    safe_url(policy["catalog_url"])
    if type(policy["inquiries_enabled"]) is not bool:
        fail("inquiries policy must be boolean")
    items(registry["reviews"], "reviews", MAX_FILES)
    result = {}
    for review in registry["reviews"]:
        shape(review, ("path", "record_sha256", "github_author", "source_pr_url", "public_disclosure_reviewed", "evidence_sha256", "reproduction"), where="review")
        relative_path(review["path"], "submissions")
        text(review["record_sha256"], "review hash", 64, SHA)
        text(review["github_author"], "reviewed author", 39, AUTHOR)
        safe_url(review["source_pr_url"], pr=True)
        if review["public_disclosure_reviewed"] is not True:
            fail("review must explicitly approve disclosure")
        if not isinstance(review["evidence_sha256"], dict) or len(review["evidence_sha256"]) > 100:
            fail("review evidence hash map invalid")
        for path, digest in review["evidence_sha256"].items():
            relative_path(path, "evidence")
            text(digest, "review evidence hash", 64, SHA)
        if review["path"] in result:
            fail("duplicate review path")
        result[review["path"]] = review
    return policy, result


def _reproduced(reader, review, record, digest):
    attestation = review["reproduction"]
    if attestation is None:
        return None
    shape(attestation, ("path", "sha256"), where="reproduction review")
    relative_path(attestation["path"], "reproductions")
    text(attestation["sha256"], "reproduction hash", 64, SHA)
    report, report_digest = reader.read(attestation["path"])
    shape(report, ("format", "evaluation_sha256", "reviewer", "method", "environment", "sample", "results_sha256", "public_release"), where="reproduction report")
    public_release(report["public_release"])
    text(report["reviewer"], "reproduction reviewer", 39, AUTHOR)
    for field in ("method", "environment"):
        text(report[field], field, 4000)
    sample(report["sample"])
    expected_results = hashlib.sha256(json.dumps(record["results"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    if (report_digest != attestation["sha256"] or report["format"] != "openline.catalog.reproduction.v1"
            or report["evaluation_sha256"] != digest or report["results_sha256"] != expected_results
            or report["sample"] != record["sample"] or report["method"] != record["method"]
            or report["environment"] != record["environment"]
            or report["reviewer"].casefold() == record["evaluator_id"].casefold()):
        fail("reproduction attestation does not bind exact independent evaluation outcomes")
    return {"reviewer": report["reviewer"], "method": report["method"], "environment": report["environment"],
            "sample": report["sample"], "report_sha256": report_digest, "source_url": attestation["path"]}


def _compile_source(source, *, pending=False, fixture=False):
    reader = Reader(source)
    policy, registry = load_registry(reader)
    records, raw, digests, paths = {k: [] for k in KINDS}, {}, {}, {}
    preparation = []
    for kind, path in reader.submissions():
        record, digest = reader.read(path)
        validate_record(record, kind)
        if record["synthetic"] != fixture:
            fail("synthetic records must live only in the opt-in fixture source")
        key = (kind, record["id"], record.get("version"))
        if key in raw:
            fail("duplicate immutable record identity/version")
        evidence = []
        for descriptor in record.get("evidence", []):
            payload, evidence_digest = reader.read(descriptor["path"])
            if evidence_digest != descriptor["sha256"]:
                fail("evidence does not match its declared immutable hash")
            verdict = assess_receipt(payload, descriptor["format"])
            evidence.append({"path": descriptor["path"], "sha256": evidence_digest, "format": descriptor["format"], **verdict})
        review = registry.get(path)
        preparation.append({"path": path, "record_sha256": digest,
                            "evidence_sha256": {e["path"]: e["sha256"] for e in evidence},
                            "approval": "PENDING_MAINTAINER_REVIEW"})
        raw[key], digests[key], paths[key] = record, digest, path
        if review:
            author = record["evaluator_id"] if kind == "evaluations" else record["contributor_id"]
            if (review["record_sha256"] != digest or review["github_author"].casefold() != author.casefold()
                    or review["evidence_sha256"] != {e["path"]: e["sha256"] for e in evidence}):
                fail("review does not bind exact content, evidence and contributor")
        elif not pending:
            continue
        out = copy.deepcopy(record)
        out["record_sha256"] = digest
        out["record_url"] = path
        out["evidence"] = evidence
        for item in out["evidence"]:
            item["source_url"] = item["path"]
        out["publication"] = {"reviewed": bool(review), "identity_basis": "MAINTAINER_ATTESTED_GITHUB_AUTHOR" if review else "UNREVIEWED_CLAIM",
                              "source_pr_url": review["source_pr_url"] if review else None,
                              "identity_limit": "The compiler does not authenticate GitHub authors, legal identity or organizational independence."}
        if kind != "evaluations":
            out["inquiry"]["accepts_inquiries"] = bool(review and policy["inquiries_enabled"] and record["inquiry"]["accepts_inquiries"] and not fixture)
        else:
            reproduction = _reproduced(reader, review, record, digest) if review else None
            reproduced = bool(reproduction)
            out["reproduction"] = reproduction
            out["outcome_verification"] = "SYNTHETIC" if fixture else "MAINTAINER_REPRODUCED" if reproduced else "EVALUATOR_REPORTED"
            out["scope"] = "WORKER_EXECUTION" if record["worker_id"] else "CAPABILITY"
        records[kind].append(out)
    if set(registry) - set(paths.values()):
        fail("review references missing submission")
    # All proposed records must have resolvable and immutable local references.
    for (kind, _, _), record in raw.items():
        if kind == "capabilities":
            for link in record["lineage"]:
                target = ("capabilities", link["capability_id"], link["version"])
                if target not in raw or digests[target] != link["record_sha256"] or raw[target] is record:
                    fail("lineage must bind an existing earlier immutable capability record")
            if record["worker_id"] is not None:
                target = ("workers", record["worker_id"], None)
                if target not in raw or record["id"] not in raw[target]["capability_ids"]:
                    fail("capability worker link must be declared by a submitted worker")
        elif kind == "workers":
            for cap_id in record["capability_ids"]:
                if not any(k[0] == "capabilities" and k[1] == cap_id for k in raw):
                    fail("worker references unknown capability")
        else:
            target = ("capabilities", record["capability_id"], record["capability_version"])
            if target not in raw:
                fail("evaluation references unknown immutable capability version")
            if record["worker_id"] is not None and record["worker_id"] != raw[target]["worker_id"]:
                fail("worker execution evidence must name that capability's worker")
    # Reject lineage cycles, including cycles across different IDs.
    def visit(key, active, done):
        if key in active:
            fail("cyclic capability lineage forbidden")
        if key in done:
            return
        if len(active) > 100:
            fail("capability lineage depth exceeds limit")
        active.add(key)
        for link in raw[key]["lineage"]:
            visit(("capabilities", link["capability_id"], link["version"]), active, done)
        active.remove(key)
        done.add(key)
    done = set()
    for key in raw:
        if key[0] == "capabilities":
            visit(key, set(), done)
    caps = {(r["id"], r["version"]): r for r in records["capabilities"]}
    workers = {r["id"]: r for r in records["workers"]}
    # Published records cannot depend on unpublished prerequisites.
    for cap in records["capabilities"]:
        if (cap["worker_id"] and cap["worker_id"] not in workers) or any((x["capability_id"], x["version"]) not in caps for x in cap["lineage"]):
            fail("published capability references unpublished worker or lineage")
    for worker in records["workers"]:
        if any(not any(k[0] == cap_id for k in caps) for cap_id in worker["capability_ids"]):
            fail("published worker references unpublished capability")
    for evaluation in records["evaluations"]:
        cap = caps.get((evaluation["capability_id"], evaluation["capability_version"]))
        if not cap:
            fail("published evaluation references unpublished capability")
        is_separate = (evaluation["publication"]["reviewed"] and cap["publication"]["reviewed"] and
                       evaluation["evaluator_id"].casefold() != cap["contributor_id"].casefold())
        if cap["worker_id"]:
            is_separate = is_separate and evaluation["evaluator_id"].casefold() != workers[cap["worker_id"]]["contributor_id"].casefold()
        reproduction = evaluation["reproduction"]
        if reproduction:
            excluded = {cap["contributor_id"].casefold(), evaluation["evaluator_id"].casefold()}
            if cap["worker_id"]:
                excluded.add(workers[cap["worker_id"]]["contributor_id"].casefold())
            if reproduction["reviewer"].casefold() in excluded or not is_separate:
                fail("independent reproduction must use a distinct reviewed evaluator and a separate maintainer reproducer")
        evaluation["independence"] = "SEPARATE_REVIEWED_CONTRIBUTOR" if is_separate else "NOT_INDEPENDENT"
        evaluation["independence_limit"] = "Separate reviewed GitHub contributors; account control, affiliation and reported conflicts are not independently established."
    for cap in records["capabilities"]:
        cap["evidence_summary"] = summarize(cap["evidence"], [e for e in records["evaluations"] if e["capability_id"] == cap["id"] and e["capability_version"] == cap["version"] and e["worker_id"] is None], fixture, cap["limitations"])
        cap["evidence_summary"]["scope"] = "CAPABILITY_ONLY"
    for worker in records["workers"]:
        worker["evidence_summary"] = summarize([], [e for e in records["evaluations"] if e["worker_id"] == worker["id"]], fixture, worker["limitations"])
        worker["evidence_summary"]["scope"] = "WORKER_EXECUTIONS_ONLY"
    return {"format": FORMAT, "synthetic": fixture, "submission": {k: policy[k] for k in ("repository_url", "contribution_url", "catalog_url")},
            "policy": {"inquiries_enabled": policy["inquiries_enabled"] and not fixture,
                       "payment_processing": False, "contributed_code_execution": False,
                       "attribution_limit": "Lineage and author metadata preserve attribution; they do not establish legal ownership or license rights.",
                       "ranking": "No universal trust score; compare task-specific sample results, prices and limitations."}, **records}, preparation


def summarize(receipts, evaluations, fixture, limitations):
    separate = [e for e in evaluations if e["independence"] == "SEPARATE_REVIEWED_CONTRIBUTOR"]
    reproduced = [e for e in separate if e["outcome_verification"] == "MAINTAINER_REPRODUCED"]
    all_receipts = receipts + [r for e in evaluations for r in e["evidence"]]
    authentic = sum(r["cryptographic_authenticity"] == "AUTHENTICATED_KEY" for r in all_receipts)
    missing = []
    if not all_receipts:
        missing.append("Supporting receipts")
    if not separate:
        missing.append("Evaluation from a separate reviewed contributor")
    if not reproduced:
        missing.append("Independent reproduction of task outcomes")
    if not limitations:
        missing.append("Documented capability limitations")
    if not authentic:
        missing.append("Cryptographic authentication of receipt keys")
    return {"label": "SYNTHETIC" if fixture else "INDEPENDENTLY_REPRODUCED" if reproduced else "INDEPENDENTLY_REPORTED" if separate else "SELF_REPORTED",
            "receipt_count": len(all_receipts), "independent_evaluation_count": len(separate),
            "reproduced_evaluation_count": len(reproduced), "cryptographic_authenticity": "UNKNOWN" if not authentic else "AUTHENTICATED_KEY" if authentic == len(all_receipts) else "MIXED",
            "missing": missing, "sample_context": [e["sample"] | {"task": e["task"], "evaluation_id": e["id"], "outcome_verification": e["outcome_verification"]} for e in evaluations]}


def build_catalog(source="catalog", *, fixtures=False, pending=False):
    catalog, _ = _compile_source(source, pending=pending)
    if fixtures:
        synthetic, _ = _compile_source(Path(source) / "fixtures", pending=pending, fixture=True)
        catalog = synthetic
        catalog["policy"]["fixture_notice"] = "Synthetic fixture catalog; no real contributor, independently reproduced outcome, inquiry acceptance or payment."
    return catalog


def export_artifacts(source, outdir, *, fixtures=False, index_name="index.json"):
    """Copy only approved bytes; raw receipts remain inspectable and hash-bound."""
    catalog = build_catalog(source, fixtures=fixtures)
    actual_source = Path(source) / "fixtures" if fixtures else Path(source)
    reader = Reader(actual_source)
    outdir = Path(outdir).absolute()
    if outdir.resolve().is_relative_to(Path(source).resolve()):
        fail("compiled artifact outputs must be outside contribution source")
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.json", index_name):
        fail("compiled output name must be a simple JSON filename")
    expected = {}
    for kind in KINDS:
        for record in catalog[kind]:
            expected[record["record_url"]] = record["record_sha256"]
            expected.update({e["path"]: e["sha256"] for e in record.get("evidence", [])})
            if record.get("reproduction"):
                expected[record["reproduction"]["source_url"]] = record["reproduction"]["report_sha256"]
    artifacts = []
    for rel in sorted(expected):
        _, digest = reader.read(rel)
        data = (reader.root / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or digest != expected[rel]:
            fail("source changed during artifact export")
        target = outdir / rel
        for p in [target, *target.parents]:
            if p.is_symlink():
                fail("artifact output symlink forbidden")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        artifacts.append({"path": rel, "sha256": digest})
    schemas = Path(source) / "schemas"
    if schemas.is_dir():
        schema_reader = Reader(schemas)
        for schema in sorted(schemas.glob("*.json")):
            _, schema_digest = schema_reader.read(schema.name, scan=False)
            schema_bytes = schema.read_bytes()
            if hashlib.sha256(schema_bytes).hexdigest() != schema_digest:
                fail("schema changed during artifact export")
            target = outdir / "schemas" / schema.name
            for p in [target, *target.parents]:
                if p.is_symlink():
                    fail("schema artifact output symlink forbidden")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(schema_bytes)
            artifacts.append({"path": "schemas/" + schema.name, "sha256": schema_digest})
    manifest_path = outdir / "artifacts.json"
    if manifest_path.exists():
        previous = Reader(outdir).read("artifacts.json")[0]
        shape(previous, ("format", "catalog", "artifacts"), where="artifact manifest")
        if previous["format"] != "openline.catalog.artifacts.v1":
            fail("existing output has no supported artifact manifest")
        items(previous["artifacts"], "previous artifacts", MAX_FILES)
        current = {a["path"] for a in artifacts}
        for artifact in previous["artifacts"]:
            shape(artifact, ("path", "sha256"), where="previous artifact")
            relative_path(artifact["path"])
            if artifact["path"].split("/")[0] not in ("submissions", "evidence", "reproductions", "schemas"):
                fail("prior artifact manifest path outside generated directories")
            if artifact["path"] in current:
                continue
            old = outdir / artifact["path"]
            for p in [old, *old.parents]:
                if p.is_symlink():
                    fail("stale artifact symlink forbidden")
            if old.is_file():
                old.unlink()
    serialized = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    manifest = {"format": "openline.catalog.artifacts.v1", "catalog": {"path": index_name, "sha256": hashlib.sha256(serialized.encode()).hexdigest()}, "artifacts": sorted(artifacts, key=lambda a: a["path"])}
    for p in [manifest_path, *manifest_path.parents]:
        if p.is_symlink():
            fail("artifact manifest output symlink forbidden")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return catalog


def validate_source(source="catalog", *, pending=False):
    """Validate contributed data with trusted code; pending never approves data."""
    return build_catalog(source, pending=pending)


def load_json(path):
    """Read one bounded, data-only JSON file without printing its content."""
    path = Path(path).absolute()
    return Reader(path.parent).read(path.name)[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "build", "prepare-review"))
    parser.add_argument("--source", default="catalog")
    parser.add_argument("--fixtures", action="store_true")
    parser.add_argument("--pending", "--unreviewed", action="store_true", help="Validate proposed records without publishing or approving them")
    parser.add_argument("--out", help="Compiled catalog output (build only)")
    args = parser.parse_args(argv)
    try:
        if args.command == "build" and args.pending:
            fail("pending content cannot be built for publication")
        if args.command != "build" and args.out:
            fail("only build writes output")
        if args.command == "prepare-review":
            _, review = _compile_source(args.source, pending=True)
            print(json.dumps({"format": "openline.catalog.review-preparation.v1", "notice": "Digests only. No identity verification, public disclosure approval or review is granted.", "records": review}, indent=2))
        else:
            catalog = build_catalog(args.source, fixtures=args.fixtures, pending=args.pending)
            if args.command == "build":
                if args.out:
                    out = Path(args.out)
                    if out.exists() and out.is_symlink():
                        fail("output symlink forbidden")
                    source_root = Path(args.source).resolve()
                    if out.resolve().is_relative_to(source_root):
                        fail("compiled outputs must be outside the contribution source")
                    catalog = export_artifacts(args.source, out.parent, fixtures=args.fixtures, index_name=out.name)
                    serialized = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(serialized, encoding="utf-8")
                else:
                    serialized = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                    print(serialized, end="")
            else:
                print(json.dumps({"valid": True, "pending": args.pending, "synthetic": catalog["synthetic"], "counts": {k: len(catalog[k]) for k in KINDS}}))
    except (CatalogError, OSError) as exc:
        print("catalog validation failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
