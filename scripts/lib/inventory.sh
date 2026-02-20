#!/usr/bin/env bash
# Shell wrappers around inventory_helper.py for use in deployment scripts.
# Source this file after common.sh.

_INV_HELPER="$MCTL_PROJECT_ROOT/scripts/lib/inventory_helper.py"

# Run the inventory helper with the configured inventory file.
_inv() {
    uv run python3 "$_INV_HELPER" --inventory "$MCTL_INVENTORY" "$@"
}

# Validate the inventory file. Dies on error.
inv_validate() {
    _inv validate >/dev/null || die "Invalid inventory file: $MCTL_INVENTORY"
}

# Print the number of clients.
inv_count() {
    _inv count
}

# Print "index name host" per line.
inv_list_clients() {
    _inv list-clients
}

# Get a field for a client (with defaults fallback).
# Usage: inv_get_field INDEX FIELD
inv_get_field() {
    _inv get-field "$1" "$2"
}

# Print workload config paths for a client, one per line.
# Usage: inv_get_workloads INDEX
inv_get_workloads() {
    _inv get-workloads "$1"
}

# Print KEY=VALUE env overrides for a client, one per line.
# Usage: inv_get_env INDEX
inv_get_env() {
    _inv get-env "$1"
}
