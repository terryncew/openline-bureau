# TRUST-HANDOFF-001 — PREREGISTRATION (frozen 2026-09-18, pre-contact)

## Scientific question

Can a consequence artifact created while Worker A was authorized produce a
new receiver-controlled effect after A is revoked, either directly or after
transformation by trusted intermediaries?

## Stage 0 result (inspection, read-only, no production code modified)

- Wallet origin/main: `687bf0d8fe2158969fcecb5c2522d8d8908856dd`
- Receipt-gate origin/main: `9c06dfd62b0e42de927899b9538ab675067390cd`
- `ReferenceGate.evaluate` / `EffectGate._standing` revalidate the
  PRESENTER's mandate at consequence time (MANDATE_REVOKED stops a revoked
  presenter; proven by existing tests + WALLET-EFFECT-CLOSURE-001).
- Receipt-gate `olp_gate/ancestry.py` propagates standing loss only along
  receiver-recorded BASIS_FOR edges; edges are created solely by
  `record_commit` at the commit boundary, and `assess_untrusted_edge`
  explicitly rejects producer assertions.
- STOLEN-AUTHORITY-001 subject-binding stops B presenting AS A; it does not
  stop B presenting under B's own mandate.
- **Gap found (not already proved end-to-end):** an artifact X created by A
  while valid that never crosses the receiver commit boundary (no admission,
  no receipt, no ancestry edge), later presented by trusted B under B's own
  valid standing after A is revoked. Current machinery evaluates the
  presenter's standing only; the artifact's causal origin is never tracked.
- Receipt-gate ancestry is inapplicable to never-committed artifacts
  (documented, not a defect claim). No honest baseline exposure exists in
  current code that blocks the B-presents-under-own-standing case, so this
  experiment is NOT already proved. Proceeding to fixture.

## Bound inputs

- Wallet main SHA: `687bf0d8fe2158969fcecb5c2522d8d8908856dd`
- Receipt-gate main SHA: `9c06dfd62b0e42de927899b9538ab675067390cd` (inspected; no reusable primitive for never-committed artifacts)
- Reused production primitives (wallet, pinned main, read-only worktree
  `build/wallet-main`): `Wallet.create/grant/revoke/export_bundle/timeline`,
  `ReferenceGate(pin_principal/admit_bundle/issue_challenge/evaluate)`,
  `create_presentation`, ed25519 via `openline_wallet.crypto`.
- Artifact schema: `trust-handoff-001.deferred_artifact.v1`
  `{schema, artifact_id, action, params, origin:{worker_id, mandate_id},
  created_at, creator_sig}` — creator signs canonical body with the subject
  key pinned in the wallet grant; verifier uses the PINNED key, not the
  artifact's self-assertion.
- Transformed schema: `trust-handoff-001.transformed_artifact.v1`
  `{schema, artifact_id, transformer_id, transformed_at, normalizations,
  wrapped_artifact (inner body byte-preserved), wrapped_sig}`.

## Roles (exact)

- Owner: issues/revokes mandates via the wallet; admits bundles at the receiver.
- A (`worker-a`, `mandate-a`, scopes `["update_case"]`): worker, revoked at T4.
- B (`scheduler-b`, `mandate-b`, scopes `["execute_deferred"]`): trusted
  transformer/scheduler; presents artifacts to the receiver via the real gate.
- C: the receiver = `ReferenceGate("trust-handoff-001-receiver")` + one fake
  append-only effect ledger per path/phase.
- D (`worker-d`, `mandate-d`, scopes `["update_case"]`): fresh successor.

## T-sequence (frozen, deterministic clock, BASE 2026-09-18T08:00:00Z)

- T0 (+0s): owner grants mandate-a, mandate-b; receiver admits bundle.
- T1 (+10s): A creates X-001 (signed; creation causes NO protected effect).
- T2 (+20s): CONTROL — B presents X-001 while A valid. Expected: COMMIT
  (naive path and treatment path).
- T3 (+30s): clean ledger reset; A creates equivalent X-002 while valid.
- T4 (+40s): owner revokes mandate-a; receiver admits updated bundle.
- T5 (+50s): B presents X-002. Naive expected: COMMIT (hole demonstrated).
  Treatment expected: STOPPED / ORIGIN_REVOKED, ledger empty.
- T6 (+60s): B transforms X-002 -> Y-001 (normalize/wrap, origin block
  byte-preserved); C presents Y-001. Treatment expected: STOPPED /
  ORIGIN_REVOKED, ledger empty. Cheap hostile variant Y-002 (origin
  stripped): treatment expected STOPPED / ORIGIN_UNBOUND (fail closed).
- T7 (+70s): owner grants mandate-d to D.
- T8 (+80s): D creates Z-001 (origin mandate-d).
- T9 (+90s): B presents Z-001. Expected: COMMIT (naive and treatment).

## Lineage rule (frozen)

A deferred artifact's standing to cause a NEW protected consequence is the
CURRENT standing of its bound origin mandate at execution time, read from the
receiver's latest admitted wallet timeline. Structured binding
(worker_id, mandate_id) inside the signed body — no string matching on notes.
Missing/unverifiable origin -> ORIGIN_UNBOUND, fail closed: trusted
intermediaries cannot mint new authority.

## Decision laws (frozen, boundary.py)

- naive_execute: ARTIFACT_TAMPERED? -> presenter ALLOWED via real
  gate.evaluate? -> mandate ACTIVE at created_at per wallet event history?
  -> COMMIT else STOPPED.
- lineage_execute: ARTIFACT_TAMPERED? -> origin extractable? ->
  current status ACTIVE? -> not expired? -> presenter ALLOWED? -> COMMIT.

## Success/failure criteria (frozen precedence)

- PASS_TRUST_HANDOFF_001_DEFERRED_AUTHORITY_REVOKED iff: T2 naive+ treatment
  COMMIT; T5 treatment STOPPED/ORIGIN_REVOKED with empty ledger;
  transformed Y-001 treatment STOPPED/ORIGIN_REVOKED with empty ledger;
  Y-002 stripped STOPPED/ORIGIN_UNBOUND; D naive+treatment COMMIT;
  all frozen artifacts byte-identical at end.
- FAIL_TRUST_HANDOFF_001_STALE_AUTHORITY_SURVIVES iff T5 treatment COMMITs.
- FAIL_TRUST_HANDOFF_001_TRANSFORM_LAUNDERING iff T5 treatment stops but
  Y-001 treatment COMMITs.
- FAIL_TRUST_HANDOFF_001_SUCCESSOR_BREAKAGE iff D treatment does not COMMIT.
- Else INCOMPLETE_TRUST_HANDOFF_001.

## Code ceiling

- boundary.py: 53 AST statements (ceiling 150). fixture.py / run.py /
  evidence.py excluded as fixture/test/serialization. No scheduler, queue
  service, provenance DB, or new general auth system built.

## Model / spend

- Zero-model default: no LLM invoked; frozen deterministic artifacts.
  model_calls = 0, spend = $0.00.

## Claim ceiling (frozen)

"In one bounded deferred-execution fixture, an artifact created while Worker
A was authorized did not retain standing to cause a new protected consequence
after A was revoked. Transforming the artifact through trusted intermediaries
did not erase the revoked origin, while an equivalent artifact created under
fresh successor authority remained executable."

No claim beyond: arbitrary persistence containment, malware prevention,
sandbox escape, unmanaged schedulers, external credential revocation,
production security certification.

## No-rerun rule

One frozen execution after the seal. No tuning after contact. A failed or
crashed run is recorded as-is; any corrected replication is a new experiment,
not authorized here.

## Apparatus hashes (pre-contact)

- boundary.py: `b103345197927745bcb3d21def1301f3bfc88689afbd09ca04dabe7abf8a9b94`
- fixture.py: `88435837de9482606c57a28653ff88717523a272b84e31a487982d77a5d31c0e`
- run.py: `ca486788876612ad46c0cb2e57c6c814b5699beb5d8f44367dcc85e5fba8355d`
- evidence.py: `2d7787ceca75d8552dade74b6f1c1ea7eed540843879b4079152183f10daeaf1`
