# Conformance corpus and package QA

## Two scopes

[conformance.json](../fixtures/conformance.json) contains 53 vectors: twenty-three executable package mutations and thirty future product obligations. Future_runtime entries are descriptions, not available automated product tests.

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
| V-011 | Weight below one point in the declared units | WEIGHT_RANGE |
| V-012 | Risk label outside the band of the weight | RISK_BAND_MISMATCH |
| V-013 | Requirement naming an undeclared flag | UNKNOWN_FLAG |
| V-014 | Flagged must requirement tested in one flag state | FLAG_STATE_UNTESTED |
| V-015 | Flag kept past its removal target | STALE_FLAG |
| V-016 | Version that skips a step after the baseline | INVALID_VERSION_STEP |
| V-017 | Acknowledged break without a migration | MISSING_MIGRATION |
| V-018 | Optional requirement without a flag | OPTIONAL_WITHOUT_FLAG |
| V-019 | Band naming a method no key provides | UNKNOWN_APPROVAL_METHOD |
| V-020 | Band asking for more approvers than the keys can supply | UNSATISFIABLE_APPROVAL_POLICY |
| V-021 | Export of an object the specification does not hold | INVALID_EXPORT |
| V-022 | Import used by an object the specification does not hold | UNKNOWN_IMPORT_USER |
| V-023 | Attesting key held by an actor that is not a service | ATTESTOR_NOT_SERVICE |

Apply mutations independently. Require the full versioned ID set, valid metadata, expected gate/verdict and targeted reference diagnostic. A replace/remove target must already exist; an add target must be a new object member. An unrelated failure is insufficient.

### AX-F-001 — Turn an obligation into a test

Provide reproducible setup, input, controlled fault, actual command/API, oracle and inspected artifacts. Implement it in the runner. Changing a data label to executed does not execute anything.

### AX-F-002 — Honest denominator

Report twenty-three mutations checked and thirty product obligations not executed. Never count descriptions as successful tests or silently remove them from the result.

## Future obligations

V-101-103 cover parsing/confinement; 104-108 types, units, budget and missing data; 109-112 decisions and states; 113-116 evidence and authority; 117-121 context, rights, freshness and cursors; 122-127 impacts and policy; 128-130 partial traces, business revision and interrupted publication. These are a starting corpus, not an exhaustive standard.

## Observations and regressions

Thirty-one observations carry 84 Boolean expectations: nine ledger snapshots for the five BCIR constraints of ENV-001, eight before/after observations of a reservation attempt for the two of ENV-002, nine of a cancel or commit command for the two of ENV-003, and five of the audit rows one attempt added for the one of ENV-004. Require one observation per canonical Scenario and one expectation per active BCIR constraint in its environment. Reject duplicate/missing cases or expectations removed from both copies. This establishes declared-corpus coverage, not completeness of the business model.

The reference evaluator does not implement complete static typing, unit analysis or reachability. Package self-checks and review regressions cover specific defects. The 500-row uniqueness test expects an explicit budget limit; it does not claim the performance issue is fixed.

Run from the package root with the [pinned QA dependencies](../qa/requirements-qa.txt):

```text
python3 qa/run_checks.py
```

This command explicitly executes the package's test code, records collected IDs/results, input hashes, toolchain and raw output, runs the worked example's own tests the same way, then runs the artifact checker. The receipt is local and untrusted. It is checked for consistency, not producer authenticity. Zero, duplicate, skipped or failed tests cannot produce a successful receipt.

`python3 qa/check_package.py` only checks artifacts and the existing receipt. It does not replay the regression suite or refresh an old receipt. Changed test inputs or toolchain require a new run through run_checks.py. Receipt format 0.2 replaces the incomplete earlier package receipt; it is separate from the product report format.

The checker writes report, manifest, configuration, statistics and VALIDATION.md. It executes no test itself and disables remote schema retrieval. Input failures replace the current result with error when output remains writable. The wrapper publishes a distinct `axiomspec-verification-incomplete/0.1` marker until the checker completes, including when dependency/import failures prevent a normal report. That marker cannot be accepted as a normal successful report. Files are atomically replaced individually; consumers must verify digests across outputs.

The manifest excludes validation outputs and cache files to avoid circular hashes. Package symlinks and escaping documentation links are rejected. Extend the corpus with real defects and another product domain. Reserve external cases where useful; a known finite suite can be overfit.

Local documentation links must be relative, even when an absolute path happens to exist on the current machine. Reject unsafe input/output symlinks before opening files or writing diagnostics. If the output path is unsafe or unwritable, report the failure on stderr and do not reuse an older result. Compare input manifests before and after verification and reject detected changes. This is a single-writer consistency check, not protection from an adversary controlling the host or verification code.

Third-review tests also check ordering invariance of selected reference resolution and 100 seeded ledger observations against direct domain calculations. They broaden the exercised reference subset without qualifying a general BCIR compiler or product behavior.

Fourth-review tests cover rules that the contracts stated and the reference checks did not enforce: a witness scenario must illustrate a requirement its test verifies, goals and requirements at the far end of a required link must be active, requirement patterns fix their populated fields, effective windows are UTC and ordered, transition IDs use `TRN-`, a terminal state has no exit, unit annotations name one integer leaf and a `binding:` locator agrees with its binding. Local links must also match the file name's letter case, which a case-insensitive filesystem would otherwise hide. Edition 0.4.0 adds the cases for a literal array used as a collection, a binding naming the wrong node kind and a link declared twice, and compares the two before/after predicates with direct calculations on 200 seeded transitions. These remain selected reference checks, not a complete G02-G07 implementation.

Edition 0.5.0 tests cover format 0.2: every weight boundary in each minor unit, each flag rule, each release-declaration rule, the migration from 0.1 and the release comparison. The comparison cases derive a candidate from release 1.0.0 of the ledger, change one thing and require one level or one error, for requirements, constraints, models, terms, environments and flags, and they check the score arithmetic by hand, including dependents and a change of minor units.

Edition 0.6.0 tests cover format 0.3. The approval cases sign with fictional keys and simulate a passkey authenticator: each policy shape from zero to seven approvers, each way an approval can fail to count, key rotation through three releases, and the union of approval files in every order. The store cases build the same set of files in different orders and from two replicas and require one verdict; they create a fork, check that both sides stay verified, and settle it with a later release. The impact cases change one thing in the provider and require the reached uses and the score in the consumer. The parts cases split, join, damage and misplace parts, and check a generated specification of 3,000 requirements that no single file could hold.

Edition 0.7.0 tests cover the service interface. The annotation cases place a tag before, inside and after definitions and in files that must not be scanned. The query cases require exact sets of IDs for a direct context, containment for a change context, pages that stay within four budgets and join to the whole answer, and cursors that serve only their own snapshot and query. Every answer is validated against the schema the contract names. The server's own tests, beside the package, replay each operation over HTTP and MCP and require the same answer as the reference query.

Edition 0.7.1 tests are the regressions of the fifth review, and each failed on edition 0.7.0. They merge valid approvals with forged ones of the same actor and key and require a pass; write approvals through two service processes and require both; upload a release whose indented form exceeds one file, a release with a non-integer number and a body over the limit; propose a refused candidate and require the store unchanged; change the code under a running service and require the new annotations, a revalidated answer and a refused old cursor; break a bound file and require a gap, not a failure; and scan annotations written with a colon, with parentheses, with no ID and under a path that does not exist.

## Example application evidence

`run_checks.py` also runs the ledger's 32 application tests and writes `validation/example-test-run.json` with the executed IDs, the digest of every executed input, the toolchain, the environment and the hashed raw output. The checker accepts that receipt only if it is successful, complete and current, then requires that every binding marked `must_resolve` names a symbol that exists in the file (found by parsing, not by importing), that every active TestCase is implemented and has at least one executed test under its bound class, and that no executed test is outside a binding.

This is G09 and G10 for one example, on local SQLite, from an untrusted local producer. It demonstrates the evidence chain. It does not qualify a runner adapter, another language or another store.

`PKG.RELEASE` runs the reference comparison of release 1.0.0 with release 1.1.0 and requires it to pass. The report is not stored; `python3 qa/release_diff.py examples/refund-ledger/releases/1.0.0.json examples/refund-ledger/spec.json` prints it.

The optional execution and CROA fixtures receive structural/reference checks. Their fields cannot authorize execution or certify CROA conformance.
