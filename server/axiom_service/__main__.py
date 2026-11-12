"""Run the reference service.

Sandbox, for one coding task (read-only, one snapshot, annotations read from the repository):
    python3 -m axiom_service --store path/to/specs --snapshot <digest> --repo path/to/repository

Organization (every release of the store, plus candidates, uploads and approvals):
    python3 -m axiom_service --store path/to/store --mode organization
"""
import argparse
import math
import os
import json
import sys

import uvicorn

def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def seconds(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('must be a finite positive number of seconds')
    return number


def arguments(argv=None):
    parser = argparse.ArgumentParser(prog='axiom_service', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', nargs='+', required=True, help='files or directories holding releases and approvals')
    parser.add_argument('--mode', choices=('sandbox', 'organization'), default='sandbox')
    parser.add_argument('--snapshot', help='digest of the one release a sandbox service serves')
    parser.add_argument('--repo', help='repository whose @req annotations are read (sandbox)')
    parser.add_argument('--include', nargs='+', default=['.'], help='paths under --repo to scan')
    parser.add_argument('--exclude', nargs='*', default=[], help='paths under --repo left out of the scan')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=os.environ.get('AXIOM_PORT', '8787'))
    parser.add_argument('--allowed-host', action='append', default=[], help='extra Host value the MCP endpoint accepts, such as host.openshell.internal:8787')
    parser.add_argument('--allowed-origin', action='append', default=[], help='extra MCP Origin value, such as https://spec.example.com; repeat for each origin')
    parser.add_argument('--workers', type=positive, default=os.environ.get('AXIOM_WORKERS', '1'))
    parser.add_argument('--max-inflight', type=positive, default=os.environ.get('AXIOM_MAX_INFLIGHT', '32'))
    parser.add_argument('--body-timeout', type=seconds, default=os.environ.get('AXIOM_BODY_TIMEOUT', '15'))
    parser.add_argument('--store-wait', type=seconds, default=os.environ.get('AXIOM_STORE_WAIT', '1'))
    parser.add_argument('--limit-concurrency', type=positive, default=128, help='Uvicorn connection/task ceiling per worker')
    parser.add_argument('--shutdown-timeout', type=positive, default=30)
    parser.add_argument('--proxy-headers', action='store_true', help='trust forwarded headers only from --forwarded-allow-ips')
    parser.add_argument('--forwarded-allow-ips', default='127.0.0.1')
    parser.add_argument('--access-log', action='store_true')
    parser.add_argument('--log-level', choices=('debug', 'info', 'warning', 'error'), default='info')
    options = parser.parse_args(argv)
    if not 0 <= options.port <= 65535:
        parser.error('--port must be between 0 and 65535')
    return options


def main():
    if sys.version_info < (3, 14):
        sys.exit('The AxiomSpec service needs Python 3.14 or later')
    options = arguments()
    os.environ['AXIOM_SERVICE_OPTIONS'] = json.dumps(dict(
        service=dict(store_paths=options.store, mode=options.mode, snapshot=options.snapshot, repository=options.repo,
                     include=options.include, exclude=options.exclude, lock_timeout=options.store_wait),
        http=dict(allowed_hosts=options.allowed_host, allowed_origins=options.allowed_origin,
                  max_inflight=options.max_inflight, body_timeout=options.body_timeout)))
    uvicorn.run('axiom_service.app:configured_app', factory=True, workers=options.workers,
                host=options.host, port=options.port, log_level=options.log_level, access_log=options.access_log,
                limit_concurrency=options.limit_concurrency, backlog=256, timeout_keep_alive=5,
                timeout_graceful_shutdown=options.shutdown_timeout,
                proxy_headers=options.proxy_headers, forwarded_allow_ips=options.forwarded_allow_ips, server_header=False)


if __name__ == '__main__':
    main()
