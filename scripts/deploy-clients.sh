#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/inventory.sh"

# --- Defaults ---
PARALLEL="$MCTL_DEPLOY_PARALLEL"
DRY_RUN=0
SYNC_ONLY=0
FORCE_RESTART=0
DEPLOY_VERSION=""
TARGET_CLIENTS=()

# --- Usage ---
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Deploy master_control to remote clients defined in an inventory file.

Options:
  --inventory FILE    Path to inventory YAML (default: \$MCTL_INVENTORY or ./inventory.yaml)
  --client NAME       Deploy to specific client(s) only (repeatable)
  --parallel N        Max parallel deployments (default: $MCTL_DEPLOY_PARALLEL)
  --dry-run           Show what would be done without doing it
  --sync-only         Sync project files and configs but don't restart daemon
  --force-restart     Force daemon restart even if no config changes
  --version VERSION   Write version string to .mctl-version on remote
  -h, --help          Show this help

Environment variables:
  MCTL_INVENTORY          Inventory file path (default: ./inventory.yaml)
  MCTL_DEPLOY_PARALLEL    Max parallel deployments (default: 5)
  MCTL_INSTALL_DIR        Default remote install directory (default: /opt/master_control)
  MCTL_SSH_TIMEOUT        SSH connection timeout in seconds (default: 10)
EOF
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --inventory)
            MCTL_INVENTORY="$2"
            shift 2
            ;;
        --client)
            TARGET_CLIENTS+=("$2")
            shift 2
            ;;
        --parallel)
            PARALLEL="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --sync-only)
            SYNC_ONLY=1
            shift
            ;;
        --force-restart)
            FORCE_RESTART=1
            shift
            ;;
        --version)
            DEPLOY_VERSION="$2"
            shift 2
            ;;
        -h|--help|help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            usage >&2
            exit 1
            ;;
    esac
done

# --- Validate inventory ---
if [[ ! -f "$MCTL_INVENTORY" ]]; then
    die "Inventory file not found: $MCTL_INVENTORY"
fi
inv_validate

# --- Build SSH command ---
build_ssh_opts() {
    local index="$1"
    local user host port key
    user=$(inv_get_field "$index" ssh_user)
    host=$(inv_get_field "$index" host)
    port=$(inv_get_field "$index" ssh_port)
    key=$(inv_get_field "$index" ssh_key)

    local opts=(-o "ConnectTimeout=$MCTL_SSH_TIMEOUT" -o "StrictHostKeyChecking=accept-new" -o "BatchMode=yes")
    [[ -n "$port" && "$port" != "22" ]] && opts+=(-p "$port")
    [[ -n "$key" ]] && opts+=(-i "$key")

    echo "${opts[*]}"
}

build_ssh_target() {
    local index="$1"
    local user host
    user=$(inv_get_field "$index" ssh_user)
    host=$(inv_get_field "$index" host)
    if [[ -n "$user" ]]; then
        echo "$user@$host"
    else
        echo "$host"
    fi
}

# --- Deploy to a single client ---
deploy_client() {
    local index="$1"
    local name host install_dir ssh_opts ssh_target
    name=$(inv_get_field "$index" name)
    host=$(inv_get_field "$index" host)
    install_dir=$(inv_get_field "$index" install_dir)
    [[ -z "$install_dir" ]] && install_dir="$MCTL_INSTALL_DIR"
    [[ -z "$name" ]] && name="$host"

    ssh_opts=$(build_ssh_opts "$index")
    ssh_target=$(build_ssh_target "$index")

    local log_file="/tmp/mctl-deploy-${name}.log"

    info "[$name] Deploying to $host..."

    # Step 1: Validate SSH connectivity
    info "[$name] Checking SSH connectivity..."
    if ! ssh $ssh_opts "$ssh_target" true 2>"$log_file"; then
        error "[$name] SSH connection failed. See $log_file"
        return 1
    fi

    # Step 2: Create remote install directory
    info "[$name] Ensuring install directory: $install_dir"
    ssh $ssh_opts "$ssh_target" "mkdir -p '$install_dir'" 2>>"$log_file"

    # Step 3: Rsync project files (excluding runtime artifacts)
    info "[$name] Syncing project files..."
    local rsync_port_opt=""
    local port
    port=$(inv_get_field "$index" ssh_port)
    [[ -n "$port" && "$port" != "22" ]] && rsync_port_opt="-e 'ssh -p $port'"

    local rsync_ssh="ssh $ssh_opts"
    rsync -az --delete \
        -e "$rsync_ssh" \
        --exclude='.venv/' \
        --exclude='logs/' \
        --exclude='run/' \
        --exclude='*.db' \
        --exclude='.git/' \
        --exclude='__pycache__/' \
        --exclude='.pytest_cache/' \
        --exclude='configs/' \
        "$MCTL_PROJECT_ROOT/" \
        "$ssh_target:$install_dir/" \
        2>>"$log_file"

    # Step 4: Sync workload configs
    info "[$name] Syncing workload configs..."
    ssh $ssh_opts "$ssh_target" "mkdir -p '$install_dir/configs'" 2>>"$log_file"

    local workloads
    workloads=$(inv_get_workloads "$index")

    if [[ -z "$workloads" ]]; then
        # Empty workloads list = deploy all configs
        rsync -az --delete \
            -e "$rsync_ssh" \
            "$MCTL_PROJECT_ROOT/configs/" \
            "$ssh_target:$install_dir/configs/" \
            2>>"$log_file"
    else
        # Deploy only specified workload configs
        # Clear existing configs first
        ssh $ssh_opts "$ssh_target" "rm -f '$install_dir'/configs/*.yaml" 2>>"$log_file"
        while IFS= read -r config_path; do
            if [[ -f "$MCTL_PROJECT_ROOT/$config_path" ]]; then
                rsync -az \
                    -e "$rsync_ssh" \
                    "$MCTL_PROJECT_ROOT/$config_path" \
                    "$ssh_target:$install_dir/configs/" \
                    2>>"$log_file"
            else
                warn "[$name] Config file not found: $config_path"
            fi
        done <<< "$workloads"
    fi

    # Step 4b: Write version file if specified
    if [[ -n "$DEPLOY_VERSION" ]]; then
        info "[$name] Writing version: $DEPLOY_VERSION"
        ssh $ssh_opts "$ssh_target" "echo '$DEPLOY_VERSION' > '$install_dir/.mctl-version'" 2>>"$log_file"
    fi

    # Step 5: Run bootstrap on remote (unless --sync-only)
    if (( SYNC_ONLY )); then
        info "[$name] Sync complete (--sync-only, skipping bootstrap)"
        return 0
    fi

    info "[$name] Running bootstrap on remote..."

    # Build env vars to pass
    local env_str="MCTL_INSTALL_DIR='$install_dir'"
    if (( FORCE_RESTART )); then
        env_str="$env_str MCTL_FORCE_RESTART=1"
    fi

    local client_env
    client_env=$(inv_get_env "$index")
    if [[ -n "$client_env" ]]; then
        env_str="$env_str MCTL_ENV_VARS='$client_env'"
    fi

    ssh $ssh_opts "$ssh_target" \
        "$env_str bash '$install_dir/scripts/lib/remote-bootstrap.sh'" \
        2>>"$log_file"

    info "[$name] Deployment complete"
}

# --- Main ---
main() {
    echo ""
    echo "========================================="
    echo "  Master Control — Client Deployment"
    echo "========================================="
    echo ""

    require_cmd rsync "Install rsync to continue."
    require_cmd ssh "Install openssh-client to continue."

    local client_count
    client_count=$(inv_count)
    info "Inventory: $MCTL_INVENTORY ($client_count clients)"
    info "Parallel: $PARALLEL"

    if (( DRY_RUN )); then
        info "DRY RUN — showing deployment plan only"
        echo ""
    fi

    # Build target list
    local targets=()
    while IFS=' ' read -r idx name host; do
        if (( ${#TARGET_CLIENTS[@]} > 0 )); then
            local matched=0
            for target_name in "${TARGET_CLIENTS[@]}"; do
                if [[ "$name" == "$target_name" || "$host" == "$target_name" ]]; then
                    matched=1
                    break
                fi
            done
            (( matched )) || continue
        fi
        targets+=("$idx")

        if (( DRY_RUN )); then
            local install_dir
            install_dir=$(inv_get_field "$idx" install_dir)
            [[ -z "$install_dir" ]] && install_dir="$MCTL_INSTALL_DIR"
            local workloads
            workloads=$(inv_get_workloads "$idx")
            echo "  [$name] $host → $install_dir"
            if [[ -n "$workloads" ]]; then
                while IFS= read -r w; do
                    echo "    - $w"
                done <<< "$workloads"
            else
                echo "    - (all configs)"
            fi
        fi
    done < <(inv_list_clients)

    if (( ${#targets[@]} == 0 )); then
        warn "No matching clients found"
        exit 0
    fi

    if (( DRY_RUN )); then
        echo ""
        info "Would deploy to ${#targets[@]} client(s)"
        exit 0
    fi

    info "Deploying to ${#targets[@]} client(s)..."
    echo ""

    # Parallel deployment with semaphore
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"
    exec 3<>"$fifo"
    rm "$fifo"

    # Fill semaphore with tokens
    for ((i = 0; i < PARALLEL; i++)); do
        echo >&3
    done

    local pids=()
    local results_dir
    results_dir=$(mktemp -d)

    for idx in "${targets[@]}"; do
        read -u 3  # acquire semaphore token
        (
            if deploy_client "$idx"; then
                echo "0" > "$results_dir/$idx"
            else
                echo "1" > "$results_dir/$idx"
            fi
            echo >&3  # release semaphore token
        ) &
        pids+=($!)
    done

    # Wait for all deployments
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    exec 3>&-  # close semaphore fd

    # Collect results
    local succeeded=0 failed=0 failed_names=()
    for idx in "${targets[@]}"; do
        local name
        name=$(inv_get_field "$idx" name)
        [[ -z "$name" ]] && name=$(inv_get_field "$idx" host)
        local result_file="$results_dir/$idx"
        if [[ -f "$result_file" ]] && [[ "$(cat "$result_file")" == "0" ]]; then
            (( succeeded++ ))
        else
            (( failed++ ))
            failed_names+=("$name")
        fi
    done
    rm -rf "$results_dir"

    # Summary
    echo ""
    echo "========================================="
    echo "  Deployment Summary"
    echo "========================================="
    info "Succeeded: $succeeded"
    if (( failed > 0 )); then
        error "Failed: $failed"
        for name in "${failed_names[@]}"; do
            error "  - $name (see /tmp/mctl-deploy-${name}.log)"
        done
        exit 1
    fi
    echo ""
    info "All deployments succeeded!"
}

main "$@"
