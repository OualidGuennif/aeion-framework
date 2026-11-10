# Conformance corpus and package QA

## Two scopes

[conformance.json](../fixtures/conformance.json) contains 40 vectors: ten executable package mutations and thirty future product obligations. Future_runtime entries are descriptions, not available automated product tests.

Package QA checks schemas, selected references, all declared reference observations, targeted errors and editorial integrity. Its report scope is package. It does not qualify the future engine.

| Vector | Mutation | Expected result |
|---|---|---|
| V-001 | Unknown canonical field | Schema error |
| V-002 | Misspelled operator | Schema error |
| V-003 | Missing requirement response | Schema error |
| V-004 | Unknown risk value | Schema error |
| V-005 | Floating revision | Schema error |
| V-006 | Unknown edge target | UNKNOWN_TARGET |
| V-007 | Wrong endpoint kind | WRONG_EDGE_TYPE |
| V-008 | Duplicate identifier | DUPLICATE_ID |
| V-009 | Unknown author/owner reference | UNKNOWN_ACTOR |
| V-010 | Self-dependency | DEPENDENCY_CYCLE |

Apply mutations independently. Require the full versioned ID set, valid metadata, expected gate/verdict and targeted reference diagnostic. A replace/remove target must already exist. An unrelated failure is insufficient.

### AX-F-001 — Turn an obligation into a test

Provide reproducible setup, input, controlled fault, actual command/API, oracle and inspected artifacts. Implement it in the runner. Changing a data label to executed does not execute anything.

### AX-F-002 — Honest denominator

Report ten mutations checked and thirty product obligations not executed. Never count descriptions as successful tests or silently remove them from the result.

## Future obligations

V-101-103 cover parsing/confinement; 104-108 types, units, budget and missing data; 109-112 decisions and states; 113-116 evidence and authority; 117-121 context, rights, freshness and cursors; 122-127 impacts and policy; 128-130 partial traces, business revision and interrupted publication. These are a starting corpus, not an exhaustive standard.

## Observations and regressions

Nine observations carry 45 Boolean expectations for five BCIR constraints. Require one observation per canonical Scenario and one expectation per active BCIR constraint in its environment. Reject duplicate/missing cases or expectations removed from both copies. This establishes declared-corpus coverage, not completeness of the business model.

The reference evaluator does not implement complete static typing, unit analysis or reachability. Package self-checks and review regressions cover specific defects. The 500-row uniqueness test expects an explicit budget limit; it does not claim the performance issue is fixed.

Run from the package root with the [pinned QA dependencies](../qa/requirements-qa.txt):

```text
python3 qa/run_checks.py
```

This command explicitly executes the package's test code, records collected IDs/results, input hashes, toolchain and raw output, then runs the artifact checker. The receipt is local and untrusted. It is checked for consistency, not producer authenticity. Zero, duplicate, skipped or failed tests cannot produce a successful receipt.

`python3 qa/check_package.py` only checks artifacts and the existing receipt. It does not replay the regression suite or refresh an old receipt. Changed test inputs or toolchain require a new run through run_checks.py. Receipt format 0.2 replaces the incomplete earlier package receipt; it is separate from the product report format.

The checker writes report, manifest, configuration, statistics and VALIDATION.md. It runs no fictional binding or application test. It disables remote schema retrieval. Input failures replace the current result with error when output remains writable. The wrapper publishes a distinct `axiomspec-verification-incomplete/0.1` marker until the checker completes, including when dependency/import failures prevent a normal report. That marker cannot be accepted as a normal successful report. Files are atomically replaced individually; consumers must verify digests across outputs.

The manifest excludes validation outputs and cache files to avoid circular hashes. Package symlinks and escaping documentation links are rejected. Extend the corpus with real defects and another product domain. Reserve external cases where useful; a known finite suite can be overfit.

Local documentation links must be relative, even when an absolute path happens to exist on the current machine. Reject unsafe input/output symlinks before opening files or writing diagnostics. If the output path is unsafe or unwritable, report the failure on stderr and do not reuse an older result. Compare input manifests before and after verification and reject detected changes. This is a single-writer consistency check, not protection from an adversary controlling the host or verification code.

Third-review tests also check ordering invariance of selected reference resolution and 100 seeded ledger observations against direct domain calculations. They broaden the exercised reference subset without qualifying a general BCIR compiler or product behavior.

The optional execution and CROA fixtures receive structural/reference checks. Their fields cannot authorize execution or certify CROA conformance.
