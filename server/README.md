# Reference service

This FastAPI server implements the AxiomSpec [service interface](../AxiomSpec/docs/19_SERVICE_INTERFACE.md) over REST and MCP. Successful specification answers come from the package's reference operations; admission, body limits and healthchecks belong to the transport.

The [deployment guide](DEPLOYMENT.md) describes the Python 3.15 Docker image, Compose, worker processes,
bounded ingestion, healthchecks, durable publication, recovery and reproducible container/load tests.

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

In organization mode, list the held releases and use their digests for queries:

```bash
curl -s http://127.0.0.1:8787/v1/snapshots
```

For the sandbox example, `current` names its one pinned release:

```bash
curl -s http://127.0.0.1:8787/v1/snapshots/current/nodes/REQ-004
```

The MCP endpoint is `http://127.0.0.1:8787/mcp/` (Streamable HTTP, stateless). It accepts requests addressed to `127.0.0.1` and `localhost`. If clients reach it under another host name, add that name with `--allowed-host`, for example `--allowed-host host.openshell.internal:8787`.

For clients sending an Origin header through an HTTPS gateway, explicitly add the origin too:
`--allowed-host spec.example.com --allowed-origin https://spec.example.com`. Repeat `--allowed-origin`
for each permitted origin. Host and Origin checks remain enabled, independently of proxy-header trust.

## How it works

| File | Role |
|---|---|
| `axiom_service/service.py` | Every operation of the contract as one method over a release store |
| `axiom_service/app.py` | The HTTP routes, caching headers and problem documents |
| `axiom_service/mcp_tools.py` | The MCP tools, built from `mcp-tools.json` |
| `tests/test_service.py` | Each operation over HTTP, MCP and a listening port, validated against the contract |

Files are the only durable state; in-memory views are disposable, and content-named files are never rewritten.

In organization mode each accepted upload becomes its own file in the first store directory: a release as `<digest>.json` in canonical form with `format` first, or as `<digest>.parts/` when it exceeds one megabyte, and approvals as `<release digest>.approvals.<digest of the approvals>.json`. A file is staged under a name that starts with `.incoming-` and published whole; a file that already holds the same bytes is left alone, so a repeated upload changes nothing.

An organization request that reads inventories, approvals or verdicts, or writes files, refreshes the store. A pinned read whose source files are unchanged checks those files instead of listing unrelated releases; a missing digest triggers discovery. Several processes on one shared POSIX directory therefore converge on the same files. A request body is limited to one megabyte and a receive deadline before REST or MCP parses it. Excess work returns 503 with bounded client retries, and an accepted release must be readable back.

In sandbox mode with `--repo`, the annotations are read again when a scanned file changes. If that scan cannot complete, code-dependent reads return `CODE_UNAVAILABLE` (503) until it recovers. A context query reads only the release and never looks at the code. Answers that depend on the code carry an ETag and `no-cache`; answers that depend on the release alone are immutable. Context, trace and gap pages include their omissions within the requested byte budget. A lookup over 32,768 UTF-8 bytes returns `RESPONSE_TOO_LARGE` (422).

A release verdict also checks its baseline chain. A successor of a failed release cannot become the accepted head, even when signatures under that failed release's new policy verify locally. Invalid reference graphs are reported as failed releases and do not prevent verdicts on unrelated releases.

## Limits

The service has no authentication and no access policy. Put it behind your gateway, or on a host that only the sandbox can reach.

The [container qualification](DEPLOYMENT.md#reproduce-the-container-qualification) exercises local concurrency,
saturation and recovery. It does not establish a large-fleet capacity SLO or qualify a real sandbox.
The [sandbox playbook](../playbooks/03_AGENT_IN_A_SANDBOX.md) gives a policy for one and says what was tried.

Each worker holds the store in memory and handles one operation at a time, with a bounded lock wait.
Scale pinned reads with replicas and keep ingestion stores bounded. Increasing workers multiplies memory.
