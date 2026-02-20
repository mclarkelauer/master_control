"""Subprocess entry point. Imports and runs the target function.

Usage:
    python -m master_control.engine._worker \
        --module agents.examples.hello_agent \
        --entry-point run \
        --params-json '{"source_url": "https://example.com"}'
"""

import argparse
import asyncio
import importlib
import json
import sys
from pathlib import Path

from master_control.logging_config import configure_worker_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Master Control worker process")
    parser.add_argument("--module", required=True, help="Python module path to import")
    parser.add_argument("--entry-point", required=True, help="Function name to call")
    parser.add_argument("--params-json", default="{}", help="JSON-encoded parameters")
    parser.add_argument("--log-file", default=None, help="Path to log file")
    parser.add_argument("--workload-name", default="worker", help="Workload name for logging")
    args = parser.parse_args()

    log_file = Path(args.log_file) if args.log_file else None
    configure_worker_logging(args.workload_name, log_file)

    try:
        mod = importlib.import_module(args.module)
    except ImportError as e:
        print(f"Failed to import module '{args.module}': {e}", file=sys.stderr)
        sys.exit(1)

    func = getattr(mod, args.entry_point, None)
    if func is None:
        print(
            f"Module '{args.module}' has no function '{args.entry_point}'",
            file=sys.stderr,
        )
        sys.exit(1)

    params = json.loads(args.params_json)
    result = func(**params)

    if asyncio.iscoroutine(result):
        asyncio.run(result)


if __name__ == "__main__":
    main()
