#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$@"; exit 1; }

# --- Check Python version ---
check_python() {
    if ! command -v python3 &>/dev/null; then
        die "python3 not found. Please install Python 3.12+."
    fi

    local version
    version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    local major minor
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if (( major < 3 || (major == 3 && minor < 12) )); then
        die "Python 3.12+ required, found Python $version"
    fi

    info "Python $version found"
}

# --- Check uv ---
check_uv() {
    if ! command -v uv &>/dev/null; then
        die "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi
    info "uv $(uv --version | awk '{print $2}') found"
}

# --- Install dependencies ---
install_deps() {
    info "Installing dependencies..."
    cd "$PROJECT_ROOT"
    uv sync
    info "Dependencies installed"
}

# --- Create directories ---
create_dirs() {
    local dirs=("configs" "logs" "run")
    for dir in "${dirs[@]}"; do
        mkdir -p "$PROJECT_ROOT/$dir"
    done
    info "Created directories: ${dirs[*]}"
}

# --- Validate configs ---
validate_configs() {
    if ls "$PROJECT_ROOT"/configs/*.yaml "$PROJECT_ROOT"/configs/**/*.yaml 2>/dev/null | head -1 &>/dev/null; then
        info "Validating configs..."
        if uv run master-control --config-dir "$PROJECT_ROOT/configs" validate 2>/dev/null; then
            info "All configs valid"
        else
            warn "Config validation had issues (this is OK if using example configs with invalid fixtures)"
        fi
    else
        info "No configs found yet — add YAML files to configs/"
    fi
}

# --- Main ---
main() {
    echo ""
    echo "========================================="
    echo "  Master Control — Installation"
    echo "========================================="
    echo ""

    check_python
    check_uv
    install_deps
    create_dirs
    validate_configs

    echo ""
    info "Installation complete!"
    echo ""
    echo "  Next steps:"
    echo "    1. Add workload configs to configs/"
    echo "    2. Start the daemon:  ./scripts/mctl-daemon.sh start"
    echo "    3. Check status:      ./scripts/mctl-daemon.sh status"
    echo "    4. List workloads:    uv run master-control list"
    echo ""
}

main "$@"
