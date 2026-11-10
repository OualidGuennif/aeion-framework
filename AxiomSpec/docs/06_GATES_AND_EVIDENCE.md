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
| G12 | Policy-required authority and decisions |
| G13 | Runtime observations in a stated window |

Diagnostics have stable codes, subjects, JSON Pointers and explanations. Version code meanings independently of explanation wording.

### AX-G-001 — Aggregation

For required checks: error dominates fail, which dominates unknown, which dominates pass. Keep every diagnostic. Required unexecuted checks are unknown. `not_applicable` is permitted only for a non-required check with a verifiable reason; it is not a passed test.

### AX-G-002 — Capability is not result

Expose supported capabilities. Missing language resolution, identity, solver or test adapters cannot be silently skipped when required. A configured adapter name does not prove installation or qualification.

## Phase outputs

| Output | Minimum conditions |
|---|---|
| design_ready | G01-G07 pass; blocking decisions answered and assumptions validated |
| coding_packet_ready | design_ready, G08, G09 for existing sources, G12 decisions required by policy |
| implementation_accepted | Applicable G01-G12, resolved required bindings, fresh executed test evidence |
| runtime_conformance_observed | G13 for specified traces and window |

Greenfield coding packets may retain explicitly planned bindings. They cannot claim accepted implementation. Design readiness does not authenticate business approval. The core emits no `release_authorized` status.

### AX-G-003 — References

An active must requirement satisfies an active goal. Active requirements have sources; active constraints formalize active requirements. Validate unique IDs, reserved prefixes and typed edges. A product baseline needs at least one active goal and requirement.

Unit references target Terms. State guards are Boolean BCIR constraints in the model's environment, not review protocols. Never repair an ID by choosing a similar name.

### AX-G-004 — Decisions and assumptions

A blocking active Decision with null answer prevents design readiness. So does a blocking Assumption not validated. AI proposals do not become confirmed answers through silence. Authenticated authority is checked separately by G12.

### AX-G-005 — State models

Require existing initial state, unique state names and transition IDs, valid endpoints and compatible guards. Topological reachability ignores guard feasibility. Simulation, determinization and exhaustive exploration are additional capabilities; descriptive effects do not support those claims.

### AX-G-006 — Scenarios

Validate given data against its environment and referenced expectations against compatible constraints. A witness cannot violate an applicable hard invariant. A counterexample may intentionally expect false: detecting it validates the reference check, not the business state. A correct refusal may be a witness with a false guard.

### AX-G-007 — Verification plan

Each active must requirement has an active TestCase with an explicit oracle. High/critical requirements need normal and negative behavior cases, plus integration or E2E verification appropriate to the behavior. Policy adds relevant concurrency, authorization and recovery obligations.

`TestCase.negative` distinguishes normal cases from refusal/violation cases. Its referenced scenarios must illustrate the requirement being verified. `Scenario.intent` is a different axis: admissible state or counterexample. A shared link or snapshot alone does not establish a meaningful retry/recovery oracle. This gate checks the plan; G10 checks real execution.

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

### AX-G-012 — Report envelope 0.2

Require profile, requested_phase, available_capabilities, unsupported_capabilities and configuration reference, plus subjects and checks. Capability lists cannot overlap. Configuration points to normalized options by byte digest; required missing configuration remains unknown.

| Scope | Requested phase |
|---|---|
| package | package |
| baseline | design_ready |
| change | coding_packet_ready |
| implementation | implementation_accepted |
| runtime | runtime_conformance_observed |

Semantic validation enforces these combinations and aggregation. Report 0.1 could not express all required metadata; regenerate it as 0.2 from real inputs rather than invent missing values. The canonical specification format remains 0.1.

## Invalidation

Invalidate product evidence on canonical changes. Source, test, environment, runner or policy changes also invalidate dependent results. Start with conservative global invalidation; qualify dependency closure before optimizing it. Time-limited observations additionally require explicit freshness checks. Neither a recent timestamp nor an identical stale observation is sufficient.

Authors cannot remove a required gate or convert unknown into a non-blocking warning to obtain success. Soft preferences never compensate for a hard violation. Execution mode does not waive G08-G12. CROA readiness is a separate optional evidence mapping, not another name for these phases.
