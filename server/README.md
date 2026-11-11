# Reference service

The [service interface](../AxiomSpec/docs/19_SERVICE_INTERFACE.md) of AxiomSpec over HTTP and MCP. It transports the reference queries of the package and adds no behavior: each answer is the one `AxiomSpec/qa/queries.py` gives.

The contract is [openapi.json](../AxiomSpec/api/openapi.json) and [mcp-tools.json](../AxiomSpec/api/mcp-tools.json). This server conforms to them and serves the first at `/v1/openapi.json`.

## Run

Install the dependencies of the package and of the service:

```bash
python3 -m pip install -r AxiomSpec/qa/requirements-qa.txt -r server/requirements.txt
```

For one coding task, read-only, from the `server` directory. The digest is the `spec_sha256` of the graph index; it may be left out when the store holds one release.

```bash
python3 -m axiom_service --store ../AxiomSpec/examples/refund-ledger/spec.json --repo ../AxiomSpec --include examples/refund-ledger
```

For an organization, over a whole release store, with uploads, approvals and candidates:

```bash
python3 -m axiom_service --store ../AxiomSpec/examples --mode organization
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

The service keeps nothing between requests but files. In organization mode it writes each release and approval file under the name of its digest into the first store directory, so several processes on one directory answer the same.

## What it is not

- It authenticates nobody and applies no access policy. Put it behind your gateway, or keep it on a host only the sandbox can reach.
- It was not load-tested, and it was not run inside a real sandbox. The [sandbox playbook](../playbooks/03_AGENT_IN_A_SANDBOX.md) gives the policy for one and says what was and was not tried.
- It holds every release of the store in memory.
