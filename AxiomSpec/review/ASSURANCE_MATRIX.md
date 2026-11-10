# Assurance matrix

This is a manual scope map, not a product-gate report. Package pass means the listed local checks succeeded on recorded inputs.

| Gate | Implemented here | Still required for a product engine |
|---|---|---|
| G01 parsing/schema | Strict local loader, schema library, guards and reference fixtures | Qualify the production CLI and profiles across supported inputs |
| G02 references | Selected ID/prefix/edge checks and iterative cycle detection | Complete all normative semantic/applicability conditions |
| G03 static semantics | Runtime checks in a reference subset | Complete BCIR type/unit analysis and qualified methods |
| G04 authoring/decisions | Shape fields and templates | Pattern consistency, blocking decisions and assumption semantics |
| G05 state models | Selected state/transition/guard references | Full topology semantics and executable effects before exploration claims |
| G06 scenarios | Nine observations/45 expectations; 100 extra seeded states in tests | General processing with qualified applicability and semantics |
| G07 test plan | Declared links and an incomplete example plan | Complete behavioral scenarios and oracles |
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
