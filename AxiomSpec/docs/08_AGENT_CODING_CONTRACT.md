# Coding-agent contract

A developer or agent receives a bounded task, admitted context, rights and expected verification. It does not become the sole authority for requirements or acceptance.

### AX-D-001 — Change packet

Include change ID, objective, scope/exclusions, specification/source/policy/graph digests, affected requirements and components, impact limits, hard rules, optional preferences, context references, tests/oracles/runners, required decisions and delivery criteria.

Incomplete packets permit investigation or independent work, not invented business answers.

## Execution mode and decision rights

Execution cadence and decision authority are separate. A task may run without step-by-step interaction while protected decisions still require an authorized decision-maker.

The optional [execution declaration](../schemas/execution.schema.json) belongs to the task packet, not to each requirement or the canonical product root:

```json
{
  "format": "axiomspec-execution/0.1",
  "execution_mode": "bounded_autonomous",
  "decision_policy_ref": {"id": "example-policy/v1", "sha256": null}
}
```

`assisted` is an interactive workflow; `bounded_autonomous` allows routine execution within the task's authorized scope and pinned policy. Neither mode grants permissions. A null/unverified policy digest cannot authorize autonomous work. The example is a declaration fixture, not an authorization.

Policy defines which technical choices are delegated and which changes require a new decision. Typical protected decisions concern behavior, rights, data retention, irreversible migration, external publication or deployment. An unresolved protected decision pauses the affected work; independent authorized work may continue. A test failure or exhausted budget is not permission to relax the rule.

If a UI needs `autonomous: true/false`, derive it from the validated mode. Do not persist a second authority flag. A mode change requires a refreshed packet and applicable G08-G12 checks. CROA exposure item A4 concerns observed operation, not this declared string.

## Work sequence

1. Verify task scope, snapshots and required context.
2. Inspect the actual code path, interfaces, tests and configuration.
3. Compare discovered impact with the packet.
4. Implement the smallest coherent change.
5. Preserve oracles and add relevant tests.
6. Run authorized verification, update bindings, regenerate views and collect evidence on the final inputs.
7. Return actual results and remaining limits.

### AX-D-002 — Scope changes

New affected requirements, unmapped symbols or data boundaries require a revised change and context calculation. Do not treat the initial packet as complete after discovering new impact. Unrelated cleanup and abstractions need a concrete benefit.

### AX-D-003 — Preserve oracles

Distinguish observed failure, confirmed cause and hypothesis. Changing an expected result requires a justified test correction or a corresponding approved requirement change. Tests from the same assumptions as the implementation are not independent validation. Multiple agents do not automatically provide independence.

### AX-D-004 — Preserve verification levels

Mocks do not validate real transaction concurrency. Internal function tests are not end-to-end scenarios. Compilation does not verify authorization. Receipts state the levels and environments actually executed.

### AX-D-005 — Propose specification changes explicitly

A proposed rule change identifies problem, source, alternatives and impact. Record behavior-changing decisions before accepting implementation against them. Edit generated documentation through its source/generator. A hard-rule change invalidates affected evidence.

### AX-D-006 — Return evidence

Return implemented requirements, files changed, new risks, actual commands/results, receipts/digests, proposed specification changes, unresolved bindings and unknowns. The summary does not replace raw evidence.

## Execution boundaries

Validation never runs project scripts. Resolve runner names through trusted adapters rather than shell interpolation. Isolate test data. External effects require the task's real authority; a fixture endpoint is not permission to contact it. Filesystem/network restrictions come from the environment, not a prompt promise.

Review depth follows risk and policy. Add another agent only for useful capability, information or independence. At handoff, preserve change ID, digests, decisions, failures and next action. Recheck changeable facts and invalidated evidence when resuming.
