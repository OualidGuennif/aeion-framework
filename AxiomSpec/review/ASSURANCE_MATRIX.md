# Assurance matrix

This is a manual scope map, not a product-gate report. Package pass means the listed local checks succeeded on recorded inputs.

| Gate | Implemented here | Still required for a product engine |
|---|---|---|
| G01 parsing/schema | Strict local loader, schema library, guards and reference fixtures | Qualify the production CLI and profiles across supported inputs |
| G02 references | Selected ID/prefix/edge checks, active link targets, binding targets, repeated edges, asset locators, iterative cycle detection, flag declarations and removal targets, release declaration | Complete all normative semantic/applicability conditions |
| G03 static semantics | Runtime checks in a reference subset; unit-annotation targets, effective-window shape and path-only collections | Complete BCIR type/unit analysis and qualified methods |
| G04 authoring/decisions | Shape fields, templates, requirement-pattern consistency, weight range and risk band, flag on optional requirements | Blocking decisions and assumption semantics |
| G05 state models | State/transition/guard references, terminal states and topological reachability | Executable effects before simulation or exploration claims |
| G06 scenarios | 26 observations/79 expectations, seventeen of them before/after pairs; 100 seeded states and 200 seeded transitions in tests | General processing with qualified applicability and semantics |
| G07 test plan | Declared links, scenario-to-requirement agreement and a test in each flag state for a flagged must requirement | Required normal/negative/integration cases by risk, complete behavioral scenarios and oracles |
| G08 context | Contract and closure algorithm | Engine, access control, pagination and omission tests |
| G09 bindings/impact | Lexical checks; for the example, Python symbols resolved by parsing and every TestCase bound | Resolution for other languages, coverage, call relationships and unmapped-change handling |
| G10 product tests | The example's 32 tests executed on local SQLite with a receipt bound to its inputs | Runner adapters, other stores, isolation and a trusted producer |
| G11 evidence | Local receipt consistency, hashes and detected-change checks | Independent producer/storage and product freshness qualification |
| G12 authority | Explicit untrusted-local mode | Authenticated actors, trusted policy and scoped authorization |
| G13 operation | No operational observations | Actual traces, coverage, timing and runtime checks |
| G14 release | Reference comparison: identity and revision rules, classification by ID, recorded overrides, version step, change risk score | Qualification on real release histories; product-level API and data compatibility |

## Available claims

- Replay package checks with `python3 qa/run_checks.py`.
- Selected reference data satisfy their declared expectations.
- Covered metadata inconsistencies are detected.
- CROA input structure and selected red-flag calculations are available with explicit evidence limits.
- The example's test cases were executed on the recorded inputs and its required bindings resolve.
- Release 1.1.0 of the example is a valid minor step after release 1.0.0 under the reference comparison.

## Unavailable claims

No product design_ready, coding_packet_ready, implementation_accepted, runtime_conformance_observed or release authorization is established. No CROA level, authenticated autonomy or complete code-dependency graph is established.

## Trust boundary

A digest establishes byte identity. A consistent receipt establishes agreement among local fields and current files. Neither establishes producer honesty, requirement completeness, sound abstraction or correctness of an untested deployment. Current evidence is local and untrusted.

The source-change guard assumes a stable single-writer workflow. It detects observed manifest changes, not every adversarial intermediate mutation. Writes are individually atomic; consumers verify complete manifests/configuration before combining outputs.
