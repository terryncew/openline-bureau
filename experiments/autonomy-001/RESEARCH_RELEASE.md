# OPENLINE-AUTONOMY-001: public research release

The goal is **“AI that can improve its own work without granting itself more power.”**

This experiment studies the controls needed around that goal. An owner sets a
small task and its boundaries. A worker proposes a change, separate checks
evaluate it, and Receipt Gate authorizes the exact permitted action. The
worker cannot change its own governing policy or authorize more work.

The current demonstration uses a **scripted worker**, not a live AI. It adds
an empty-state message to the review-desk UI and accepts it on a separate
branch in a disposable scratch clone. Passing those checks demonstrates one
bounded coding workflow. It does not establish that software quality improved.

## Reproduce one cycle

Use Linux with Python **3.12+** and its `venv` support, Git, and a working Docker
daemon, as a non-root user with Docker access. Package installation needs
access to GitHub and a package index; the
first run also downloads the digest-pinned Docker image. Run this command from
the Bureau checkout:

```bash
bash experiments/autonomy-001/demo/reproduce.sh
```

The command runs the existing pinned [setup](setup/setup.sh), checks offline
Docker execution, and runs the [single-cycle demo](demo/run-demo.sh). It makes
no model/API call and uses no paid service, hosting or deployment. The untrusted
worker adapter and candidate evaluation run in network-disabled Docker. This
demo's deterministic patcher runs as trusted coordinator code. The checkout's branch and
owner mission remain unchanged; candidate acceptance affects only the scratch
clone.

The command prints a private workspace and a private state directory. Keep
them local: state contains signing keys. The state directory also contains
`demo.log`, `dashboard.html`, `state.json`, signed receipts and Gate evidence.
Do not upload that directory or copy credentials into it. The wrapper refuses
a temporary-directory location inside this checkout and retains its files for
inspection if a step fails. Remove that private workspace yourself when you
have finished reviewing it.

Success prints `Verified: one scripted UI task accepted in the isolated
scratch clone.` A setup or demo failure exits with a nonzero status. A failure
is evidence to investigate, not a successful autonomous improvement.

## What the controls mean

| Situation | Expected result |
|---|---|
| A small authorized change passes the protected tests and holdouts | Receipt Gate can authorize one exact new branch in the scratch clone; a signed receipt records it. |
| A change breaks a checked behavior | Evaluation rejects it; no acceptance branch is created. |
| A worker tries to edit its rules or exceed allowed paths | The proposal is refused or quarantined; it receives no additional authority. |
| The process dies during work | Restart holds unfinished work for review; a completed authorized branch update can be recorded without repeating it. |
| The owner revokes permission | Later branch updates and new work stop. A running sandbox remains subject to its deadline. |

These cases have dedicated regression tests; the one-cycle command above
demonstrates the authorized UI change only. See [PHASE15.md](PHASE15.md) for
the exact test results, fault injections, dependency pins and limitations.

To revoke the private run, substitute the two paths printed by the command:

```bash
/private/workspace/venv/bin/python experiments/autonomy-001/coordinator.py \
    --state-dir /private/state-directory --revoke
```

The stop command records revocation under the same lock used for acceptance.
After it returns, later branch updates cannot pass. It does not undo a change
that completed before revocation.

## What remains unproved

A live coding-agent experiment is blocked by the absence of a safe isolated
authentication route with an established **$0 charge guarantee**. The pinned
container has no live coding agent or model. Host credentials, paid API access
and added worker network access are not substitutes for resolving that blocker.

The source, witness and receiver signing keys are controlled by the local
operator. Their signatures bind the recorded evidence; they are not
independent external attestation. Protected tests and holdouts cover specific
behaviors, and hostile candidate code can still deceive checks. Docker
isolation has not been certified against kernel or container escapes, and
there is no total writable-disk quota or power-loss fault-injection result.

This is experimental research software. No production security, continuous
self-improvement or recursive improvement is claimed. Demonstrating the goal
requires a real coding agent, an independently defined quality measure and
independent evidence of improvement while its authority stays fixed.

