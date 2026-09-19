#!/usr/bin/env python3
"""OpenLine Bureau — public evidence bundle validator.

One-command validation of public-evidence bundles:

    python3 -m bureau.evidence public-evidence            # all bundles
    python3 -m bureau.evidence public-evidence/<exp-id>  # one bundle
    python3 -m bureau.evidence <path> --json             # machine-readable

Read-only, deterministic, stdlib-only, no network. Returns 0 only when
every checked bundle passes; nonzero on any structural, hash,
conformance, or classification failure.

Per bundle it verifies:
  1. bundle structure (manifest, README, hashes, receipts, source,
     preregistration + result bindings);
  2. hashes.json digests against recomputed file bytes;
  3. manifest source digests against the actual source files;
  4. the manifest's terminal classification appears verbatim in the
     bound terminal-result artifact (a FAIL relabeled PASS fails here);
  5. receipt_ids are unique within the bundle;
  6. no bundle references another experiment's source artifacts;
  7. every derived receipt conforms (VALID or CONFORMANT_NO_CLAIMS;
     INVALID / UNSUPPORTED_VERSION / UNREADABLE fail);
  8. no bundle file was modified during validation (read-only proof).
"""

import hashlib
import json
import os
import sys

from .conformance import validate as conformance_validate, CLAIMS

REQUIRED_BUNDLE_FILES = ("manifest.json", "README.md", "hashes.json")
REQUIRED_BUNDLE_DIRS = ("receipts", "source", "preregistration", "result")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(bdir):
    """Map of relpath -> sha256 for every file under bdir."""
    out = {}
    for root, _ds, files in os.walk(bdir):
        for name in sorted(files):
            p = os.path.join(root, name)
            out[os.path.relpath(p, bdir)] = sha256_file(p)
    return out


def find_bundles(path):
    """Return bundle dirs: subdirs of path containing manifest.json,
    or [path] itself if it is a bundle."""
    path = os.path.abspath(path)
    if os.path.isfile(os.path.join(path, "manifest.json")):
        return [path]
    found = []
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            cand = os.path.join(path, name)
            if os.path.isdir(cand) and os.path.isfile(
                    os.path.join(cand, "manifest.json")):
                found.append(cand)
    return found


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_bundle(bdir):
    """Return (passed: bool, report: dict). Never raises on bad bundles."""
    report = {"bundle": os.path.basename(bdir), "path": bdir,
              "passed": False, "checks": [], "receipts": [],
              "problems": []}
    before = snapshot(bdir)

    def fail(msg):
        report["problems"].append(msg)

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok),
                                 "detail": detail})
        if not ok:
            fail("%s: %s" % (name, detail or "failed"))
        return bool(ok)

    # 1. structure ------------------------------------------------------
    for fname in REQUIRED_BUNDLE_FILES:
        check("structure:" + fname,
              os.path.isfile(os.path.join(bdir, fname)),
              "missing" if not os.path.isfile(os.path.join(bdir, fname))
              else "")
    for dname in REQUIRED_BUNDLE_DIRS:
        check("structure:" + dname + "/",
              os.path.isdir(os.path.join(bdir, dname)),
              "missing" if not os.path.isdir(os.path.join(bdir, dname))
              else "")
    rec_dir = os.path.join(bdir, "receipts")
    rec_files = sorted(f for f in os.listdir(rec_dir)
                       if f.endswith(".json")) if os.path.isdir(rec_dir) \
        else []
    check("structure:receipts-nonempty", len(rec_files) > 0,
          "no receipts/*.json" if not rec_files else
          "%d receipts" % len(rec_files))
    src_dir = os.path.join(bdir, "source")
    src_files = []
    for root, _ds, files in os.walk(src_dir):
        for n in files:
            src_files.append(os.path.relpath(os.path.join(root, n), src_dir))
    check("structure:source-nonempty", len(src_files) > 0,
          "source/ is empty" if not src_files else
          "%d source files" % len(src_files))

    manifest = None
    if os.path.isfile(os.path.join(bdir, "manifest.json")):
        try:
            manifest = _load_json(os.path.join(bdir, "manifest.json"))
            check("manifest:parseable", True)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            check("manifest:parseable", False, str(e))
    else:
        check("manifest:parseable", False, "manifest.json missing")

    exp_id = (manifest or {}).get("experiment_id") \
        or os.path.basename(bdir)

    # 2. hashes.json ------------------------------------------------------
    hashes_ok = False
    if os.path.isfile(os.path.join(bdir, "hashes.json")):
        try:
            hashes = _load_json(os.path.join(bdir, "hashes.json"))["files"]
            mism = []
            for rel, want in sorted(hashes.items()):
                p = os.path.join(bdir, rel)
                if not os.path.isfile(p):
                    mism.append("%s (missing)" % rel)
                elif sha256_file(p) != want:
                    mism.append("%s (digest mismatch)" % rel)
            hashes_ok = check("hashes:recomputed", not mism,
                              "; ".join(mism) if mism
                              else "%d files verified" % len(hashes))
        except (json.JSONDecodeError, KeyError, OSError) as e:
            check("hashes:recomputed", False, str(e))
    else:
        check("hashes:recomputed", False, "hashes.json missing")

    # 3. manifest source digests vs actual source files -------------------
    if manifest:
        src_digests = manifest.get("source_files", {})
        mism = []
        for rel, meta in sorted(src_digests.items()):
            p = os.path.join(src_dir, rel)
            want = (meta or {}).get("sha256")
            if not os.path.isfile(p):
                mism.append("%s (missing)" % rel)
            elif sha256_file(p) != want:
                mism.append("%s (digest mismatch: source byte altered?)"
                            % rel)
        check("source:manifest-digests", not mism,
              "; ".join(mism) if mism else
              "%d source files match manifest" % len(src_digests))

    # 4. terminal classification verbatim in the bound terminal artifact --
    if manifest:
        term = manifest.get("terminal_classification")
        check("terminal:manifest-present", bool(term),
              "manifest lacks terminal_classification" if not term else term)
        if term:
            ref_path = os.path.join(bdir, "result", "ref.json")
            found_in = []
            try:
                ref = _load_json(ref_path)
                for entry in ref.get("files", []):
                    p = os.path.join(bdir, entry["bundle_path"])
                    try:
                        with open(p, "rb") as f:
                            text = f.read().decode("utf-8", "replace")
                    except OSError:
                        continue
                    if term in text:
                        found_in.append(entry["bundle_path"])
            except (json.JSONDecodeError, OSError, KeyError) as e:
                check("terminal:verbatim-in-source", False,
                      "result/ref.json unreadable: %s" % e)
                found_in = None
            if found_in is not None:
                check("terminal:verbatim-in-source", bool(found_in),
                      ("classification %r not found verbatim in any bound "
                       "terminal artifact (mislabeled?)" % term)
                      if not found_in else
                      "found in: %s" % ", ".join(found_in))
            # preregistration binding resolves
            pre_path = os.path.join(bdir, "preregistration", "ref.json")
            try:
                pre = _load_json(pre_path)
                pre_ok = all(
                    os.path.isfile(os.path.join(bdir, e["bundle_path"]))
                    for e in pre.get("files", [])) and pre.get("files")
                check("preregistration:binding-resolves", bool(pre_ok),
                      "" if pre_ok else "binding missing or unresolvable")
            except (json.JSONDecodeError, OSError, KeyError) as e:
                check("preregistration:binding-resolves", False, str(e))

    # 5/6/7. receipts ------------------------------------------------------
    seen_ids = {}
    dupes = []
    cross_refs = []
    supported_union = set()
    for fname in rec_files:
        fpath = os.path.join(rec_dir, fname)
        entry = {"file": fname, "receipt_id": None, "status": "UNREADABLE",
                 "supported_claims": [], "not_established": [],
                 "signature": "unreadable"}
        try:
            payload = _load_json(fpath)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            entry["problems"] = ["unreadable: %s" % e]
            report["receipts"].append(entry)
            check("receipt:%s:readable" % fname, False, str(e))
            continue
        rid = payload.get("receipt_id")
        entry["receipt_id"] = rid
        if rid in seen_ids:
            dupes.append(rid)
        else:
            seen_ids[rid] = fname
        # Bundle policy (stricter than the claim engine, which only warns):
        # every derived receipt must carry attributable provenance, and the
        # source_ref must resolve to a real file inside this bundle.
        prov = payload.get("provenance") or {}
        prov_ok = (isinstance(prov, dict) and prov.get("system")
                   and prov.get("source_ref"))
        check("receipt:%s:provenance-present" % fname, bool(prov_ok),
              "provenance.system and provenance.source_ref are required"
              if not prov_ok else "")
        if prov_ok:
            ref = prov.get("source_ref")
            unsafe = (not isinstance(ref, str) or os.path.isabs(ref)
                      or ".." in ref.split("/"))
            target = os.path.normpath(os.path.join(bdir, ref)) \
                if not unsafe else None
            resolves = (not unsafe and target is not None
                        and target.startswith(os.path.abspath(bdir)
                                              + os.sep)
                        and os.path.isfile(target))
            check("receipt:%s:source-ref-resolves" % fname, resolves,
                  "source_ref %r does not resolve inside this bundle"
                  % ref if not resolves else "")
        # cross-bundle reference check
        ext = payload.get("extensions") or {}
        refs = " ".join(str(x) for x in (
            prov.get("source_ref"), prov.get("system"),
            ext.get("bureau.derived/source_artifact")))
        for other in _OTHER_BUNDLES:
            if other != exp_id and other in refs:
                cross_refs.append("%s references %s" % (rid, other))
        v = conformance_validate(payload)
        entry["status"] = v["status"]
        entry["supported_claims"] = v["supported_claims"]
        entry["not_established"] = v["not_established"]
        entry["signature"] = ("present (preserved, unverified)"
                              if v["signature_present"]
                              else "absent (not authenticated)")
        if v["problems"]:
            entry["problems"] = v["problems"]
        supported_union.update(v["supported_claims"])
        ok_status = v["status"] in ("VALID", "CONFORMANT_NO_CLAIMS")
        check("receipt:%s:conforms" % fname, ok_status,
              v["status"] + ("; " + "; ".join(v["problems"])
                             if v["problems"] else ""))
        report["receipts"].append(entry)
    check("receipts:unique-ids", not dupes,
          "duplicate receipt_ids: %s" % ", ".join(sorted(set(dupes)))
          if dupes else "%d unique" % len(seen_ids))
    check("receipts:no-cross-bundle-refs", not cross_refs,
          "; ".join(cross_refs) if cross_refs else "")
    report["claims_evidenced"] = sorted(supported_union)
    report["claims_not_measurable"] = sorted(
        set(CLAIMS) - supported_union)
    if manifest:
        report["terminal_classification"] = manifest.get(
            "terminal_classification")
        report["authenticity"] = manifest.get("authenticity")

    # 8. read-only proof --------------------------------------------------
    after = snapshot(bdir)
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    check("readonly:bundle-unmodified", not changed,
          ("modified during validation: %s" % ", ".join(changed))
          if changed else "source files modified: 0")
    report["source_files_modified"] = len(changed)

    report["passed"] = all(c["ok"] for c in report["checks"])
    return report["passed"], report


_OTHER_BUNDLES = set()  # filled by main() before validating


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="Validate OpenLine Bureau public evidence bundles. "
                    "Read-only; deterministic; stdlib-only; no network.")
    ap.add_argument("path", help="a bundle dir or the public-evidence root")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON report")
    args = ap.parse_args(argv)

    bundles = find_bundles(args.path)
    global _OTHER_BUNDLES
    _OTHER_BUNDLES = {os.path.basename(b) for b in bundles}

    if not bundles:
        print("no bundles found under %s" % args.path, file=sys.stderr)
        return 2

    results = []
    for b in bundles:
        passed, rep = validate_bundle(b)
        results.append(rep)

    all_ok = all(r["passed"] for r in results)
    if args.json:
        print(json.dumps({"bundles": results,
                          "bundles_passed": sum(1 for r in results
                                                if r["passed"]),
                          "bundles_total": len(results)},
                         indent=1, sort_keys=True))
        return 0 if all_ok else 1

    print("BUREAU PUBLIC EVIDENCE VALIDATION")
    print()
    for r in results:
        print("bundle: %s" % r["bundle"])
        print("  terminal: %s" % r.get("terminal_classification"))
        print("  bundle validation: %s" % ("PASS" if r["passed"] else "FAIL"))
        n_ok = sum(1 for e in r["receipts"]
                   if e["status"] in ("VALID", "CONFORMANT_NO_CLAIMS"))
        print("  receipts: %d checked, %d conform"
              % (len(r["receipts"]), n_ok))
        print("  claims evidenced: %s"
              % (", ".join(r["claims_evidenced"]) or "none"))
        print("  claims not measurable from this bundle: %s"
              % (", ".join(r["claims_not_measurable"]) or "none"))
        print("  authenticity: %s" % (r.get("authenticity") or "unstated"))
        if r["problems"]:
            print("  problems:")
            for p in r["problems"]:
                print("    - %s" % p)
        print("  source files modified: %d" % r["source_files_modified"])
        print()
    print("bundles passed: %d/%d"
          % (sum(1 for r in results if r["passed"]), len(results)))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
