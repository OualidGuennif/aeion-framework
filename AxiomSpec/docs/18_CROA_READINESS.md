# Optional CROA readiness profile

## Purpose

Make specification evidence easy to collect, trace and review against the supplied CROA draft. Keep the core model unchanged. Use the optional [sidecar schema](../schemas/croa-readiness.schema.json) and [illustrative record](../examples/refund-ledger/croa-readiness.json).

This profile checks selected readiness inputs. It is not a CROA implementation, full normative-coverage inventory, official scorecard or conformance assessment.

## Pinned sources

| Source | Identity |
|---|---|
| Framework | CROA Public Review Draft v1.0, editorial identifier `1.0.0-draft.3`, DOI `10.5281/zenodo.21063423` |
| Framework PDF SHA-256 | `75198ad1712c82250c59e534ce82d85c4eedd1db61dd149cf1f36ff0202e4778` |
| Readiness guide PDF SHA-256 | `aaf1efd3b65fdf10361d113bdc670a3fb4f1de0b86920af1739cf8b962755b6a` |

Pin the exact bytes: the framework's cover and publication page use different month labels. The separate six-page readiness guide is a different source. Neither PDF is redistributed in this archive.

Source attribution: The CROA Project, framework public review draft and readiness companion, CC BY 4.0. This profile is an adaptation of selected inputs and reference links, with no endorsement or conformance claim.

## Separate three subjects

1. **Specification quality:** can requirements, constraints, tests and evidence be traced and checked?
2. **Readiness assessment:** what is the current exposure, technical capability and organizational capacity?
3. **Deployment conformance:** does the real governed system satisfy applicable CROA requirements on independent reproducible evidence?

A specification can support the first two. It cannot prove deployed network containment, signature trust, audit integrity, sponsorship or assessor independence.

The sidecar identifies whether its subject is the target product or the authoring agent's execution environment. Never use evidence from one as proof about the other.

## Minimal compatibility data

The sidecar records source hashes, canonical specification digest, project/boundary/action class, consequence class, assessment answers with sources, traceability, framework-section links and selected invariant metadata. It references existing IDs instead of creating a second requirements database.

| CROA concern | Existing AxiomSpec data | Additional declaration or evidence |
|---|---|---|
| Boundary and typed action | Project, actors, components | Scoped action class and operational boundary |
| Requirements traceability | Requirement, Constraint, Component, TestCase edges | RTM export and review |
| Invariant evaluability, §2.6 | Constraint and environment | E1/E2/E3 class, method, abstraction and residuals |
| Trajectories, §4.6.3 | State models and observations | TP-0/TP-W/TP-C/TP-X profile and real projection/aggregation method |
| Consequences, T5 / Appendix K | Risk and decisions | Explicit R0-R4 per action; do not infer from low/medium/high/critical |
| Policy and execution boundary | Controls, bindings and G12 | Real C1-C7 responsibilities, trust boundaries and enforcement tests |
| Evidence, §29.2 | Sources, test plan, bindings and receipts | C-22/23/24/25, C-29 -> C-32, C5 extracts and deployed cross-checks |

These namespaces differ: guide answer E1 is an organizational item, invariant class E1 is an evaluability class, and consequence R4 differs from guide answer R4. Qualify references by their field paths.

Do not infer E2 merely because an expression uses BCIR. Do not infer TP-0 because a check reads one snapshot. A cumulative hazard may need persistent or cross-session analysis. Classifications require reviewed meaning and a qualified method. AQL requirements and deployment prerequisites depend on the actual scoped CROA profile; an execution-mode flag cannot waive them.

## Readiness guide inputs

The guide defines 37 items: A1-A7, B1-B7 and R1-R6 describe Need; D1-D10 and E1-E7 describe Readiness. High Need means high exposure, not better governance. High Readiness means stronger prerequisites.

Each answer stores score, source IDs and note. Scores are integers 0-4. This sidecar preserves unanswered as null rather than silently treating unknown as observed absence. The guide's zero anchor includes unknown; an official-scorecard export would need an explicit conversion while retaining the missing-data flag.

Declared scores are not verified facts. Do not derive A4 from `execution_mode: bounded_autonomous`, D6 from the existence of formulas, or D7 from a planned audit requirement. Organizational items require external evidence. Illustrative records remain labeled illustrative; fixture sources cannot support an evidence_record assessment.

For evidence_record inputs, a scored answer without captured, reviewed source declarations is treated as unknown in finding calculation. Preserve its original number in declared_scores and expose the effective_scores actually used. These are source-reference checks, not authentication of the source or approval of its interpretation. Illustrative examples may calculate from synthetic scores and are labeled accordingly.

## Deterministic checks shipped here

Package QA validates the sidecar's schema, source baseline, specification digest, ID references, score types, classification references and missing inputs. It calculates the guide's 13 red-flag predicates from declared scores using true/false/unknown logic.

| Finding | Trigger | Severity |
|---|---|---|
| CRF-001 | B2 >= 3 AND B3 >= 3 | Critical |
| CRF-002 | R1 >= 3 AND (B1 >= 3 OR B2 >= 3) | Critical |
| CRF-003 | A3 >= 3 AND B3 >= 2 | Critical |
| CRF-004 | B4 >= 3 | High |
| CRF-005 | A2 >= 3 AND B6 >= 3 | High |
| CRF-006 | A4 >= 3 AND B1 >= 3 | High |
| CRF-007 | D4 <= 1 | High |
| CRF-008 | E3 <= 1 OR E4 <= 1 | High |
| CRF-009 | D3 <= 1 | Medium |
| CRF-010 | D5 <= 1 AND A7 >= 2 | Medium |
| CRF-011 | D6 <= 1 | Medium |
| CRF-012 | B5 >= 3 | Medium |
| CRF-013 | A6 >= 3 AND B1 >= 3 | Medium |

AND returns false if any operand is false, otherwise unknown if one is missing. OR returns true if any operand is true, otherwise unknown if one is missing. Unknown is not not_triggered. Thresholds follow guide pages 5-6; regression tests cover their boundaries.

The derived diagnostic file `validation/croa-input-review.json` uses format `axiomspec-croa-input-review/0.2` and reports input completeness, declared/effective scores, finding basis and evidence gaps. The 0.2 version makes the stricter evidence handling explicit; consumers must not silently treat it as the earlier diagnostic format. It always keeps assessment status not_scored and conformance status not_assessed. Completing the input structure does not complete an assessment.

Reject current-snapshot mappings to retired nodes. Draft references remain incomplete. An evaluation-method binding must directly target the referenced Constraint and have kind code, enforcement or observation; an existing binding for an unrelated component is not a method for that constraint. The sidecar schema itself remains `axiomspec-croa-readiness/0.1`.

## Deliberately uncomputed

The companion workbook is not supplied. The guide describes weighted domain scores and a maturity derivation but does not provide the complete weights or formula. Domain totals, Need, Readiness, quadrant and maturity baseline therefore remain uncomputed. Do not invent equal weights or a percentage-to-L0-L5 conversion.

## Path to a real CROA assessment

Use §29.2 to prepare evidence records, then qualify adapters against actual operational sources. Use §27.3 and §29.3 for the complete applicable negative-test battery. Appendix Q's reference cases are examples, not the entire battery. Capture forged/expired/replayed commitments, scope expansion, stale invariants and other applicable refusal paths with real boundary evidence.

Do not use CC_COMPILED alone as proof of execution; the more specific execution-evidence rule in §28.2 identifies EXECUTION_AUTHORIZED. A planned test or declared component cannot establish C5 integrity, C6 enforcement or C7 signature verification.

A passing BCIR predicate is only an input, never a CROA permit decision. A future adapter must preserve unknown/error as non-permission and apply the draft's AMBIGUOUS/fail-deny semantics. Do not translate a successful package-QA result into a runtime authorization.

The supplied framework requires a scoped independent assessment for conformance and distinguishes adoption status from achieved levels. It also says L5 is not independently assessable in this draft. This package emits none of those claims.

The practical result is a specification format that can carry CROA assessment inputs and evidence links. Runtime governance remains an integration with a real deployment.
