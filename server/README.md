# Reference service

This server implements the AxiomSpec [service interface](../AxiomSpec/docs/19_SERVICE_INTERFACE.md) over HTTP and MCP. It passes requests to the package's reference queries, so every answer is exactly what `AxiomSpec/qa/queries.py` returns.

Its contract is in [openapi.json](../AxiomSpec/api/openapi.json) and [mcp-tools.json](../AxiomSpec/api/mcp-tools.json), and it serves the first at `/v1/openapi.json`.

## Run

With Python 3.14 or later, install the dependencies of the package and of the service:

```bash
python3 -m pip install -r AxiomSpec/qa/requirements-qa.txt -r server/requirements.txt
```

Start the service from the `server` directory with the interpreter you installed them for. From another directory, put `PYTHONPATH=server` in front of the command.

For one coding task, the service is read-only. `--snapshot` takes the `spec_sha256` of the graph index, and you can leave it out when the store holds a single release. Each path given to `--include` must exist, or the service will not start. `--exclude` leaves a path out of the scan, which you need when the repository holds other code that mentions `@req`, such as a copy of the AxiomSpec package.

```bash
python3 -m axiom_service --store ../AxiomSpec/examples/refund-ledger/spec.json --repo ../AxiomSpec --include examples/refund-ledger
```

For an organization, the service runs over a whole release store and also accepts uploads, approvals and candidates. It writes into the first store directory, so point it at a working copy and not at the package's examples:

```bash
cp -R ../AxiomSpec/examples /tmp/axiom-store
python3 -m axiom_service --store /tmp/axiom-store --mode organization
```

Then, from another terminal:

```bash
curl -s http://127.0.0.1:8787/v1/snapshots/current/nodes/REQ-004
```

The MCP endpoint is `http://127.0.0.1:8787/mcp/` (Streamable HTTP, stateless). It accepts requests addressed to `127.0.0.1` and `localhost`. If clients reach it under another host name, add that name with `--allowed-host`, for example `--allowed-host host.openshell.internal:8787`.

## How it works

| File | Role |
|---|---|
| `axiom_service/service.py` | Every operation of the contract as one method over a release store |
| `axiom_service/app.py` | The HTTP routes, caching headers and problem documents |
| `axiom_service/mcp_tools.py` | The MCP tools, built from `mcp-tools.json` |
| `tests/test_service.py` | Each operation over HTTP, MCP and a listening port, validated against the contract |

Between requests the service keeps nothing except files, and it never rewrites a file.

In organization mode each accepted upload becomes its own file in the first store directory: a release as `<digest>.json` in canonical form with `format` first, or as `<digest>.parts/` when it exceeds one megabyte, and approvals as `<release digest>.approvals.<digest of the approvals>.json`. A file is staged under a name that starts with `.incoming-` and moved into place whole; a file that already holds the same bytes is left alone, so a repeated upload changes nothing.

Before each organization request the service lists the store and reads the files that appeared, each once. Several processes on one directory therefore give the same answers, and asking for a digest the store does not hold costs one listing of the directory. A request body must be strict JSON of at most one megabyte, and the service refuses a release that the store could not read back.

In sandbox mode with `--repo`, the annotations are read again when a scanned file changes. If that scan cannot complete, code-dependent reads return `CODE_UNAVAILABLE` (503) until it recovers. A context query reads only the release and never looks at the code. Answers that depend on the code carry an ETag and `no-cache`; answers that depend on the release alone are immutable. Context, trace and gap pages include their omissions within the requested byte budget. A lookup over 32,768 UTF-8 bytes returns `RESPONSE_TOO_LARGE` (422).

A release verdict also checks its baseline chain. A successor of a failed release cannot become the accepted head, even when signatures under that failed release's new policy verify locally. Invalid reference graphs are reported as failed releases and do not prevent verdicts on unrelated releases.

## Limits

The service has no authentication and no access policy. Put it behind your gateway, or on a host that only the sandbox can reach.

It has not been load-tested or run inside a real sandbox. The [sandbox playbook](../playbooks/03_AGENT_IN_A_SANDBOX.md) gives a policy for one and says what was tried.

It holds every release of the store in memory, handles one operation at a time, and lists the store directory before each organization request.
