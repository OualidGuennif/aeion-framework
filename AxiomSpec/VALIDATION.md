# Package validation: pass

Run: 2026-11-11T09:39:21.689392+00:00.

**Scope: design package. No product or example-application acceptance is asserted.**

Python 3.12.8; jsonschema 4.26.0; untrusted local runner.

## Results

- `PKG.APPROVALS` : **pass** — 5 approval signatures on 3 releases verify against the keys the governing release declares, with the approvers its policy requires per band (reference G12). The keys are fictional and derived from public labels; no authenticator hardware and no identity binding was involved.
- `PKG.EDITORIAL` : **pass** — 181 local link targets, 3 JSON blocks and 118 unique normative rule headings checked. External URLs not revalidated by this script.
- `PKG.ENVIRONMENTS` : **pass** — Restricted environment shapes and all scenario observations valid.
- `PKG.EXAMPLE_TESTS` : **pass** — 33 example application tests executed on current inputs cover all 20 active TestCases; 30 required bindings resolve. Local SQLite reference implementation, untrusted producer.
- `PKG.NEGATIVE_FIXTURES` : **pass** — 23 mutations verified with expected diagnostics; 30 future product obligations NOT executed.
- `PKG.OBSERVATIONS` : **pass** — 84 reference expectations checked across all 31 synthetic observations. Fixtures, not application runs.
- `PKG.OPTIONAL_EXTENSIONS` : **pass** — Execution declaration and CROA input fixture valid; 37 unassessed items, 13 unknown findings. No execution authority or CROA conformance.
- `PKG.QA_SELF_CHECKS` : **pass** — 17 targeted QA parser/evaluator self-checks passed; no full static typing qualification.
- `PKG.REFERENCES` : **pass** — Selected reference checks passed: 92 nodes, 182 edges. No completeness claim.
- `PKG.REGRESSION_RECEIPT` : **pass** — 150 test IDs in a current, successful local receipt; inputs/toolchain/output match. Producer remains untrusted.
- `PKG.RELEASE` : **pass** — Reference G14 comparison 1.0.0 -> 1.1.0: 122 changes, required step minor, change risk score 194.250 points. Classification is mechanical, not a compatibility proof.
- `PKG.RELEASE_STORE` : **pass** — 3 releases of 2 projects verify as one store from their files alone: chain links, approvals and 1 pinned import. No index, log or clock is consulted.
- `PKG.SCHEMAS` : **pass** — Five schema documents valid under Draft 2020-12; example shape valid.

## Limits

- Artifact QA only. The product CLI, static type/unit compiler, graph/query engine and test adapters are not implemented.
- 30 future product obligations are descriptions, not executed tests.
- The worked example runs its own tests on a local SQLite reference implementation. That is not a production store, and no other application was tested.
- Release comparison classifies changes mechanically by ID; API compatibility and data migration are not examined.
- Approval signatures are checked against declared keys. Nothing binds a key to a person, and the example keys are fictional.
- Local untrusted runner; no runtime isolation or production approval.
- Reference evaluation is not proof of business completeness, formal equivalence or all executions.

## Reproduce

Run `python3 qa/run_checks.py` from this directory with [requirements-qa.txt](qa/requirements-qa.txt). This replays tests before checking their receipt and the package.

[Report](validation/package-report.json) · [Input manifest](validation/package-manifest.json) · [Statistics](validation/package-statistics.json).

The manifest records exact input digests. Validation outputs are excluded to avoid circularity. A filename or commit alone is not an attestation.
