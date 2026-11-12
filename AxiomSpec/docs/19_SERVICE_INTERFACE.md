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

- A colon or an opening parenthesis may follow the token, and the IDs are separated by spaces or commas: `@req: REQ-004` and `@req(REQ-004, CON-005)` are read the same. All the IDs of an annotation are on the line of the token: a list continued on the next comment line is not read, so a long list is split into several annotations.
- It belongs to the definition a comment block directly precedes, otherwise to the innermost definition that contains it, otherwise to the file. Symbols are resolved for Python; elsewhere the location is the file and line.
- For Python, only comments and actual module, class or function docstrings are read. Ordinary string literals are data. During an incomplete edit, identified comments are still read but no docstring is guessed. Other supported languages use a lexical token scan, not a language parser; keep annotation tokens in comments and exclude source fixtures that contain them as data.
- It names an object the release holds and has not retired. Anything else fails the scan, and so does the token with no ID after it: an annotation that is skipped would tell an agent that no requirement concerns the code.
- An ID of the release that follows other words on the line, as in `@req REQ-004 and CON-005`, also fails the scan: it was meant to be annotated and was not read. Other words on the line are ignored.
- A scanned path that does not exist is an error, not an empty scan. Below a scanned path, version-control, dependency, cache and output folders (`.git`, `node_modules`, `build`, `dist`, `target` and the like) are not entered; a source folder with such a name is scanned by naming it. A path can be left out of the scan; a repository that contains a copy of this package, which mentions the token in its own code, leaves that copy out.
- It yields a trace of kind `test` in a test file and `code` elsewhere. A trace on a constraint, component or test leads to the requirements that object concerns.
- An active must requirement with no binding and no annotation in code is reported as a gap of the implementation phase.

An annotation is a declared link, like a binding. It says where an author placed a requirement. It does not show that the code satisfies it; an executed test does.

## Reading

### AX-V-003 — Immutable reads

Every read is a GET on a release named by its canonical digest. An answer that is a function of the release alone cannot change, so it carries an ETag and may be cached without limit. A service that serves exactly one release also accepts `current` in place of the digest; that form is not cached, and the answer still names the digest.

The digest covers the release, not the code beside it. When a service reads annotations and bindings from a repository, the index, a lookup, a trace and the gaps also depend on that code. Those answers carry an ETag and are revalidated on each use; they are never marked immutable. The context of a requirement reads the release only and stays immutable.

Paged context, trace and gap answers are bounded as AX-K-006 states: at most 100 records (items and omissions together) and 32,768 UTF-8 bytes for the complete JSON envelope, or the smaller requested budget. A cursor binds the snapshot, query and, for an answer that reads the code, the state of the scanned files. It holds no state on the service and grants nothing. A trace or gap page begun before the code changed is not continued afterwards, even if its annotations stayed the same; context pages read the release alone and continue. An object that cannot fit the budget is named in `omissions` and never cut; omissions themselves are paged within the budget. `complete` is true only when the whole answer was deliverable. A place in the code is listed once, however many declared links lead to it.

A lookup is also bounded at 32,768 bytes. If its statement, content, links or traces do not fit, it returns `RESPONSE_TOO_LARGE` (422), never a cut rule. Context can identify the oversized object in an omission; reading the full specification is a separate file operation. The index, release downloads, comparisons and organization inventories are whole-document operations, not paged answers; they are not covered by the query-page budget.

An unknown ID is `not_found`. Errors are problem documents (RFC 9457) with a stable `code`, including `INTERNAL_ERROR` for a defect of the service. A bound file that does not parse, as happens while it is being edited, is a gap in the answer and not a failed request.

### AX-V-004 — One behavior, two transports

Each specification operation is defined once. The HTTP route and the MCP tool for it return the same successful answer under the same schema. Transport admission, body deadlines and health probes are separate runtime behavior. The tool list is kept short, because every tool definition is read by the agent before it asks anything: four tools for an agent, four more for authoring.

The queries are a fixed set. There is no query language, no free-form search and no access to files: selection follows declared links and annotations only, and nothing is ranked or learned.

### AX-V-005 — Context scopes

A question about a requirement has three depths. An agent takes the first that answers it.

| Depth | Operation | Returns | On the ledger |
|---|---|---|---|
| Brief | `lookup` | The requirement as a sentence, its weight and risk, the IDs and titles linked to it, and where it is implemented and tested | 2 to 6 KB |
| Direct | `context`, scope `direct` | The requirement with its goals, terms, assumptions and governing decisions, the constraints that formalize it with their environments, and every hard project rule | 11 to 22 KB, one page |
| Change | `context`, scope `change` | The conservative closure of AX-K-010: also the requirements under project rules, with scenarios, tests and components | 80 to 91 KB, three pages |

The direct scope answers "what does this demand and what binds it". It is not the mandatory context of a change, and its answer says so. Before changing behavior, the change scope is required (AX-K-007) and stays incomplete until every page is delivered.

The change scope is conservative by design. On a specification as small and connected as the ledger it returns most of it; it is the direct scope that keeps an ordinary question small.

### AX-V-006 — Sandbox mode

In sandbox mode the service serves one release, chosen when it starts, and only the read operations. No other method and no other route exists. It runs outside the agent's sandbox, which is allowed to reach it by host and port for GET only.

The release is fixed for the task; the code is not. The service reads the annotations again when a scanned file changes, so an annotation the agent adds is in the next answer.

If the scan cannot complete, including when an explicitly included path disappears, code-dependent reads return `CODE_UNAVAILABLE` (503). They never return the last scan as if it were current. Release-only context reads remain available, and code reads recover when the scan succeeds again.

The task names the release by digest. Every answer carries that digest, so an agent cannot mix two versions of the requirements within one task (AX-K-008).

An agent that believes a requirement is wrong does not edit it. It returns a proposal with its evidence (AX-D-005).

## Managing releases

### AX-V-007 — Content-named writes

In organization mode the service also accepts releases and approvals. A release is uploaded to the path of its own digest and the body must have that digest; approvals are added to the release they name and merge by union. A repeated or reordered request therefore changes nothing, and two replicas that receive different files converge when they share them (AX-L-010).

- **A file is named by its content and never rewritten.** Each accepted upload is its own file: a release under its digest, approvals under the release digest and the digest of the approvals themselves. Two processes that receive different approvals write different files, and neither can undo the other.
- **What is accepted is what the store reads back.** A body is strict JSON of at most one megabyte, the size of one store file, and a document is written in canonical form with `format` first, so that a copy cut short is reported as a broken store file instead of being ignored. A file that already holds the same bytes is not written again. A number, a duplicate key or a size the store would refuse on reading is refused on writing. A release larger than one file is held as parts (AX-M-022).
- **Approvals are checked when they can be.** With the governing release at hand, only the approvals that verify are kept, and a body in which none verifies is refused. Without it they are kept as offered and the verdict sets aside what does not verify. A read of the approvals follows the same rule: it returns those that count, or all that were offered while the governing release is absent.
- **Reads discover what they need.** Inventories, approval reads, verdicts and writes refresh the store before answering. A held immutable read checks its own source files instead of listing unrelated releases; a missing digest triggers discovery. Changed or missing parts invalidate the shortcut, including when the store was configured by manifest filename. A rejected manifest is retried when a watched missing/repaired part arrives. Verification uses no clock or freshness TTL.
- **Publication is complete and durable within the storage contract.** New files are flushed before exclusive publication, and their parent directory is synced before acknowledgement. Parts are flushed before an atomic directory rename. Competing identical files are idempotent; different bytes at a content-named file produce `STORE_CONFLICT` (409). This requires a shared POSIX filesystem with the documented link/rename/fsync semantics, not a replication protocol between independent volumes.

An upload grants nothing. What makes a release usable is its verdict: its link to its baseline, the comparison, its approvals and its imports, computed from the files held. An uploaded release is kept whatever its verdict, and it becomes the accepted head of its project only when that verdict is pass (AX-L-010).

The service keeps no durable state between requests other than files. In-memory views are disposable. It authenticates nobody: it sits behind the organization's gateway, and access policy is applied there before any content is returned (AX-K-009).

### AX-V-008 — Candidates from edits

A candidate release is built from a baseline and a list of edits addressed by ID, never by position:

| Edit | Effect |
|---|---|
| `put` | Insert or replace one object of a section by its ID |
| `retire` | Retire a node; a node is never removed |
| `remove` | Remove an edge, binding, flag, context asset, import or environment |
| `set` | Replace the exports, the approval policy or the compatibility entries |

The service names the baseline by digest, sets the revision of each changed node, checks the result against the schema and the reference rules and runs the comparison (G14). The same request always yields the same digest.

A candidate enters the store only when it passes these checks, and the answer says so in `held`. A refused candidate is returned to its author with the reasons and changes nothing: no file, no head, no verdict. A held candidate is still only a candidate until it has its approvals (G12).

## Operations

| Operation | Route | Tool | Mode |
|---|---|---|---|
| `listSnapshots` | `GET /v1/snapshots` | | both |
| `liveness`, `readiness` (transport probes) | `GET /health/live`, `GET /health/ready` | | both |
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
- The reference server has no authentication or access control; multi-user deployment requires an authenticated gateway. Each worker serializes store operations with bounded admission and lock waits. Inventories, approvals, verdicts and writes refresh the store; pinned reads check their own unchanged source files. The repository's deployment guide records local container concurrency and recovery tests and their workload limits; these are not a production capacity SLO.
- A delivery records what was supplied. It does not show that an agent read or obeyed it.
