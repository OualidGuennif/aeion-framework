# Final global review

Edition 0.4.0 · 11 November 2026. The fourth review describes edition 0.3.1 and the section after it edition 0.4.0. The sections below those describe edition 0.3.0 and are kept as written, except where marked.

## Verdict

**Suitable as a design handoff and local reference package for a small implementation pilot. Not a completed specification engine or an autonomous execution authority.**

The useful core is explicit requirements, stable IDs, typed links, named decisions and evidence tied to revisions. Those mechanisms are worth testing on a real change. Generality, lower maintenance cost and reliability at scale remain hypotheses.

This review checked contracts against schemas, reference data, checker behavior, test receipts and distribution artifacts. It used isolated fault injection, ordering checks and direct calculations rather than treating previous green reports as proof. It is a third review by the same assistant, not an independent external assessment.

## Fourth review

11 November 2026. A fourth pass by an assistant, again not an independent external assessment. It read every contract, schema, fixture and QA program, mutated the reference ledger against each stated rule, and compared the contracts with the engine that aeion-factory 3.0.0 built from them. That engine is separate code by a separate implementation effort; it is used here as a cross-check, not as an authority.

### Stated rules that nothing checked

Each row is a rule already in the contracts. Before correction the reference checks accepted a ledger that broke it; the [before-correction probes](review/probes-review4-before.json) record that.

| Rule | Accepted before correction | Diagnostic now |
|---|---|---|
| AX-G-007 | A test citing scenarios that illustrate none of the requirements it verifies; **twelve such references in the shipped example** | SCENARIO_NOT_ILLUSTRATING |
| AX-G-003 | A must requirement whose only goal is draft; a constraint whose only requirement is draft; a product baseline with no active goal | REQUIREMENT_PROVENANCE, UNLINKED_CONSTRAINT, EMPTY_BASELINE |
| AX-M-006 | An `event` requirement with no trigger, or any pattern with a field it does not use | PATTERN_FIELDS |
| AX-C-013 | A reversed or empty effective window; a bound with a non-UTC offset | INVALID_WINDOW |
| AX-M-003 | A transition ID without the `TRN-` prefix | WRONG_PREFIX |
| AX-C-008 | A unit annotation on a missing path or a non-integer; two units for one path | UNIT_ANNOTATION |
| AX-X-002 | A `binding:` locator naming an unknown binding or disagreeing with `binding_id` | UNKNOWN_ASSET_LOCATOR, ASSET_BINDING_MISMATCH |

### Checker defects

| Finding | Before correction | Correction |
|---|---|---|
| Local links were compared through the filesystem | A link whose letter case differs from the file name passed on a case-insensitive disk and breaks on a case-sensitive one | Compare each path component with the directory listing |
| Mutation `add` on an array index | Silently replaced the existing element | `add` creates a new object member only; `replace` and `append` cover the rest |

### Worked example

- Removed the twelve scenario references above. The tests keep the scenarios that do illustrate their requirements; TEST-013 keeps none, because no audit scenario exists.
- Removed 25 `uses_term` links. All seven requirements were linked to all five terms with one shared rationale, so a context closure for any requirement returned the whole vocabulary. Ten links remain, each to a term the requirement's wording relies on.
- REQ-007 (audit output without credentials) was linked to the capacity goal to satisfy AX-G-003. It now satisfies a new GOAL-003 about non-disclosure.
- The canonical digest changed to `af5192c2...`; the CROA sidecar pins the new value. Node and edge positions used by the conformance vectors are unchanged.

Run on the corrected ledger, the aeion-factory engine computes the same canonical digest, matches all 45 reference expectations, passes G01-G06 and fails G07 on two diagnostics: REQ-003 and REQ-004 have no normal case. Before the correction it reported fourteen.

### Contract changes

Four clarifications where the text was silent and the engine had to choose; each follows the engine's choice and the example already complies:

- AX-C-010: the root expression is at depth 0.
- AX-C-013: a rule outside its window is not evaluated; a required check that depends on it is unknown.
- AX-C-005: a collection is a declared environment array. Literal arrays as collections are left undecided (see below).
- AX-G-007: for a requirement that itself states a refusal, the normal case is a nearby request that must still succeed.

The conformance document also states that a fixture `add` creates a new object member.

One addition, AX-G-005: a terminal state has no outgoing transition and every state is reachable from the initial state. `terminal` was a required field with no stated meaning. The example and three specifications in sibling repositories already satisfy it. This tightens profile `AX-CORE-0.1` without renaming it; an implementation built from 0.3.0 does not check it yet.

### Left open by 0.3.1

Items 1 to 3 were decided in edition 0.4.0, and item 4 was tried there; see the next section.

1. **Literal arrays as collections.** AX-C-003 gives a bound variable "the element type", which a literal array has; the reference evaluator and one QA self-check use a literal collection; the aeion-factory analyzer rejects it. The contract now says a portable specification avoids it. A profile revision should decide.
2. **Binding kinds and node kinds.** AX-M-014 does not say which node kinds a `code`, `test` or `observation` binding may target; only `enforcement` is constrained, through the Constraint that names it. A `test` binding on a Requirement is accepted.
3. **Repeated edges.** Two edges with the same source, relation and target and different IDs are accepted. AX-K-001's sort order tolerates them; no rule says whether they are meaningful.
4. **Behavior over time.** Every scenario is one snapshot evaluated by snapshot predicates. Retry, refusal-without-mutation and recovery need a before and an after. This is why the ledger's remaining G07 gaps cannot be closed by adding links. An environment holding both states, with `observation_assertion` constraints over the pair, would express them inside the current format; it has not been tried.

### Literature check

Google Scholar and arXiv were searched on 10-11 November 2026 for work on specification-driven development, requirement traceability, test oracles and agent context. Ten studies were added to [Foundations](docs/01_FOUNDATIONS.md) as later context, from their abstracts only. The five arXiv links already cited were reloaded and match. No study evaluates this package, and none changes a rule.

## Edition 0.4.0

11 November 2026. This edition acts on the four items the fourth review left open. Format and profile names are unchanged; three rules are tighter.

### Rules decided

| Question | Decision | Diagnostic |
|---|---|---|
| May a literal array be a collection? (AX-C-005) | No. A collection is a declared array reached by a path; a literal array is only the right operand of `in`. The reference evaluator now refuses it, as the aeion-factory analyzer already did. | LITERAL_COLLECTION |
| Which nodes may a binding name? (AX-M-014) | code: Component or Constraint. test: TestCase. enforcement: Constraint or Control. observation: Constraint or Requirement. | WRONG_BINDING_TARGET |
| Is a link declared twice meaningful? (AX-M-010) | No. One source, relation and target is declared once. | DUPLICATE_EDGE |

The 216 bindings and all edges of the worked example and of three specifications in sibling repositories already comply: every code binding names a Component, every test binding a TestCase, every enforcement binding a Constraint, and no link is repeated. The observation row and the Control and Constraint-method targets are not exercised by any of them.

### Before/after scenarios

The reference ledger gains ENV-002, which holds the ledger before and after one reservation attempt with the request and its outcome, two `observation_assertion` constraints over that pair, and eight scenarios, three of them counterexamples in which the wrong thing happened. No schema or format change was needed. The [authoring workflow](docs/04_AUTHORING_WORKFLOW.md) describes the pattern.

Writing the predicates exposed two things the snapshot scenarios had hidden:

- **No requirement asked the ledger to admit anything.** All seven requirements were refusals, retries or later transitions, so a ledger refusing every request satisfied them, and the tests that reserve successfully verified nothing. REQ-008 and GOAL-004 state the admission.
- **"Without changing the ledger" was ambiguous.** The environments and the state model carry a `rejected` status, which suggests that a refusal writes a record; REQ-001 says it changes nothing. DEC-002 records the reading the predicate uses and keeps the leftover status visible.

Both are fictional reference decisions, like DEC-001. They are the kind of finding the method is meant to force, and they were found by formalizing, not by review.

TEST-015 and TEST-016 are the normal cases that REQ-003 and REQ-004 lacked. Run on this ledger, the aeion-factory 3.0.0 engine computes the same digest (`1496f052...`), matches all 61 expectations and reports G01-G07 pass, `design_ready: pass`. This package's QA emits no phase status; it checks that the 61 expectations hold and that the two new predicates agree with direct calculations on 200 seeded transitions.

### Still open for the ledger

Cancellation, commitment and audit output have no before/after observation. No requirement covers a command on a record in the wrong state. CON-007 is quadratic and is unknown from 267 rows under the default budget, as CON-004 is at 500. One attempt observed before and after says nothing about two attempts interleaving. All 16 tests are planned and none has run.

### Outside the package

`tools/check_repo.py` applies the package's link, JSON and specification checks to the root README and the playbooks, which the self-contained package QA cannot read. A workflow replays both on every push. The playbooks themselves are unchanged.

## Confirmed findings and corrections

| Finding | Before correction | Correction |
|---|---|---|
| Stale regression evidence could remain apparently current | Tampered receipt hashes or changed checker source still allowed package pass | Required receipt consistency: exact input inventory, digests, toolchain, collected IDs, outcomes and raw output |
| Test replay was not a packaged workflow | Separate commands were documented; the receipt-writing helper was not shipped | run_checks.py replays the suite, writes a local receipt and runs artifact QA |
| Absolute local links passed portability checks | A host-specific absolute link to an internal file was accepted | Require relative local links even when an absolute target currently exists |
| Input/output confinement was too late or incomplete | Symlink checks occurred after loading; error publication could follow unsafe output parents | Check paths before read/write, reject unsafe outputs and retain failing status when a diagnostic cannot be written |
| A manifest could describe different inputs from its checks | Inputs were hashed only after checks | Compare input manifests before and after verification; reject detected changes |
| CROA mappings accepted retired or unrelated references | Retired nodes and a method binding for another component were accepted | Reject retired mappings, flag draft references and require methods to bind the same Constraint |
| Unsupported operational scores could clear a finding | A score without source evidence could yield not_triggered | Preserve declared scores; use unknown for unsupported evidence_record inputs; expose effective scores and basis |

The [before-correction probes](review/probes-review3-before.json) preserve the stale-receipt, portability and CROA cases. Path hardening and source-change detection also have isolated regression tests. These are package defects and contract clarifications, not reports of a deployed-system exploit.

## Evidence now available

The [recorded regression run](review/regression-run.json) contains collected test IDs, outcomes, toolchain and input digests. The checker verifies receipt consistency, not producer authenticity. A party controlling the code and evidence can still fabricate a consistent local receipt.

The suite retains earlier cases and adds:

- stale/incomplete receipts, changed tools, modified raw output and zero/duplicate/skipped test metadata;
- portable links, read/write symlinks and detected source changes;
- selected reference checks under five deterministic order permutations;
- 100 seeded ledger states checked against five direct domain calculations;
- CROA evidence eligibility, retired mappings and method ownership;
- fourth review: one case per stated rule listed above, all eight field combinations of all six requirement patterns, window boundaries, state topology, letter-case links and the `add` mutation.

The 45 hand-authored reference expectations and ten mutation vectors remain separate from the regression-suite count. Thirty future product obligations remain unexecuted. The additional states exercise formulas, not the ledger application.

See [VALIDATION.md](VALIDATION.md), [raw output](review/regression-output.txt) and the [assurance matrix](review/ASSURANCE_MATRIX.md) for current results and scope. The package was copied into a different directory with spaces and the shipped verification command passed there with the same tested code/data input inventory; see the [portability record](review/portability-run.json), repeated for edition 0.3.1. This is a same-platform check, not cross-platform qualification. The final archive and manifest include the resulting evidence records.

## Global design assessment

### Requirements and semantics

The separation between need, structured wording, formal predicate and test oracle is coherent. It prevents formatting quality from being mistaken for business validity. BCIR remains the most expensive design choice: a compiler must qualify types, units, resource bounds and translation semantics. Runtime evaluation order is now explicit; the reference interpreter is still not a qualified general compiler.

Compare reusable modeling/constraint tools with BCIR before S2. A new language need not precede a useful traceability prototype.

### Graph retrieval

A deterministic graph retrieves declared obligations reproducibly. It cannot establish that declarations capture every dependency. Conservative closure and explicit unmapped changes are appropriate safeguards. No query engine or extraction coverage is qualified here. Measure omissions as well as retrieval speed; structure has a maintenance cost.

### Authority and autonomy

Execution cadence and decision authority remain separate. Bounded_autonomous does not authenticate an actor, authorize a tool or replace a scoped policy. The example has no verified policy digest. Task-packet, enforcement and authority adapters still need implementation before the declaration can govern an autonomous run.

### CROA compatibility

The optional sidecar carries selected readiness inputs and evidence links, with pinned sources, unknown answers and declared/effective scoring. It is not a complete normative inventory or deployed-system assessment. Weighted scores and maturity remain uncomputed without the companion workbook. A passing formula is not a CROA permit decision.

## Remaining blockers to stronger claims

1. **Ledger design readiness:** authorized-access, retry, invalid-transition and recovery cases need full behavioral oracles. Its 14 application tests remain planned. No design_ready status is emitted. *(0.4.0: authorized access, retry, refusal, conflict and denial now have scenarios and predicates; an external engine reports design_ready for the declared model. Invalid transitions still have no requirement, and the 16 tests remain planned.)*
2. **Evaluation cost:** CON-004 is quadratic and exhausts the reference budget at 500 rows although the environment admits 1,000. This remains unknown, not pass. Qualify the algorithm and its declared budget together before claiming the full bound.
3. **Engine implementation:** complete static analysis, graph/query APIs, real binding resolution, product runners, trusted identity and operational evidence are absent from this package. The matrix lists gaps per gate. *(0.3.1: aeion-factory 3.0.0 implements G01-G07, graph queries, context packets and one test adapter outside this package; it reports identity, policy and runtime observation as unsupported. This package does not qualify it.)*
4. **External validity:** no independent assessor or comparative study establishes generality or scale benefits. *(0.3.1: aeion-factory carries a second domain as a field test, a holiday planner built by a coding agent against a checked specification. It is the authors' own demonstration, not a comparative study.)*

These are qualification work, not problems solved by another editorial review.

## Next step

Build one small vertical slice: a structured requirement, terms and constraint, normal/refusal scenarios, real code/tests and a change that invalidates evidence. Retrieve its obligations through a simple declared graph. Measure useful defects, omissions and maintenance effort against a lightweight baseline before adding infrastructure.

The package supports that experiment. The experiment must earn stronger claims.
