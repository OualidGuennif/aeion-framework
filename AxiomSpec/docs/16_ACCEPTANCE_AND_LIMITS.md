# Acceptance and limits

## Delivered package

Design contracts, artifact schemas, a structured example in two releases, reference observations, conformance vectors and package QA. The example has a reference implementation and executed tests. A reference release comparison and a migration from format 0.1 are included. Execution and CROA declarations are optional sidecars. Actual checks and review results are linked from the README.

The product CLI, static compiler, an access-controlled query engine, identity integration, deployed execution controls and runner adapters remain unimplemented. The queries and the service of the [service interface](19_SERVICE_INTERFACE.md) are references. Approval signatures are verified against declared keys; enrolling those keys for real people is part of that missing identity integration. One example executed on local SQLite is evidence about that example only.

### AX-ACT-001 — Demonstrate advertised capabilities

A partial implementation may be useful if it exposes missing capabilities. Emit a phase status only after its required checks actually pass in their stated scope. Before a pilot, qualify parsing/references, supported semantics, views/queries and stale-evidence detection. Integrations add real confinement, isolation, failure and recovery tests.

High-risk acceptance needs the trusted runner, authority and boundary evidence specified by policy. A local configuration cannot create that trust. An execution-mode declaration grants no rights. A CROA metadata check does not establish an assessed deployment level.

### AX-ACT-002 — Bound qualification claims

Name corpus, versions, cardinalities, environments and exercised capabilities. Distinguish format conformance, model coherence, satisfaction on observations, code tests and operational evidence. None automatically proves the next level.

## Remaining uncertainty

Precise requirements may address the wrong problem. Formalization may differ from intent. Tests can share specification errors. Code extraction can omit dynamic effects. Partial traces can miss causes. A local author can fabricate evidence under its control.

The framework exposes these boundaries; it does not remove the need for decisions and counterexamples. Complete, perfect and universally safe are not measurable acceptance criteria.

## Proportionate use

A small reversible change does not need the full example model. Use a declared profile proportionate to actual risk. The format uses one canonical specification per product or service and global invalidation. A large organization has many specifications that pin each other by digest (AX-M-021); one that is large by nature is stored in parts (AX-M-022). Verification needs only files (AX-L-010), so it works the same on a laptop, in a pipeline and across regions. Measure conflicts and cost before introducing dependency-sensitive caching.

Weights, flags and versions are required fields, not options. They cost one integer and one null per requirement when a product has no flags and a single release. What they buy is a mechanical answer to "what changed, is it breaking, and how much of what matters does it touch" at every release.

BCIR has a compiler and qualification cost. Reuse a suitable existing model/solver integration when that is simpler and robust. Evaluate a small vertical slice before building optional infrastructure.

## Evaluation

Define comparable tasks, participants, time accounting, defect criteria, corpus and assessment method before measuring benefits. Track useful early defects, context omissions, clarification effort and maintenance cost, including failures. A well-documented toy example is not evidence of performance at scale.

Next step: run the release comparison on a real product across several releases and measure two things: how many breaking candidates the classifier raises that reviewers override, and whether the score orders releases the way incident history does. Then define how specifications of separate services refer to each other. Qualify each additional capability rather than treating the document count as progress.
