# Principles and scope

AxiomSpec addresses ambiguity and drift between intended behavior, implementation and verification. Human and AI authors use the same data contracts. Their authority is established separately.

## Core rules

### AX-P-001 — One canonical product specification

`spec.json` is the editable authority. Generated Markdown, diagrams and graph indexes are derived views. Notes may propose changes but do not silently amend requirements.

### AX-P-002 — Separate intent, model, execution and observation

A requirement states an obligation; a constraint formalizes part of it; a component declares a realization; a test observes behavior. Preserve their distinct identities and evidence scopes.

### AX-P-003 — Syntax does not establish business validity

A structured sentence may express the wrong policy. A satisfiable model may solve the wrong problem. Detected consistency does not establish completeness or code correctness.

### AX-P-004 — Keep unknown results explicit

Missing data, adapters, decisions or computation capacity must not become success. An unknown required check blocks the phase that requires it.

### AX-P-005 — Reproduce results in a stated scope

Record inputs, profiles, schemas, policy, tools, corpus and options. Pure checks do not read the clock, network or a model service. Supply time explicitly when the domain requires it.

### AX-P-006 — Traceability records claims

Declared `implements` and `verifies` edges do not establish behavior or test effectiveness. Retain provenance and the results actually available.

### AX-P-007 — Bind evidence to revisions

Evidence identifies the specification, source, policy, tool and observation digests. A recent timestamp cannot compensate for different inputs.

### AX-P-008 — Separate authority for critical controls

An author cannot grant permissions by editing a specification. High-risk acceptance requires the authority and evidence producers defined by trusted policy. Local mode must expose missing trust integrations.

### AX-P-009 — Do not redefine requirements to fit failures

An unexpected result may reveal a code defect, invalid assumption or wrong requirement. Investigate before changing the contract or oracle.

### AX-P-010 — Bound cost

Limit input size, graph size, expressions, evaluation work and query output. A substantial design package does not justify sending every document to every coding session.

## Minimal architecture

```text
Explicit inputs: spec, trusted profiles, policy, source snapshot, observations
  -> strict parsing and structural/reference validation
  -> semantic checks and bounded pure evaluation
  -> reports, generated views and immutable graph snapshots
  -> bounded queries and change packets
  -> acceptance in the requested scope
```

The initial implementation uses local files and in-memory adjacency tables. Add storage or infrastructure only after measuring a need. Publish generated product snapshots atomically; interrupted generation retains the previous complete snapshot.

The core validates declared information. Optional adapters may add code analysis, model exploration, external identity, runtime observations or solver support. Their absence must remain visible.

The framework does not certify security, legal compliance, universal correctness, complete dependency extraction or release permission.
