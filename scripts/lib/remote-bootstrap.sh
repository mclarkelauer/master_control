#!/usr/bin/env bash
# Remote bootstrap script for master_control clients.
#
# This script is copied to a remote client and executed there.
# It installs dependencies, sets up the environment, and starts the daemon.
#
# Expected environment variables (set by the deployer):
#   MCTL_INSTALL_DIR  — where master_control is installed (required)
#   MCTL_ENV_VARS     — newline-separated KEY=VALUE env overrides (optional)
#   MCTL_FORCE_RESTART — set to "1" to force daemon restart (optional)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$@"; exit 1; }

INSTALL_DIR="${MCTL_INSTALL_DIR:?MCTL_INSTALL_DIR must be set}"

# --- Detect distro ---
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        . /etc/os-release
        echo "$ID"
    else
        echo "unknown"
    fi
}

# --- Check Python version ---
python_version_ok() {
    local python_cmd="$1"
    if ! command -v "$python_cmd" &>/dev/null; then
        return 1
    fi
    local version
    version=$("$python_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)
    (( major >= 3 && minor >= 12 ))
}

# --- Install Python 3.12+ if needed ---
install_python() {
    if python_version_ok python3; then
        info "Python 3.12+ already available"
        return 0
    fi

    # Try python3.12 specifically
    if python_version_ok python3.12; then
        info "Python 3.12 already available"
        return 0
    fi

    local distro
    distro=$(detect_distro)
    info "Detected distro: $distro"

    case "$distro" in
        ubuntu|debian)
            info "Installing Python 3.12 via apt..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3.12 python3.12-venv 2>/dev/null \
                || sudo apt-get install -y -qq python3 python3-venv
            ;;
        fedora)
            info "Installing Python 3.12 via dnf..."
            sudo dnf install -y -q python3.12 2>/dev/null \
                || sudo dnf install -y -q python3
            ;;
        rhel|centos|rocky|alma)
            info "Installing Python 3.12 via dnf..."
            sudo dnf install -y -q python3.12 2>/dev/null \
                || sudo dnf install -y -q python3
            ;;
        *)
            die "Unsupported distro: $distro. Install Python 3.12+ manually."
            ;;
    esac

    # Verify installation
    if python_version_ok python3 || python_version_ok python3.12; then
        info "Python installed successfully"
    else
        die "Failed to install Python 3.12+. Install it manually."
    fi
}

# --- Install uv if needed ---
install_uv() {
    if command -v uv &>/dev/null; then
        info "uv already installed: $(uv --version)"
        return 0
    fi

    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"

    if command -v uv &>/dev/null; then
        info "uv installed: $(uv --version)"
    else
        die "Failed to install uv"
    fi
}

# --- Install project dependencies ---
install_deps() {
    info "Installing project dependencies..."
    cd "$INSTALL_DIR"
    uv sync
    info "Dependencies installed"
}

# --- Create runtime directories ---
create_dirs() {
    local dirs=("configs" "logs" "run")
    for dir in "${dirs[@]}"; do
        mkdir -p "$INSTALL_DIR/$dir"
    done
    info "Runtime directories ready"
}

# --- Write .env file with per-client overrides ---
write_env() {
    if [[ -n "${MCTL_ENV_VARS:-}" ]]; then
        info "Writing environment overrides to .env..."
        echo "$MCTL_ENV_VARS" > "$INSTALL_DIR/.env"
    fi
}

# --- Validate configs ---
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

# --- Start or restart daemon ---
start_daemon() {
    local daemon_script="$INSTALL_DIR/scripts/mctl-daemon.sh"
    if [[ ! -x "$daemon_script" ]]; then
        chmod +x "$daemon_script"
    fi

    # Source .env if it exists
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        set -a
        # shellcheck source=/dev/null
        . "$INSTALL_DIR/.env"
        set +a
    fi

    if [[ "${MCTL_FORCE_RESTART:-}" == "1" ]]; then
        info "Force-restarting daemon..."
        "$daemon_script" restart
    else
        # Check if daemon is running; start or restart as appropriate
        if "$daemon_script" status &>/dev/null; then
            info "Daemon already running — restarting..."
            "$daemon_script" restart
        else
            info "Starting daemon..."
            "$daemon_script" start
        fi
    fi
}

# --- Main ---
main() {
    echo ""
    echo "========================================="
    echo "  Master Control — Client Bootstrap"
    echo "========================================="
    echo ""

    install_python
    install_uv
    create_dirs
    install_deps
    write_env
    validate_configs
    start_daemon

    echo ""
    info "Bootstrap complete!"
    echo ""
}

main "$@"
