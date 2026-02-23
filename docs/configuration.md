# Configuration Reference

This document covers all configuration files used by Master Control.

## Workload Configuration

Workloads are defined in YAML files placed in the `configs/` directory. Each file defines one workload (or multiple using the `workloads:` list format).

### Single Workload File

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
restart_delay: 5.0
memory_limit_mb: 256
cpu_nice: 10
tags:
  - data
  - collection
```

### Multi-Workload File

Multiple workloads can be defined in a single YAML file using a top-level `workloads` key:

```yaml
workloads:
  - name: collector_a
    type: agent
    run_mode: schedule
    schedule: "*/5 * * * *"
    module: agents.collector_a
    entry_point: run

  - name: collector_b
    type: agent
    run_mode: schedule
    schedule: "*/10 * * * *"
    module: agents.collector_b
    entry_point: run
```

### Field Reference

| Field              | Type           | Default | Required | Description                                           |
|--------------------|----------------|---------|----------|-------------------------------------------------------|
| `name`             | string         | —       | Yes      | Unique workload identifier                            |
| `type`             | enum           | —       | Yes      | `agent`, `script`, or `service`                       |
| `run_mode`         | enum           | —       | Yes      | `schedule`, `forever`, or `n_times`                   |
| `module`           | string         | —       | Yes      | Python module path (e.g., `agents.examples.hello_agent`) |
| `entry_point`      | string         | `"run"` | No       | Function name to call in the module                   |
| `version`          | string \| null | `null`  | No       | Version tag for tracking deployments                  |
| `schedule`         | string \| null | `null`  | Conditional | Cron expression, required when `run_mode` is `schedule` |
| `max_runs`         | int \| null    | `null`  | Conditional | Max execution count, required when `run_mode` is `n_times` |
| `params`           | dict           | `{}`    | No       | Key-value pairs passed as kwargs to the entry point   |
| `restart_delay`    | float          | `5.0`   | No       | Seconds to wait before restarting after exit          |
| `timeout`          | float \| null  | `null`  | No       | Max execution time in seconds before SIGTERM          |
| `memory_limit_mb`  | int \| null    | `null`  | No       | Memory limit in MB (enforced via `RLIMIT_AS`)         |
| `cpu_nice`         | int \| null    | `null`  | No       | CPU nice value (-20 to 19, higher = lower priority)   |
| `tags`             | list[string]   | `[]`    | No       | Arbitrary tags for grouping/filtering                 |

### Validation Rules

- `name` must be unique across all loaded config files.
- `schedule` is **required** when `run_mode` is `schedule` and must be a valid cron expression.
- `max_runs` is **required** when `run_mode` is `n_times` and must be a positive integer.
- `memory_limit_mb` must be a positive integer if set.
- `cpu_nice` must be between -20 and 19 if set.

## Daemon Configuration

The daemon reads an optional `daemon.yaml` file from the config directory for fleet and central API settings.

### Example `daemon.yaml`

```yaml
fleet:
  enabled: true
  client_name: "sensor-node-1"
  api_host: "0.0.0.0"
  api_port: 9100
  central_api_url: "http://control-host:8080"
  heartbeat_interval_seconds: 30.0
  api_token: "your-secret-token"

central:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  db_path: "./fleet.db"
  inventory_path: "./inventory.yaml"
  api_token: "your-secret-token"
  stale_threshold_seconds: 90.0
  deploy_script_path: "./scripts/deploy-clients.sh"
```

### Fleet Config (Client Daemons)

These settings enable client-side fleet features: an HTTP API for remote management and heartbeat reporting to the central server.

| Field                        | Type           | Default     | Description                                |
|------------------------------|----------------|-------------|--------------------------------------------|
| `enabled`                    | bool           | `false`     | Enable fleet features on this client       |
| `client_name`                | string \| null | `null`      | Name for this client in the fleet          |
| `api_host`                   | string         | `"0.0.0.0"` | Bind address for the client HTTP API      |
| `api_port`                   | int            | `9100`      | Port for the client HTTP API               |
| `central_api_url`            | string \| null | `null`      | URL of the central API server              |
| `heartbeat_interval_seconds` | float          | `30.0`      | Seconds between heartbeat reports          |
| `api_token`                  | string \| null | `null`      | Bearer token for API authentication        |

### Central Config (Control Host)

These settings enable the central fleet management API, which aggregates client status, proxies commands, and manages rolling deployments.

| Field                      | Type           | Default           | Description                                    |
|----------------------------|----------------|-------------------|------------------------------------------------|
| `enabled`                  | bool           | `false`           | Enable the central API server                  |
| `host`                     | string         | `"0.0.0.0"`      | Bind address for the central API               |
| `port`                     | int            | `8080`            | Port for the central API                       |
| `db_path`                  | string         | `"./fleet.db"`   | Path to the fleet SQLite database              |
| `inventory_path`           | string         | `"./inventory.yaml"` | Path to the client inventory file          |
| `api_token`                | string \| null | `null`            | Required bearer token for API requests         |
| `stale_threshold_seconds`  | float          | `90.0`            | Mark clients offline after this many seconds without a heartbeat |
| `deploy_script_path`       | string \| null | `null`            | Path to the deploy-clients.sh script           |

## Inventory Configuration

The inventory file defines remote clients for deployment. Copy `configs/examples/inventory.yaml` as a starting point.

### Example `inventory.yaml`

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

### Defaults Section

| Field         | Type   | Description                          |
|---------------|--------|--------------------------------------|
| `ssh_user`    | string | SSH username for deployment          |
| `ssh_port`    | int    | SSH port                             |
| `ssh_key`     | string | Path to SSH private key              |
| `install_dir` | string | Installation directory on the client |

### Client Entry

| Field       | Type          | Description                                          |
|-------------|---------------|------------------------------------------------------|
| `host`      | string        | IP address or hostname                               |
| `name`      | string        | Unique client name (used in fleet API and dashboard)  |
| `workloads` | list[string]  | Config file paths to deploy to this client           |
| `env`       | dict          | Environment variable overrides for this client        |
