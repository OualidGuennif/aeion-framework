# Assurance matrix

This is a manual scope map, not a product-gate report. Package pass means the listed local checks succeeded on recorded inputs.

| Gate | Implemented here | Still required for a product engine |
|---|---|---|
| G01 parsing/schema | Strict local loader, schema library, guards and reference fixtures | Qualify the production CLI and profiles across supported inputs |
| G02 references | Selected ID/prefix/edge checks, active link targets, asset locators and iterative cycle detection | Complete all normative semantic/applicability conditions |
| G03 static semantics | Runtime checks in a reference subset; unit-annotation targets and effective-window shape | Complete BCIR type/unit analysis and qualified methods |
| G04 authoring/decisions | Shape fields, templates and requirement-pattern consistency | Blocking decisions and assumption semantics |
| G05 state models | State/transition/guard references, terminal states and topological reachability | Executable effects before simulation or exploration claims |
| G06 scenarios | Nine observations/45 expectations; 100 extra seeded states in tests | General processing with qualified applicability and semantics |
| G07 test plan | Declared links, scenario-to-requirement agreement and an incomplete example plan | Required normal/negative/integration cases, complete behavioral scenarios and oracles |
| G08 context | Contract and closure algorithm | Engine, access control, pagination and omission tests |
| G09 bindings/impact | Planned declarations and lexical checks | Real symbol resolution, coverage and unmapped-change handling |
| G10 product tests | Package tests only | Ledger implementation and real runner adapters |
| G11 evidence | Local receipt consistency, hashes and detected-change checks | Independent producer/storage and product freshness qualification |
| G12 authority | Explicit untrusted-local mode | Authenticated actors, trusted policy and scoped authorization |
| G13 operation | No operational observations | Actual traces, coverage, timing and runtime checks |

## Available claims

- Replay package checks with `python3 qa/run_checks.py`.
- Selected reference data satisfy their declared expectations.
- Covered metadata inconsistencies are detected.
- CROA input structure and selected red-flag calculations are available with explicit evidence limits.

## Unavailable claims

No product design_ready, coding_packet_ready, implementation_accepted, runtime_conformance_observed or release authorization is established. No CROA level, authenticated autonomy or complete code-dependency graph is established.

## Trust boundary

A digest establishes byte identity. A consistent receipt establishes agreement among local fields and current files. Neither establishes producer honesty, requirement completeness, sound abstraction or correctness of an untested deployment. Current evidence is local and untrusted.

The source-change guard assumes a stable single-writer workflow. It detects observed manifest changes, not every adversarial intermediate mutation. Writes are individually atomic; consumers verify complete manifests/configuration before combining outputs.
