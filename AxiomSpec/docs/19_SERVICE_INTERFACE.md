# Service interface

How a coding agent and an organization reach a release without holding the whole specification.

The interface is three files: [openapi.json](../api/openapi.json) for HTTP, [mcp-tools.json](../api/mcp-tools.json) for MCP and [graph.schema.json](../schemas/graph.schema.json) for the index. `qa/graph_index.py` and `qa/queries.py` are the reference implementations; a reference server that transports them lives beside the package. The specification format is unchanged: everything here is derived from a release.

## What the agent holds

An agent that builds a feature is not given the specification. It is given an index, code that names the requirements it carries, and a service it may ask.

### AX-V-001 — Graph index

The index of a release (`axiomspec-graph/0.1`) lists every node by ID, kind, status and title, every declared link, and every trace: a place in the code or tests and the requirements behind it. A requirement also carries its priority, risk, weight and flag. The index names its release by canonical digest.

It is sorted and is a function of the release and the annotations. It is written as JSON with one record per line, so a line search for an ID or a file path returns exactly the records that mention it. It is a derived view: it never replaces the specification and is rebuilt, not edited.

### AX-V-002 — Requirement annotations

An annotation is the token `@req` followed by one or more IDs, in a comment or docstring of a source file:

```text
# @req REQ-004 CON-005
def authorize(principal, request_tenant, resource_tenant):
```

- It belongs to the definition a comment block directly precedes, otherwise to the innermost definition that contains it, otherwise to the file. Symbols are resolved for Python; elsewhere the location is the file and line.
- It names an object the release holds and has not retired. Anything else fails the scan.
- It yields a trace of kind `test` in a test file and `code` elsewhere. A trace on a constraint, component or test leads to the requirements that object concerns.
- An active must requirement with no binding and no annotation in code is reported as a gap of the implementation phase.

An annotation is a declared link, like a binding. It says where an author placed a requirement. It does not show that the code satisfies it; an executed test does.

## Reading

### AX-V-003 — Immutable reads

Every read is a GET on a release named by its canonical digest. The answer cannot change, so it carries an ETag and may be cached without limit. A service that serves exactly one release also accepts `current` in place of the digest; that form is not cached, and the answer still names the digest.

Reads are bounded as AX-K-006 states: at most 100 items and 32,768 bytes, with a cursor bound to the snapshot and the query. A cursor holds no state on the service and grants nothing. An object that cannot fit the budget is named in `omissions` and never cut, and `complete` is true only when the whole answer was deliverable.

An unknown ID is `not_found`. Errors are problem documents (RFC 9457) with a stable `code`.

### AX-V-004 — One behavior, two transports

Each operation is defined once. The HTTP route and the MCP tool for it return the same answer under the same schema, and neither adds behavior. The tool list is kept short, because every tool definition is read by the agent before it asks anything: four tools for an agent, four more for authoring.

The queries are a fixed set. There is no query language, no free-form search and no access to files: selection follows declared links and annotations only, and nothing is ranked or learned.

### AX-V-005 — Context scopes

A question about a requirement has three depths. An agent takes the first that answers it.

| Depth | Operation | Returns | On the ledger |
|---|---|---|---|
| Brief | `lookup` | The requirement as a sentence, its weight and risk, the IDs and titles linked to it, and where it is implemented and tested | 2 to 6 KB |
| Direct | `context`, scope `direct` | The requirement with its goals, terms, assumptions and governing decisions, the constraints that formalize it with their environments, and every hard project rule | 9 to 22 KB, one page |
| Change | `context`, scope `change` | The conservative closure of AX-K-010: also the requirements under project rules, with scenarios, tests and components | 79 to 90 KB, three pages |

The direct scope answers "what does this demand and what binds it". It is not the mandatory context of a change, and its answer says so. Before changing behavior, the change scope is required (AX-K-007) and stays incomplete until every page is delivered.

The change scope is conservative by design. On a specification as small and connected as the ledger it returns most of it; it is the direct scope that keeps an ordinary question small.

### AX-V-006 — Sandbox mode

In sandbox mode the service serves one release, chosen when it starts, and only the read operations. No other method and no other route exists. It runs outside the agent's sandbox, which is allowed to reach it by host and port for GET only.

The task names the release by digest. Every answer carries that digest, so an agent cannot mix two versions of the requirements within one task (AX-K-008).

An agent that believes a requirement is wrong does not edit it. It returns a proposal with its evidence (AX-D-005).

## Managing releases

### AX-V-007 — Content-named writes

In organization mode the service also accepts releases and approvals. A release is uploaded to the path of its own digest and the body must have that digest; approvals are added to the release they name and merge by union. A repeated or reordered request therefore changes nothing, and two replicas that receive different files converge when they share them (AX-L-010).

An upload grants nothing. What makes a release usable is its verdict: its link to its baseline, the comparison, its approvals and its imports, computed from the files held.

The service keeps no state between requests other than files. It authenticates nobody: it sits behind the organization's gateway, and access policy is applied there before any content is returned (AX-K-009).

### AX-V-008 — Candidates from edits

A candidate release is built from a baseline and a list of edits addressed by ID, never by position:

| Edit | Effect |
|---|---|
| `put` | Insert or replace one object of a section by its ID |
| `retire` | Retire a node; a node is never removed |
| `remove` | Remove an edge, binding, flag, context asset, import or environment |
| `set` | Replace the exports, the approval policy or the compatibility entries |

The service names the baseline by digest, sets the revision of each changed node, checks the result against the schema and the reference rules and runs the comparison (G14). The same request always yields the same digest. A candidate that passes these checks is still only a candidate until it has its approvals (G12).

## Operations

| Operation | Route | Tool | Mode |
|---|---|---|---|
| `listSnapshots` | `GET /v1/snapshots` | | both |
| `getIndex` | `GET /v1/snapshots/{digest}/index` | | both |
| `lookup` | `GET /v1/snapshots/{digest}/nodes/{id}` | `axiom_lookup` | both |
| `context` | `GET /v1/snapshots/{digest}/context` | `axiom_context` | both |
| `trace` | `GET /v1/snapshots/{digest}/trace` | `axiom_trace` | both |
| `gaps` | `GET /v1/snapshots/{digest}/gaps` | `axiom_gaps` | both |
| `getProject` | `GET /v1/projects/{project_id}` | | organization |
| `getRelease`, `putRelease` | `GET`, `PUT /v1/releases/{digest}` | | organization |
| `getApprovals`, `putApprovals` | `GET`, `PUT /v1/releases/{digest}/approvals` | | organization |
| `getVerdict` | `GET /v1/releases/{digest}/verdict` | `axiom_verdict` | organization |
| `getStatement` | `GET /v1/releases/{digest}/statement` | | organization |
| `compare` | `GET /v1/compare` | `axiom_compare` | organization |
| `impact` | `GET /v1/impact` | `axiom_impact` | organization |
| `propose` | `POST /v1/candidates` | `axiom_propose` | organization |

## Limits

- The queries follow declared links and annotations. An undeclared dependency, a requirement nobody annotated and a call path through other code are not found, and each answer states this.
- Symbols are resolved for Python only. No call graph is built.
- The reference server has no authentication and no access control, and was not load-tested.
- A delivery records what was supplied. It does not show that an agent read or obeyed it.
