# Æion Framework

[![qa](https://github.com/OualidGuennif/aeion-framework/actions/workflows/qa.yml/badge.svg)](https://github.com/OualidGuennif/aeion-framework/actions/workflows/qa.yml)
[![release](https://img.shields.io/github/v/release/OualidGuennif/aeion-framework)](https://github.com/OualidGuennif/aeion-framework/releases)
![format](https://img.shields.io/badge/format-axiomspec%2F0.3-6f42c1)
![python](https://img.shields.io/badge/python-3.14%2B-3776ab)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

AxiomSpec 0.3 is a format for writing down what a product must do, in one `spec.json` file that a
program can check. Every goal, requirement, constraint, scenario and test in it has an ID and links to
the others, so you can ask which test covers a requirement, what a release changed, and who approved it.

Coding agents now write code faster than people can check it against what was asked. A prompt or a
design document does not help much there: no checker runs on prose, and nobody can say which sentence a
given test proves. AxiomSpec keeps the same content as structured data, and the checks in this
repository read it.

```mermaid
flowchart TB
  subgraph specify ["1 · Specify and approve"]
    direction LR
    idea["Idea, examples<br/>and decisions"] --> spec[("spec.json<br/>AxiomSpec 0.3")]
    spec --> checks{{"Deterministic checks<br/>pass · fail · unknown"}}
    checks --> release["Signed release<br/>version · digest · approvals"]
  end
  subgraph build ["2 · Build and prove"]
    direction LR
    agent["Coding agent<br/>index · @req · MCP"] --> code["Code and tests"]
    code --> evidence["Executed tests<br/>as evidence"]
    evidence --> next["Next release: diff,<br/>risk score, back to 1"]
  end
  specify ==> build

  classDef source fill:#ede9fe,stroke:#6f42c1,color:#1e1b4b
  classDef gate fill:#fef3c7,stroke:#b45309,color:#451a03
  classDef proof fill:#dcfce7,stroke:#15803d,color:#052e16
  class spec source
  class checks,release gate
  class evidence proof
```

## What it does

Each check answers pass, fail or unknown, and unknown never counts as a pass. A requirement linked to
code is only a claim until an executed test with a receipt covers it.

Every specification names the release before it. Comparing two releases lists each change by ID, says
whether the version needs a patch, minor or major step, and computes a risk score from the weights of
the requirements touched. In the example ledger, release 1.1.0 has 136 changes, needs a minor step and
scores 194.25 points.

The specification also holds its own approval policy: how many approvers each risk band needs, and
which methods count (passkeys, single sign-on, or whatever your approval service signs). The
signatures are checked from the files, with no server involved.

A coding agent never reads the whole specification. It gets a 31 KB index instead of the 220 KB file,
code annotated with `@req`, and a read-only service over HTTP and MCP. When it is unsure, it asks for
one requirement, for what constrains it, or for everything a change touches.

Verification needs only files. There is no database, log or clock, and the result is the same in
whatever order the files arrive and from whichever copy they come. A missing file makes the answer
unknown, and two conflicting releases are reported as a fork.

Specifications can depend on each other. A product pins the releases of the services it uses by
digest, and when a provider changes, the comparison follows the change into each consumer's
requirements.

An annotation in the code, and the request an agent sends to read that requirement:

```python
# @req REQ-004 CON-005
def authorize(principal, request_tenant, resource_tenant):
```

```bash
curl -s http://127.0.0.1:8787/v1/snapshots/current/nodes/REQ-004
```

## What is here

| Path | Content |
| --- | --- |
| [`AxiomSpec/`](AxiomSpec/README.md) | The package, edition 1.1.8: contracts, JSON schemas, a file checker, Markdown generation, release comparison and store verification, with a worked example (a fictional [refund ledger](AxiomSpec/docs/13_REFUND_LEDGER_WALKTHROUGH.md) in two signed releases, with executed tests) |
| [`server/`](server/README.md) | The FastAPI REST and MCP service, with a Python 3.15 Docker image, bounded admission and persistent file storage |
| [`playbooks/`](playbooks/01_NEW_PROJECT_AXIOMSPEC.md) | Three procedures: [a new project](playbooks/01_NEW_PROJECT_AXIOMSPEC.md), [an existing one](playbooks/02_EXISTING_PROJECT_NVIDIA_TO_AXIOMSPEC.md), and [an agent in a sandbox](playbooks/03_AGENT_IN_A_SANDBOX.md) |

The Æion family:

| Repository | Role |
| --- | --- |
| aeion-framework (this one) | The method itself: the format, the checks, the example and the playbooks |
| [aeion-factory](https://github.com/OualidGuennif/aeion-factory) | A project template that makes the method executable |
| [aeion-core](https://github.com/OualidGuennif/aeion-core) | A local web app that takes a feature from brainstorm to a checked specification |

## Quick start

With Python 3.14 or later:

```bash
python3 -m venv .venv && .venv/bin/pip install -r AxiomSpec/qa/requirements-qa.txt -r server/requirements.txt
.venv/bin/python AxiomSpec/axiom.py check AxiomSpec/examples/refund-ledger/spec.json
.venv/bin/python AxiomSpec/axiom.py markdown AxiomSpec/examples/refund-ledger/spec.json --output ledger.md
```

Replace the example path with your own specification. `check` reads strict JSON and verifies the
schema, the environments and selected reference rules; add `--json` for a report a program can read.
`markdown` runs the same checks, then writes a view of the requirements, decisions, constraints and
links. Without `--output` it prints to stdout, and it never overwrites a file. Both accept a parts
manifest, and neither runs product code.

The same CLI compares releases and verifies a whole store from its files:

```bash
.venv/bin/python AxiomSpec/axiom.py compare AxiomSpec/examples/refund-ledger/releases/1.0.0.json AxiomSpec/examples/refund-ledger/spec.json
.venv/bin/python AxiomSpec/axiom.py verify-store AxiomSpec/examples --json
```

`compare` prints JSON; add `--format markdown --output changes.md` for a report to read. `verify-store`
checks release chains, approvals and imports, says what is missing when it cannot conclude, and
exits with 3 in that case.

To replay the package QA, including the ledger's tests, run the following from `AxiomSpec` with the
dependencies installed. It rewrites the package's receipts:

```bash
../.venv/bin/python qa/run_checks.py
```

From that directory, compare the two releases of the ledger with:

```bash
../.venv/bin/python qa/release_diff.py examples/refund-ledger/releases/1.0.0.json examples/refund-ledger/spec.json
```

The service has its own [README](server/README.md) and tests
(`.venv/bin/python -m unittest discover -s server/tests`), and `tools/check_repo.py` checks the repository
guides and playbooks. CI runs these on Python 3.14 and 3.15 and also qualifies the Docker image.

For Docker, run `docker compose up --build -d` from the repository root. This starts the organization API
on `http://127.0.0.1:8787` with a persistent named volume. The [deployment guide](server/DEPLOYMENT.md)
covers pinned snapshots, concurrency limits, healthchecks, recovery and the scope of the load tests.

## License

[MIT](LICENSE).
