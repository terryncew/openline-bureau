# TRUST-HANDOFF-001 — TERMINAL FREEZE (2026-09-18, single execution)

## Terminal classification

**PASS_TRUST_HANDOFF_001_DEFERRED_AUTHORITY_REVOKED**

Frozen precedence applied: all scored checks true; none of the FAIL
conditions triggered (T5 treatment did not COMMIT; transformed treatment did
not COMMIT; D treatment COMMITted).

## Pinned bases (recorded pre-contact, unmodified)

- Wallet origin/main: `687bf0d8fe2158969fcecb5c2522d8d8908856dd`
- Receipt-gate origin/main: `9c06dfd62b0e42de927899b9538ab675067390cd`
- Inspection was read-only (git show / git grep against origin/main). A
  detached read-only worktree of wallet main was used at runtime
  (`build/wallet-main`); no production file was modified.

## Existing primitives reused (all from pinned wallet main)

`Wallet.create/grant/revoke/export_bundle/timeline`,
`ReferenceGate(pin_principal/admit_bundle/issue_challenge/evaluate)`,
`create_presentation`, ed25519 via `openline_wallet.crypto`. Receipt-gate
was inspected; its ancestry closure is inapplicable to artifacts that never
crossed a commit boundary (recorded in preregistration as the analyzed gap,
not a defect claim).

## Was there a real hole?

Yes — in the naive composition. The baseline deferred executor (integrity +
presenter validity + creation-time validity only) COMMITted the A-origin
artifact AFTER A's revocation (1 effect on the naive T5 ledger). Current
production machinery evaluates the presenter's standing, not the artifact's
causal origin, so a trusted scheduler presenting under its own valid mandate
would execute stale authority. The treatment (bound lineage evaluated at
execution time against the wallet's current revocation state) closed it.

## Results (single frozen run, deterministic)

- Pre-revocation control (T2, A valid): naive COMMIT, treatment COMMIT.
  The artifact represents legitimate deferred work under both paths.
- Post-revocation direct (T5, A revoked at T4): naive COMMIT — hole
  demonstrated (1 effect). Treatment: STOPPED / ORIGIN_REVOKED, 0 effects.
- Transformed (T6, B wraps X-002 -> Y-001, origin byte-preserved, C
  presents): treatment STOPPED / ORIGIN_REVOKED, 0 effects. Transformation
  did NOT erase the revoked origin; no string matching was used (structured
  signed origin binding -> wallet timeline lookup).
- Stripped variant (Y-002, origin removed by transformer): treatment
  STOPPED / ARTIFACT_TAMPERED, 0 effects. Note: the sealed expectation
  guessed ORIGIN_UNBOUND; the observed reason is ARTIFACT_TAMPERED because
  removing the origin block breaks A's signature over the body, so the
  artifact no longer authenticates against the wallet-pinned key. Fail-closed
  either way; this arm was unscored and does not affect the verdict. The
  origin binding is cryptographically entangled with authenticity.
- Fresh successor (D granted at T7, Z-001 created at T8, presented at T9):
  naive COMMIT, treatment COMMIT (1 effect). Deferred work is not killed
  globally; stale A-origin and fresh D-origin are distinguished.
- A-origin post-revocation effects on treatment ledgers: ZERO.
- Historical artifacts: all five frozen artifact files byte-identical at end
  (hashes match); wallet event log append-only, no rewrites.

## Code

- boundary.py: 53 AST statements (ceiling 150). fixture.py / run.py /
  evidence.py excluded as fixture/test/serialization per the work order.
- No scheduler, queue service, provenance DB, or general auth system built.

## Hashes

- PREREGISTRATION.md: `6a179df35b660166da50d4c0f0f50d5c821d69ec981cadc2b5456702ae4029ff`
- PRECONTACT_SEAL.md: `07bb2fdc91298412f7010da8dba2429fabd98a9761429e542e324f84df7d328b`
- RESULT.json: `7baa8682ac79023c4d417a2219bdd3933abd3bc187d6d8004a5be73f6c8fa1df`
- boundary.py: `b103345197927745bcb3d21def1301f3bfc88689afbd09ca04dabe7abf8a9b94`
- Apparatus (fixture/run/evidence) hashes in PREREGISTRATION.md.

## Spend

- Model calls: 0. Spend: $0.00. Frozen deterministic artifacts; no LLM.

## Confirmations

- Single execution; no rerun, no tuning after contact, no rescue.
- Nothing merged to any production repo; nothing published.
- Prior FIRE-AI / SENTRY / CONTAINMENT / RECOVERY evidence untouched.
- CONTAINMENT not reopened; FIRE-AI untouched; no new SENTRY experiment;
  no workflow engine built.
- Claim ceiling (frozen): "In one bounded deferred-execution fixture, an
  artifact created while Worker A was authorized did not retain standing to
  cause a new protected consequence after A was revoked. Transforming the
  artifact through trusted intermediaries did not erase the revoked origin,
  while an equivalent artifact created under fresh successor authority
  remained executable."
