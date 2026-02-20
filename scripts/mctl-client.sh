#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SOCKET_PATH="${MCTL_SOCKET_PATH:-/tmp/master_control.sock}"
CONFIG_DIR="${MCTL_CONFIG_DIR:-$PROJECT_ROOT/configs}"
DB_PATH="${MCTL_DB_PATH:-$PROJECT_ROOT/master_control.db}"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Usage ---

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands (require running daemon):
  list                List all workloads and their status
  status <name>       Show detailed status of a workload
  start <name>        Start a specific workload
  stop <name>         Stop a specific workload
  restart <name>      Restart a specific workload
  logs <name> [-n N]  Show recent log lines for a workload

Commands (offline):
  validate            Validate all config files
  run <name>          Run a workload in foreground (bypasses daemon)

Environment variables:
  MCTL_CONFIG_DIR    Config directory (default: ./configs)
  MCTL_DB_PATH       SQLite database path (default: ./master_control.db)
  MCTL_SOCKET_PATH   IPC socket path (default: /tmp/master_control.sock)
EOF
}

# --- Check daemon ---

check_daemon() {
    if [[ ! -S "$SOCKET_PATH" ]]; then
        error "Daemon is not running (no socket at $SOCKET_PATH)"
        error "Start it with: ./scripts/mctl-daemon.sh start"
        exit 1
    fi
}

# --- Main ---

CMD="${1:-}"

case "$CMD" in
    # Commands that need a running daemon
    list|status|start|stop|restart)
        check_daemon
        shift
        cd "$PROJECT_ROOT"
        exec uv run master-control \
            --socket-path "$SOCKET_PATH" \
            --config-dir "$CONFIG_DIR" \
            --db-path "$DB_PATH" \
            "$CMD" "$@"
        ;;

    logs)
        check_daemon
        shift
        cd "$PROJECT_ROOT"
        exec uv run master-control "$CMD" "$@"
        ;;

    # Offline commands
    validate)
        shift
        cd "$PROJECT_ROOT"
        exec uv run master-control \
            --config-dir "$CONFIG_DIR" \
            validate "$@"
        ;;

    run)
        shift
        cd "$PROJECT_ROOT"
        exec uv run master-control \
            --config-dir "$CONFIG_DIR" \
            run "$@"
        ;;

    -h|--help|help)
        usage
        ;;

    *)
        usage >&2
        exit 1
        ;;
esac
