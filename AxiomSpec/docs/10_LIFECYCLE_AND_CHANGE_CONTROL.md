# Lifecycle and change control

### AX-L-001 — Identity and revision

An ID denotes a stable concept. Increment revision when normative content changes. A new incompatible meaning needs a new ID and explicit migration. Draft/active/retired describe the model, not authenticated approval. Keep historical retired objects; never reuse their IDs.

## Change request

Record problem, baseline, intended observable result, affected requirements/files, exclusions, material decisions, risk, compatibility, tests and recovery where relevant. Distinguish additions, retirement, wording, unit/domain changes, constraints, relationships, bindings and policy. Text diff alone does not establish business impact.

### AX-L-002 — Fixed baseline

Bind work to baseline and candidate digests. Rebase or reject an application if the source changed. A local revision counter is not compare-and-swap. A single writer and atomic local replacement may be sufficient initially; qualify the actual mechanism rather than introducing distributed transactions.

## Responsibilities

| Phase | Output | Authority question |
|---|---|---|
| Explore | Sources and alternatives | Who supplied the need? |
| Clarify | Terms and decisions | Who may decide consequences? |
| Design | Model and verification plan | Which checks does policy require? |
| Implement | Code and tests | What scope and tools are authorized? |
| Accept | Evidence and residual decisions | Who accepts the remaining risk? |
| Operate | Observations and incidents | Who may revise the contract? |

One author can contribute to multiple phases. Policy determines any required separation. Autonomous execution concerns cadence, not authority; retain the task's execution declaration and policy digest with each change packet.

### AX-L-003 — Trusted policy controls exemptions

Policy defines required gates, risk floors, rights, runners and decision authority. A specification may propose classification but cannot waive its own obligations. Policy changes require their own authorized process. Local unauthenticated mode cannot establish real identities from names.

### AX-L-004 — Conservative invalidation

Canonical changes invalidate product acceptance evidence. Code, tests, environment, policy and tool changes invalidate dependent results; use global invalidation when dependency coverage is not qualified. Matching inputs and acceptable observation age are separate requirements. A cache is an optimization, never authority.

### AX-L-005 — Declared migrations

Reject or report unsupported format versions. Never silently discard unknown fields. State source/target versions, transformations and decisions that cannot be automated. Preserve the source, produce a candidate, show the diff and rerun checks.

A structural migration does not decide a new business policy. API compatibility, data migration, mixed-version operation and rollback are product requirements to verify separately.

## Publication and recovery

Generate product views in a new immutable snapshot, verify its manifest and atomically switch the published pointer. Interrupted generation retains the last complete snapshot. Returning to an old version requires compatible specification, code, policy and data, not just restored Markdown.

A recovery journal retains change ID, baselines, completed work, actual commands, stale evidence and next action. It is navigation evidence, not self-authentication.

An emergency process must already be defined by policy with authority, scope, retained checks, accepted gaps, duration and follow-up. An urgent issue does not create an exemption. Record exceptions as exceptions rather than passed original checks.
