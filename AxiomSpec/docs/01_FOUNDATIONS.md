# Foundations and references

## Scope

The design combines requirements engineering, explicit modeling, constraint reasoning and knowledge provenance. Context engineering supports retrieval and execution; it does not replace the requirements model.

Published work motivates the approach. The canonical format, BCIR, gate names, query protocol and implementation plan are proposals defined by this package. No cited paper establishes their correctness.

## Design implications

| Topic | Relevant result or method | AxiomSpec decision |
|---|---|---|
| Intentions and process guidance | MAP represents intentions and strategies and can use graph algorithms for guidance [R-03] | Keep goals and decisions; generate explanatory graph views |
| Configuration constraints | Integer constraint solving can express admissible product configurations [R-04] | Separate model validity, satisfiability and implementation conformance |
| Model conformance | Constraint-based checking has been studied for feature models [R-05] | State the model and domain of every claimed result |
| Security requirements | An ontology can support elicitation of security concepts and relationships [R-06] | Link assets, threats, requirements, controls and negative cases |
| AI assistance | Requirement classification results vary across evaluated classes [R-07] | Treat AI outputs as proposals; do not assume universal model superiority |
| Synthetic data | Generated data can support classification experiments [R-08] | Label synthetic fixtures; retain independent evaluation cases |
| Structured language | EARS constrains requirement syntax [R-09] | Use structured fields and repeatable rendering; review meaning separately |
| Model constraints | OCL defines constraints over models [R-10] | Reuse qualified adapters when appropriate; do not claim BCIR is OCL |
| Context design | CDCE characterizes constraints, context assets and representations [R-18] | Separate guidance, enforcement and verification with explicit provenance |

The CDCE preprint uses comparative cases. It is not a causal benchmark of coding productivity or a proof of a deterministic engine. Its formalization holds some categories fixed while refining institutional constraints; this package permits governed revision of any rule category.

## Engineering disciplines

Requirements engineering supplies elicitation, scenarios and prioritization. Modeling supplies types, states and transformations. Constraint reasoning supplies explicit domains and bounded analysis. Knowledge engineering supplies relations and provenance. Testing supplies executable observations and regression cases.

ML, process mining, pervasive computing, security, decision support and governance are extensions driven by the product. They do not each require a separate subsystem. See [extensions](11_RISK_SECURITY_AND_EXTENSIONS.md).

## References

References use titles and identifiers. Access limitations matter: a public abstract is not a full experimental review.

| ID | Publication or standard | Use and access scope |
|---|---|---|
| R-03 | [Enhancing the Guidance of the Intentional Model MAP: Graph Theory Application](https://arxiv.org/abs/0911.0430), 2009 | Process guidance; open paper |
| R-04 | [Using Integer Constraint Solving in Reuse Based Requirements Engineering](https://arxiv.org/abs/2309.16279), RE 2010 | Configuration constraints; open paper deposited in 2023 |
| R-05 | [Conformance Checking with Constraint Programming: A Case Study Using Feature Models](https://research.jku.at/en/publications/conformance-checking-with-constraint-programming-a-case-study-usi/), 2011 | Model conformance; metadata and public summary only; direct reload unavailable during the first review |
| R-06 | [A Security Ontology for Security Requirements Elicitation](https://doi.org/10.1007/978-3-319-15618-7_13), 2015 | Security elicitation; publisher abstract, not restricted full text |
| R-07 | [Which AI Technique Is Better to Classify Requirements? An Experiment with SVM, LSTM, and ChatGPT](https://arxiv.org/abs/2311.11547v2), 2024 | Classification limits; abstract and metadata |
| R-08 | [Synthline: A Product Line Approach for Synthetic Requirements Engineering Data Generation using Large Language Models](https://arxiv.org/abs/2505.03265v1), 2025 | Synthetic data; abstract and metadata |
| R-09 | [Easy Approach to Requirements Syntax](https://doi.org/10.1109/RE.2009.9), 2009 | Bibliographic reference; syntax also checked against a public guide in the earlier review; full paper not accessed here |
| R-10 | [OCL 2.4](https://www.omg.org/spec/OCL/2.4/PDF) | Constraint and collection sections consulted |
| R-11 | [JSON Schema Validation 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation) | Structural validation specification |
| R-12 | [SHACL](https://www.w3.org/TR/shacl/) | Optional RDF validation; not a core dependency |
| R-13 | [PROV-O](https://www.w3.org/TR/prov-o/) | Provenance concepts; no full compliance claim |
| R-14 | [Gherkin reference](https://cucumber.io/docs/gherkin/reference/) | Scenario syntax; execution requires implemented steps |
| R-15 | [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) | Existing JSON canonicalization reference; the package defines a restricted profile |
| R-18 | [Constraint-Driven Context Engineering: Designing Domain Interfaces for AI Systems](https://arxiv.org/html/2609.27354v1), 2026 | Context design; relevant sections, cases and discussion consulted; preprint |

## CROA sources

| ID | Source | Access scope |
|---|---|---|
| R-19 | [CROA: Constrained Reachability Orchestration Architecture](https://doi.org/10.5281/zenodo.21063423), Public Review Draft v1.0 | Supplied PDF; selected normative and evidence sections; exact baseline in the optional profile |
| R-20 | CROA Readiness Assessment Guide | Supplied six-page PDF, read in full; source hashes in the [audit](../review/SOURCE_AUDIT.md); companion workbook not supplied |

These sources support an optional readiness mapping, not a redesign of the core or an achieved conformance claim. [CROA profile](18_CROA_READINESS.md).

## Evaluation questions

Does the workflow detect useful defects earlier? Does graph retrieval reduce omissions and effort? What maintenance cost does the model introduce? Do gains persist across products and authors? Answer these with a defined corpus, baseline and protocol. This package contains no measured productivity or scale claim.
