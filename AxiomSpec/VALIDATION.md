# Package validation: pass

Run: 2026-11-09T19:10:18.053812+00:00.

**Scope: design package. No product or example-application acceptance is asserted.**

Python 3.12.14; jsonschema 4.26.0; untrusted local runner.

## Results

- `PKG.EDITORIAL` : **pass** — 153 local link targets, 3 JSON blocks and 104 unique normative rule headings checked. External URLs not revalidated by this script.
- `PKG.ENVIRONMENTS` : **pass** — Restricted environment shapes and all scenario observations valid.
- `PKG.NEGATIVE_FIXTURES` : **pass** — 10 mutations verified with expected diagnostics; 30 future product obligations NOT executed.
- `PKG.OBSERVATIONS` : **pass** — 45 reference expectations checked across all 9 synthetic observations; no application tests.
- `PKG.OPTIONAL_EXTENSIONS` : **pass** — Execution declaration and CROA input fixture valid; 37 unassessed items, 13 unknown findings. No execution authority or CROA conformance.
- `PKG.QA_SELF_CHECKS` : **pass** — 16 targeted QA parser/evaluator self-checks passed; no full static typing qualification.
- `PKG.REFERENCES` : **pass** — Selected reference checks passed: 51 nodes, 119 edges. No completeness claim.
- `PKG.REGRESSION_RECEIPT` : **pass** — 47 test IDs in a current, successful local receipt; inputs/toolchain/output match. Producer remains untrusted.
- `PKG.SCHEMAS` : **pass** — Four schema documents valid under Draft 2020-12; example shape valid.

## Limits

- Artifact QA only. The product CLI, static type/unit compiler, graph/query engine and test adapters are not implemented.
- 30 future product obligations are descriptions, not executed tests.
- No application unit/integration/E2E tests were run; planned bindings are fictitious.
- Local untrusted runner; no identity attestation, runtime isolation or production approval.
- Reference evaluation is not proof of business completeness, formal equivalence or all executions.

## Reproduce

Run `python3 qa/run_checks.py` from this directory with [requirements-qa.txt](qa/requirements-qa.txt). This replays tests before checking their receipt and the package.

[Report](validation/package-report.json) · [Input manifest](validation/package-manifest.json) · [Statistics](validation/package-statistics.json).

The manifest records exact input digests. Validation outputs are excluded to avoid circularity. A filename or commit alone is not an attestation.
