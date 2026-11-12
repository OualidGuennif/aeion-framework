#!/usr/bin/env python3
"""Exercise two isolated Docker replicas, bounded client load, ingestion and recovery.

Uses only containers and a volume created by this invocation. Install the repository's pinned QA and
service dependencies on the host; build the image first. This is a local qualification, not a capacity SLO.
"""
import argparse
import asyncio
from collections import Counter
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'AxiomSpec/qa'))
from check_package import canonical, digest  # noqa: E402
import fictional_keys  # noqa: E402


def docker(*arguments, check=True):
    return subprocess.run(['docker', *arguments], text=True, capture_output=True, check=check)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def source_manifest():
    paths = [ROOT / name for name in ('Dockerfile', '.dockerignore', 'server/requirements.txt', 'server/constraints.txt',
                                     'AxiomSpec/axiom.py', 'AxiomSpec/qa/requirements-qa.txt')]
    for folder, pattern in (('server/axiom_service', '*.py'), ('AxiomSpec/qa', '*.py'),
                            ('AxiomSpec/schemas', '*.json'), ('AxiomSpec/api', '*.json')):
        paths += sorted((ROOT / folder).glob(pattern))
    return {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in sorted(paths)}


def source_digest():
    return digest(canonical(source_manifest()))


async def request(client, method, url, **options):
    """Retries are bounded; the test writes only content-addressed, idempotent PUT operations."""
    for attempt in range(8):
        retry_after = 0
        try:
            response = await client.request(method, url, **options)
            if response.status_code != 503:
                return response
            value = response.headers.get('retry-after', '')
            retry_after = int(value) if value.isdigit() else 0
        except httpx.TransportError:
            if attempt == 7:
                raise
        if attempt < 7:
            await asyncio.sleep(max(retry_after, min(1, 0.05 * 2 ** attempt)) + random.random() * 0.1)
    raise RuntimeError('Request stayed overloaded after eight bounded attempts')


async def exercise(urls, requests, concurrency):
    load = lambda path: json.loads((ROOT / 'AxiomSpec/examples' / path).read_text())
    identity = load('identity-adapter/spec.json')
    baseline = load('refund-ledger/releases/1.0.0.json')
    ledger = load('refund-ledger/spec.json')
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=15) as client:
        for spec, approvals in ((identity, load('identity-adapter/approvals.json')),
                                (baseline, load('refund-ledger/releases/1.0.0.approvals.json')),
                                (ledger, load('refund-ledger/approvals.json'))):
            key = digest(canonical(spec))
            response = await request(client, 'PUT', urls[0] + '/v1/releases/' + key, content=canonical(spec))
            require(response.status_code == 200, response.text[:300])
            response = await request(client, 'PUT', urls[0] + f'/v1/releases/{key}/approvals', content=canonical(approvals))
            require(response.status_code == 200, response.text[:300])
        key = digest(canonical(ledger))
        for url in urls:
            response = await request(client, 'GET', url + f'/v1/releases/{key}/verdict')
            require(response.json()['status'] == 'pass', 'Initial replicas do not agree on the approved release')

        # Competing unique writes and retries to one shared POSIX volume, from separate containers/workers.
        documents = []
        for number in range(16):
            spec = copy.deepcopy(identity)
            spec['project']['id'] = f'PROJECT-{100000 + number}'
            spec['project']['name'] = f'Concurrent ingestion fixture {number}'
            for band in spec['approval']['policy'].values():
                band['approvers'] = 0  # synthetic throughput fixture, not an approval integration
            documents.append(spec)

        async def put(number, spec):
            response = await request(client, 'PUT', urls[number % len(urls)] + '/v1/releases/' + digest(canonical(spec)),
                                     content=canonical(spec))
            require(response.status_code == 200, response.text[:300])

        started = time.perf_counter()
        await asyncio.gather(*(put(number, spec) for number, spec in enumerate(documents * 2)))
        ingestion_seconds = time.perf_counter() - started
        for url in urls:
            for spec in documents:
                response = await request(client, 'GET', url + '/v1/releases/' + digest(canonical(spec)))
                require(response.status_code == 200 and response.json() == spec, 'A concurrent upload was lost')

        candidate = copy.deepcopy(ledger)
        candidate['release'] = dict(version='1.1.1', compatibility=[], previous=dict(version='1.1.0', spec_sha256=key))
        node = next(n for n in candidate['nodes'] if n['id'] == 'REQ-004')
        node['title'] += ' (concurrent approval fixture)'
        node['revision'] += 1
        await put(0, candidate)
        signed = fictional_keys.approvals_for(candidate, ledger, [('ACTOR-001', 'KEY-001'), ('ACTOR-003', 'KEY-002')])
        candidate_key = digest(canonical(candidate))

        async def approve(number):
            half = dict(signed, approvals=[signed['approvals'][number % 2]])
            response = await request(client, 'PUT', urls[number % len(urls)] + f'/v1/releases/{candidate_key}/approvals',
                                     content=canonical(half))
            require(response.status_code == 200, response.text[:300])

        await asyncio.gather(*(approve(number) for number in range(16)))
        for url in urls:
            response = await request(client, 'GET', url + f'/v1/releases/{candidate_key}/verdict')
            require(response.json()['status'] == 'pass', 'Concurrent approval fragments did not converge')

        # Near-limit invalid bodies must be refused without exhausting the runtime memory budget.
        near_limit = b'[' + b'0,' * 524286 + b'0]'

        async def large_body(number):
            response = await request(client, 'PUT', urls[number % len(urls)] + f'/v1/releases/{key}', content=near_limit)
            require(response.status_code == 409, 'A large non-specification body was not cleanly refused')

        await asyncio.gather(*(large_body(number) for number in range(32)))
        invalid = dict(identity, nodes=[0] * 400000)
        invalid_raw = canonical(invalid)

        async def dense_invalid(number):
            response = await request(client, 'PUT', urls[number % len(urls)] + '/v1/releases/' + digest(invalid_raw),
                                     content=invalid_raw)
            require(response.status_code == 422 and len(response.content) < 2048, 'Dense invalid input was not cleanly refused')

        await asyncio.gather(*(dense_invalid(number) for number in range(16)))

        statuses, latencies = Counter(), []
        gate = asyncio.Semaphore(concurrency)

        async def agent(number):
            async with gate:
                started = time.perf_counter()
                url = urls[number % len(urls)] + f'/v1/snapshots/{key}/nodes/REQ-004'
                for attempt in range(8):
                    response = await client.get(url)
                    statuses[str(response.status_code)] += 1
                    require(response.status_code in (200, 503), response.text[:300])
                    if response.status_code == 200:
                        require(response.json()['id'] == 'REQ-004', 'Wrong requirement returned under load')
                        latencies.append((time.perf_counter() - started) * 1000)
                        return
                    value = response.headers.get('retry-after', '')
                    retry_after = int(value) if value.isdigit() else 0
                    await asyncio.sleep(max(retry_after, min(1, 0.05 * 2 ** attempt)) + random.random() * 0.1)
                raise RuntimeError('Agent never completed after bounded overload retries')

        started = time.perf_counter()
        await asyncio.gather(*(agent(number) for number in range(requests)))
        elapsed = time.perf_counter() - started
        latencies.sort()
        response = await client.post(urls[0] + '/mcp/', content=b'x' * 1048577)
        require(response.status_code == 413, 'MCP body ceiling was not enforced')
        return dict(logical_requests=requests, client_concurrency=concurrency, replicas=len(urls), workers_per_replica=2,
                    completed=len(latencies), statuses=dict(statuses), seconds=round(elapsed, 3),
                    completed_per_second=round(requests / elapsed, 2),
                    latency_including_retries_ms=dict(p50=round(latencies[len(latencies) // 2], 2),
                                                     p99=round(latencies[min(len(latencies) - 1, int(len(latencies) * 0.99))], 2)),
                    synthetic_ingestion=dict(unique_releases=16, attempted_puts=32, seconds=round(ingestion_seconds, 3)),
                    concurrent_approval_puts=16, near_limit_body_requests=32, near_limit_body_bytes=len(near_limit),
                    dense_invalid_specifications=16,
                    approved_release=candidate_key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='aeion-framework:1.1.5')
    parser.add_argument('--requests', type=int, default=2000)
    parser.add_argument('--concurrency', type=int, default=128)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    require(args.requests > 0 and 0 < args.concurrency <= 1000, 'Use positive counts and concurrency at most 1000')
    prefix = 'axiom-check-' + uuid.uuid4().hex[:12]
    volume, containers, urls = prefix + '-data', [], []
    before = source_digest()

    def ready(url):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                if httpx.get(url + '/health/ready', timeout=2).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.2)
        raise RuntimeError('Container did not become ready within 45 seconds')

    def address(name):
        port = docker('port', name, '8787/tcp').stdout.strip().rsplit(':', 1)[1]
        return 'http://127.0.0.1:' + port

    try:
        docker('volume', 'create', volume)
        for number in range(2):
            name = f'{prefix}-{number}'
            containers.append(name)
            docker('run', '-d', '--name', name, '--init', '--read-only', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges:true', '--tmpfs', '/tmp:rw,noexec,nosuid,nodev,size=16m',
                   '--memory', '512m', '--cpus', '2', '--pids-limit', '128',
                   '-e', 'AXIOM_WORKERS=2', '--mount', f'type=volume,source={volume},target=/data',
                   '-p', '127.0.0.1::8787', args.image)
            urls.append(address(name))
            ready(urls[-1])
        expected = {name: sha for name, sha in source_manifest().items()
                    if name.startswith(('AxiomSpec/', 'server/axiom_service/'))}
        actual = docker('exec', containers[0], 'python', '-c',
                        "import sys,json,hashlib,pathlib; print(json.dumps({p:hashlib.sha256((pathlib.Path('/app')/p).read_bytes()).hexdigest() for p in json.loads(sys.argv[1])}))",
                        json.dumps(list(expected)))
        require(json.loads(actual.stdout) == expected, 'The image does not contain the current source; rebuild it')
        denied = docker('exec', containers[0], 'python', '-c', "open('/app/unexpected-write','w').write('x')", check=False)
        require(denied.returncode != 0, 'The container root filesystem was writable')
        result = asyncio.run(exercise(urls, args.requests, args.concurrency))
        memory = []
        for name in containers:
            sample = docker('exec', name, 'python', '-c',
                            "import json,pathlib; p=pathlib.Path('/sys/fs/cgroup'); print(json.dumps({n:(p/n).read_text().strip() if (p/n).exists() else None for n in ('memory.events','memory.peak','memory.max')}))")
            sample = json.loads(sample.stdout)
            events = dict(line.split() for line in (sample['memory.events'] or '').splitlines())
            require(int(events.get('oom_kill', '0')) == 0, 'A worker was OOM killed during load')
            memory.append(sample)
        docker('stop', '--time', '40', containers[1])
        exit_code = json.loads(docker('inspect', containers[1]).stdout)[0]['State']['ExitCode']
        require(exit_code in (0, 143), f'Unexpected graceful shutdown exit: {exit_code}')
        docker('start', containers[1])
        urls[1] = address(containers[1])  # Docker may reassign a dynamically published host port on restart
        ready(urls[1])
        docker('kill', '--signal', 'KILL', containers[0])
        docker('start', containers[0])
        urls[0] = address(containers[0])
        ready(urls[0])
        for url in urls:
            response = httpx.get(url + f"/v1/releases/{result['approved_release']}/verdict", timeout=15)
            require(response.status_code == 200 and response.json()['status'] == 'pass', 'Acknowledged data did not survive restart')
        verified = docker('exec', containers[0], 'python', '/app/AxiomSpec/qa/release_store.py', 'verify', '/data')
        require(json.loads(verified.stdout)['status'] == 'pass', 'The shared store did not verify after recovery')
        image = json.loads(docker('image', 'inspect', args.image).stdout)[0]
        healthcheck = image['Config']['Healthcheck']['Test']
        require(healthcheck[0] == 'CMD', 'Expected an exec-form Docker healthcheck')
        for name in containers:
            docker('exec', name, *healthcheck[1:])
        states = [json.loads(docker('inspect', name).stdout)[0]['State'] for name in containers]
        require(not any(state['OOMKilled'] for state in states), 'A container was OOM killed')
        require(source_digest() == before, 'Source changed during qualification; rerun on stable inputs')
        result.update(status='pass', image_id=image['Id'], image_bytes=image['Size'], architecture=image['Architecture'],
                      python=docker('exec', containers[0], 'python', '--version').stdout.strip(),
                      source_sha256=before, driver_sha256=digest(Path(__file__).read_bytes()), trust='untrusted_local',
                      memory_before_restart=memory,
                      graceful_stop=True, restart_after_sigkill=True, store_status='pass',
                      limits='Local synthetic workload on a shared POSIX volume; not a distributed-storage, power-loss or capacity SLO.')
        body = json.dumps(result, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(body)
        print(body)
        return 0
    except Exception:
        for name in containers:
            print(docker('logs', '--tail', '25', name, check=False).stderr, file=sys.stderr)
        raise
    finally:
        for name in containers:
            docker('rm', '-f', name, check=False)
        docker('volume', 'rm', volume, check=False)


if __name__ == '__main__':
    sys.exit(main())
