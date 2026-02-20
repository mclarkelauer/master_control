#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

CONFIG_DIR="${MCTL_CONFIG_DIR:-$PROJECT_ROOT/configs}"
DB_PATH="${MCTL_DB_PATH:-$PROJECT_ROOT/master_control.db}"
SOCKET_PATH="${MCTL_SOCKET_PATH:-/tmp/master_control.sock}"
PID_DIR="$PROJECT_ROOT/run"
PID_FILE="$PID_DIR/master-control.pid"
LOG_DIR="$PROJECT_ROOT/logs"
DAEMON_LOG="$LOG_DIR/daemon.log"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Helpers ---

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(<"$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # Stale PID file
        rm -f "$PID_FILE"
    fi
    return 1
}

get_pid() {
    if [[ -f "$PID_FILE" ]]; then
        cat "$PID_FILE"
    fi
}

# --- Commands ---

cmd_start() {
    if is_running; then
        local pid
        pid=$(get_pid)
        info "Daemon already running (PID $pid)"
        return 0
    fi

    mkdir -p "$PID_DIR" "$LOG_DIR"

    info "Starting master-control daemon..."
    info "  Config dir:   $CONFIG_DIR"
    info "  Database:     $DB_PATH"
    info "  Socket:       $SOCKET_PATH"
    info "  Daemon log:   $DAEMON_LOG"

    cd "$PROJECT_ROOT"
    nohup uv run master-control \
        --config-dir "$CONFIG_DIR" \
        --db-path "$DB_PATH" \
        --socket-path "$SOCKET_PATH" \
        up \
        >> "$DAEMON_LOG" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"

    # Wait briefly and check it actually started
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        info "Daemon started (PID $pid)"
    else
        error "Daemon failed to start. Check $DAEMON_LOG"
        rm -f "$PID_FILE"
        return 1
    fi
}

cmd_stop() {
    if ! is_running; then
        info "Daemon is not running"
        return 0
    fi

    local pid
    pid=$(get_pid)
    info "Stopping daemon (PID $pid)..."

    # Try graceful shutdown via IPC first
    if [[ -S "$SOCKET_PATH" ]]; then
        uv run master-control --socket-path "$SOCKET_PATH" down 2>/dev/null || true
        # Wait for graceful shutdown
        local waited=0
        while kill -0 "$pid" 2>/dev/null && (( waited < 10 )); do
            sleep 1
            (( waited++ ))
        done
    fi

    # If still running, send SIGTERM
    if kill -0 "$pid" 2>/dev/null; then
        warn "Graceful shutdown timed out, sending SIGTERM..."
        kill -TERM "$pid" 2>/dev/null || true

        local waited=0
        while kill -0 "$pid" 2>/dev/null && (( waited < 5 )); do
            sleep 1
            (( waited++ ))
        done
    fi

    # Last resort: SIGKILL
    if kill -0 "$pid" 2>/dev/null; then
        warn "SIGTERM failed, sending SIGKILL..."
        kill -KILL "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    info "Daemon stopped"
}

cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    if is_running; then
        local pid
        pid=$(get_pid)
        info "Daemon is running (PID $pid)"
        info "  Socket: $SOCKET_PATH"

        # Try to get workload list
        if [[ -S "$SOCKET_PATH" ]]; then
            echo ""
            uv run master-control --socket-path "$SOCKET_PATH" list 2>/dev/null || true
        fi
        return 0
    else
        info "Daemon is not running"
        return 1
    fi
}

cmd_logs() {
    local lines="${1:-50}"
    if [[ -f "$DAEMON_LOG" ]]; then
        tail -n "$lines" "$DAEMON_LOG"
    else
        error "No daemon log found at $DAEMON_LOG"
        return 1
    fi
}

# --- Usage ---

usage() {
    cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  start     Start the master-control daemon in the background
  stop      Stop the running daemon gracefully
  restart   Restart the daemon
  status    Check if the daemon is running
  logs [N]  Show last N lines of daemon log (default: 50)

Environment variables:
  MCTL_CONFIG_DIR    Config directory (default: ./configs)
  MCTL_DB_PATH       SQLite database path (default: ./master_control.db)
  MCTL_SOCKET_PATH   IPC socket path (default: /tmp/master_control.sock)
EOF
}

# --- Main ---

case "${1:-}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    status)  cmd_status ;;
    logs)    cmd_logs "${2:-50}" ;;
    -h|--help|help) usage ;;
    *)
        usage >&2
        exit 1
        ;;
esac
