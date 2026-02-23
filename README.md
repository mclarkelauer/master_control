# Master Control

A Python-based software orchestrator for managing agents, scripts, and services across a fleet of lightweight devices. Master Control runs a daemon on each machine that supervises workload processes, handles scheduling, health monitoring, and automatic restarts — all driven by simple YAML configuration.

Designed for deployment to small, resource-constrained clients (Raspberry Pi and similar SBCs) managed from a central control host over SSH.

## Quick Start

```bash
# Install dependencies (requires Python 3.12+ and uv)
make install

# Validate example workload configs
make validate

# Start the daemon (foreground)
uv run master-control up

# Or start as a background daemon
make start
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## Project Structure

```
master_control/
├── agents/examples/       # Example workload scripts
├── configs/examples/      # Example YAML workload configs
├── scripts/               # Install, daemon, and deployment scripts
│   └── lib/               # Shared shell and Python helpers
├── src/master_control/    # Core Python package
│   ├── api/               # Fleet HTTP APIs (central + client)
│   ├── cli/               # Click-based CLI
│   ├── config/            # YAML loading, validation, registry
│   ├── db/                # Async SQLite persistence
│   ├── engine/            # Orchestrator, runner, scheduler, IPC, resource limits
│   ├── fleet/             # Heartbeat, rolling deployer, fleet state store
│   ├── health/            # Process health monitoring and system metrics
│   └── models/            # Data models and events
├── templates/             # Jinja2 templates for the web dashboard
├── static/                # CSS/JS assets for the web dashboard
└── tests/                 # Unit and integration tests
```

## Workloads

A **workload** is any Python callable that Master Control manages. There are three types:

| Type      | Purpose                                    | Example                  |
|-----------|--------------------------------------------|--------------------------|
| `agent`   | Periodic data collection or transformation | Fetch API data every 5m  |
| `script`  | Batch processing, runs a fixed number of times | Generate 3 reports   |
| `service` | Long-running daemon, always restarted      | Continuous web watcher   |

### Run Modes

| Mode       | Behavior                                  | Required Config       |
|------------|-------------------------------------------|-----------------------|
| `schedule` | Triggered by a cron expression            | `schedule: "*/5 * * * *"` |
| `forever`  | Runs continuously, restarts on failure    | —                     |
| `n_times`  | Runs exactly N times then completes       | `max_runs: 3`         |

### Workload Configuration

Workloads are defined in YAML files placed in the `configs/` directory:

```yaml
name: data_collector
type: agent
run_mode: schedule
schedule: "*/5 * * * *"
module: agents.examples.hello_agent
entry_point: run
version: "1.2.0"
params:
  source_url: "https://api.example.com/data"
  batch_size: 100
timeout: 300
memory_limit_mb: 256
cpu_nice: 10
tags:
  - data
  - collection
```

See `configs/examples/` for more examples and [docs/configuration.md](docs/configuration.md) for the full field reference.

### Resource Limits

Workloads can be constrained to prevent runaway processes:

- **`memory_limit_mb`** — sets an address space limit (via `RLIMIT_AS`). The process receives `MemoryError` if it exceeds the limit.
- **`cpu_nice`** — adjusts CPU scheduling priority (-20 to 19). Higher values yield lower priority.

## CLI Usage

```bash
# Daemon control
uv run master-control up                  # Start daemon (foreground)
uv run master-control down                # Graceful shutdown via IPC

# Workload management
uv run master-control list                # List all workloads and status
uv run master-control start <name>        # Start a workload
uv run master-control stop <name>         # Stop a workload
uv run master-control restart <name>      # Restart a workload
uv run master-control status <name>       # Detailed workload status
uv run master-control logs <name>         # Recent log output

# Utilities
uv run master-control validate            # Validate all config files
uv run master-control run <name>          # Run a workload in foreground (one-shot)
```

Global options: `--config-dir`, `--db-path`, `--socket-path`.

## Fleet Management

Master Control includes a fleet management layer for centralized monitoring and control across all clients.

### Architecture

```
┌─────────────────────────────────────────────┐
│            Control Host                     │
│                                             │
│   Central API (:8080)  ◄── Heartbeats ──┐  │
│   Web Dashboard        ── Commands ──►  │  │
│   Rolling Deployer     ── Deploy ───►   │  │
│   Fleet Database                        │  │
└─────────────────────────────────────────│──┘
          │              │                │
          ▼              ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Client A    │ │  Client B    │ │  Client C    │
│  API (:9100) │ │  API (:9100) │ │  API (:9100) │
│  Heartbeat   │ │  Heartbeat   │ │  Heartbeat   │
│  Daemon      │ │  Daemon      │ │  Daemon      │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Features

- **Central API** — aggregated fleet status, remote workload control, deployment management
- **Web Dashboard** — browser-based fleet overview at `http://<host>:8080/`
- **Heartbeat System** — clients periodically report status, workload state, and system metrics (CPU, memory, disk)
- **Rolling Deployments** — update clients in batches with health checks and automatic rollback on failure
- **Config Hot-Reload** — push new configs and reload without restarting daemons
- **Version Tracking** — track deployed versions per client

### Daemon Configuration

Fleet features are configured in `daemon.yaml` placed in the config directory:

```yaml
# Client daemon settings
fleet:
  enabled: true
  client_name: "sensor-node-1"
  api_port: 9100
  central_api_url: "http://control-host:8080"
  heartbeat_interval_seconds: 30.0
  api_token: "your-secret-token"

# Control host settings (only on the central server)
central:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  db_path: "./fleet.db"
  inventory_path: "./inventory.yaml"
  api_token: "your-secret-token"
```

See [docs/configuration.md](docs/configuration.md) for all fields and [docs/operations.md](docs/operations.md) for setup instructions.

## Makefile Targets

```
make install          Install dependencies and set up project
make start            Start the daemon in background
make stop             Stop the daemon
make restart          Restart the daemon
make status           Check daemon status and list workloads
make logs             Show last 50 lines of daemon log
make test             Run all tests
make lint             Run ruff linter
make validate         Validate workload configs
make clean            Remove runtime artifacts
```

## Deployment

Master Control can be deployed from a control host to remote clients over SSH. Clients are defined in an inventory file.

### Inventory

Copy the example and customize:

```bash
cp configs/examples/inventory.yaml inventory.yaml
# Edit inventory.yaml with your client hosts
```

```yaml
defaults:
  ssh_user: deploy
  ssh_port: 22
  ssh_key: ~/.ssh/id_ed25519
  install_dir: /opt/master_control

clients:
  - host: 192.168.1.10
    name: sensor-node-1
    workloads:
      - configs/ticker_service.yaml
    env:
      MCTL_SOCKET_PATH: /var/run/mctl.sock

  - host: 192.168.1.11
    name: batch-runner-1
    workloads:
      - configs/counter_script.yaml
```

### Deploy Commands

```
make setup            Set up control host and deploy to all clients
make setup-local      Set up control host only
make deploy           Deploy to all clients
make deploy-client CLIENT=sensor-node-1   Deploy to one client
make deploy-dry-run   Preview deployment without executing
make deploy-sync      Sync files without restarting daemons
```

Deployment uses rsync to transfer project files and SSH to run a bootstrap script on each client. The bootstrap script installs Python, uv, dependencies, validates configs, and starts the daemon.

## Documentation

| Document | Description |
|----------|-------------|
| [Usage Guide](docs/usage.md) | Getting started, workload types, resource limits, common workflows |
| [Architecture](docs/architecture.md) | System design, component overview, data models |
| [Configuration](docs/configuration.md) | Full reference for all YAML config fields |
| [API Reference](docs/api-reference.md) | Central and client HTTP API endpoints |
| [Operations](docs/operations.md) | Fleet setup, deployments, troubleshooting |
| [Future Work](docs/future-work.md) | Planned enhancements and roadmap |

## Development

```bash
# Run tests
make test

# Run linter
make lint

# Type checking
uv run mypy src/
```

## License

Private — all rights reserved.
