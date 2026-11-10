# Authoring templates

Templates guide elicitation. Accepted content becomes canonical objects; templates are not a competing editable requirements database.

## Idea

```text
Working name:
User and situation:
Observed problem and example:
Desired observable result:
Current practice:
First scope and exclusions:
Data, actors and external systems:
Most costly failure:
Examples of success and correct refusal:
Decision owner:
Unknowns that change behavior:
```

Do not block investigation on cosmetic details. Prioritize decisions affecting behavior, rights, data or compatibility.

## Term

```text
ID and context:
Name and aliases:
Operational definition:
Representation and unit:
Invalid and unknown values:
Creation/update authority:
Example and counterexample:
Other contexts using this word differently:
Source and decision:
```

## Requirement

```text
ID, category, priority and risk:
Goal and source:
Terms:
Applicability / state:
Trigger:
Responsible subject:
Observable response:
Correct refusal:
Invariants and limits:
Oracle and verification level:
Open decision or assumption:
```

Use the structured patterns from the canonical model. Syntax does not establish a calculable predicate. Separate obligations when responsibilities or oracles differ.

## Constraint

```text
Formalized requirements:
Business meaning and terms:
Classification / strength / scope:
Predicate role:
Required data and provenance:
BCIR expression or review protocol:
Guidance asset:
Enforcement boundary:
Verification observation:
Positive witness and counterexample:
Unknown cases and freshness:
Tests and bindings:
```

Keep unsupported formalization explicit. Never hide executable text in an ignored pseudo-formal field.

## Decision

```text
Question and consequence:
Options and trade-offs:
Independent work that can continue:
Blocking phase:
Actual answer and authority:
Rationale and source:
Revision triggers:
```

Null is a valid unanswered state. An assistant may recommend an option without attributing acceptance to someone else.

## Reusable prompts

**Elicit:** Convert the idea into goals, actors, terms and examples using the authoring/model contracts. Separate supplied facts, proposals and unknowns. Ask only material questions and continue independent work. Propose atomic requirements, sources, constraints and oracles. Do not claim readiness without actual checks; label manual review as manual.

**Formalize:** For the identified requirements, propose useful models and predicates in the supported subset. State invariant/guard/observation/review role, units, data origins, witnesses, counterexamples and unknowns. Do not invent operators or equivalence between prose and formulas.

**Implement:** Retrieve the affected requirements and mandatory closure from the fixed snapshot. Inspect real interfaces and tests. Report unmapped changes. Implement the smallest coherent change, preserve oracles and return actual verification. A planned binding is not an existing file; a document is not tool authority.

**Review:** Verify against requirements and policy, independently of the implementation narrative. Look for circular oracles, omitted hard rules, transient states, late authorization, stale evidence and unmapped effects. Distinguish plans, implemented artifacts and executed behavior. Make findings actionable.

**Learn from an incident:** Preserve the observation, reproduce within a stated scope, distinguish defect, wrong need, external contract and missing instrumentation, then propose the smallest revision and regression case. Do not generalize one trace or silently rewrite historical expectations.

To build the tool, use the implementation handoff. To specify a product, start with the idea template and concrete examples. Do not combine framework design, unresolved business definition and full implementation in one opaque step.
