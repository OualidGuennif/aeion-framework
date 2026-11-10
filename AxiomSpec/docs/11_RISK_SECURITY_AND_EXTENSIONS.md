# Risk, security and extensions

Treat specifications, documents, generated outputs, bindings, receipts and indexes as untrusted inputs. Reading them must not trigger execution, disclose unrelated content or manufacture favorable results.

| Boundary | Representative failure | Control |
|---|---|---|
| JSON | Duplicate keys, unsafe numbers, excessive nesting | Strict parser and bounds |
| BCIR | Hidden code, coercion, excessive work | Closed AST, static analysis and budgets |
| Bindings | Traversal and symlink escape | Confined resolution |
| Documents | Prompt injection | Data-only treatment and limited tool capabilities |
| Receipts | Fabrication or stale results | Subject digests and trusted producer policy |
| Graph | Old snapshot or metadata leakage | Snapshot checks and filtering before disclosure |
| Runner | Shell text from the specification | Authorized adapter and isolated execution |

### AX-S-001 — Path confinement

Bindings are repository-relative without absolute paths, `..`, NUL or URL schemes. Check actual symlink targets, not just spelling. Avoid check/open races with suitable platform primitives and state their coverage. Package QA is not a production sandbox. Distribution must also reject symlinks and escaping local documentation links so an archive cannot include unrelated files.

### AX-S-002 — Separate data from execution

Parsing, evaluation and graph queries run no project commands. Resolve runner declarations through trusted adapters. Never concatenate a specification string into a shell command. A document asking for secret disclosure remains data; actual protection comes from environment capabilities.

### AX-S-003 — Minimize data

Keep secrets out of specifications, fixtures, graphs and logs. Reference secret categories and delivery adapters. Collect only observation fields needed for the property. Avoid copying forbidden data into an authorization failure report. Define purpose, access, retention and deletion before collecting real traces. A digest of predictable data is not anonymization; metadata can also be sensitive.

## Product controls

Connect Risk to affected goals/requirements, Control to Risk, then requirements realizing the control. Name enforcement location and negative tests. A prompt rule does not establish prevention. Framework security and target-product security remain separate subjects.

## Governance and ML

Record purpose, data categories, jurisdictions, source versions, decision roles and review obligations when relevant. A regulatory constraint needs a qualified interpretation for the actual use case. The framework does not issue legal or compliance certification.

A probabilistic target product can still have deterministic boundaries and empirical model criteria. Separate tool restrictions and output schemas from corpus-based performance. Record model/corpus versions, splits, contamination risks, metrics and errors. Fixed temperature alone does not promise bitwise reproducibility from a remote service. Model-based review needs its own scope and bias assessment.

## Time, sensors and traces

Define event versus receipt time, clock uncertainty, delay, loss, duplicates, missing values and freshness. Missing is not zero. BCIR reads no clock; adapters supply explicit observations. Temporal arithmetic needs a versioned extension, not improvised integer conventions.

## Metrics

A metric specifies population, window, units, dimensions, sources, exclusions, missing-value handling and formula. A correctly computed metric may still measure the wrong outcome. Bind dashboard calculations to the metric contract.

### AX-S-004 — Add capabilities for a concrete need

For a dependency or service, state the observed problem, simpler alternative, expected benefit, maintenance cost and acceptance test. OCL, solvers, feature models and RDF/SHACL are optional adapters with explicit versions, subsets and losses. For another agent, identify added information, capability or independence. Repeated reasoning alone is not justification.

The optional CROA sidecar organizes readiness inputs and evidence links. It does not install an execution governor, firewall or audit infrastructure.
