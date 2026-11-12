# Final global review

Edition 1.0.1 · 12 November 2026. The fourth review describes edition 0.3.1 and the seven sections after it editions 0.4.0, 0.5.0, 0.6.0, 0.7.0, 0.7.1, 0.7.2 and 1.0.0; editions 0.5.1 and 1.0.1 are notes at the end of the second and of the last. The section on edition 0.7.1 is a fifth review, and it names three claims of the two sections before it that did not hold. The section on edition 0.7.2 is a sixth, of the corrected code, and the section on edition 1.0.0 a seventh. The sections below those describe edition 0.3.0 and are kept as written, except where marked.

## Verdict

**Suitable as a design handoff and local reference package for a small implementation pilot. Not a completed specification engine or an autonomous execution authority.** Edition 0.5.0 does not change that verdict: it adds release, weight and flag semantics with reference implementations and one executed example, none of them qualified on a real product.

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

## Edition 0.5.0

11 November 2026. The specification format changes to `axiomspec/0.2` and the profile to `AX-CORE-0.2`. Until this edition the format described one snapshot well and said almost nothing checkable about the step from one snapshot to the next: no release number, no record of what changed, no numeric weight, no flag, no classification of a change as breaking. These are now required fields and one new gate, not an optional sidecar.

### What the format gains

| Subject | Field | Checked rule | Contract |
|---|---|---|---|
| Release | `release.version`, `release.previous` | One version step after the named baseline | AX-M-017 |
| Compatibility | `release.compatibility` | Each entry rests on an active answered Decision; a break states its migration | AX-M-017, AX-L-007 |
| Weight | `project.weight_minor_units`, `weight_minor` on every requirement | 1 to 100 points in units of 1, 10, 100 or, from 0.5.1, 1000; the risk label is the band of the weight | AX-M-018 |
| Flag | `flags`, `flag_id` on requirements, `flag_states` on tests | Declared, owned, used, tested in both states for a must requirement, removed by its target version | AX-M-019 |
| Release comparison | Gate G14, two documents | Identity and revision rules, classification by ID, recorded overrides, version step, change risk score | AX-L-006 to AX-L-009 |

`qa/release_diff.py` is a reference implementation of G14 and `qa/migrate_0_1.py` of the migration. Report format 0.3 adds the gate. Eight conformance vectors and 38 regression tests cover the new rules; the comparison tests derive every candidate from a real baseline and check the score arithmetic by hand.

### Decisions taken in the design

- **The risk label stays and is derived.** The weight is the number; the label is its band. Rules keyed on risk keep working and can no longer disagree with the weight.
- **The classifier is conservative and overridable.** It cannot tell a tightened formula from a relaxed one. Both are breaking candidates until a recorded decision says `compatible`. An override lowers the change to minor, never to nothing, and an unused override fails.
- **The score never touches a gate.** It ranks releases for review. The existing rule against compensating scores (AX-K-005) is unchanged.
- **A flag waives nothing.** A requirement behind a disabled flag keeps every obligation. A flag past its removal target fails the baseline.
- **Flag state is per release, not per environment.** Deployment overrides are runtime configuration and belong to G13.

### The ledger

Three items left open by 0.4.0 are closed.

- **Cancellation and commitment** have a before/after environment (ENV-003), two predicates and nine scenarios, four of them counterexamples.
- **Commands on a record in the wrong state** have a requirement (REQ-009) and a decision (DEC-003): a repeated command is reported as already done, a contradictory one is refused, and neither changes the ledger.
- **The tests run.** A reference implementation on SQLite and 32 test methods cover all 20 TestCases. Package QA resolves every binding by parsing, runs the tests and binds the receipt to the digest of every executed input. The concurrency test forces the interleaving and is also run against a variant without the transaction, which it must and does catch.

The example now has two releases. Comparing them raises two breaking candidates, both new predicates on requirements 1.0.0 already had; DEC-004 records why they are compatible. The step is minor and the score is 179.25 of 592.5 active points. *(0.5.1: three candidates, 194.25 points.)*

### What this edition does not establish

- The classification and the score were exercised on one fictional example and on synthetic single-change candidates. Whether the classifier's candidates match what reviewers of a real product call breaking, and whether the score orders releases as incident history would, is unmeasured.
- The factors (100%, 50%, 10%, dependents at most 25%) and the band limits (25, 50, 75) are choices, not findings. They are stated in one place each so a pilot can change and compare them.
- The executed evidence is one example on local SQLite from an untrusted producer. No runner adapter, other language or other store is qualified.
- One specification is one file of at most one megabyte. References between specifications are undefined. *(Closed in 0.6.0.)*
- aeion-factory and aeion-core read format 0.1. The external `design_ready` result reported for 0.4.0 does not carry over to release 1.1.0.
- This is still a review by the assistant that wrote the change.

### Edition 0.5.1

11 November 2026. Two changes and no new rule.

- **A fourth weight unit.** `weight_minor_units` also accepts 1000, so 37.5 points can be written 37500 and `weight_minor` reaches 100000. This widens format 0.2 without renaming it: every 0.2 specification stays valid, and a checker built from edition 0.5.0 rejects one that uses 1000. The score keeps exact integers; its own unit is then 100000 per point.
- **Audit output has scenarios.** REQ-007 had an executed test and no scenario. ENV-004 observes one attempt and the audit rows it added. CON-011 requires exactly one row, equal field by field to the attempt's identifier, operation kind and outcome. Of five scenarios, three are counterexamples: a row that copied the credential, a row that copied the request body, and a denied attempt that left no row. TEST-013 now evaluates CON-011 on rows read from the store for seven attempts across the four operations.

Writing the predicate exposed one loose end in the implementation: an operation identifier longer than the 64 characters the audit row keeps was stored truncated. The entrypoint now refuses it as invalid.

Release 1.1.0 of the example was amended in place, not followed by a 1.2.0. The example's releases illustrate the comparison; no one depends on them. A product would not do this. CON-011 is a third breaking candidate, accepted as compatible under the same DEC-004, and REQ-007 now counts at 50% instead of 10%: the score is 194.25 of 592.5 points.

BCIR still has no substring operator. "No stored column contains the credential" remains an assertion in test code on the raw rows; CON-011 says the stronger thing that can be said in the formula language, which is what each field must equal.

## Edition 0.6.0

11 November 2026. The specification format changes to `axiomspec/0.3` and the profile to `AX-CORE-0.3`. Edition 0.5.0 left three things open: nothing authenticated an approval, one specification was one file of a megabyte, and specifications could not refer to each other. This edition closes them under one constraint that shaped every choice: verification must need no shared service.

### What the format gains

| Subject | Field or file | Checked rule | Contract |
|---|---|---|---|
| Approval policy | `approval.policy`: approvers and accepted methods per risk band | Stated for all four bands; satisfiable by the declared keys | AX-M-020 |
| Keys | `approval.keys`: actor, method label, algorithm, public key, `attests` | No key twice; an attesting key is held by a service | AX-M-020 |
| Approvals | A separate file per release: signatures over the release digest | The baseline governs; bands reached; distinct approvers per band and method | AX-G-014 |
| Imports and exports | `imports`, `exports` | Exact pin by digest; only exported IDs are used; classification of a moved pin | AX-M-021 |
| Parts | A manifest and part files | Joining reproduces the canonical digest | AX-M-022 |
| Release store | Any set of files | Verdict per release from files alone; forks reported; missing is unknown | AX-L-010 |
| Impact | Two provider releases and a store | Uses reached, consumer requirements and score | AX-L-011 |

`qa/approvals.py`, `qa/release_store.py`, `qa/spec_parts.py` and `qa/migrate_0_2.py` are the reference implementations. Five conformance vectors and 42 regression tests cover the new rules. Signature checks use the `cryptography` library, a new QA dependency.

### Decisions taken in the design

- **The policy is the organization's.** The number of approvers per band is any integer from 0 to 128, zero included. The method is a label the organization chooses. Nothing is hard-coded: not a threshold, not a role, not one authentication technology.
- **Any authentication fits through one mechanism.** A person's own key signs directly. Everything else, such as single sign-on, e-mail confirmation or a ticket workflow, is attested by a service key the specification declares. The check is the same signature check either way.
- **No blockchain, no log, no witness servers.** A private chain run by one organization is no harder to rewrite than a signed file and adds a service that can be down or out of step. What a chain is wanted for is here without one: each release names its baseline by digest, each approval signs the digest, and each consumer pins its providers by digest under its own approvers' signatures. The pins are the witnesses, and they scale with use.
- **The verdict is a function of a set of files.** No index, no clock, no ordering service. Files may arrive in any order from any replica, stores merge by union, and a file received twice changes nothing. Twenty of the 720 arrival orders of the example store are replayed in the tests and give one verdict.
- **Absence is unknown; conflict is a fork; neither corrupts.** A missing baseline or provider leaves a release unknown until the file arrives. Two releases claiming the same highest version are reported as a fork on every replica, with the same preferred head, while both stay verified. A later approved release settles it. Nothing is deleted.
- **A bad fragment blocks nothing.** An approval that does not verify is set aside and reported. A file that cannot be read is listed. Each release has its own status.
- **The baseline governs its successor.** This is what removes the clock: a key added by a release cannot approve that release, a removed key cannot approve the next, and earlier releases stay valid.
- **Exact pins.** No version ranges and no resolver, so there is nothing to resolve differently in two places.

### The examples

The ledger's two releases are signed by two simulated passkeys under a policy of 0, 1, 1 and 2 approvers. A second specification, the identity adapter, is approved through an attesting service under a policy of 0, 0, 1 and 1. Ledger 1.1.0 pins it by digest and declares two uses. The `examples` directory verifies as one store.

### Measured

On one laptop (Apple silicon, Python 3.12), with a specification generated by repeating one requirement:

| Requirements | Size | Parts | Rule checks | Comparison | Approval check | Store of two releases |
|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.8 MB | 1 | under 0.01 s | 0.02 s | 0.04 s | 0.8 s |
| 10,000 | 7.1 MB | 8 | 0.03 s | 0.13 s | 0.31 s | 7 s |
| 50,000 | 35 MB | 36 | 0.19 s | 0.88 s | 1.6 s | 39 s |

The store time is almost entirely JSON Schema validation in Python. The schema's own bound was 10,000 nodes; it is now 100,000 nodes and 500,000 edges.

### What this edition does not establish

- **Who holds a key.** The check proves that declared keys signed. Binding a key to a person, and a label such as `device_passkey` to real hardware, is enrolment, and stays with the organization's identity system.
- **Real authenticators.** The passkey assertions are produced by a simulated authenticator with fictional keys. The verification follows the WebAuthn assertion format; no browser or device produced one here.
- **The attesting service.** Its key can approve for any actor, so it is as sensitive as all of them together. A band that must not depend on it accepts personal methods only, as the ledger's critical band does.
- **Freshness.** A store cannot show that it holds the newest release. A consumer that needs a particular release pins it.
- **The first release.** It governs itself. Trust in it comes from pinning its digest through a channel the organization trusts.
- **A compromised approver device.** A key signs what its machine sends. Showing the digest on a second device is outside the package.
- **Scale on a real product.** The measurements use generated requirements of one shape on one machine. A real specification of that size has formulas and scenarios whose evaluation budgets were not exercised.
- **Legal weight.** These are integrity signatures, not qualified electronic signatures.
- aeion-factory and aeion-core read format 0.1.
- This is still a review by the assistant that wrote the change.

## Edition 0.7.0

11 November 2026. The specification format stays `axiomspec/0.3`. This edition adds the service interface: how an agent and an organization reach a release without holding the whole specification.

### Decisions

- **The specification stays one canonical JSON document.** Every pin, approval and store check rests on one unambiguous byte form. On the ledger, JSON parsed in 0.5 ms and YAML in 20 ms with its C parser; the YAML text was larger than compact JSON, and YAML retypes values silently (`no` became false, `010` became 8). A specification written as code would have to be executed to be read.
- **The implementation stays in Python.** At 50,000 requirements the rule checks take 0.2 s and the comparison 0.9 s. The contract is language-neutral, so an organization can implement it in another language.
- **HTTP with a contract, plus MCP; no query language.** Reads are GETs on an immutable release, so they cache without limit and a sandbox can allow the service read-only by method. A free-form query language would work against the bounded, fixed queries the package already requires (AX-K-006).
- **One behavior, two transports.** The queries live in the package (`qa/queries.py`). The server beside it and its MCP tools only transport them, and the tests require the same answer from each.
- **Few tools.** Four for an agent and four for authoring, because tool definitions are read before any question is asked.

### What was added

| Subject | Where | Contract |
|---|---|---|
| Graph index, one record per line | `qa/graph_index.py`, `schemas/graph.schema.json` | AX-V-001 |
| `@req` annotations in code | `qa/graph_index.py` | AX-V-002 |
| Immutable, bounded reads with stateless cursors | `qa/queries.py` | AX-V-003, AX-K-006 |
| HTTP and MCP contract | `api/openapi.json`, `api/mcp-tools.json` | AX-V-004 |
| Context in two scopes | `qa/queries.py` | AX-V-005, AX-K-010 |
| Sandbox and organization modes | the reference server | AX-V-006, AX-V-007 |
| Candidates from edits by ID | `qa/queries.py` | AX-V-008 |

Thirty-four regression tests cover them in the package. The reference server has nineteen more, which replay each operation over HTTP, MCP and a listening port.

### Found while building

- **The conservative closure is most of a small specification.** The plan estimated 5 to 28 KB for the context of a requirement. Implemented as AX-K-010 states it, the closure of any ledger requirement is 79 to 90 KB of a 117 KB specification, because two hard project rules bring the capacity and tenant requirements with all their scenarios and tests. The contract is right for a change and wrong for a doubt, so a second scope, `direct`, was added: 9 to 22 KB in one page. Its answer says it is not the context of a change.
- **A real gap in the example.** The `gaps` query reports that REQ-010 has no scenario. It was not fixed.
- **A stale read in the server.** With two processes on one directory, a lookup read the store before the reload that resolving the digest triggered. The two-process test caught it.
- **An oversized object on an early page.** `complete` was computed per page, so an answer could end complete after naming an object it could not deliver. It now covers the whole answer.

### Measured on the ledger

| Question | Answer |
|---|---|
| The index, against the specification file | 29 KB against 209 KB |
| Search of the index for one symbol | 0.5 KB |
| One requirement, brief | 2 to 6 KB |
| What binds one requirement | 9 to 22 KB, one page |
| The context of a change | 79 to 90 KB, three or four pages |

### What this edition does not establish

- **Benefit to an agent.** No agent was measured on a real task with and without this setup. The two 2026 studies found on context files disagree, and none was found on requirement IDs in code.
- **A real sandbox.** The OpenShell policy in the playbook is written from the version 0.1.8 documentation and was not run there.
- **Access control.** The reference server authenticates nobody and filters nothing (AX-K-009 is not implemented). It was not load-tested and keeps every release in memory.
- **Symbols outside Python.** Annotations are found in any language; the symbol they belong to is resolved for Python only. No call graph is built.
- **Truth of an annotation.** It says where a requirement was placed. Only an executed test says it is met.
- **Other MCP clients.** The tools were exercised with the official Python SDK, version 2.3.0, in process and over HTTP.
- This is still a review by the assistant that wrote the change.

## Edition 0.7.1

11 November 2026. A fifth review, of the code of editions 0.6.0 and 0.7.0. It ran the approvals, the store, the queries and the reference server against hostile and concurrent inputs. It found ten defects and reproduced nine of them before any fix. All ten are corrected. The specification format stays `axiomspec/0.3`.

### Claims that did not hold

| Claim | Where it was made | What was true |
|---|---|---|
| A damaged or hostile approval file cannot block a release that has its approvers | Edition 0.6.0, AX-G-014 | True for an approval of another actor or key. A forged approval of the same actor and key replaced the valid one when files were merged. |
| Two replicas that receive different files converge | Edition 0.7.0, AX-V-007 | True for releases. Two server processes that each received an approval wrote the same file and one approval was lost. |
| A file that cannot be read withholds nothing | Edition 0.6.0, AX-L-010 | True, and the file was dropped without a word: a release the server had just accepted could disappear at the next start. |

The tests of those editions used a forged approval of another key, and one writer per directory.

### Defects and corrections

| Defect on edition 0.7.0 | Correction |
|---|---|
| The merge of approval files kept one approval per actor and key, the smaller in bytes, valid or not. Merging the ledger's valid approvals with forged ones turned its verdict from pass to fail. | The merge keeps every distinct approval. Verification sets aside what does not verify and counts each approver once. |
| The server rewrote one approvals file per release from its memory and never read a known release again. With two processes, one of two approvals was lost and each process answered from its own stale copy. | Every accepted upload is its own file, named by its content. Before each organization request the server reads the files that appeared. |
| The server wrote releases indented and parsed bodies loosely, while the store reads strict JSON of at most one megabyte. A release of 800 KB was accepted, written as 1.09 MB and gone after a restart; so was one holding `10.0` for an integer. | Bodies are strict JSON of at most one megabyte and releases are written in canonical form; a larger release is held as parts. The store names a broken store file in `rejected_files` instead of skipping it. |
| Every schema-valid candidate was stored, and the head of a project was its highest version whatever its status. A refused candidate became the head and turned the verdict on the store to fail. | A candidate is held only when it passes its checks. A project also has an accepted head, its highest release that passes, and the impact report measures consumers there. |
| Answers that depend on the code (index, lookup, trace, gaps) were marked immutable for a year. The same address returned 23 traces, then 10 after the code changed. | Those answers are revalidated. The annotations are read again when a scanned file changes, and a cursor does not continue across that change. |
| The gaps query failed with status 500 when a bound file did not parse, which is the normal state of a file being edited. Other unexpected errors also left as bare pages. | An unparsable file is a gap in the answer. Any other failure is a problem document with code `INTERNAL_ERROR`. |
| The annotation scan skipped `@req: REQ-004` and `@req(REQ-005)`, returned nothing for a path that does not exist, and never read a source folder named `build`. | Both spellings are read. The token with no ID after it, and a path that does not exist, fail the scan. A named folder is always read. |
| A request for a digest that was not held reloaded and revalidated the whole store. Bodies had no size limit and requests shared the store without a lock. | New files are read once and an unknown digest costs a directory listing. Bodies are capped and the server answers one operation at a time. |
| A lookup listed one place in the code once per declared link to it: nine traces for REQ-004, seven distinct. | A place is listed once. |
| The store compared each release with its baseline twice and recompiled the approvals schema for every release. | The comparison is computed once and passed on; the schemas are compiled once. The gain was not timed. |

Found while fixing: the output schema of each MCP tool had no `type` at its root, which the protocol requires. The Python SDK logged a validation error over HTTP and continued; a stricter client would refuse the tool list. The root type is now stated.

### Decisions

- **The head is unchanged; the accepted head is added.** The head still describes the chain and its forks. What a project stands on is its accepted head. The store check report is `axiomspec-store-check/0.2`.
- **A refused candidate is not stored.** Edition 0.7.0 stored it and left its use to approvals. A candidate now enters the store only when its schema, its references and its comparison pass, and the answer says so in `held`.
- **The server filters approvals when it can.** With the governing release at hand it keeps only the approvals that verify. The store itself still accepts any approvals file, because a file may arrive before the baseline that judges it.
- **Nothing is read below a name that starts with a dot.** That is where a writer stages a file.

### Tests

Eighteen regression tests in the package and nine in the server, 27 in all. Run against the code of edition 0.7.0, 26 fail; the other one guards the new rule on names that start with a dot.

### What this edition does not establish

- **Concurrency under load.** Two and three service objects on one directory were exercised in one process, in sequence. Parallel writers and a real shared file system were not.
- **The cost of listing.** The server lists the store before each organization request. That was not timed on a large store.
- **Growth of approval files.** Each distinct upload is a file, and nothing compacts them.
- **Every broken file.** A broken store file is recognized by its `format` field in its first megabyte. A larger file whose field comes later is still ignored.
- **The relying party of a passkey.** The assertion check compares the challenge, the user-verification flags and the signature. It does not compare the relying party or the origin; the declared key is the only binding.
- **Forks below the head.** Two different releases under one version that is not the highest are not reported as a fork.
- This is a review by the assistant that wrote the code, and its earlier reviews missed these defects.

## Edition 0.7.2

12 November 2026. A sixth review, of the code as edition 0.7.1 left it. Ten findings, none as serious as those of the fifth; eight were reproduced or measured before any fix. Nine are corrected and one is left as it is. The specification format stays `axiomspec/0.3`.

### Defects and corrections

| Finding on edition 0.7.1 | Correction |
|---|---|
| The scan could not leave a folder out. A repository that contains this package failed on the package's own mentions of `@req`: 13 problems in three files of `qa/`. | The scan, the index command and the service take `--exclude`. |
| `@req REQ-004 and CON-005` read REQ-004 and dropped CON-005 without a word. | An ID of the release that follows other words on the line fails the scan. Other words, such as `SHA-256`, are ignored. |
| With one rejected file in the store, every new file made the service read the whole store again: 36 files for three uploads instead of 3. | Only the rejected files are read again, since a new file may be the part one of them was missing. |
| A candidate was announced as held without looking: when the write did not land, `held` was still true. | `held` is what the store holds, and a write that does not land is an error. |
| The service listed the store with several system calls per file before each organization request: 165 ms at 5,000 files. | One pass per directory, about one call per file: 47 ms on the same store. |
| Every read of a sandbox service walked the code, also for a context, which does not read it: 95 ms for 1,300 source files. | The code is looked at only by the queries that read it. A context cursor now survives a change of the code. |
| A read of the approvals returned every approval offered, forged ones included. | It returns those that count, or all that were offered while the governing release is absent. |
| A part that is a symbolic link passed a check that tested the path after following the link. | The link is refused before it is followed. |
| The ledger shipped with a gap its own query reported: REQ-010 had no scenario, and REQ-004 no counterexample. | The ledger gains ENV-005, CON-012 and three scenarios for the report, and a counterexample for a denial. The tests evaluate CON-012 on each answer. Package QA now requires that the ledger's own gaps query reports nothing. |

Left as it is: a sandbox service given a whole store validates every release in it to serve one. Given the single file of the task, as the playbook does, it costs nothing.

Found while fixing: `qa/fictional_keys.py` refused every valid call from the command line, because it counted its arguments wrongly. The examples had been signed by calling its functions.

### What changed in the example

Release 1.1.0 of the ledger has a new digest, so its approvals were signed again with the fictional keys and its index rebuilt. It now holds 35 observations with 89 expectations, and the comparison with release 1.0.0 reports 136 changes with the same score, 194.25 points.

### Tests

Eight regression tests in the package and six in the server. Run against the code of edition 0.7.1, 13 of the 14 fail; the last guards the new rule on rejected files.

### What this edition does not establish

- The listing still grows with the store: 47 ms per organization request at 5,000 files, on one machine. The code signature still costs about 80 ms at 1,300 source files for each query that reads the code.
- CON-012 covers a request by a verified principal of the ledger tenant. A request by anyone else is covered by the tenant predicates, not by this one.
- The open points of edition 0.7.1 stand: parallel writers under load, growth of approval files, the relying party of a passkey, forks below the head.
- This is again a review by the assistant that wrote the code.

## Edition 1.0.0

12 November 2026. The first tagged release, after a seventh review of the code as edition 0.7.2 left it. Seven findings, six reproduced before any fix; all seven are corrected. The specification format stays `axiomspec/0.3`. The number says that this release is published and will not change. It does not change the verdict above: this is a reference package, not a qualified engine.

### Defects and corrections

| Finding on edition 0.7.2 | Correction |
|---|---|
| The store merged approval files by release digest alone. A file with the digest of release 1.1.0 and another version, read first, made the valid file fail to merge: the release failed. Read last, it was dropped and the release passed. The verdict depended on the order of reading, and one hostile file could block a release. | Approvals are kept by digest, project and version. A file that names a held release under another project or version is never counted and is reported in `rejected_files`; the verdict is the same in any order. |
| The service wrote store files in canonical form, where `format` comes in the middle of a release and near the end of an approvals file. A copy cut at 30 % lost that field: the store ignored the file as one of another format, passed, and the release was gone without a word. | `format` is written first. A cut copy is reported as a broken store file. |
| The same approvals sent again rewrote their file with the same bytes. The new modification time made every process that shares the store read all of it again: 22 files for a store of 11. A client that retries after a timeout does exactly that. | A file that already holds the same bytes is not written again. |
| The organization command of the server README pointed the service at the examples of the package. After one candidate, package QA failed on a file it did not expect. | The README copies the examples to a working directory first. |
| A context over HTTP took any number of IDs, although the contract allows 100. Two thousand unknown IDs gave an error message of 24,019 characters. | A context names from 1 to 100 IDs, and the message names at most ten missing ones. |
| `--include` with no path started a service that scanned nothing and reported no gap. | `--include` takes at least one path. |
| IDs continued on the next comment line were not read, without a word. | Documented in AX-V-002 and the sandbox playbook: all IDs of an annotation are on the line of the token. Detecting the continuation would also flag ordinary comments. |

### Tests

Three regression tests in the package and four in the server. Run against the code of edition 0.7.2, all seven fail.

### What this edition does not establish

- The open points of editions 0.7.1 and 0.7.2 stand: the listing grows with the store, parallel writers under load, growth of approval files, the relying party of a passkey, forks below the head.
- **Benefit to an agent.** Still not measured. The next useful step is an agent on a real task with the sandbox playbook, with and without the service, not a further review.
- This is again a review by the assistant that wrote the code.

### Edition 1.0.1

12 November 2026. Python 3.14 or later is required: the package QA and the reference service refuse an older interpreter, and the automated checks run on 3.14. The receipts were replayed on Python 3.15.2. The root README of the repository was rewritten as a shorter overview. Nothing else changed: the format, the checks, the service and the examples are those of edition 1.0.0.

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

1. **Ledger design readiness:** authorized-access, retry, invalid-transition and recovery cases need full behavioral oracles. Its 14 application tests remain planned. No design_ready status is emitted. *(0.4.0: authorized access, retry, refusal, conflict and denial now have scenarios and predicates; an external engine reports design_ready for the declared model. Invalid transitions still have no requirement, and the 16 tests remain planned.)* *(0.5.0: invalid transitions have REQ-009, cancellation and commitment have before/after scenarios, and all 20 tests are executed on a reference implementation. Audit output still has no scenario.)*
2. **Evaluation cost:** CON-004 is quadratic and exhausts the reference budget at 500 rows although the environment admits 1,000. This remains unknown, not pass. Qualify the algorithm and its declared budget together before claiming the full bound.
3. **Engine implementation:** complete static analysis, graph/query APIs, real binding resolution, product runners, trusted identity and operational evidence are absent from this package. The matrix lists gaps per gate. *(0.3.1: aeion-factory 3.0.0 implements G01-G07, graph queries, context packets and one test adapter outside this package; it reports identity, policy and runtime observation as unsupported. This package does not qualify it.)* *(0.5.0: this package now resolves Python bindings and runs tests for its one example, and has a reference G14. That engine reads format 0.1.)*
4. **External validity:** no independent assessor or comparative study establishes generality or scale benefits. *(0.3.1: aeion-factory carries a second domain as a field test, a holiday planner built by a coding agent against a checked specification. It is the authors' own demonstration, not a comparative study.)*

These are qualification work, not problems solved by another editorial review.

## Next step

Build one small vertical slice: a structured requirement, terms and constraint, normal/refusal scenarios, real code/tests and a change that invalidates evidence. Retrieve its obligations through a simple declared graph. Measure useful defects, omissions and maintenance effort against a lightweight baseline before adding infrastructure.

The package supports that experiment. The experiment must earn stronger claims.
