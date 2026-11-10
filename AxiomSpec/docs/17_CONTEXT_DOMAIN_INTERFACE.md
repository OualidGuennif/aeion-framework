# Context admission

Requirements and model reasoning remain the foundation. Context engineering selects faithful, authorized representations for a task. The optional graph connects documents, structured data, rules, states and traces; it does not require converting everything into RDF.

### AX-X-001 — Distinguish mechanisms

| Role | Mechanism | Evidence |
|---|---|---|
| guidance | Information delivered to the author/executor | Delivery receipt, without a compliance guarantee |
| enforcement | A boundary preventing a forbidden action | Qualified mechanism, resolved binding and refusal tests |
| verification | A check on an artifact or observation | Scoped result tied to inputs |

A prompt about file confinement is guidance, not a filesystem restriction. Post-action detection is not prevention of an irreversible action. One rule can have several roles with separate evidence.

### AX-X-002 — Declarations and resolution

ASSET records identify supported objects, representation, sources, classification, restrictions and locator. Resolution supplies actual bytes or objects and digests. Dynamic data need observation provenance and freshness rules. Derived pieces retain parent IDs/digests, transformation/version and uncertainty.

The minimal resolver supports `node:<ID>` in the fixed snapshot and `binding:<BIND-ID>` for an admitted local binding. A supplied binding_id must agree. Other locators remain provenance references until an explicit adapter exists. URLs are not fetched automatically.

### AX-X-003 — Meaning has provenance

Policy-derived rules identify the source version. Conversational rules distinguish proposal from confirmation. Incident-derived rules remain hypotheses until clarified. Reformatting tacit knowledge does not make it authoritative.

### AX-X-004 — Admission order

Inputs: task, affected requirements, fixed specification snapshot, trusted principal/policy, explicit time and response budget.

1. Resolve applicability and mandatory closure.
2. Identify required assets.
3. Check rights before content disclosure.
4. Resolve only admitted available locators.
5. Verify digests and freshness.
6. Select faithful representations retaining source access.
7. Deliver required objects without semantic truncation.
8. Add optional objects in deterministic order.
9. Record provenance, omissions and limits.

A failed required step prevents a complete packet. Do not fetch forbidden data elsewhere to compensate.

### AX-X-005 — Hard rules survive budget pressure

Split context or the task when mandatory content exceeds budget. Record part count and complete-closure digest. A required forbidden asset leaves a condition unsatisfied without revealing restricted metadata; route that work to an authorized task.

### AX-X-006 — Preferences do not offset violations

Soft preferences choose among admissible solutions. No weighted score compensates for a hard violation. Conflicting domain rules require an explicit decision, not a misleading optimum.

### AX-X-007 — Time is input data

Tie observations and policies to versions and windows. Freshness checks receive observed_at, evaluated_at and clock assumptions. Unknown clock uncertainty cannot satisfy a strong freshness claim. Stable documents may have no TTL but must still match the requested version.

### AX-X-008 — AI proposals retain provenance

Proposed terms, criteria and requirement decompositions retain sources and open questions. Run structural checks immediately; accept meaning under project authority. A contradiction opens a decision or defect rather than silently correcting the source. Model review is not deterministic business proof.

### AX-X-009 — Govern rule evolution

Any rule family may change with source, authority, rationale, effective window, impact and tests. Keep prior baselines and their evidence. Do not accumulate every historical rule into an unqualified union.

An asset should explain why it is included and which obligation it supports. Evaluate useful task completion and detection of known violations against cost and omissions, not context volume.
