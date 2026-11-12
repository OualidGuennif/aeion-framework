# Gates and evidence

Checks concern a specification baseline, change, implementation or runtime window. Package QA is a separate scope. The [report schema](../schemas/report.schema.json) defines shape, not producer trust or complete gate semantics.

## Gate registry

| Gate | Subject |
|---|---|
| G01 | Strict parser and artifact schema |
| G02 | IDs, references, typed relationships and retirement |
| G03 | BCIR operators, scope, types, units and bounds |
| G04 | Authoring patterns, decisions and assumptions |
| G05 | State-model topology and declared executable capabilities |
| G06 | Reference scenarios and expected predicate outcomes |
| G07 | Test plan, scenarios, oracles and traceability |
| G08 | Context admission, rights, completeness and freshness |
| G09 | Bindings and coverage of the proposed change |
| G10 | Tests actually executed |
| G11 | Evidence integrity and freshness |
| G12 | Approvals the governing release's policy requires |
| G13 | Runtime observations in a stated window |
| G14 | Release comparison with the named baseline: identity, classification, version step |

Diagnostics have stable codes, subjects, JSON Pointers and explanations. Version code meanings independently of explanation wording.

### AX-G-001 — Aggregation

For required checks: error dominates fail, which dominates unknown, which dominates pass. Keep every diagnostic. Required unexecuted checks are unknown. `not_applicable` is permitted only for a non-required check with a verifiable reason; it is not a passed test.

### AX-G-002 — Capability is not result

Expose supported capabilities. Missing language resolution, identity, solver or test adapters cannot be silently skipped when required. A configured adapter name does not prove installation or qualification.

## Phase outputs

| Output | Minimum conditions |
|---|---|
| design_ready | G01-G07 pass; blocking decisions answered and assumptions validated; G14 pass when the release names a previous baseline |
| coding_packet_ready | design_ready, G08, G09 for existing sources, G12 for the release |
| implementation_accepted | Applicable G01-G12, resolved required bindings, fresh executed test evidence |
| runtime_conformance_observed | G13 for specified traces and window |

A first release has nothing to compare: G14 is then not required and reports not_applicable with that reason. When `release.previous` is set, G14 is required, and it is unknown until the named baseline is supplied.

Greenfield coding packets may retain explicitly planned bindings. They cannot claim accepted implementation. Design readiness does not authenticate business approval. The core emits no `release_authorized` status.

### AX-G-003 — References

An active must requirement satisfies an active goal. Active requirements have sources; active constraints formalize active requirements. Validate unique IDs, reserved prefixes and typed edges. A product baseline needs at least one active goal and requirement.

Unit references target Terms. State guards are Boolean BCIR constraints in the model's environment, not review protocols. Never repair an ID by choosing a similar name.

A requirement or test names only declared flags; a flag has a declared owner, governs at least one requirement and is not past its removal target. A release that names a baseline is one version step after it, and each compatibility entry rests on an active answered Decision (AX-M-017, AX-M-019).

### AX-G-004 — Decisions and assumptions

A blocking active Decision with null answer prevents design readiness. So does a blocking Assumption not validated. A weight lies within 1 to 100 points in the declared units and the risk label is its band (AX-M-018). AI proposals do not become confirmed answers through silence. Authenticated authority is checked separately by G12.

### AX-G-005 — State models

Require existing initial state, unique state names and transition IDs, valid endpoints and compatible guards. A terminal state has no outgoing transition, and every state is reachable from the initial state along declared transitions. Topological reachability ignores guard feasibility: a reachable state in the drawing may still be unreachable in behavior. Simulation, determinization and exhaustive exploration are additional capabilities; descriptive effects do not support those claims.

### AX-G-006 — Scenarios

Validate given data against its environment and referenced expectations against compatible constraints. A witness cannot violate an applicable hard invariant. A counterexample may intentionally expect false: detecting it validates the reference check, not the business state. A correct refusal may be a witness with a false guard.

### AX-G-007 — Verification plan

Each active must requirement has an active TestCase with an explicit oracle. High/critical requirements need normal and negative behavior cases, plus integration or E2E verification appropriate to the behavior. Policy adds relevant concurrency, authorization and recovery obligations.

An active must requirement behind a flag has an active TestCase with the flag enabled and another with it disabled.

`TestCase.negative` distinguishes normal cases from refusal/violation cases. For a requirement that itself states a refusal (pattern `unwanted`), the negative case is the trigger firing and the normal case is a nearby admissible request that must still succeed; a refusal rule tested only by refusals does not show that it refuses the right requests. Its referenced scenarios must illustrate the requirement being verified. `Scenario.intent` is a different axis: admissible state or counterexample. A shared link or snapshot alone does not establish a meaningful retry/recovery oracle. This gate checks the plan; G10 checks real execution.

### AX-G-008 — Digests

Hash validated canonical JSON as UTF-8, without BOM or final newline. Sort ASCII object keys, preserve array order, use minimal decimal safe integers and lowercase true/false/null. Preserve scalar Unicode without normalization.

Escape quotes and backslashes. Use short JSON escapes for U+0008/0009/000A/000C/000D, lowercase `\u00xx` for other U+0000-001F controls, and direct UTF-8 for remaining scalars, including `/` and U+2028/2029. This is a restricted profile, not a general JCS implementation.

Source-tree digests use a sorted explicit manifest of relevant paths and byte digests, including relevant untracked files. Exclude generated views and evidence to avoid circularity. A commit ID alone does not identify a dirty working tree. Also record policy, toolchain, observations and normalized configuration. Required unknown digests block acceptance.

### AX-G-009 — Deterministic body and execution envelope

Sort checks and retain subjects, statuses, digests and limits in the deterministic body. Attempt, timestamp, duration and host belong to execution metadata. Different durations do not imply different deterministic results.

### AX-G-010 — Evidence answers a specific question

A test receipt identifies executed test IDs, level, authorized command/adapter, runner/version, environment, input digests, case count, result and hashed raw output. Distinguish absent, unexecuted, failed, partial, stale and untrusted evidence. An interrupted report is not a successful global result.

### AX-G-011 — Producer trust

A JSON receipt can be fabricated when its author controls the evidence store. High-risk acceptance needs the independent runner, storage or attestation required by policy. Use `untrusted_local` until that boundary exists. Local hashing does not establish producer identity.

### AX-G-012 — Report envelope

Require profile, requested_phase, available_capabilities, unsupported_capabilities and configuration reference, plus subjects and checks. Capability lists cannot overlap. Configuration points to normalized options by byte digest; required missing configuration remains unknown.

| Scope | Requested phase |
|---|---|
| package | package |
| baseline | design_ready |
| change | coding_packet_ready |
| implementation | implementation_accepted |
| runtime | runtime_conformance_observed |

Semantic validation enforces these combinations and aggregation. Report 0.4 names profile `AX-CORE-0.3`; it reports on specifications in format 0.3. Regenerate an older report from real inputs rather than edit its version.

### AX-G-013 — Release comparison

G14 takes a candidate and the baseline it names and applies AX-L-006 to AX-L-008. Its report gives every changed ID with its level and reasons, the errors, the required and declared steps and the change risk score. It fails on an identity or revision error, an unacknowledged breaking candidate, an unused compatibility entry or a version step that is too small. The score is reported next to the result and has no part in it.

### AX-G-014 — Approval verification

G12 takes a release, the approvals offered for it and the baseline it names. It uses no clock, no network and no shared service.

1. **What governs.** The baseline's `approval` and `actors` govern the release that succeeds it. A first release governs itself. A key added by a release cannot approve that release, and a key removed by a release no longer approves the next one, while every earlier release it approved still verifies. The order of releases replaces time.
2. **What is signed.** Each approval is a signature over one statement: the project, the version, the canonical digest of the release, the actor, the key and its method. An approval of other content, of another release or for another actor does not verify.
3. **What is required.** The low band applies to every release. Each requirement the release reaches (AX-L-009) adds its band; a first release reaches every active requirement. A change to the actors, the policy or the keys adds all four bands.
4. **What counts.** For each required band, the distinct actors with a valid approval through a method that band accepts. One person approving by two methods is one approver.

The result is pass when every required band has its number, fail when one has not, and unknown when the governing baseline was not supplied. An approval that does not verify is set aside and reported. It never invalidates the approvals that do, so a damaged or hostile file cannot block a release that has its approvers.

Approvals are a set. They can be made in any order, on separate devices and at separate times, and files of approvals for one release merge by union. The union keeps every distinct approval. It never chooses between two approvals of the same actor and key, because a merge cannot tell which of them verifies: a forged approval that replaced a valid one would block the release. An approver is counted once, however many approvals name them.

A pass says the declared keys signed. It does not say who held them, and trust in a first release comes from pinning its digest, not from this gate. Design readiness still does not authenticate business approval; `coding_packet_ready` is the first output that requires G12.

## Invalidation

Invalidate product evidence on canonical changes. Source, test, environment, runner or policy changes also invalidate dependent results. Start with conservative global invalidation; qualify dependency closure before optimizing it. Time-limited observations additionally require explicit freshness checks. Neither a recent timestamp nor an identical stale observation is sufficient.

Authors cannot remove a required gate or convert unknown into a non-blocking warning to obtain success. Soft preferences never compensate for a hard violation. Execution mode does not waive G08-G12. CROA readiness is a separate optional evidence mapping, not another name for these phases.
