# Operations Guide

This guide covers day-to-day operations for running and managing a Master Control fleet.

## Setting Up Fleet Management

Fleet management adds centralized monitoring and remote control on top of the base daemon. It requires two components:

1. **Central API** — runs on the control host, aggregates client status
2. **Client fleet features** — each client runs an HTTP API and heartbeat reporter

### 1. Configure the Control Host

Create a `daemon.yaml` in your config directory:

```yaml
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

Start the daemon on the control host:

```bash
uv run master-control up
```

The central API and web dashboard will be available at `http://<host>:8080/`.

### 2. Configure Client Daemons

Add fleet settings to each client's `daemon.yaml`:

```yaml
fleet:
  enabled: true
  client_name: "sensor-node-1"
  api_port: 9100
  central_api_url: "http://control-host:8080"
  heartbeat_interval_seconds: 30.0
  api_token: "your-secret-token"
```

Once the client daemon starts, it will:
- Expose a local HTTP API on port 9100
- Send heartbeats to the central API every 30 seconds
- Report workload status and system metrics (CPU, memory, disk)

### 3. Verify Connectivity

Check the fleet overview:

```bash
curl http://control-host:8080/api/fleet/clients
```

You should see your clients listed with `"status": "online"`.

## Rolling Deployments

Rolling deployments update clients in batches with health checks between each batch. If a batch fails, the deployer can automatically rollback.

### Starting a Deployment

Via the API:

```bash
curl -X POST http://control-host:8080/api/fleet/deployments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token" \
  -d '{
    "version": "1.3.0",
    "batch_size": 2,
    "auto_rollback": true,
    "health_check_timeout": 60.0
  }'
```

Or target specific clients:

```bash
curl -X POST http://control-host:8080/api/fleet/deployments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-secret-token" \
  -d '{
    "version": "1.3.0",
    "target_clients": ["sensor-node-1"],
    "batch_size": 1
  }'
```

### Deployment Flow

For each batch:

1. **Deploy files** — runs `deploy-clients.sh --client <name> --sync-only --version <version>` for each client in the batch (parallel within batch)
2. **Reload configs** — sends a POST to each client's `/api/reload` endpoint
3. **Health check** — polls each client's `/api/health` endpoint until all pass or timeout

If any step fails and `auto_rollback` is true, all deployed batches are rolled back to their previous version.

### Monitoring a Deployment

```bash
# List recent deployments
curl http://control-host:8080/api/fleet/deployments

# Get specific deployment status
curl http://control-host:8080/api/fleet/deployments/<deployment-id>
```

Or use the web dashboard at `http://control-host:8080/deployments`.

### Cancelling a Deployment

```bash
curl -X POST http://control-host:8080/api/fleet/deployments/<deployment-id>/cancel
```

## Config Hot-Reload

Workload configurations can be reloaded without restarting the daemon. This is useful after deploying new config files.

### Via IPC (Local)

```bash
uv run master-control reload
```

### Via Client HTTP API

```bash
curl -X POST http://client-host:9100/api/reload
```

### Via Central API (Remote)

```bash
curl -X POST http://control-host:8080/api/fleet/clients/sensor-node-1/reload
```

The reload process:
1. Re-scans the config directory for YAML files
2. Validates all configs against Pydantic schemas
3. Adds new workloads, removes deleted ones, updates changed ones
4. Returns a summary of changes

## Resource Limits

Workloads can be constrained with memory and CPU limits to prevent runaway processes from affecting other workloads or the system.

### Memory Limits

Set `memory_limit_mb` in the workload config:

```yaml
name: data_processor
type: agent
run_mode: forever
module: agents.data_processor
memory_limit_mb: 256
```

This sets `RLIMIT_AS` (address space limit) on the child process. If the workload tries to allocate more memory than the limit, it will receive a `MemoryError`.

The health checker also monitors RSS usage when `psutil` is available and logs a warning when a workload reaches 90% of its memory limit.

### CPU Nice

Set `cpu_nice` to adjust the scheduling priority:

```yaml
name: background_task
type: script
run_mode: n_times
max_runs: 1
module: agents.background_task
cpu_nice: 15
```

Values range from -20 (highest priority) to 19 (lowest priority). Use positive values for background tasks that shouldn't compete with more critical workloads.

## Web Dashboard

The web dashboard provides a browser-based view of the fleet. It is served by the central API.

### Pages

- **Fleet Overview** (`/`) — lists all clients with status, workload counts, and system metrics
- **Client Detail** (`/clients/{name}`) — shows a client's workloads, system info, and remote control options
- **Deployments** (`/deployments`) — lists recent rolling deployments with status
- **Deployment Detail** (`/deployments/{id}`) — shows per-client progress of a deployment

### Access

Navigate to `http://<control-host>:<port>/` in a browser. The dashboard runs on the same port as the central API (default 8080).

## Remote Workload Control

Workloads on any client can be controlled remotely through the central API.

### Start / Stop / Restart

```bash
# Start a workload on a specific client
curl -X POST http://control-host:8080/api/fleet/clients/sensor-node-1/workloads/data_collector/start

# Stop
curl -X POST http://control-host:8080/api/fleet/clients/sensor-node-1/workloads/data_collector/stop

# Restart
curl -X POST http://control-host:8080/api/fleet/clients/sensor-node-1/workloads/data_collector/restart
```

### View Logs

```bash
curl "http://control-host:8080/api/fleet/clients/sensor-node-1/workloads/data_collector/logs?lines=100"
```

## Troubleshooting

### Client Shows as "stale" or "offline"

- Verify the client daemon is running: `make status` on the client
- Check that `fleet.enabled` is `true` and `central_api_url` is correct in the client's `daemon.yaml`
- Ensure the client can reach the control host on the configured port
- Check the daemon log on the client: `make logs` or `logs/daemon.log`
- Heartbeat warnings appear as `"heartbeat failed"` in the client log

### Deployment Fails

- Check the deployment detail: `GET /api/fleet/deployments/<id>` — each client has its own status and error message
- Common causes:
  - SSH connectivity to the client is down
  - The deploy script path is incorrect in `central.deploy_script_path`
  - Client health check endpoint is unreachable after deploy
- If `auto_rollback` was enabled, clients will be automatically reverted to their previous version

### Config Reload Returns Errors

- Run `uv run master-control validate` on the client to check for YAML or schema errors
- Ensure new config files are in the correct directory
- Check that workload names are unique across all config files

### Workload Keeps Failing

- Check the workload log: `uv run master-control logs <name>`
- Check `last_error` in the status: `uv run master-control status <name>`
- If using memory limits, the workload may be exceeding its allocation — check for `MemoryError` in logs
- For scheduled workloads, verify the cron expression is correct

### Cannot Connect to IPC Socket

- Ensure the daemon is running
- Check the socket path matches between CLI and daemon (default: `/tmp/master_control.sock`)
- Verify file permissions on the socket file
