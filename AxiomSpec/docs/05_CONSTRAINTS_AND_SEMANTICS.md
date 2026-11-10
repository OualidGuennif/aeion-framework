# BCIR 0.1 constraint semantics

BCIR is a proposed **Bounded Constraint Intermediate Representation**. It is a small pure AST, not a general programming language, OCL implementation or automatic natural-language compiler. Compare its implementation cost with reusable tools before building a compiler.

### AX-C-001 — Explicit inputs and no effects

Evaluation receives an expression, validated environment, profile and resource limits. It reads no files, network, process environment or system clock and changes no business state.

### AX-C-002 — Restricted environment schemas

Allowed keywords: type, properties, required, additionalProperties, items, enum, minimum, maximum, minItems, maxItems, minLength, maxLength, description. Allowed types: object, array, integer, boolean, string.

Objects are closed and every declared property is required. Arrays have maxItems, strings maxLength, integers safe minimum and maximum. Exclude unions, references, conditional schemas, regex patterns, dynamic evaluation and implicit extensions. This restriction concerns BCIR environments; the package's own artifact schemas use full JSON Schema.

## Expression forms

| kind | Fields | Result |
|---|---|---|
| literal | value | Boolean, safe integer, string or homogeneous scalar array |
| path | root, pointer | Declared value |
| apply | operator, arguments | Operator result |
| aggregate | operator, bind, collection, filter, projection | Integer |
| quantifier | operator, bind, collection, predicate | Boolean |

`env` is the complete environment; another root is a bound collection variable. Paths are object-field JSON Pointers. Empty pointer selects the root. Decode `~1` then `~0` exactly once; reject any other `~` escape. Do not traverse arrays by index or wildcard; bind their elements. Unknown paths or roots are errors during static analysis. Missing operational data are an unknown result, not an empty collection.

### AX-C-003 — Variable scope

Collection variables are lowercase ASCII identifiers. They cannot be `env` or shadow enclosing variables. Their type is the element type; their scope is their own filter/projection/predicate. Iterations retain no variable state.

### AX-C-004 — Operators

| Operator | Arity | Types |
|---|---:|---|
| and, or | at least 2 | Booleans |
| not | 1 | Boolean |
| implies | 2 | Booleans |
| eq, ne | 2 | Same scalar type, including compatible units for integers |
| lt, le, gt, ge | 2 | Integers with compatible units |
| add, sub | 2 | Integers with the same unit |
| mul | 2 | At least one operand dimensionless |
| in | 2 | Scalar and homogeneous scalar array of that type |

No coercion. String equality is exact, case-sensitive Unicode equality without normalization. Exclude array equality, division, floating point, implicit dates, regexes, user functions and method calls. An empty literal array in `in` takes its expected element type from the left operand.

The reference traversal is explicit: visit apply arguments eagerly, left to right; do not short-circuit Boolean operators. Visit collection items in stored order and evaluate every quantifier predicate. For aggregates, evaluate each filter, then its projection if retained; validate and collect retained projections before the final left-to-right sum/count reduction. Static analysis still precedes runtime visits.

A qualified optimized adapter must preserve completed Boolean/error semantics and declare its engine version and work accounting. Budget exhaustion may differ between implementations; unknown is not a contradictory Boolean result. Do not compare or reuse receipts across those versions. A changed operator meaning or profile contract needs a profile revision; an equivalent implementation optimization still needs pinned tool identity and differential qualification.

### AX-C-005 — Aggregates

Collection is finite; filter is Boolean. `sum` adds integer projections in a common unit, preserving duplicates. Empty sum is zero in the statically established projection unit. `count` counts retained elements and requires projection to be the literal integer 1. Validate all intermediate integers against the safe range; overflow is an error.

### AX-C-006 — Quantifiers

`all` is true on an empty collection; `exists` is false. Report vacuous cases separately when relevant to coverage. Include nonempty witnesses in the test plan. Missing data must not be replaced with a favorable empty collection.

### AX-C-007 — Analyze before evaluation

Validate every path, scope, operator, arity and type before execution, including branches that could be short-circuited. The constraint result is Boolean. An integer does not become a Boolean by being nonzero; a Python Boolean does not become an integer.

The package reference evaluator is not this complete static compiler. It exercises selected fixtures only.

### AX-C-012 — Predicate role

`predicate_role` is invariant, admission_guard, observation_assertion or review. An invariant holds on admissible states in its scope. A false admission guard may be the correct result of a refused request. An observation assertion applies in its declared evaluation context.

Review requires representation `review_protocol`, a non-null protocol and null expression. Other roles require BCIR, an environment and expression, with null review protocol. A positive witness cannot expect an applicable hard invariant to be false. Do not infer predicate role from a title or binding.

### AX-C-008 — Units

Environment annotations reference Term IDs. Unannotated integers are dimensionless. Calculated values preserve units. Literal zero may take the expected unit; other integer literals are dimensionless. Supply dimensioned constants through annotated environment paths.

Annotation patterns may use `*` only for an array-element level, such as `/state/refunds/*/amount_minor`. They must resolve to integer leaves without conflicting annotations. This is annotation syntax, not a wildcard expression path. A nearby currency field does not establish unit compatibility.

### AX-C-009 — Results

| Result | Meaning |
|---|---|
| pass | Boolean true on the stated validated data |
| fail | Boolean false; include a counter-observation where feasible |
| unknown | Missing data/capability, incomplete search or exhausted budget |
| error | Invalid syntax/type, overflow or processing contract violation |
| not_applicable | Not required in this scope, with a policy-grounded reason |

Invalid input is not downgraded to unknown. A valid unsupported extension may be unknown. A false predicate can satisfy a negative fixture's expected result; that validates the fixture, not the invalid business state.

### AX-C-010 — Resource bounds

| Resource | Default |
|---|---:|
| Canonical input bytes | 1,048,576 |
| Canonical nodes / edges | 10,000 / 50,000 |
| Expression depth / nodes | 24 / 2,000 |
| Observation collection items | 10,000 |
| Steps per evaluation | 1,000,000 |
| Bounded exploration combinations | 100,000 |

Count a step per expression-node visit and collection iteration. Reset per evaluation. Record actual bounds. A wall-clock timeout never yields pass. Larger limits require explicit configuration and qualification.

These bounds do not promise completion for every structurally valid input. The reference uniqueness constraint CON-004 is quadratic: 500 ledger rows exceed the default step budget although the environment permits 1,000. Preserve unknown on exhaustion. Qualify the algorithm and its declared work budget together before claiming full-bound coverage; either an explicit measured budget or a versioned equivalent method needs evidence. Never raise a bound silently.

## Example

The consumed capacity is the sum of reserved and committed amounts. It must not exceed captured capacity.

```json
{
  "kind": "apply", "operator": "le", "arguments": [
    {
      "kind": "aggregate", "operator": "sum", "bind": "r",
      "collection": {"kind": "path", "root": "env", "pointer": "/state/refunds"},
      "filter": {"kind": "apply", "operator": "in", "arguments": [
        {"kind": "path", "root": "r", "pointer": "/status"},
        {"kind": "literal", "value": ["reserved", "committed"]}
      ]},
      "projection": {"kind": "path", "root": "r", "pointer": "/amount_minor"}
    },
    {"kind": "path", "root": "env", "pointer": "/state/captured_minor"}
  ]
}
```

For capacity 1,000, amounts 600 and 400 satisfy this predicate; 600 and 401 violate it. This formula does not implement atomic reservation or prove concurrency safety.

### AX-C-011 — No unqualified equivalence

The core evaluates finite observations. It does not automatically prove satisfiability, reachability or conformance of arbitrary code. Exhaustive exploration requires finite domains, executable transition effects and completed enumeration.

Record solver version, logic, assumptions, domain, timeout and status when an adapter is used. EARS-to-BCIR and BCIR-to-OCL/SMT transformations must declare their supported subsets and test equivalence in that scope. Judgment-based obligations retain a review protocol.

### AX-C-013 — Effective window

An active rule applies when `effective_from <= evaluated_at < effective_until`, with null bounds open. Validate UTC instants and reject empty or reversed intervals. If a bound exists and evaluation time is missing, applicability is unknown. Out-of-window is not pass. Observation freshness is a separate condition.
