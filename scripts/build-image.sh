#!/usr/bin/env bash
# Build a pre-baked Raspberry Pi OS image with Master Control installed.
#
# Takes a stock Raspberry Pi OS Lite image, mounts it, injects the
# Master Control project files and a first-boot systemd service, then
# outputs a ready-to-flash .img file.
#
# Requires: sudo, losetup, rsync, and standard coreutils.
# Does NOT require QEMU — all ARM package installation happens on the
# Pi itself via the first-boot service.
#
# Usage:
#   sudo ./scripts/build-image.sh \
#       --image raspios-bookworm-arm64-lite.img.xz \
#       --hostname sensor-node-1 \
#       --ssh-key ~/.ssh/id_ed25519.pub

set -euo pipefail

# ─── Source common helpers if available ────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/lib/common.sh" ]]; then
    source "$SCRIPT_DIR/lib/common.sh"
else
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
    info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
    warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
    error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
    die()   { error "$@"; exit 1; }
    MCTL_PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# ─── Defaults ─────────────────────────────────────────────────────
IMAGE=""
OUTPUT=""
HOSTNAME="mctl-node"
WIFI_SSID=""
WIFI_PASSWORD=""
WIFI_COUNTRY="US"
SSH_KEY=""
INVENTORY=""
CLIENT=""
CONFIGS_DIR=""
FLEET_URL=""
FLEET_TOKEN=""
VERSION=""
INSTALL_DIR="/opt/master_control"

# Cleanup state
LOOP_DEV=""
MOUNT_BOOT=""
MOUNT_ROOT=""
WORK_IMG=""

# ─── Usage ────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: sudo $(basename "$0") [OPTIONS]

Build a pre-baked Raspberry Pi OS image with Master Control.

Required:
  --image FILE             Base Raspberry Pi OS image (.img or .img.xz)

Optional — OS configuration:
  --output FILE            Output image path (default: mctl-<hostname>.img)
  --hostname NAME          Set Pi hostname (default: mctl-node)
  --wifi-ssid SSID         Pre-configure WiFi
  --wifi-password PASS     WiFi password (required if --wifi-ssid set)
  --wifi-country CC        WiFi country code (default: US)
  --ssh-key FILE           SSH public key to authorize (also enables SSH)

Optional — Master Control configuration:
  --inventory FILE         Inventory file (to pull client-specific settings)
  --client NAME            Client name from inventory to configure
  --configs DIR            Workload configs directory to embed
  --fleet-url URL          Central API URL for fleet heartbeat
  --fleet-token TOKEN      API bearer token for fleet auth
  --version VERSION        Version string to write to .mctl-version
  --install-dir DIR        Install directory on Pi (default: /opt/master_control)

  -h, --help               Show this help
EOF
    exit 0
}

# ─── Parse arguments ──────────────────────────────────────────────
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --image)        IMAGE="$2"; shift 2 ;;
            --output)       OUTPUT="$2"; shift 2 ;;
            --hostname)     HOSTNAME="$2"; shift 2 ;;
            --wifi-ssid)    WIFI_SSID="$2"; shift 2 ;;
            --wifi-password) WIFI_PASSWORD="$2"; shift 2 ;;
            --wifi-country) WIFI_COUNTRY="$2"; shift 2 ;;
            --ssh-key)      SSH_KEY="$2"; shift 2 ;;
            --inventory)    INVENTORY="$2"; shift 2 ;;
            --client)       CLIENT="$2"; shift 2 ;;
            --configs)      CONFIGS_DIR="$2"; shift 2 ;;
            --fleet-url)    FLEET_URL="$2"; shift 2 ;;
            --fleet-token)  FLEET_TOKEN="$2"; shift 2 ;;
            --version)      VERSION="$2"; shift 2 ;;
            --install-dir)  INSTALL_DIR="$2"; shift 2 ;;
            -h|--help)      usage ;;
            *)              die "Unknown option: $1" ;;
        esac
    done

    [[ -n "$IMAGE" ]] || die "Missing required --image argument.  Use --help for usage."
    [[ -f "$IMAGE" ]] || die "Image file not found: $IMAGE"

    if [[ -n "$WIFI_SSID" && -z "$WIFI_PASSWORD" ]]; then
        die "--wifi-password is required when --wifi-ssid is set"
    fi

    if [[ -n "$SSH_KEY" && ! -f "$SSH_KEY" ]]; then
        die "SSH key file not found: $SSH_KEY"
    fi

    if [[ -n "$CONFIGS_DIR" && ! -d "$CONFIGS_DIR" ]]; then
        die "Configs directory not found: $CONFIGS_DIR"
    fi

    if [[ -n "$CLIENT" && -z "$INVENTORY" ]]; then
        die "--inventory is required when --client is set"
    fi

    if [[ -n "$INVENTORY" && ! -f "$INVENTORY" ]]; then
        die "Inventory file not found: $INVENTORY"
    fi

    [[ -z "$OUTPUT" ]] && OUTPUT="mctl-${HOSTNAME}.img"
}

# ─── Cleanup on exit ──────────────────────────────────────────────
cleanup() {
    local exit_code=$?
    set +e

    if [[ -n "$MOUNT_BOOT" && -d "$MOUNT_BOOT" ]]; then
        umount "$MOUNT_BOOT" 2>/dev/null
        rmdir "$MOUNT_BOOT" 2>/dev/null
    fi
    if [[ -n "$MOUNT_ROOT" && -d "$MOUNT_ROOT" ]]; then
        umount "$MOUNT_ROOT" 2>/dev/null
        rmdir "$MOUNT_ROOT" 2>/dev/null
    fi
    if [[ -n "$LOOP_DEV" ]]; then
        losetup -d "$LOOP_DEV" 2>/dev/null
    fi

    if [[ $exit_code -ne 0 && -n "$WORK_IMG" && -f "$WORK_IMG" ]]; then
        rm -f "$WORK_IMG"
        error "Cleaned up partial image: $WORK_IMG"
    fi

    exit $exit_code
}
trap cleanup EXIT

# ─── Validate prerequisites ───────────────────────────────────────
check_prereqs() {
    [[ $EUID -eq 0 ]] || die "This script must be run as root (sudo)."

    local cmds=(losetup mount umount rsync fdisk)
    for cmd in "${cmds[@]}"; do
        command -v "$cmd" &>/dev/null || die "Required command not found: $cmd"
    done

    if [[ "$IMAGE" == *.xz ]]; then
        command -v xz &>/dev/null || die "xz is required to decompress .img.xz images"
    fi
}

# ─── Prepare working copy of the image ────────────────────────────
prepare_image() {
    if [[ "$IMAGE" == *.xz ]]; then
        info "Decompressing $IMAGE ..."
        WORK_IMG="$OUTPUT"
        xz -dkc "$IMAGE" > "$WORK_IMG"
    else
        info "Copying $IMAGE → $OUTPUT ..."
        WORK_IMG="$OUTPUT"
        cp "$IMAGE" "$WORK_IMG"
    fi
    info "Working image: $WORK_IMG"
}

# ─── Mount the image partitions ───────────────────────────────────
mount_image() {
    # Set up a loop device with partition scanning.
    LOOP_DEV=$(losetup --find --show --partscan "$WORK_IMG")
    info "Loop device: $LOOP_DEV"

    # Wait briefly for partition devices to appear.
    sleep 1

    local part_boot="${LOOP_DEV}p1"
    local part_root="${LOOP_DEV}p2"

    [[ -b "$part_boot" ]] || die "Boot partition not found: $part_boot"
    [[ -b "$part_root" ]] || die "Root partition not found: $part_root"

    MOUNT_BOOT=$(mktemp -d /tmp/mctl-boot.XXXXXX)
    MOUNT_ROOT=$(mktemp -d /tmp/mctl-root.XXXXXX)

    mount "$part_boot" "$MOUNT_BOOT"
    mount "$part_root" "$MOUNT_ROOT"

    info "Mounted boot → $MOUNT_BOOT"
    info "Mounted root → $MOUNT_ROOT"
}

# ─── Enable SSH ───────────────────────────────────────────────────
setup_ssh() {
    # Raspberry Pi OS enables SSH if an empty "ssh" file exists on the boot
    # partition.
    touch "$MOUNT_BOOT/ssh"
    info "SSH enabled (boot/ssh sentinel created)"

    if [[ -n "$SSH_KEY" ]]; then
        local ssh_dir="$MOUNT_ROOT/root/.ssh"
        mkdir -p "$ssh_dir"
        chmod 700 "$ssh_dir"
        cp "$SSH_KEY" "$ssh_dir/authorized_keys"
        chmod 600 "$ssh_dir/authorized_keys"
        info "SSH public key installed for root"
    fi
}

# ─── Configure WiFi ──────────────────────────────────────────────
setup_wifi() {
    [[ -n "$WIFI_SSID" ]] || return 0

    cat > "$MOUNT_BOOT/wpa_supplicant.conf" <<WPAEOF
country=$WIFI_COUNTRY
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PASSWORD"
    key_mgmt=WPA-PSK
}
WPAEOF
    info "WiFi configured: SSID=$WIFI_SSID country=$WIFI_COUNTRY"
}

# ─── Set hostname ────────────────────────────────────────────────
setup_hostname() {
    echo "$HOSTNAME" > "$MOUNT_ROOT/etc/hostname"

    # Update /etc/hosts — replace the default "raspberrypi" entry.
    if [[ -f "$MOUNT_ROOT/etc/hosts" ]]; then
        sed -i "s/raspberrypi/$HOSTNAME/g" "$MOUNT_ROOT/etc/hosts"
    fi
    info "Hostname set to: $HOSTNAME"
}

# ─── Copy Master Control project files ────────────────────────────
copy_project() {
    local target="$MOUNT_ROOT$INSTALL_DIR"
    mkdir -p "$target"

    rsync -a \
        --exclude='.venv/' \
        --exclude='logs/' \
        --exclude='run/' \
        --exclude='*.db' \
        --exclude='.git/' \
        --exclude='__pycache__/' \
        --exclude='.pytest_cache/' \
        --exclude='configs/' \
        "$MCTL_PROJECT_ROOT/" "$target/"

    # Ensure scripts are executable.
    chmod +x "$target"/scripts/*.sh 2>/dev/null || true
    chmod +x "$target"/scripts/lib/*.sh 2>/dev/null || true

    info "Project files copied to $INSTALL_DIR"
}

# ─── Copy workload configs ────────────────────────────────────────
copy_configs() {
    local target="$MOUNT_ROOT$INSTALL_DIR/configs"
    mkdir -p "$target"

    if [[ -n "$CLIENT" && -n "$INVENTORY" ]]; then
        # Copy only the workload configs assigned to this client in the
        # inventory.  Uses the inventory_helper.py to resolve the client.
        local helper="$MCTL_PROJECT_ROOT/scripts/lib/inventory_helper.py"
        if [[ -f "$helper" ]]; then
            local idx
            # Find client index by name.
            idx=$(python3 "$helper" "$INVENTORY" list-clients \
                | awk -v name="$CLIENT" '$2 == name { print $1; exit }')

            if [[ -z "$idx" ]]; then
                warn "Client '$CLIENT' not found in inventory — skipping workload configs"
                return 0
            fi

            local workloads
            workloads=$(python3 "$helper" "$INVENTORY" get-workloads "$idx" 2>/dev/null || true)

            if [[ -n "$workloads" ]]; then
                while IFS= read -r wl_path; do
                    if [[ -f "$MCTL_PROJECT_ROOT/$wl_path" ]]; then
                        cp "$MCTL_PROJECT_ROOT/$wl_path" "$target/"
                        info "  config: $wl_path"
                    else
                        warn "  config not found: $wl_path"
                    fi
                done <<< "$workloads"
            else
                info "No workloads assigned to client '$CLIENT' — copying all configs"
                copy_all_configs "$target"
            fi

            # Also extract and write per-client env overrides.
            local env_vars
            env_vars=$(python3 "$helper" "$INVENTORY" get-env "$idx" 2>/dev/null || true)
            if [[ -n "$env_vars" ]]; then
                echo "$env_vars" > "$MOUNT_ROOT$INSTALL_DIR/.env"
                info "Per-client environment overrides written to .env"
            fi
        else
            warn "inventory_helper.py not found — falling back to full config copy"
            copy_all_configs "$target"
        fi
    elif [[ -n "$CONFIGS_DIR" ]]; then
        cp "$CONFIGS_DIR"/*.yaml "$target/" 2>/dev/null || true
        info "Workload configs copied from $CONFIGS_DIR"
    else
        copy_all_configs "$target"
    fi
}

copy_all_configs() {
    local target="$1"
    if ls "$MCTL_PROJECT_ROOT"/configs/*.yaml 2>/dev/null | head -1 &>/dev/null; then
        cp "$MCTL_PROJECT_ROOT"/configs/*.yaml "$target/"
        info "All workload configs copied"
    else
        info "No workload configs found to copy"
    fi
}

# ─── Write fleet daemon.yaml ─────────────────────────────────────
write_fleet_config() {
    [[ -n "$FLEET_URL" ]] || return 0

    local daemon_yaml="$MOUNT_ROOT$INSTALL_DIR/configs/daemon.yaml"
    mkdir -p "$(dirname "$daemon_yaml")"

    cat > "$daemon_yaml" <<YAMLEOF
fleet:
  enabled: true
  client_name: "$HOSTNAME"
  api_host: "0.0.0.0"
  api_port: 9100
  central_api_url: "$FLEET_URL"
  heartbeat_interval_seconds: 30.0
YAMLEOF

    if [[ -n "$FLEET_TOKEN" ]]; then
        echo "  api_token: \"$FLEET_TOKEN\"" >> "$daemon_yaml"
    fi

    info "Fleet config written: central_api_url=$FLEET_URL"
}

# ─── Write version file ──────────────────────────────────────────
write_version() {
    [[ -n "$VERSION" ]] || return 0
    echo "$VERSION" > "$MOUNT_ROOT$INSTALL_DIR/.mctl-version"
    info "Version: $VERSION"
}

# ─── Install first-boot service ───────────────────────────────────
install_first_boot() {
    local service_src="$MCTL_PROJECT_ROOT/scripts/lib/mctl-first-boot.service"
    local service_dst="$MOUNT_ROOT/etc/systemd/system/mctl-first-boot.service"

    [[ -f "$service_src" ]] || die "First-boot service unit not found: $service_src"

    # The install dir may differ from the default /opt/master_control.
    # Patch the unit file and first-boot script paths if needed.
    if [[ "$INSTALL_DIR" != "/opt/master_control" ]]; then
        sed "s|/opt/master_control|$INSTALL_DIR|g" "$service_src" > "$service_dst"
    else
        cp "$service_src" "$service_dst"
    fi

    # Enable the service by creating the symlink manually (no systemctl
    # available on the host for the image's filesystem).
    local wants_dir="$MOUNT_ROOT/etc/systemd/system/multi-user.target.wants"
    mkdir -p "$wants_dir"
    ln -sf /etc/systemd/system/mctl-first-boot.service "$wants_dir/mctl-first-boot.service"

    # Patch the first-boot script's INSTALL_DIR if non-default.
    local boot_script="$MOUNT_ROOT$INSTALL_DIR/scripts/lib/mctl-first-boot.sh"
    if [[ "$INSTALL_DIR" != "/opt/master_control" && -f "$boot_script" ]]; then
        sed -i "s|INSTALL_DIR=\"/opt/master_control\"|INSTALL_DIR=\"$INSTALL_DIR\"|" "$boot_script"
    fi

    # Create the sentinel file that triggers the service.
    touch "$MOUNT_ROOT$INSTALL_DIR/.mctl-first-boot"

    info "First-boot service installed and enabled"
}

# ─── Main ─────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}  Master Control — SD Card Image Builder${NC}"
    echo -e "${BLUE}==========================================${NC}"
    echo ""

    parse_args "$@"
    check_prereqs

    info "Base image:  $IMAGE"
    info "Output:      $OUTPUT"
    info "Hostname:    $HOSTNAME"
    info "Install dir: $INSTALL_DIR"
    echo ""

    prepare_image
    mount_image
    setup_ssh
    setup_wifi
    setup_hostname
    copy_project
    copy_configs
    write_fleet_config
    write_version
    install_first_boot

    # Unmount cleanly (cleanup trap handles error cases).
    umount "$MOUNT_BOOT"
    umount "$MOUNT_ROOT"
    rmdir "$MOUNT_BOOT" "$MOUNT_ROOT"
    MOUNT_BOOT=""
    MOUNT_ROOT=""
    losetup -d "$LOOP_DEV"
    LOOP_DEV=""

    echo ""
    info "Image ready: $OUTPUT"
    info "Flash with:  sudo dd if=$OUTPUT of=/dev/sdX bs=4M status=progress"
    echo ""
}

main "$@"
