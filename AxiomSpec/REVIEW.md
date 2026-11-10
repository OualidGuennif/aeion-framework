# Final global review

Edition 0.3.0 · 9 November 2026.

## Verdict

**Suitable as a design handoff and local reference package for a small implementation pilot. Not a completed specification engine or an autonomous execution authority.**

The useful core is explicit requirements, stable IDs, typed links, named decisions and evidence tied to revisions. Those mechanisms are worth testing on a real change. Generality, lower maintenance cost and reliability at scale remain hypotheses.

This review checked contracts against schemas, reference data, checker behavior, test receipts and distribution artifacts. It used isolated fault injection, ordering checks and direct calculations rather than treating previous green reports as proof. It is a third review by the same assistant, not an independent external assessment.

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
- CROA evidence eligibility, retired mappings and method ownership.

The 45 hand-authored reference expectations and ten mutation vectors remain separate from the regression-suite count. Thirty future product obligations remain unexecuted. The additional states exercise formulas, not the ledger application.

See [VALIDATION.md](VALIDATION.md), [raw output](review/regression-output.txt) and the [assurance matrix](review/ASSURANCE_MATRIX.md) for current results and scope. The archive was extracted into a different directory with spaces and the shipped verification command passed there with the same tested code/data input inventory; see the [portability record](review/portability-run.json). This is a same-platform check, not cross-platform qualification. The final archive and manifest include the resulting evidence records.

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

1. **Ledger design readiness:** authorized-access, retry, invalid-transition and recovery cases need full behavioral oracles. Its 14 application tests remain planned. No design_ready status is emitted.
2. **Evaluation cost:** CON-004 is quadratic and exhausts the reference budget at 500 rows although the environment admits 1,000. This remains unknown, not pass. Qualify the algorithm and its declared budget together before claiming the full bound.
3. **Engine implementation:** complete static analysis, graph/query APIs, real binding resolution, product runners, trusted identity and operational evidence are absent. The matrix lists gaps per gate.
4. **External validity:** no second product domain, independent assessor or comparative study establishes generality or scale benefits.

These are qualification work, not problems solved by another editorial review.

## Next step

Build one small vertical slice: a structured requirement, terms and constraint, normal/refusal scenarios, real code/tests and a change that invalidates evidence. Retrieve its obligations through a simple declared graph. Measure useful defects, omissions and maintenance effort against a lightweight baseline before adding infrastructure.

The package supports that experiment. The experiment must earn stronger claims.
