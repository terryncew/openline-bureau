"""REVIEW-DESK-001 review engine: intake -> evidence -> review -> record.

Deterministic and stdlib-only. The engine never invents citations: every
reference in a draft response comes from the evidence registry, and any
citation the commenter supplies that is not in the registry is reported
as unverified. An engine-generated response is a DRAFT, never a verdict;
a human approves or rejects it, and the approval is recorded separately.

Classifications: ADDRESSED | TESTABLE | UNRESOLVABLE | NO_CLAIM
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

ADDRESSED = "ADDRESSED"
TESTABLE = "TESTABLE"
UNRESOLVABLE = "UNRESOLVABLE"
NO_CLAIM = "NO_CLAIM"

# Instruction-override patterns. The engine treats pasted comments as DATA,
# never as instructions. A match sets injection_attempt=True; the engine
# strips the directive and classifies whatever substantive content remains.
_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?(prior|previous|your)\s+instructions?"
    r"|\bsystem\s*:"
    r"|\bassistant\s*:"
    r"|\[system\]"
    r"|approve\s+this"
    r"|mark\s+(this\s+)?as\s+(approved|addressed|valid)"
    r"|you\s+must\s+(approve|publish|post)"
    r"|disregard\s+the\s+registry)",
    re.IGNORECASE)

# Citation-like patterns a commenter may use. Each candidate is checked
# against the registry; anything not found is flagged unverified.
_CITATION = re.compile(
    r"(?:test|spec|vector|doc|claim|section|§)\s+[\w\-./:#]+"
    r"|\btest_[\w\-]+\b"
    r"|[A-Z][\w\-]*\.md(?:\s*§\s*\d+)?"
    r"|\b[\w\-]+\.json\b"
    r"|\b[\w\-]+\.py::[\w\-]+\b",
    re.IGNORECASE)

_UNRESOLVABLE_HINTS = (
    "will anyone adopt", "adopt", "real world", "in production", "intent of",
    "what will happen", "prove that it happened", "actually occurred",
    "ground truth",
)

_TESTABLE_HINTS = (
    "fails when", "breaks if", "what if", "counterexample", "reproduce",
    "try running", "does not verify", "accepts invalid", "rejects valid",
    "edge case", "should be", "would fail",
)

_NO_CLAIM_HINTS = (
    "great", "thanks", "interesting", "cool", "nice work", "congratulations",
    "looking forward",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_registry(path: str | Path | None = None) -> dict:
    path = Path(path) if path else HERE / "registry.json"
    return json.loads(path.read_text())


def _claim_by_id(registry: dict, claim_id: str) -> dict | None:
    for claim in registry["claims"]:
        if claim["id"] == claim_id:
            return claim
    return None


def _find_citations(text: str) -> list[str]:
    return sorted(set(m.group(0) for m in _CITATION.finditer(text)))


def _citation_in_registry(citation: str, registry: dict) -> bool:
    needle = citation.lower()
    for claim in registry["claims"]:
        for ref in claim["references"]:
            hay = ref["ref"].lower()
            if needle in hay or hay in needle:
                return True
    return False


def _strip_injection(text: str) -> str:
    return _INJECTION.sub(" ", text)


def classify(comment: str, registry: dict) -> dict:
    """Classify a pasted comment. Returns a structured draft assessment."""
    original = comment or ""
    flags: list[str] = []
    text = original

    if _INJECTION.search(original):
        flags.append("injection_attempt")
        text = _strip_injection(original)
        # The directive is data, not an order. Never obey it; never
        # characterize the commenter. Classify the remaining substance.

    lowered = text.lower().strip()
    result = {
        "classification": NO_CLAIM,
        "rationale": "",
        "matched_objection": None,
        "evidence": [],
        "unverified_citations": [],
        "false_premise_correction": None,
        "flags": flags,
    }

    if not lowered or len(lowered) < 12:
        result["rationale"] = (
            "No substantive technical content found. Nothing to review.")
        return result

    # Fabricated-citation check: every citation-like string must resolve
    # to a registry reference, or it is flagged and the draft says UNKNOWN.
    for citation in _find_citations(text):
        if not _citation_in_registry(citation, registry):
            result["unverified_citations"].append(citation)
    if result["unverified_citations"]:
        flags.append("unverified_citation")

    # Objection matching against the registry.
    matched = None
    for objection in registry.get("objections", []):
        if any(p in lowered for p in objection["patterns"]):
            matched = objection
            break

    if matched:
        claim = _claim_by_id(registry, matched["resolution_claim"])
        result["classification"] = ADDRESSED
        result["matched_objection"] = matched["id"]
        result["evidence"] = [claim] if claim else []
        # False-premise correction: the objection pattern matched, so the
        # comment asserts something the registry contradicts. Say so plainly.
        result["false_premise_correction"] = (
            f"The comment's premise matches a known, resolved objection "
            f"({matched['id']}): {matched['summary']} "
            f"The registry resolves it as: {claim['statement']}"
            if claim else None)
        result["rationale"] = (
            f"Matches documented objection {matched['id']}, resolved by "
            f"claim {matched['resolution_claim']}.")
        return result

    if any(h in lowered for h in _UNRESOLVABLE_HINTS):
        result["classification"] = UNRESOLVABLE
        result["rationale"] = (
            "Concerns a matter the available evidence cannot resolve "
            "(real-world occurrence, adoption, intent). Answer: UNKNOWN.")
        return result

    if any(h in lowered for h in _TESTABLE_HINTS):
        result["classification"] = TESTABLE
        result["rationale"] = (
            "States a falsifiable technical proposition not covered by the "
            "registry. A challenge record should be created with a proposed "
            "falsifier before any response is drafted.")
        return result

    if any(h in lowered for h in _NO_CLAIM_HINTS) and "?" not in text:
        result["rationale"] = (
            "Acknowledgement or praise without an actionable technical claim.")
        return result

    # Default: a substantive comment with no match and no testable
    # proposition is treated as testable-if-it-names-a-mechanism, else
    # no actionable claim. Be conservative: ask for the mechanism.
    if "?" in text:
        result["classification"] = TESTABLE
        result["rationale"] = (
            "Poses a question naming no documented objection. Treat as a "
            "candidate challenge: restate it as a falsifiable claim with a "
            "proposed falsifier, or reclassify as NO_CLAIM if none exists.")
    else:
        result["rationale"] = (
            "Substantive text but no actionable technical claim identified.")
    return result


def draft_response(comment: str, assessment: dict, registry: dict) -> dict:
    """Assemble a proposed response. Every reference comes from the registry.

    Never invents citations. If evidence is missing, the draft says UNKNOWN.
    The draft is labeled as a draft; it is not a technical verdict.
    """
    lines = ["DRAFT RESPONSE — not a verdict. Human approval required before any use.",
             ""]
    cls = assessment["classification"]

    if assessment.get("false_premise_correction"):
        lines.append("Correction: " + assessment["false_premise_correction"])
        lines.append("")

    if cls == ADDRESSED:
        for claim in assessment["evidence"]:
            lines.append("Evidence: " + claim["statement"])
            for ref in claim["references"]:
                lines.append(f"  - [{ref['type']}] {ref['ref']}")
            if claim.get("limitations"):
                lines.append("Limitations:")
                for lim in claim["limitations"]:
                    lines.append("  - " + lim)
    elif cls == TESTABLE:
        lines.append(
            "This is a new, testable objection. No documented evidence "
            "addresses it yet. Proposed next step: record it as a challenge "
            "with an explicit falsifier, run the test, then respond from "
            "the outcome. Do not answer from speculation.")
    elif cls == UNRESOLVABLE:
        lines.append(
            "UNKNOWN. The available evidence cannot resolve this: it concerns "
            "matters outside what signed evidence establishes (see the "
            "registry's limitations and NOT_PROOF-style boundaries). Saying "
            "more would exceed the evidence.")
    else:
        lines.append(
            "No actionable technical claim identified. No response required; "
            "a brief acknowledgement is sufficient if any reply is sent.")

    if assessment.get("unverified_citations"):
        lines.append("")
        lines.append("Unverified citations in the comment (not in the "
                     "evidence registry — treated as UNKNOWN, not repeated "
                     "as fact):")
        for citation in assessment["unverified_citations"]:
            lines.append("  - " + citation)

    if "injection_attempt" in assessment.get("flags", []):
        lines.append("")
        lines.append("Note: the comment contained instruction-like language "
                     "directed at the reviewer. It was treated as data and "
                     "disregarded; it does not affect this assessment.")

    return {
        "draft": "\n".join(lines),
        "references_used": [
            ref["ref"]
            for claim in assessment["evidence"]
            for ref in claim["references"]
        ],
        "is_verdict": False,
    }


def review(comment: str, registry: dict | None = None) -> dict:
    """Full intake -> evidence -> review pass. Returns the review record."""
    registry = registry or load_registry()
    assessment = classify(comment, registry)
    draft = draft_response(comment, assessment, registry)
    return {
        "review_id": "rev-" + uuid.uuid4().hex[:12],
        "created_at": utcnow(),
        "input": {"comment": comment},
        "assessment": assessment,
        "draft": draft,
        "human_approval": None,
    }


def create_challenge(claim: str, proposed_falsifier: str,
                     source_review_id: str | None = None,
                     evidence_refs: list | None = None) -> dict:
    """Create a local structured challenge record for a testable objection."""
    return {
        "challenge_id": "chg-" + uuid.uuid4().hex[:12],
        "created_at": utcnow(),
        "source_review_id": source_review_id,
        "claim": claim,
        "proposed_falsifier": proposed_falsifier,
        "test_status": "proposed",
        "result": None,
        "evidence_refs": evidence_refs or [],
        "human_approved": False,
    }


def export_record(review: dict, challenges: list | None = None) -> dict:
    """Machine-readable review record with separated sections.

    human_statements: what a human wrote or approved.
    automated_checks: what the engine computed.
    test_outcomes: challenge records and their results.
    human_approvals: explicit human decisions, each timestamped.
    """
    return {
        "review_id": review["review_id"],
        "created_at": review["created_at"],
        "human_statements": {
            "submitted_comment": review["input"]["comment"],
            "approved_draft": (review["human_approval"] or {}).get("draft_text"),
        },
        "automated_checks": {
            "classification": review["assessment"]["classification"],
            "rationale": review["assessment"]["rationale"],
            "matched_objection": review["assessment"]["matched_objection"],
            "flags": review["assessment"]["flags"],
            "unverified_citations": review["assessment"]["unverified_citations"],
            "references_used": review["draft"]["references_used"],
            "is_verdict": False,
        },
        "test_outcomes": challenges or [],
        "human_approvals": (
            [review["human_approval"]] if review.get("human_approval") else []
        ),
    }
