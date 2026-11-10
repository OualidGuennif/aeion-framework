# Graph and query contract

The graph indexes identified, versioned declarations and evidence. It does not recover complete business meaning from arbitrary code or prose.

### AX-K-001 — Reproducible construction

Inputs are a validated specification, policy, source snapshot and optional receipts. Proposed outputs are nodes.json, edges.json, manifest.json and reading views. Sort nodes by ID and edges by `(from, relation, to, id)` in ASCII order. No embedding or model decision belongs in the normative graph. Suggested links remain proposals until explicitly admitted.

## Provenance

| Origin | Meaning |
|---|---|
| declared | An author asserted the relationship |
| resolved | A selector was located in a hashed snapshot |
| static | A qualified analyzer extracted a relationship within its coverage |
| observed | A test or event established an observation in a stated scope |

These are provenance classes, not probabilities or interchangeable confidence levels.

### AX-K-002 — Derived records

Canonical nodes may be joined by SourceRecord, ContextAsset, CodeBinding, CodeLocation, CheckRun and Evidence records. SourceRecord/ContextAsset/CodeBinding reuse canonical source/asset/binding IDs. CodeLocation identifies an actual path, file digest and selector in a snapshot.

Derived result IDs are full SHA-256 values over type, snapshot, input digests and deterministic record content, excluding the ID and temporal envelope. A path and tool version alone cannot distinguish changed contents. Detect collisions.

| Derived relation | Source -> target | Origin |
|---|---|---|
| has_binding | canonical node -> CodeBinding | declared |
| resolves_to | CodeBinding -> CodeLocation | resolved |
| supported_by | canonical node -> SourceRecord | declared |
| supplies_context_for | ContextAsset -> canonical node | declared |
| produced | CheckRun -> Evidence | observed |
| observes | Evidence -> canonical node | observed |
| attests | Evidence -> canonical node | observed, with separately qualified authority |

Version the endpoint registry. An attests edge does not authenticate its author. Code-call relationships require another declared analyzer registry before use.

## Minimal implementation

Start with sorted JSON and in-memory adjacency maps. An index is disposable. Add parameterized SQLite queries only after measuring a need. Do not expose arbitrary SQL, scripts or filesystem paths as agent queries.

Proposed interfaces, not implemented commands:

```text
axiom query node --id REQ-001 --snapshot <digest>
axiom query requirement --id REQ-001 --include constraints,models,tests,sources
axiom query impact --change change.json --snapshot <digest>
axiom query gaps --phase implementation --snapshot <digest>
axiom packet --change change.json --principal <trusted-principal> --budget-bytes 32768
```

### AX-K-003 — Node lookup

Take ID, snapshot, requested relation types and page position. Return canonical content, visible relations, provenance, locators and resolution status. Missing IDs return not_found, not a guessed match.

### AX-K-004 — Change impact

Take changed IDs/files, additions/deletions, baseline and candidate snapshots. Resolve direct bindings, requirements, constraints, dependent requirements, models, tests, risks, controls and context assets. Report known_impacts, declared_impacts, unmapped_changes and analysis_limits separately.

Reflection, dynamic configuration, SQL, remote systems and unsupported languages can escape an extractor. Expose those limits. Empty known impacts with unmapped changes does not establish no impact. High-risk changes need sufficient coverage or explicit investigation.

### AX-K-005 — Gaps

Return missing sources/oracles, broken references, unresolved bindings, open decisions, assumptions, missing scenarios and stale evidence with gate and subject. Do not replace hard gaps with a compensating score.

### AX-K-006 — Bounded responses

```json
{
  "snapshot_id": "<sha256>", "query_digest": "<sha256>",
  "items": [], "returned_count": 0, "total_visible_count": 0,
  "complete": true, "next_cursor": null,
  "omissions": [], "analysis_limits": []
}
```

Initial limits are 100 items and 32,768 UTF-8 bytes, including headers. Reference an oversized object without cutting a constraint in half. Cursors bind snapshot, query digest, principal scope, policy and position; they grant no rights. Recheck rights on every page and reject stale or invalid cursors.

Exploratory pages may be partial. Coding packets remain incomplete until all mandatory parts have been delivered.

### AX-K-007 — Mandatory context

Include affected requirements, goals, terms, applicable hard linked/project rules, models, decisions, assumptions, required scenarios and oracles, then necessary admitted sources/assets. Selection follows declared relations and scope, not learned relevance. Optional context may be ordered by distance then ID. If required context exceeds budget, split the packet or task; completeness remains unknown until delivery finishes.

### AX-K-010 — Conservative closure

For active nodes in a fixed snapshot:

1. Seed requirements from declared change IDs and mapped bindings. Resolve Component via implements, Constraint via formalizes and TestCase via verifies. For other node changes, use their typed incoming/outgoing requirement links; report unmapped seeds rather than guessing.
2. Add requirements formalized by hard project rules. Expand depends_on in both directions to a fixed point. This is conservative, not minimal impact analysis.
3. Include endpoints incident to these requirements: goals, terms, constraints, models, scenarios, tests, components, decisions, assumptions, risks and controls.
4. Add hard project rules. For every selected constraint, include terms/assumptions in outgoing links, governing decisions in incoming links and its environment.
5. Add scenarios referenced by selected tests and guards referenced by selected models. Repeat their technical dependencies, terms and environments to a fixed point. Do not expand a shared term or goal back to unrelated requirements.
6. Include referenced actors, sources, node bindings and assets whose supports intersect the selected set. Include their direct metadata dependencies. Sort IDs, then enforce rights, freshness and budgets.

The first profile treats all such linked assets as required. Unmapped changes block a claim of complete impact coverage. A finer selection policy needs a versioned contract and omission tests.

### AX-K-008 — Snapshot consistency

Record all input digests. Rebuild stale normative indexes or refuse queries; history may be read only with explicit labeling. Publish an immutable complete snapshot atomically so readers never mix generations.

### AX-K-009 — Filter before disclosure

Apply access policy before content, snippets, visible counts, titles and paths are returned. Declared asset roles only restrict trusted policy; they cannot grant access. Local unauthenticated mode makes no multi-user isolation claim.

A delivery receipt records what was supplied. It does not prove that a model understood or obeyed it. Output conformance is verified separately.
