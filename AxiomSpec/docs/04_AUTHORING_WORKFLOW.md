# Authoring workflow

Human and AI authors produce the same canonical objects and face the same checks. Authority to decide business meaning is separate from authorship.

## 1. Frame the problem

Record the user, situation, current behavior, desired observable outcome, data and external systems, costly failures, first scope and exclusions. Keep two or three concrete examples. Preserve the original input as a dated source.

### AX-A-001 — Source before certainty

Trace important requirements to a need, rule, observation or decision. A suggestion added to fill a template is not a confirmed requirement. Mark missing needs as questions or proposals.

## 2. Define the vocabulary

For each important term, state its context, definition, representation, unit, permitted and unknown values, owner and update authority. The same word in two contexts need not represent the same concept. Cross-context conversions are explicit transformations.

### AX-A-002 — Observable obligations

Replace vague obligations with criteria. Performance needs an operation, workload, environment, metric and threshold. Security needs an actor, asset, action and refusal case. Reliability needs failure, degraded behavior and recovery conditions. Use a review protocol when judgment cannot be reduced to a meaningful measurement.

## 3. Write atomic requirements

Use the fields and patterns in [the canonical model](03_CANONICAL_MODEL.md). Each requirement has one main obligation, applicability, responsible subject and observable response. Avoid prescribing technology unless the need requires it.

| Initial wording | Clarification needed |
|---|---|
| Never lose data | Which data, acknowledgment, failure and recovery guarantees? |
| The retry must not duplicate work | Key, scope, payload, in-progress state, retention and crash behavior |
| The agent must read documentation | Required objects, freshness, delivery and output verification |
| The service must be secure | Asset, authorization boundary, threat and negative oracle |

The layers are complementary: ordinary language for the initial need; structured language for the obligation; a typed predicate for a calculable property; a diagram for useful relationships or transitions. No diagram replaces all four. No translation between them is assumed correct.

### AX-A-003 — Blocking decisions

Create a Decision for alternatives that materially affect behavior, rights, data or compatibility. Record options, answer, rationale and source. A blocking unanswered decision prevents the affected readiness phase. Silence is not approval. Continue independent work rather than inventing the answer.

## 4. Select useful models

| Question | Model or view |
|---|---|
| Why and by which strategy? | Goals and decisions; an intentional process model if needed |
| Which transitions are allowed? | State model and statechart |
| Which concepts and relationships? | Domain model; a class view where useful |
| Which feature combinations are valid? | Feature model and configuration constraints |
| Who exchanges what and in which order? | Scenario and sequence view |
| What must always hold? | Constraint and violation examples |
| What actually happened? | Correlated traces and comparison to the expected process |

Do not create every diagram for every product. A paper sketch helps elicitation; decisions needed for implementation must enter the canonical objects.

### AX-A-004 — State the executability of effects

Transitions identify source, target, event, guard and intended effect. An effect described only by prose or a symbol reference does not support exhaustive execution exploration. Make that limitation explicit.

## 5. Formalize selected properties

State the business meaning and terms, required data and origin, expression or review protocol, positive witness, counterexample, unknown cases, enforcement boundary and tests. Include transient states that consume a resource. Two concurrent reservations must not each reuse the same available capacity.

### AX-A-005 — Prepare independent expectations

Write expectations from requirements and decisions before inspecting candidate implementation output. Additional generated tests are useful; they do not replace reference cases. Oracles may assert output, state, conservation, authorization or a reviewed judgment. A model's approval is not a deterministic oracle.

Choose relevant boundaries: empty, zero, maximum, overflow, duplicate, concurrent action, unauthorized actor, timeout, persisted write before response and recovery.

## 6. Prepare coding context

Declare the definitions, constraints, models, examples and sources needed for the change. Set classification and freshness. If required content cannot be disclosed to the executor, split the work or provide an authorized interface; do not drop the rule.

Output: scoped goals, terms, requirements, decisions, assumptions, models, constraints, scenarios, test plan, context assets and a report of checks actually available. A manual review is labeled manual. The presence of these artifacts alone does not establish `design_ready`.
