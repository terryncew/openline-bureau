#!/usr/bin/env python3
"""OpenLine Bureau receipt validator CLI.

    python3 -m bureau.validate receipt.json
    python3 -m bureau.validate receipt.json --json
    python3 -m bureau.validate receipt.json --claim POST_REVOCATION_ATTEMPT_OBSERVED

Read-only: the source file is opened for reading and never modified.
Deterministic: no network, no model calls.
"""

import argparse
import json
import os
import sys

from .conformance import (
    VALID, CONFORMANT_NO_CLAIMS, INVALID, UNSUPPORTED_VERSION,
    CLAIMS, CLAIM_DEFS, validate, check_claim, _file_signature,
)


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _print_human(path, payload, result, claim=None, claim_result=None):
    rid = result.get("receipt_id") or "(no receipt_id)"
    print("RECEIPT: %s" % rid)
    if claim is not None and claim_result is not None:
        verdict, missing = claim_result
        print("CLAIM:   %s" % claim)
        print("VERDICT: %s" % verdict)
        if verdict == "SUPPORTED":
            print()
            print("The receipt carries the minimum evidence this claim requires:")
            for req in CLAIM_DEFS[claim]["requires"]:
                print("  + %s" % req)
        else:
            print()
            print("Missing evidence:")
            for m in missing:
                print("  - %s" % m)
        print()
        print("RECEIPT STATUS: %s" % result["status"])
        return

    print("STATUS:  %s" % result["status"])
    print()
    print("SUPPORTED CLAIMS")
    if result["supported_claims"]:
        for c in result["supported_claims"]:
            print("  [x] %s" % c)
    else:
        print("  (none)")
    print()
    print("NOT ESTABLISHED")
    for c in result["not_established"]:
        print("  [ ] %s" % c)
    print()
    if result["problems"]:
        print("PROBLEMS")
        for p in result["problems"]:
            print("  ! %s" % p)
        print()
    if result["warnings"]:
        print("WARNINGS")
        for w in result["warnings"]:
            print("  - %s" % w)
        print()
    auth = "absent (structural conformance only)"
    if result["signature_present"]:
        auth = "present (preserved and exposed; verification is the receiver's job)"
    print("CRYPTOGRAPHIC AUTHENTICITY: %s" % auth)
    print("source files modified: 0")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Validate an external Bureau receipt (bureau.receipt.v0.1). "
                    "Read-only; deterministic.")
    ap.add_argument("path", help="JSON receipt file to validate")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    ap.add_argument("--claim", default=None, metavar="CLAIM",
                    help="check one claim explicitly (e.g. "
                    "POST_REVOCATION_ATTEMPT_OBSERVED)")
    args = ap.parse_args(argv)

    if args.claim and args.claim not in CLAIMS:
        print("unknown claim: %s" % args.claim, file=sys.stderr)
        print("known claims: %s" % ", ".join(CLAIMS), file=sys.stderr)
        return 2

    before = _file_signature(args.path)
    try:
        payload = _load(args.path)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print("RECEIPT: %s" % os.path.basename(args.path))
        print("STATUS:  UNREADABLE")
        print("PROBLEMS")
        print("  ! %s: %s" % (type(e).__name__, e))
        print("source files modified: 0")
        return 2

    result = validate(payload)
    claim_result = None
    if args.claim:
        claim_result = check_claim(payload, args.claim)

    after = _file_signature(args.path)
    if before != after:  # should be impossible; fail loud if it happens
        print("ERROR: source file was modified during validation", file=sys.stderr)
        return 1

    if args.json:
        out = dict(result)
        if claim_result is not None:
            out["claim"] = args.claim
            out["claim_verdict"], out["claim_missing"] = claim_result
        out["source_files_modified"] = 0
        print(json.dumps(out, indent=1, sort_keys=True))
    else:
        _print_human(args.path, payload, result, args.claim, claim_result)

    if args.claim:
        verdict = claim_result[0]
        return 0 if verdict == "SUPPORTED" else 1
    return 0 if result["status"] in (VALID, CONFORMANT_NO_CLAIMS) else 2


if __name__ == "__main__":
    sys.exit(main())
