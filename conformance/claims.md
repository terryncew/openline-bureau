# Claim taxonomy (v0.1)

Every claim lists the *minimum* evidence it requires. A valid
receipt may support only one or two claims. Claims not supported
by a receipt's evidence are reported as NOT ESTABLISHED, never assumed.

This file is generated from `bureau/conformance.py` CLAIM_DEFS;
the validator is the source of truth.

## ACTION_ATTEMPT_OBSERVED

The receiver records that a specific action was attempted or proposed.

Minimum evidence:
- `action.type`

## RECEIVER_DECISION_OBSERVED

The receiver records a decision outcome on the action (not the effect).

Minimum evidence:
- `decision.outcome in vocabulary`

## EFFECT_OBSERVED

The receiver reports an observed downstream effect (effect.observed=true).

Minimum evidence:
- `effect.observed == true`

## EFFECT_ABSENCE_OBSERVED

The receiver asserts no effect occurred (effect.observed=false). Receiver-attested: the receipt proves the assertion was made, not that absence was independently verified.

Minimum evidence:
- `effect.observed == false`

## CURRENT_AUTHORITY_OBSERVED

The receipt states the authority standing under which the receiver acted.

Minimum evidence:
- `authority.status in vocabulary`

## REVOCATION_OBSERVED

The receipt evidences that an authority was revoked (timestamp or status).

Minimum evidence:
- `authority.revoked_at or authority.status == REVOKED`

## POST_REVOCATION_ATTEMPT_OBSERVED

An action was attempted after revocation: revocation is evidenced, a receiver decision is recorded, and the receipt timestamp is at or after the revocation timestamp.

Minimum evidence:
- `REVOCATION_OBSERVED`
- `decision.outcome`
- `timestamp >= authority.revoked_at`

## REVOCATION_ENFORCEMENT_OBSERVED

Revocation was enforced on a post-revocation attempt: the attempt was refused AND the receiver reports no effect. Effect evidence is required — a refusal without effect evidence does not prove enforcement.

Minimum evidence:
- `POST_REVOCATION_ATTEMPT_OBSERVED`
- `decision.outcome in {STOPPED, DENY}`
- `effect.observed == false`

## SUCCESSOR_AUTHORITY_OBSERVED

A new active authority is evidenced and explicitly linked to a prior authority: either the receipt is a grant event (action.type authority_grant/grant_issued) or extensions names the superseded authority via successor_of. A bare ACTIVE status with parents is not enough — succession must be asserted, not inferred.

Minimum evidence:
- `authority.status == ACTIVE`
- `authority.issued_at`
- `parents non-empty`
- `action.type in {authority_grant, grant_issued} or extensions.successor_of`

## PROVENANCE_CHAIN_OBSERVED

The receipt links into a provenance chain: parent receipts plus a named source system.

Minimum evidence:
- `parents non-empty`
- `provenance.system`

## REPLAY_ATTEMPT_OBSERVED

The receiver reports that an action_id already seen was presented again and handled as a replay.

Minimum evidence:
- `action.action_id`
- `decision.outcome in {STOPPED, DENY, QUARANTINE}`
- `decision.reason indicates replay`

## STALE_ARTIFACT_ATTEMPT_OBSERVED

An artifact whose origin authority is no longer current was presented and refused. Artifact reference lives in extensions so the core stays vendor-neutral.

Minimum evidence:
- `extensions.stale_artifact.artifact_id`
- `authority.status in {REVOKED, SUPERSEDED}`
- `decision.outcome in {STOPPED, DENY}`

## RECOVERY_CONTINUATION_OBSERVED

A successor authority continued the work: successor authority explicitly evidenced (see SUCCESSOR_AUTHORITY_OBSERVED) plus a COMMIT decision under it.

Minimum evidence:
- `SUCCESSOR_AUTHORITY_OBSERVED`
- `decision.outcome == COMMIT`

## Controlled vocabularies

`decision.outcome`: COMMIT, DENY, OBSERVED, QUARANTINE, STOPPED

`authority.status`: ACTIVE, EXPIRED, NARROWED, NO_MANDATE, REVOKED, SUPERSEDED, UNKNOWN

## Cross-claim discipline

- A decision outcome is not an effect. `DENY` without `effect`
  evidence supports RECEIVER_DECISION_OBSERVED only.
- A revocation timestamp without enforcement evidence does not
  prove propagation; REVOCATION_ENFORCEMENT_OBSERVED requires an
  explicit `effect.observed == false` on a refused post-revocation attempt.
- Artifact provenance without current origin standing does not prove
  current authorization; STALE_ARTIFACT_ATTEMPT_OBSERVED requires
  the authority to be terminal (REVOKED or SUPERSEDED) plus refusal.
- Actor identity without an authority record does not prove permission;
  there is no claim for 'actor was permitted' from identity alone.
- `effect.observed == false` is receiver-attested: the receipt proves
  the assertion was made, not that absence was independently verified.
- Succession must be asserted, not inferred: SUCCESSOR_AUTHORITY_OBSERVED
  requires a grant event or `extensions.successor_of`, not just an
  ACTIVE status with parents.