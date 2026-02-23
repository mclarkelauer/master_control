#!/usr/bin/env bash
# Master Control — first-boot setup for pre-baked SD card images.
#
# This script runs once on the first boot of a Raspberry Pi that was
# prepared with build-image.sh.  It installs Python, uv, project
# dependencies, validates configs, and starts the daemon.
#
# Triggered by mctl-first-boot.service (systemd one-shot).
# Logs to /opt/master_control/logs/first-boot.log.

set -euo pipefail

INSTALL_DIR="/opt/master_control"
LOG_DIR="$INSTALL_DIR/logs"
LOG_FILE="$LOG_DIR/first-boot.log"
SENTINEL="$INSTALL_DIR/.mctl-first-boot"

mkdir -p "$LOG_DIR"

# Redirect all output to both console and log file.
exec > >(tee -a "$LOG_FILE") 2>&1

info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

die() {
    error "$@"
    error "First-boot setup FAILED.  See $LOG_FILE for details."
    exit 1
}

# ─── Detect distro ────────────────────────────────────────────────
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

# ─── Check Python version ────────────────────────────────────────
python_version_ok() {
    local cmd="$1"
    command -v "$cmd" &>/dev/null || return 1
    local ver
    ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major minor
    major=${ver%%.*}
    minor=${ver##*.}
    (( major >= 3 && minor >= 12 ))
}

# ─── Install Python 3.12+ ────────────────────────────────────────
install_python() {
    if python_version_ok python3 || python_version_ok python3.12; then
        info "Python 3.12+ already available"
        return 0
    fi

    local distro
    distro=$(detect_distro)
    info "Detected distro: $distro"

    case "$distro" in
        ubuntu|debian|raspbian)
            info "Installing Python 3.12 via apt..."
            apt-get update -qq
            apt-get install -y -qq python3 python3-venv
            ;;
        fedora)
            info "Installing Python 3.12 via dnf..."
            dnf install -y -q python3.12 2>/dev/null \
                || dnf install -y -q python3
            ;;
        *)
            die "Unsupported distro: $distro — install Python 3.12+ manually."
            ;;
    esac

    if python_version_ok python3 || python_version_ok python3.12; then
        info "Python installed successfully"
    else
        die "Failed to install Python 3.12+"
    fi
}

# ─── Install uv ──────────────────────────────────────────────────
install_uv() {
    if command -v uv &>/dev/null; then
        info "uv already installed: $(uv --version)"
        return 0
    fi

    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Make uv available for this session.
    export PATH="/root/.local/bin:$HOME/.local/bin:$PATH"

    if command -v uv &>/dev/null; then
        info "uv installed: $(uv --version)"
    else
        die "Failed to install uv"
    fi
}

# ─── Install project dependencies ────────────────────────────────
install_deps() {
    info "Installing project dependencies..."
    cd "$INSTALL_DIR"
    uv sync
    info "Dependencies installed"
}

# ─── Create runtime directories ──────────────────────────────────
create_dirs() {
    mkdir -p "$INSTALL_DIR"/{configs,logs,run}
    info "Runtime directories ready"
}

# ─── Validate configs ────────────────────────────────────────────
validate_configs() {
    if ls "$INSTALL_DIR"/configs/*.yaml 2>/dev/null | head -1 &>/dev/null; then
        info "Validating workload configs..."
        cd "$INSTALL_DIR"
        if uv run master-control --config-dir "$INSTALL_DIR/configs" validate 2>/dev/null; then
            info "All configs valid"
        else
            warn "Config validation had issues — check configs manually"
        fi
    else
        info "No workload configs deployed yet"
    fi
}

# ─── Start daemon ────────────────────────────────────────────────
start_daemon() {
    local daemon_script="$INSTALL_DIR/scripts/mctl-daemon.sh"
    chmod +x "$daemon_script"

    # Source .env if it exists.
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        set -a
        # shellcheck source=/dev/null
        . "$INSTALL_DIR/.env"
        set +a
    fi

    info "Starting daemon..."
    "$daemon_script" start
}

# ─── Remove sentinel so this service never runs again ─────────────
remove_sentinel() {
    rm -f "$SENTINEL"
    info "First-boot sentinel removed — this service will not run again."
}

# ─── Main ─────────────────────────────────────────────────────────
main() {
    echo ""
    echo "========================================="
    echo "  Master Control — First-Boot Setup"
    echo "========================================="
    echo ""

    if [[ ! -f "$SENTINEL" ]]; then
        info "Sentinel file not found — first-boot already completed."
        exit 0
    fi

    install_python
    install_uv
    create_dirs
    install_deps
    validate_configs
    start_daemon
    remove_sentinel

    echo ""
    info "First-boot setup complete!"
    echo ""
}

main "$@"
