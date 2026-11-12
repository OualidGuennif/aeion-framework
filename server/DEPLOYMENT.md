# Deploying the FastAPI service

The REST API already uses FastAPI; MCP shares the same service operations. This deployment adds bounded
admission, durable file publication, worker processes and probes. It does not turn a file store into a
distributed database. Size a deployment from its actual store and request mix.

## Docker

From the repository root:

```bash
docker build -t aeion-framework:1.1.1 .
docker compose up --build -d
curl --fail http://127.0.0.1:8787/health/ready
```

Compose starts two Uvicorn workers with a 512 MiB memory limit, two CPUs, 128 PIDs, a read-only root
filesystem, a 16 MiB temporary filesystem and a named volume at `/data`. It drops Linux capabilities,
disables privilege escalation, forwards signals through an init process and gives shutdown 40 seconds.
The API is published on loopback. The initial organization store is empty; upload the intended releases
and approvals. The image does not silently seed the store with the example or fictional approval keys.

The Dockerfile uses the official Python 3.15.2 `slim-trixie` image, pinned by its multi-platform digest.
Dependencies are installed in a separate stage from the existing requirements and tested transitive
constraints, using binary wheels. Runtime contains no compiler toolchain and runs as UID/GID 10001.
Only the package, service and license are copied. The context allowlist excludes local environments,
Git metadata and common credential paths (`.env`, `.aws`, `.ssh`, PEM/key files). Build from a reviewed
checkout and keep secrets out of the package. Rebuild and qualify dependency/base updates before changing their pins.

To run without Compose:

```bash
docker volume create axiom-store
docker run --name axiom-api --init --restart unless-stopped \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 512m --cpus 2 --pids-limit 128 --stop-timeout 40 \
  --log-driver local --log-opt max-size=10m --log-opt max-file=3 \
  -e AXIOM_WORKERS=2 -p 127.0.0.1:8787:8787 \
  --mount type=volume,source=axiom-store,target=/data \
  aeion-framework:1.1.1
```

For a bind mount, provision the directory so UID 10001 can read, traverse and write it. A read-only
snapshot instead needs read access only. Keep source repositories mounted read-only into the service.
The entrypoint accepts the existing CLI options, so a sandbox can select its pinned specification:

```bash
docker run --rm --init --read-only --tmpfs /tmp:size=16m \
  --cap-drop ALL --security-opt no-new-privileges:true \
  -p 127.0.0.1:8787:8787 \
  --mount type=bind,source="$PWD/AxiomSpec",target=/spec,readonly \
  aeion-framework:1.1.1 \
  --store /spec/examples/refund-ledger/spec.json --mode sandbox \
  --repo /spec --include examples/refund-ledger --host 0.0.0.0
```

The application still requires an authenticated TLS gateway for a multi-user deployment. Apply access
policy there before content is returned. Configure the externally used MCP Host explicitly with
`--allowed-host`; forward-header trust is opt-in with `--proxy-headers --forwarded-allow-ips <trusted-proxy>`.
Do not use a wildcard proxy trust setting for an API reachable directly by clients. Set gateway header/connection timeouts and per-client rate/concurrency limits; the ASGI body deadline begins after headers are available.

## Concurrency and overload

| Setting | Default | Meaning |
|---|---|---|
| `AXIOM_WORKERS` / `--workers` | 1; Compose uses 2 | Independent Uvicorn worker processes; each holds its own in-memory store |
| `AXIOM_MAX_INFLIGHT` / `--max-inflight` | 32 native; 8 in Docker | Active application requests per worker, including requests still receiving their body |
| `AXIOM_BODY_TIMEOUT` / `--body-timeout` | 15 seconds | Deadline for receiving the entire request body |
| `AXIOM_STORE_WAIT` / `--store-wait` | 1 second | Maximum wait for the per-worker operation lock |
| `--limit-concurrency` | 128 | Uvicorn connection/task ceiling per worker |
| `--shutdown-timeout` | 30 seconds | Uvicorn graceful-shutdown budget |
| `AXIOM_PORT` / `--port` | 8787 | Listen port; set `AXIOM_PORT` if changing it in Docker so the healthcheck follows |

The ASGI admission gate rejects excess work immediately with `503 OVERLOADED`; operations that cannot
acquire the store lock in time return `503 STORE_BUSY`. Both include `Retry-After: 1`. The service does
not create an unbounded operation queue. REST and MCP bodies are limited to one MiB before parsing,
including streamed bodies without a Content-Length header. A slow body returns `408 BODY_TIMEOUT`.
Parsing runs outside the event loop. The store still serializes operations inside each worker.
Validation collects a bounded prefix of diagnostics rather than accumulating every error in a dense
invalid document. The container driver exercises that case separately from a large non-object body.

The Docker default is lower because decoded one-MiB bodies, validation objects and responses consume
more memory than their wire size. Keep that admission limit aligned with the worker count, loaded store
and memory limit. Compose also rotates container logs at 10 MiB, retaining three files.

Uvicorn can reject a connection before the application runs; that 503 is a plain transport response.
Clients must handle the status even when no problem document is present. Retry idempotent content-named
PUTs with a bounded exponential backoff and jitter, honoring Retry-After. Keep the same digest and bytes
when a response is lost. Use request deadlines and a client concurrency limit; increasing all limits
until the process runs out of memory is not a throughput strategy.

`GET /health/live` checks that the application is responding. `GET /health/ready` checks access to the
configured store, including write access to an organization directory. These probes bypass application
admission and the store lock; they do not perform a full scan or approve releases. Docker uses readiness
for its healthcheck. Transport-level connection saturation can still return 503 before a probe reaches
the application. Readiness failure should drain traffic; an unhealthy Docker status alone does not
restart a container. Compose's restart policy handles process exits.

## Storage and recovery

A worker stages each upload, flushes the bytes with `fsync`, then publishes a complete file with an
exclusive hard link. It syncs the containing directory before returning. A competing writer can publish
the same bytes without changing the result; different bytes at that content-named path produce
`409 STORE_CONFLICT`, never an overwrite. Parts are flushed before their directory is renamed into place.
Ordinary storage errors return `503 STORAGE_UNAVAILABLE`. Failed staging files are cleaned up by the
writer; a process killed before cleanup may leave an ignored `.incoming-*` file.

Use a persistent POSIX filesystem with the required hard-link, atomic-rename and fsync semantics. All
writers in the tested shared-volume setup run as the same UID. Verify the actual storage driver and its
durability contract. The tests cover process termination and lost-response retries, not a physical power
failure, a storage appliance failure or arbitrary network-filesystem consistency. Clean orphaned staging
files only when all writers to that store are stopped; do not delete another live writer's staging file.

Pinned reads check only the source files for that digest, including its parts. An unchanged release can
be served without listing unrelated releases. A missing/modified source invalidates that shortcut.
Inventories, approvals, verdicts and ingestion refresh the store; unknown digests trigger discovery.
No clock or freshness TTL participates in verification.

SIGTERM allows current requests to finish within the configured budget. Keep the orchestrator's stop
grace period longer than that budget. A forced termination may lose a response; the client repeats the
same PUT and the store keeps one complete object. Back up and restore releases together with approvals,
baseline ancestry and imported releases, then run `qa/release_store.py verify` before serving verdicts.

## Scaling boundary

For a large agent fleet, prefer pinned read-only snapshots and independent replicas. One worker per
container is a useful starting point under an orchestrator; add replicas according to measured CPU,
memory and latency. Multiple workers on one machine are also supported, as Compose demonstrates.
Each worker duplicates the loaded store in memory. Keep source scans narrow and scoped to the task.

Keep ingestion stores bounded by an owned project/domain and include their required ancestry and
providers. Replicas writing one store must see the same filesystem; independent local volumes do not
replicate themselves. This edition has no distributed replication protocol, global transaction service
or routing layer. A store with millions of releases or a requirement for geographically distributed
writes needs a separately qualified storage/index design. Do not infer that capacity from a Dockerfile
or from a small synthetic workload.

## Reproduce the container qualification

With both requirements files installed on the host and Docker available:

```bash
python3 tools/check_container.py --image aeion-framework:1.1.1 \
  --requests 2000 --concurrency 128 --output /tmp/container-check.json
```

The driver creates two isolated replicas and one temporary volume, verifies that the image contains the
current runtime source, tests concurrent unique/repeated uploads and approval union, drives pinned reads
with bounded retries, rejects 32 near-limit non-specification bodies and 16 dense invalid specifications,
checks the body ceiling and read-only filesystem, exercises graceful stop and
restart after SIGKILL, verifies the whole resulting store and runs the image's healthcheck. It removes
only its own containers and volume. The output records request counts, concurrency, retries, latency,
throughput, image identity, architecture and source digest. CI runs a shorter version of the same driver.
The client concurrency is the driver's configured upper bound, not a claim that all handlers executed
simultaneously. Where cgroup v2 exposes them, the report records memory peak/limit and checks that no
worker was OOM killed before restarting the containers.

Local measurements are evidence about that workload and environment, not a guaranteed rate, an
enterprise capacity certification, a long-duration soak test or an authorization assessment.

References: [Python official image](https://hub.docker.com/_/python),
[FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/),
[Uvicorn settings](https://uvicorn.dev/settings/),
[Uvicorn resource limits](https://uvicorn.dev/server-behavior/).

## Local qualification record

The [ARM64 record for 1.1.1](validation/container-1.1.1-arm64.json) was produced on Docker Desktop with
two replicas, two workers per replica, two CPUs and 512 MiB per container. It records:

| Observation | Result |
|---|---|
| Pinned reads | 2000 completed, client concurrency ceiling 1000 |
| Read phase | 7.455 seconds, 268.26 completed reads/second |
| P99 including client scheduling/retries | 7.016 seconds |
| Concurrent synthetic release ingestion | 16 unique releases, 32 PUT attempts |
| Approval union | 16 concurrent PUTs; approved verdict on both replicas |
| Invalid-body pressure | 32 near-one-MiB bodies and 16 dense invalid specifications rejected |
| Highest cgroup memory peak | 293.4 MiB of 512 MiB; no OOM kills |
| Recovery | Graceful stop and restart after SIGKILL; final store verification passed |

These observations include client scheduling and Docker Desktop networking on a shared host. They are
not a production latency SLO or evidence that one write store scales without a bound. The record pins
the runtime source, driver and image identities so the scope of this result is reviewable.
