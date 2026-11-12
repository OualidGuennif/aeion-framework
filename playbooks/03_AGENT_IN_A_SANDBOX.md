# Agent in a sandbox

How to give a coding agent the requirements of a product without giving it the specification.

The agent works in a sandbox with three things: a small index file, code that names the requirements it implements, and a read-only service it asks when in doubt. The rules are in the [service interface](../AxiomSpec/docs/19_SERVICE_INTERFACE.md); this playbook is the procedure, with the [refund ledger](../AxiomSpec/docs/13_REFUND_LEDGER_WALKTHROUGH.md) as the example.

## 1. Annotate the code

Put `@req` and the IDs in a comment above the function, class or file that implements them:

```text
# @req REQ-005 REQ-006 REQ-009
def command(self, kind, principal, tenant_id, payment_id, record_id):
```

`@req: REQ-005` and `@req(REQ-005, REQ-006)` are read the same. The token with no valid ID after it fails the scan, so a typing mistake is reported instead of skipped. So does an ID of the release written after other words, as in `@req REQ-005 and REQ-006`: separate IDs by spaces or commas only.

Use the ID of a requirement, or of a constraint the code enforces. Annotate where the behavior is decided, not every helper. The comment form does not matter: `//`, `#`, `--` or a docstring all work, in any language. Tests do not need annotations when each test case is already bound in the specification.

## 2. Build the index

From the `AxiomSpec` directory, with its QA dependencies installed:

```bash
python3 qa/graph_index.py build examples/refund-ledger/spec.json --repo . --include examples/refund-ledger > axiom-graph.json
```

The command fails when an annotation names an ID the release does not hold or has retired, when `@req` has no ID after it, and when a path given to `--include` does not exist. If the repository holds other code that mentions `@req`, such as a copy of the AxiomSpec package, leave it out with `--exclude <path>`; the service takes the same option. The file lists every object, link and trace of the release, one record per line, and names the release by `spec_sha256`. Rebuild it whenever the specification or the annotations change; never edit it.

Place `axiom-graph.json` at the root of the repository the agent receives.

## 3. Start the service outside the sandbox

On the host the sandbox can reach, from the `server` directory:

```bash
python3 -m axiom_service --store ../AxiomSpec/examples/refund-ledger/spec.json --repo ../AxiomSpec --include examples/refund-ledger --host 0.0.0.0 --allowed-host host.openshell.internal:8787
```

It serves that one release and nothing else, by GET only. The agent cannot change it and cannot reach another version through it.

`--repo` is the copy of the code the service reads annotations from. The release never changes during a task, but when a file of that copy changes the next answer reflects it, with no restart.

## 4. Let the sandbox reach it, read-only

For NVIDIA OpenShell, add one rule to the sandbox policy. The service is reached through the gateway host, for the `curl` binary only, with reads enforced:

```yaml
version: 1
network_policies:
  axiomspec_readonly:
    endpoints:
      - host: host.openshell.internal
        port: 8787
        protocol: rest
        enforcement: enforce
        access: read-only
    binaries:
      - path: /usr/bin/curl
```

Set `enforcement: enforce` explicitly: the default only logs. `access: read-only` allows GET, HEAD and OPTIONS, which is everything the sandbox mode of the service answers. Any other sandbox works the same way: allow one host and port, for GET.

## 5. Tell the agent

Add this to the task. It is the whole protocol.

```text
The requirements of this repository are in axiom-graph.json, one record per line.
Search it for an ID, a file or a symbol. Do not read it whole.
Code names the requirements it implements in comments: @req <ID>.

AXIOM=http://host.openshell.internal:8787/v1/snapshots/current

Before changing a function, search the index for its file and symbol.
What a requirement demands:      curl -s $AXIOM/nodes/<ID>
The rules that bind it:          curl -s "$AXIOM/context?ids=<ID>"
Before changing behavior:        curl -s "$AXIOM/context?ids=<ID>&scope=change"
                                 then follow next_cursor until complete is true.

Keep the @req comments true to the code you leave.
If a requirement looks wrong or two conflict, do not work around it. Write the
problem, where you saw it and what you propose to axiom-proposals.md, and stop
that part of the work.
```

## 6. What a session costs

Measured on the ledger, for a change to the cancel and commit command. The specification file is 220 KB; the index is 31 KB.

| Step | Request | Size of the answer |
|---|---|---|
| Which requirements does `Ledger.command` carry? | Search the index for the symbol | 0.5 KB: REQ-005, REQ-006, REQ-009 |
| What does REQ-005 demand? | `nodes/REQ-005` | 3.8 KB |
| What binds REQ-005 and REQ-009? | `context?ids=REQ-005,REQ-009` | 24 KB, 22 objects, one page |
| What must a change to them take into view? | The same with `scope=change` | 99 objects in three pages of at most 32 KB |

The first three steps answer most doubts with under 30 KB. The last step is large on purpose: it is the conservative context of a change, and on a specification as small and connected as the ledger it is most of it. On a larger specification it stays the neighborhood of the change plus the project-wide rules.

## 7. MCP instead of curl

An agent without a shell uses the MCP endpoint of the same service, `http://host.openshell.internal:8787/mcp/`, with four tools: `axiom_lookup`, `axiom_context`, `axiom_trace` and `axiom_gaps`. They return exactly what the routes above return.

MCP sends POST requests, so the `read-only` preset above does not cover it. Allow it with a rule for the `mcp` protocol of your sandbox; the service itself still offers nothing that writes.

## 8. After the task

Rebuild the index on the agent's result. It fails if an annotation now names an unknown ID. Then ask what is missing:

```bash
curl -s "http://127.0.0.1:8787/v1/snapshots/current/gaps?phase=implementation"
```

A must requirement that lost its place in the code appears there. The annotations show where requirements were placed, not that they are met: the tests of the specification decide that.

## What was and was not tried

- The commands and sizes above were run on the ledger example against the reference service on one machine.
- The OpenShell policy is written from the documentation of version 0.1.8. It was not run in OpenShell, and how files are placed in a sandbox there was not checked.
- No agent was measured doing a real task with and without this setup. Published studies on giving agents context files disagree with each other; retrieving on demand is a reasoned choice here, not a measured gain.
- The reference service authenticates nobody. Keep it reachable from the sandbox only.
