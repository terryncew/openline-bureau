# REVIEW-DESK-001 — build report

Experiment branch: `experiment/review-desk-001` (not merged, not public).

## What works

- **Intake → evidence → review → record**, end to end, locally. Paste a
  comment in the browser UI; the deterministic engine (`review.py`,
  stdlib-only) classifies it as `ADDRESSED` / `TESTABLE` / `UNRESOLVABLE` /
  `NO_CLAIM`, pulls the matching registry claims, and assembles a proposed
  response with exact source references and limitations.
- **Evidence registry** (`registry.json`): 8 explicitly approved public
  claims, each with statement, references (spec/vector/test/doc/code),
  known limitations, and the objections it resolves; 8 documented
  objection patterns. Nothing is assumed — claims without listed evidence
  are not in the registry.
- **Honesty properties, test-enforced**: drafts cite only registry
  references (a test asserts every used reference resolves); false
  premises are corrected, never agreed with; missing evidence produces
  `UNKNOWN`; every draft is labeled "not a verdict."
- **Adversarial coverage** (21 tests, all passing): misleading objections,
  fabricated citations (flagged, never repeated as fact), prompt injection
  (treated as data, disregarded, no behavior change), irrelevant comments,
  and contradictory records (recorded separately, both pointing at the
  same evidence).
- **Challenge records**: testable objections become local structured
  records (claim, proposed falsifier, test status, result, evidence) via
  UI or API.
- **Machine-readable export**: `/api/export` separates `human_statements`,
  `automated_checks`, `test_outcomes`, `human_approvals`. Records live in
  `records/` (gitignored — local working state, never committed).
- **Server**: stdlib-only, binds 127.0.0.1 only. No auto-publish path
  exists anywhere in the code; approval records a local decision.

## What remains manual

- **Classification is heuristic.** Keyword/pattern matching is a draft
  suggestion; the human picks the final bucket in the UI. Subtle or novel
  objections will misclassify — the desk is honest about this by labeling
  everything a draft.
- **Draft approval is a local record only.** There is deliberately no
  path from approval to publication. Posting a response anywhere remains
  a fully manual human act.
- **Challenge tests are proposed, not run.** The desk records the claim
  and falsifier; a human (or a future harness) runs the test and records
  the outcome.
- **Registry curation is manual.** Adding, correcting, or retiring claims
  is a human edit to `registry.json`, reviewed like code.
- **No ingestion.** Comments are pasted by hand. No scraping, no mailbox,
  no forum API — by design for this MVP.

## What trustworthy automation would need

1. **A real test harness for challenges**: sandboxed execution of proposed
   falsifiers with recorded inputs/outputs, so `test_status` transitions
   are evidenced, not asserted.
2. **Registry versioning and review**: signed or hash-pinned registry
   revisions with an approval trail, so "approved claim" stays checkable
   over time.
3. **A better classifier with calibrated uncertainty**: the current
   heuristics should be replaced by something that reports confidence and
   says UNKNOWN when unsure — never a silent misclassification.
4. **Provenance for pasted comments**: URL/author/timestamp capture at
   intake, so a review record can be traced to the original public
   statement.
5. **A publication gate, if ever**: approval → human-authored post in the
   human's own channel, with the desk's draft attached as provenance —
   never the desk posting by itself.
6. **Adversarial red-teaming beyond the current set**: coordinated
   multi-comment campaigns, slowly-shifting premises, and registry
   poisoning attempts (malicious registry edits) are not yet covered.

## Test summary

- New suite: `experiments/review-desk-001/tests` — 21 tests, all passing
  (`python3 -m unittest discover -s tests` from the experiment dir).
- `node --check ui/app.js` passes.
- Pre-existing repo suites: unchanged. (`tests/` at repo root has
  pre-existing environment failures here — it needs `/workspace/openline-wallet`
  and the `exchange` module, neither present in this environment; unrelated
  to this experiment and untouched by it.)
- No frozen interop specification or test vector was modified.
