#!/usr/bin/env python3
"""CLI helper for parsing master_control inventory YAML files.

Used by shell scripts to query inventory data without inline YAML parsing.

Usage:
    python inventory_helper.py --inventory FILE <command> [args]

Commands:
    validate                 Validate inventory file structure
    count                    Print number of clients
    list-clients             Print "index name host" per line
    get-field INDEX FIELD    Get a field for a client (with defaults fallback)
    get-workloads INDEX      Print workload config paths, one per line
    get-env INDEX            Print KEY=VALUE env overrides, one per line
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def load_inventory(path: str) -> dict:
    """Load and return inventory YAML."""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: inventory file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        print("ERROR: inventory must be a YAML mapping", file=sys.stderr)
        sys.exit(1)
    return data


def get_defaults(inv: dict) -> dict:
    """Return the defaults block."""
    return inv.get("defaults", {})


def get_clients(inv: dict) -> list[dict]:
    """Return the clients list."""
    clients = inv.get("clients", [])
    if not isinstance(clients, list):
        print("ERROR: 'clients' must be a list", file=sys.stderr)
        sys.exit(1)
    return clients


def resolve_field(client: dict, defaults: dict, field: str) -> str:
    """Resolve a field value with defaults fallback."""
    val = client.get(field, defaults.get(field, ""))
    return str(val) if val is not None else ""


def cmd_validate(inv: dict) -> None:
    """Validate inventory structure."""
    errors = []
    defaults = inv.get("defaults", {})
    if not isinstance(defaults, dict):
        errors.append("'defaults' must be a mapping")

    clients = inv.get("clients")
    if clients is None:
        errors.append("'clients' key is required")
    elif not isinstance(clients, list):
        errors.append("'clients' must be a list")
    else:
        for i, client in enumerate(clients):
            if not isinstance(client, dict):
                errors.append(f"client[{i}]: must be a mapping")
                continue
            if "host" not in client:
                errors.append(f"client[{i}]: 'host' is required")
            workloads = client.get("workloads")
            if workloads is not None and not isinstance(workloads, list):
                errors.append(f"client[{i}]: 'workloads' must be a list")
            env = client.get("env")
            if env is not None and not isinstance(env, dict):
                errors.append(f"client[{i}]: 'env' must be a mapping")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print("OK")


def cmd_count(inv: dict) -> None:
    """Print number of clients."""
    print(len(get_clients(inv)))


def cmd_list_clients(inv: dict) -> None:
    """Print 'index name host' per line."""
    for i, client in enumerate(get_clients(inv)):
        name = client.get("name", client["host"])
        host = client["host"]
        print(f"{i} {name} {host}")


def cmd_get_field(inv: dict, index: int, field: str) -> None:
    """Print a single field value."""
    clients = get_clients(inv)
    if index < 0 or index >= len(clients):
        print(f"ERROR: client index {index} out of range", file=sys.stderr)
        sys.exit(1)
    print(resolve_field(clients[index], get_defaults(inv), field))


def cmd_get_workloads(inv: dict, index: int) -> None:
    """Print workload paths, one per line."""
    clients = get_clients(inv)
    if index < 0 or index >= len(clients):
        print(f"ERROR: client index {index} out of range", file=sys.stderr)
        sys.exit(1)
    workloads = clients[index].get("workloads", [])
    if workloads is None:
        workloads = []
    for w in workloads:
        print(w)


def cmd_get_env(inv: dict, index: int) -> None:
    """Print KEY=VALUE env overrides, one per line."""
    clients = get_clients(inv)
    if index < 0 or index >= len(clients):
        print(f"ERROR: client index {index} out of range", file=sys.stderr)
        sys.exit(1)
    env = clients[index].get("env", {})
    if env is None:
        env = {}
    for k, v in env.items():
        print(f"{k}={v}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Master Control inventory helper")
    parser.add_argument(
        "--inventory", required=True, help="Path to inventory YAML file"
    )
    parser.add_argument("command", help="Command to run")
    parser.add_argument("args", nargs="*", help="Command arguments")
    args = parser.parse_args()

    inv = load_inventory(args.inventory)

    match args.command:
        case "validate":
            cmd_validate(inv)
        case "count":
            cmd_count(inv)
        case "list-clients":
            cmd_list_clients(inv)
        case "get-field":
            if len(args.args) != 2:
                print("Usage: get-field INDEX FIELD", file=sys.stderr)
                sys.exit(1)
            cmd_get_field(inv, int(args.args[0]), args.args[1])
        case "get-workloads":
            if len(args.args) != 1:
                print("Usage: get-workloads INDEX", file=sys.stderr)
                sys.exit(1)
            cmd_get_workloads(inv, int(args.args[0]))
        case "get-env":
            if len(args.args) != 1:
                print("Usage: get-env INDEX", file=sys.stderr)
                sys.exit(1)
            cmd_get_env(inv, int(args.args[0]))
        case _:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
