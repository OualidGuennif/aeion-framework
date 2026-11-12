# Reference service

The [service interface](../AxiomSpec/docs/19_SERVICE_INTERFACE.md) of AxiomSpec over HTTP and MCP. It transports the reference queries of the package and adds no behavior: each answer is the one `AxiomSpec/qa/queries.py` gives.

The contract is [openapi.json](../AxiomSpec/api/openapi.json) and [mcp-tools.json](../AxiomSpec/api/mcp-tools.json). This server conforms to them and serves the first at `/v1/openapi.json`.

## Run

Install the dependencies of the package and of the service:

```bash
python3 -m pip install -r AxiomSpec/qa/requirements-qa.txt -r server/requirements.txt
```

Run the service from the `server` directory, with the interpreter those dependencies were installed for. From another directory, add `PYTHONPATH=server` in front of the command.

For one coding task, read-only. The digest is the `spec_sha256` of the graph index; it may be left out when the store holds one release. A path given to `--include` must exist, or the service does not start. `--exclude` leaves a path out of the scan, for a repository that holds other code mentioning `@req`, such as a copy of the AxiomSpec package.

```bash
python3 -m axiom_service --store ../AxiomSpec/examples/refund-ledger/spec.json --repo ../AxiomSpec --include examples/refund-ledger
```

For an organization, over a whole release store, with uploads, approvals and candidates. The service writes into the first store directory, so give it a working copy, never the examples of the package:

```bash
cp -R ../AxiomSpec/examples /tmp/axiom-store
python3 -m axiom_service --store /tmp/axiom-store --mode organization
```

Then, from another terminal:

```bash
curl -s http://127.0.0.1:8787/v1/snapshots/current/nodes/REQ-004
```

The MCP endpoint is `http://127.0.0.1:8787/mcp/` (Streamable HTTP, stateless). It accepts requests for `127.0.0.1` and `localhost`; name any other host it is reached by with `--allowed-host`, for example `--allowed-host host.openshell.internal:8787`.

## What it is

| File | Role |
|---|---|
| `axiom_service/service.py` | Every operation of the contract as one method over a release store |
| `axiom_service/app.py` | The HTTP routes, caching headers and problem documents |
| `axiom_service/mcp_tools.py` | The MCP tools, built from `mcp-tools.json` |
| `tests/test_service.py` | Each operation over HTTP, MCP and a listening port, validated against the contract |

The service keeps nothing between requests but files, and it never rewrites one.

- **Writes.** In organization mode each accepted upload becomes its own file in the first store directory: a release as `<digest>.json` in canonical form with `format` first, or as `<digest>.parts/` when it exceeds one megabyte, and approvals as `<release digest>.approvals.<digest of the approvals>.json`. A file is staged under a name that starts with `.incoming-` and moved into place whole; a file that already holds the same bytes is left alone, so a repeated upload changes nothing.
- **Reads.** Before each organization request the service lists the store and reads the files that appeared, each once. Several processes on one directory therefore answer the same, and a digest that is not held costs a listing, not a reload.
- **Bodies.** A request body is strict JSON of at most one megabyte. A release the store could not read back is refused, not written.
- **Code.** In sandbox mode with `--repo`, the annotations are read again when a scanned file changes. A context reads the release alone and does not look at the code. Answers that depend on the code carry an ETag and `no-cache`; answers that depend on the release alone are immutable.

## What it is not

- It authenticates nobody and applies no access policy. Put it behind your gateway, or keep it on a host only the sandbox can reach.
- It was not load-tested, and it was not run inside a real sandbox. The [sandbox playbook](../playbooks/03_AGENT_IN_A_SANDBOX.md) gives the policy for one and says what was and was not tried.
- It holds every release of the store in memory, answers one operation at a time, and lists the store directory before each organization request.
