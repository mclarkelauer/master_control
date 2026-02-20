#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

LOCAL_ONLY=0
DEPLOY_ONLY=0
DEPLOY_ARGS=()

# --- Usage ---
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Set up the master_control control host and optionally deploy to clients.

Options:
  --local-only        Only set up the control host, don't deploy to clients
  --deploy-only       Skip local setup, just deploy to clients
  --inventory FILE    Inventory file for client deployment (default: \$MCTL_INVENTORY)
  -h, --help          Show this help

Any additional flags (--parallel, --dry-run, etc.) are forwarded to deploy-clients.sh.

Environment variables:
  MCTL_INVENTORY          Inventory file path (default: ./inventory.yaml)
  MCTL_DEPLOY_PARALLEL    Max parallel deployments (default: 5)
EOF
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --local-only)
            LOCAL_ONLY=1
            shift
            ;;
        --deploy-only)
            DEPLOY_ONLY=1
            shift
            ;;
        --inventory)
            MCTL_INVENTORY="$2"
            DEPLOY_ARGS+=(--inventory "$2")
            shift 2
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        *)
            # Forward unknown args to deploy-clients.sh
            DEPLOY_ARGS+=("$1")
            shift
            ;;
    esac
done

# --- Local setup ---
setup_local() {
    echo ""
    echo "========================================="
    echo "  Master Control — Control Host Setup"
    echo "========================================="
    echo ""

    # Run existing install script
    info "Running local installation..."
    bash "$SCRIPT_DIR/install.sh"

    # Start daemon
    info "Starting local daemon..."
    bash "$SCRIPT_DIR/mctl-daemon.sh" start

    # Verify daemon is healthy
    sleep 2
    if bash "$SCRIPT_DIR/mctl-daemon.sh" status &>/dev/null; then
        info "Local daemon is healthy"
    else
        warn "Local daemon may not be running — check logs with: make logs"
    fi
}

# --- Deploy to clients ---
deploy_clients() {
    if [[ ! -f "$MCTL_INVENTORY" ]]; then
        info "No inventory file found at $MCTL_INVENTORY — skipping client deployment"
        info "Create an inventory file to deploy to remote clients"
        info "See configs/examples/inventory.yaml for the format"
        return 0
    fi

    info "Deploying to clients from $MCTL_INVENTORY..."
    bash "$SCRIPT_DIR/deploy-clients.sh" "${DEPLOY_ARGS[@]}"
}

# --- Main ---
main() {
    if (( LOCAL_ONLY && DEPLOY_ONLY )); then
        die "Cannot use --local-only and --deploy-only together"
    fi

    if ! (( DEPLOY_ONLY )); then
        setup_local
    fi

    if ! (( LOCAL_ONLY )); then
        deploy_clients
    fi

    echo ""
    info "Setup complete!"
}

main "$@"
