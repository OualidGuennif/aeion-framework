# Canonical model

The [schema](../schemas/spec.schema.json) defines `axiomspec/0.2`. This document and the constraint, gate and query contracts define additional semantics.

## Transport and identity

### AX-M-001 — Strict transport

Use strict UTF-8 JSON. Reject duplicate keys, non-integer numbers, NaN, Infinity, invalid scalar Unicode and trailing data. Integers are limited to `[-9007199254740991, 9007199254740991]`; booleans are not integers. Object keys are ASCII. Validation must not fetch external schemas or documents.

### AX-M-002 — Root fields

| Field | Content |
|---|---|
| format / profile | `axiomspec/0.2` / `AX-CORE-0.2` |
| release | Version, the previous release it succeeds, compatibility decisions |
| project | ID, name, description, owner, mode `product` or `example`, weight minor units |
| actors / sources | Declared roles and provenance |
| environments | Bounded input schemas and unit annotations |
| flags | Feature flags and their state in this release |
| nodes / edges | Normative objects and declared typed relationships |
| bindings | Planned or required implementation selectors |
| context_assets | Context declarations and access restrictions |

Readiness is calculated in external reports. There is no authorable `is_ready` or `all_tests_passed` field. Example mode cannot authorize production acceptance.

### AX-M-003 — Stable identifiers

IDs follow `^[A-Z][A-Z0-9_]*-[0-9]{3,6}$`, are unique across the canonical package and use reserved prefixes:

| Object | Prefix |
|---|---|
| Project, actor, source, environment | PROJECT, ACTOR, SRC, ENV |
| Goal, term, requirement | GOAL, TERM, REQ |
| Constraint, state model, scenario | CON, MODEL, SCN |
| Test case, component | TEST, COMP |
| Decision, assumption | DEC, ASM |
| Risk, control | RISK, CTRL |
| Edge, binding, context asset | EDGE, BIND, ASSET |
| Feature flag | FLAG |

Retain IDs through renames and retirement. Never reuse an ID for a different meaning. Transition IDs `TRN-*` are local to their StateModel and unique within that model.

### AX-M-004 — Common node fields

Every node has `id`, `kind`, positive integer `revision`, `status`, `title`, `owner`, `created_by`, `source_ids` and `data`. Status is `draft`, `active` or `retired`. Active means applicable in the model, not authenticated approval. Owner and author reference declared actors.

### AX-M-005 — Node kinds

| Kind | Data fields |
|---|---|
| Goal | description, success_measure |
| Term | definition, aliases, unit, context |
| Requirement | category, priority, risk, weight_minor, verification_mode, pattern, conditions, trigger, feature, subject, response, flag_id |
| Constraint | classification, scope, roles, predicate_role, representation, environment_id, expression, review_protocol, enforcement_binding_id, effective_from, effective_until |
| StateModel | environment_id, initial, states, transitions |
| Scenario | intent, environment_id, given, event, expected, constraint_expectations |
| TestCase | level, oracle, state, runner, negative, witness_scenario_ids, flag_states |
| Component | responsibility, boundary |
| Decision | question, options, answer, blocking, rationale |
| Assumption | claim, validation_method, state, blocking |
| Risk | asset, threat, impact, severity |
| Control | description, enforcement_location, verification |

The schema closes properties and defines their types. An extension requires a new profile version rather than a free-form escape field.

## Requirements

### AX-M-006 — Structured authoring and rendering

Render normative wording from structured fields. Do not add a competing editable `statement`.

| Pattern | Populated fields | English rendering |
|---|---|---|
| ubiquitous | subject, response | The subject shall response. |
| event | trigger, subject, response | When trigger, the subject shall response. |
| state | conditions, subject, response | While conditions, the subject shall response. |
| unwanted | trigger, subject, response | If trigger, then the subject shall response. |
| optional | feature, subject, response | Where feature, the subject shall response. |
| composite | conditions, trigger, subject, response | While conditions, when trigger, the subject shall response. |

Join conditions in declared order with ` and `. Unused conditions are `[]`; unused trigger and feature are null. Ignore no populated field. Subject and response are nonempty. Rendering adds connective words, not meaning or translation.

Categories: functional, quality, security, privacy, data. Priorities: must, should, could. Risks: low, medium, high, critical. Verification modes: executable, manual, mixed. The weight and its relation to the risk label are in AX-M-018. An `optional` requirement names in `flag_id` the flag that turns its feature on (AX-M-019); `feature` stays the wording that is rendered.

### AX-M-007 — Formalization is a modeling decision

A `formalizes` edge does not prove that a formula and sentence are equivalent. Review that interpretation. Similarity judgments may assist but do not close the decision.

## Constraints and environments

### AX-M-008 — Separate classification and operation

Classification fields are:

- category: domain, technical, regulatory, institutional, normative
- explicitness: explicit, elicited
- temporality: predefined, dynamic
- strength: hard, soft

Roles are a nonempty unique list of guidance, enforcement and verification. Scope is `project` or `linked`. Applicable hard project rules belong to every change packet; linked rules follow the requirements they formalize.

Representation is `bcir` or `review_protocol`. BCIR requires an expression and environment with no review protocol. A review requires an explicit protocol and no expression. Predicate roles and consistency rules are defined in AX-C-012. Time bounds are UTC timestamps or null; null means no declared bound. Dynamic rules must explain how freshness is established.

### AX-M-009 — Environments

An environment has ID, title, a restricted schema and unit annotations pointing to Term IDs. Define representations and conversions explicitly. An observed currency string does not prove unit compatibility.

An operational observation also needs adapter identity, version and coverage limits. Synthetic data remain synthetic.

## Relationships

### AX-M-010 — Typed directed edges

| Relation | Source -> target |
|---|---|
| satisfies | Requirement -> Goal |
| uses_term | Requirement or Constraint -> Term |
| formalizes | Constraint -> Requirement |
| models | StateModel -> Requirement |
| illustrates | Scenario -> Requirement |
| verifies | TestCase -> Requirement |
| checks | TestCase -> Constraint |
| implements | Component -> Requirement |
| depends_on | Requirement -> Requirement |
| assumes | Requirement or Constraint -> Assumption |
| governs | Decision -> Goal, Requirement, Constraint or StateModel |
| threatens | Risk -> Goal or Requirement |
| mitigates | Control -> Risk |
| realizes | Requirement -> Control |

Each edge has an ID, `from`, `relation`, `to`, `origin: declared` and rationale. Endpoints must exist with permitted kinds. A given source, relation and target is declared once; a second edge with the same three is a duplicate, not a stronger link. Extracted code relationships belong to a derived provenance layer.

### AX-M-011 — Cycles and retirement

Active requirement dependencies must be acyclic in this profile. Refine genuinely reciprocal requirements rather than deleting a real dependency to pass validation. Other graphs, including state machines, may contain cycles. Active links to retired objects are invalid in a new baseline; historical snapshots retain them.

## Sources and implementation

### AX-M-012 — Sources

A source has ID, type, locator, nullable capture digest and review state. Types are user_input, document, policy, standard, incident and fixture. Review states are unreviewed, reviewed and fixture. A locator grants no access; reviewed is an assertion, not a signature.

### AX-M-013 — Actors

Actors have ID, name, type human_role/ai/service and binding status unbound/asserted/verified. A trusted adapter must establish any identity required for acceptance. Editing the status cannot satisfy that obligation.

### AX-M-014 — Bindings

Bindings contain ID, kind, node_id, path, symbol, language and expected_resolution. Kinds: code, test, enforcement, observation. Languages: python, typescript, java, generic. Resolution is planned or must_resolve.

| Binding kind | Node it names | Meaning |
|---|---|---|
| code | Component, or a Constraint's evaluation method | Where the responsibility or the calculation is realized |
| test | TestCase | The test artifact a receipt will identify |
| enforcement | Constraint or Control | The boundary that prevents the forbidden action |
| observation | Constraint or Requirement | Where runtime observations of it are produced |

A requirement is realized through a Component and verified through a TestCase; binding code or a test directly to a Requirement skips the object that carries the claim.

Paths are repository-relative with `/`, without absolute paths, URLs or `..`. Reject symlink escapes. A selector is not evidence of resolution. A resolution receipt identifies the file digest, actual location, extractor and version. File existence alone does not resolve a symbol or establish a call relationship.

### AX-M-015 — Derived documentation

Generated views identify the profile, specification digest and generator version. Requirement sections retain IDs. Detect or overwrite local edits to generated views. Do not use a model to decide normative applicability during generation. Diagrams are views; exports must state semantic loss.

Escape untrusted values for each output context, including Markdown, diagram labels and links. Emit diagram identities and edges from canonical records, not embedded label syntax. Raw HTML or diagram directives inside a requirement are data, not generator instructions.

### AX-M-016 — Context assets

Each asset has ID, title, representation, classification, source_ids, supports, allowed_roles, locator, binding_id, max_age_seconds and `instruction_trust: data_only`.

Representations are document, structured, rule, state and trace. Classifications are public, internal, confidential and restricted. Supported nodes are goals, terms, requirements, constraints, models and decisions. Intersect declared roles with trusted policy; declarations grant no permission. Resolution receipts establish actual bytes and freshness. A null age limit does not waive a policy requirement for fresh data.

## Releases, weights and flags

### AX-M-017 — Release

`release` holds `version`, `previous` and `compatibility`. The version is `MAJOR.MINOR.PATCH` in decimal integers, compared as numbers. `previous` is null for a first release. Otherwise it names the baseline this release succeeds by version and canonical digest, and the version is exactly the next major, minor or patch after it.

Three things identify three different objects. A node's `revision` counts changes to that one object. The release version names the whole specification for people. The canonical digest identifies its exact bytes, and evidence stays bound to the digest.

`compatibility` records the decisions taken about this release's breaking candidates (AX-L-007): the subject ID, `breaking` or `compatible`, the active answered Decision that says so and, for `breaking`, a migration statement. It concerns this release only and is rewritten for the next one. A first release has none. Comparing a release with its baseline needs both documents and is gate G14.

### AX-M-018 — Weights in minor units

Every requirement carries an integer `weight_minor`: how much the product depends on that requirement holding, from 1 to 100 points. `project.weight_minor_units` states once how many minor units make one point: 1, 10, 100 or 1000.

| `weight_minor_units` | One point is written | 37.5 points is written | Valid `weight_minor` |
|---|---|---|---|
| 1 | 1 | not expressible | 1 to 100 |
| 10 | 10 | 375 | 10 to 1000 |
| 100 | 100 | 3750 | 100 to 10000 |
| 1000 | 1000 | 37500 | 1000 to 100000 |

No number in a specification is a fraction. Any quantity attached to a requirement is an integer in declared minor units, as monetary amounts are, and a derived quantity states its own units (AX-L-009).

The `risk` label is kept and is the band of the weight: low up to 25 points, medium above 25 up to 50, high above 50 up to 75, critical above 75. The verification obligations keyed on risk (AX-G-007) therefore follow the weight. A label that disagrees with the weight is an error, not a warning.

A weight ranks. It is not a probability, and no sum of weights compensates for a failed gate.

### AX-M-019 — Feature flags

`flags` declares each flag once: ID, `key` (the name the running product reads), title, `state` enabled or disabled, owner, `introduced_in` and `remove_by`.

- A requirement's `flag_id` puts its behavior behind that flag. An `optional` requirement must name one. A flag that governs no requirement is an error.
- `state` is the default this release ships with. Each release records its own states, so "which flags were on in 2.3.0" is answered by that release, and the comparison of two releases reports every switch (AX-L-007). A per-deployment override is runtime configuration: it is outside the specification and its observation belongs to G13.
- A flag waives nothing. A requirement behind a disabled flag stays in the model with all its gates. An active must requirement behind a flag is verified by an active TestCase with the flag enabled and by another with it disabled, stated in `flag_states`; the disabled case asserts what the product does without the feature.
- `introduced_in` is not later than the release. `remove_by` is null or later than `introduced_in`. Once the release version reaches `remove_by`, the flag is stale and the baseline fails until the flag is removed and its requirement is made unconditional or retired.
