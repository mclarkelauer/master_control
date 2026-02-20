#!/usr/bin/env bash
# Shared shell functions for master_control scripts.
# Source this file: source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()   { error "$@"; exit 1; }

# Check that a command exists or die with a helpful message.
require_cmd() {
    local cmd="$1"
    local hint="${2:-}"
    if ! command -v "$cmd" &>/dev/null; then
        if [[ -n "$hint" ]]; then
            die "$cmd not found. $hint"
        else
            die "$cmd not found."
        fi
    fi
}

# Resolve the project root (two levels up from scripts/lib/).
_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCTL_PROJECT_ROOT="$(cd "$_COMMON_DIR/../.." && pwd)"

# Default environment variables.
MCTL_INVENTORY="${MCTL_INVENTORY:-$MCTL_PROJECT_ROOT/inventory.yaml}"
MCTL_DEPLOY_PARALLEL="${MCTL_DEPLOY_PARALLEL:-5}"
MCTL_INSTALL_DIR="${MCTL_INSTALL_DIR:-/opt/master_control}"
MCTL_SSH_TIMEOUT="${MCTL_SSH_TIMEOUT:-10}"
