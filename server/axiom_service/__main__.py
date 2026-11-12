"""Run the reference service.

Sandbox, for one coding task (read-only, one snapshot, annotations read from the repository):
    python3 -m axiom_service --store path/to/specs --snapshot <digest> --repo path/to/repository

Organization (every release of the store, plus candidates, uploads and approvals):
    python3 -m axiom_service --store path/to/store --mode organization
"""
import argparse

import uvicorn

from .app import create_app
from .service import Service


def main():
    parser = argparse.ArgumentParser(prog='axiom_service', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', nargs='+', required=True, help='files or directories holding releases and approvals')
    parser.add_argument('--mode', choices=('sandbox', 'organization'), default='sandbox')
    parser.add_argument('--snapshot', help='digest of the one release a sandbox service serves')
    parser.add_argument('--repo', help='repository whose @req annotations are read (sandbox)')
    parser.add_argument('--include', nargs='+', default=['.'], help='paths under --repo to scan')
    parser.add_argument('--exclude', nargs='*', default=[], help='paths under --repo left out of the scan')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--allowed-host', action='append', default=[], help='extra Host value the MCP endpoint accepts, such as host.openshell.internal:8787')
    options = parser.parse_args()
    service = Service(options.store, options.mode, options.snapshot, options.repo, options.include, options.exclude)
    uvicorn.run(create_app(service, options.allowed_host), host=options.host, port=options.port, log_level='warning')


if __name__ == '__main__':
    main()
