# Implementation plan

## Target

A local CLI validates a specification, explains failures, generates reading views and answers bounded queries. Product commands named `axiom` are proposed interfaces. The shipped `qa/` programs verify this package and selected reference behavior, not the product engine.

Inspect an existing repository before choosing a stack. For greenfield work, Python 3.12+, standard-library modules and an established JSON Schema validator are a reasonable starting point. Package QA pins its own dependencies separately. Add SQLite only for a measured indexing need.

## Increments

| Increment | Deliverable | Acceptance |
|---|---|---|
| S0 | Applicable contracts and unresolved disagreements | No hidden contract conflict |
| S1 | Strict parsing, schema, IDs, references and dependency cycles | Positive and targeted negative cases |
| S2 | BCIR analysis/evaluation, units, bounds and diagnostics | Defined semantics and qualified cases |
| S3 | G04-G07, state topology, decisions and verification plan | No false design readiness |
| S4 | Reproducible views, graph snapshots and bounded queries | Stable output and explicit coverage limits |
| S5 | Change packets, execution declarations, context closure and bindings | Required rules cannot disappear for budget reasons |
| S6 | One real test adapter and evidence freshness checks | Required IDs executed on final inputs |
| S7 | A scoped pilot and applicable conformance corpus | Actual results and missing capabilities reported |

Before S2, compare BCIR with existing tools on three real rules: units, duplicate-preserving collections and an admission guard. Record the choice. An exploratory declared graph can already be useful after S1, with semantic checks visibly unqualified. Do not require a complete new language before demonstrating any value.

Identity/authority adapters start unavailable. A high-risk phase requiring them remains unknown. Likewise, validating an execution-mode declaration is not authorization, and validating CROA readiness inputs is not deployed-system assessment.

## Proposed CLI

```text
axiom validate --spec spec.json --phase design --report validation/report.json
axiom evaluate --spec spec.json --observations observations.json
axiom graph --spec spec.json --output generated/
axiom query requirement --id REQ-001 --snapshot <digest>
axiom packet --change change.json --principal <trusted-principal> --budget-bytes 32768
axiom check-evidence --spec spec.json --manifest evidence/manifest.json
```

Stabilize production schemas for changes, query responses, cursors and receipts in the increment that implements them. The fixture observation format is not an already-qualified integration protocol.

Proposed exit codes: 0 phase passed, 2 failed, 3 unknown, 4 input/processing error. A non-applicable isolated check does not pass a phase. Keep full diagnostics.

### AX-I-001 — Parser boundary

Bound bytes before loading; reject duplicate keys, unsafe numbers, invalid Unicode, unknown fields and excessive nesting. Report input errors without exposing secrets. Reject unsupported external schema references. Use iterative algorithms where valid graph size can exceed runtime recursion depth.

### AX-I-002 — Closed evaluator

Evaluate a typed AST, not code strings. Analyze before execution, bound collections and nested work, and distinguish invalid input, missing data and exhausted budget. Do not use favorable short-circuiting to hide a static error.

### AX-I-003 — Reproducible publication

Fixed inputs and versions produce identical deterministic bytes. Generate, validate and publish a new snapshot atomically. Do not put wall-clock values into hashed normative content or modify canonical input during a read command.

### AX-I-004 — Advertised capabilities

Expose actual operators, languages, analyzers, model exploration, runners and trust integrations. Names in configuration are not installation or qualification evidence.

## Verification priorities

Test dangerous boundaries: duplicate keys, broken references, deep valid dependency chains, Boolean/integer coercion, unit mismatch, duplicate-preserving sums, vacuity, budgets, partial context, escaping paths, stale evidence and interrupted publication. Add differential checks only with a genuinely useful independent oracle.

Start with the fictional ledger, then a small second domain such as document access and revocation. Define a comparison protocol before claiming faster retrieval or better defect detection. Keep failure cases and maintenance effort.

Defer web editors, orchestration platforms, normative vector search, autonomous rule inference and subtle incremental caches until they solve an observed problem. Deliver the smallest demonstrable capability per increment.
