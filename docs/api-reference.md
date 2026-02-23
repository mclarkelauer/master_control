# API Reference

Master Control exposes two HTTP APIs: a **Central API** running on the control host for fleet-wide management, and a **Client API** running on each client daemon for local control.

Both APIs use JSON request/response bodies. Authentication is via Bearer token when `api_token` is configured.

```
Authorization: Bearer <your-token>
```

## Central API

Base URL: `http://<control-host>:<port>/api` (default port 8080)

### Heartbeat

Receive status reports from client daemons.

```
POST /api/heartbeat
```

**Request Body:**

```json
{
  "client_name": "sensor-node-1",
  "timestamp": "2025-01-15T10:30:00",
  "deployed_version": "1.2.0",
  "workloads": [
    {
      "name": "data_collector",
      "type": "agent",
      "run_mode": "schedule",
      "status": "running",
      "pid": 1234,
      "run_count": 42,
      "last_started": "2025-01-15T10:25:00",
      "last_error": null
    }
  ],
  "system": {
    "cpu_percent": 15.2,
    "memory_used_mb": 412.5,
    "memory_total_mb": 1024.0,
    "disk_used_gb": 12.5,
    "disk_total_gb": 32.0
  }
}
```

**Response:** `{"status": "ok"}`

### Fleet Queries

#### List Clients

```
GET /api/fleet/clients
```

**Response:** Array of `ClientOverview`:

```json
[
  {
    "name": "sensor-node-1",
    "host": "192.168.1.10",
    "api_port": 9100,
    "status": "online",
    "last_seen": "2025-01-15T10:30:00",
    "workload_count": 3,
    "workloads_running": 2,
    "workloads_failed": 0,
    "deployed_version": "1.2.0",
    "system": { ... }
  }
]
```

Client `status` values: `online`, `offline`, `stale`.

#### Get Client

```
GET /api/fleet/clients/{name}
```

Returns a single `ClientOverview`. Returns 404 if the client is not found.

#### List Client Workloads

```
GET /api/fleet/clients/{name}/workloads
```

**Response:** Array of `WorkloadInfo`:

```json
[
  {
    "name": "data_collector",
    "type": "agent",
    "run_mode": "schedule",
    "status": "running",
    "pid": 1234,
    "run_count": 42,
    "last_started": "2025-01-15T10:25:00",
    "last_error": null
  }
]
```

#### Get Specific Workload

```
GET /api/fleet/clients/{client_name}/workloads/{workload_name}
```

Returns a single `WorkloadInfo`. Returns 404 if not found.

### Fleet Commands

Commands are proxied from the central API to the target client's HTTP API.

#### Start Workload

```
POST /api/fleet/clients/{client_name}/workloads/{workload_name}/start
```

#### Stop Workload

```
POST /api/fleet/clients/{client_name}/workloads/{workload_name}/stop
```

#### Restart Workload

```
POST /api/fleet/clients/{client_name}/workloads/{workload_name}/restart
```

**Response (all commands):**

```json
{
  "success": true,
  "message": "Started workload 'data_collector'"
}
```

Returns 502 if the client is unreachable.

#### Get Workload Logs

```
GET /api/fleet/clients/{client_name}/workloads/{workload_name}/logs?lines=50
```

| Parameter | Type | Default | Description                   |
|-----------|------|---------|-------------------------------|
| `lines`   | int  | 50      | Number of lines (1-10000)     |

**Response:**

```json
{
  "name": "data_collector",
  "lines": ["2025-01-15 10:25:00 INFO started", "..."]
}
```

#### Reload Client Configs

```
POST /api/fleet/clients/{client_name}/reload
```

Tells the client to hot-reload its workload configs from disk.

**Response:** `{"success": true, "changes": {...}}`

### Deployments

#### Create Deployment

```
POST /api/fleet/deployments
```

**Request Body:**

```json
{
  "version": "1.3.0",
  "target_clients": ["sensor-node-1", "sensor-node-2"],
  "batch_size": 1,
  "health_check_timeout": 60.0,
  "auto_rollback": true
}
```

| Field                  | Type             | Default | Description                                     |
|------------------------|------------------|---------|-------------------------------------------------|
| `version`              | string           | —       | Version string to deploy                        |
| `target_clients`       | list[string] \| null | `null` | Specific clients to target (null = all online) |
| `batch_size`           | int              | 1       | Clients to deploy per batch                     |
| `health_check_timeout` | float            | 60.0    | Seconds to wait for health checks per batch     |
| `auto_rollback`        | bool             | true    | Auto-rollback on failure                        |

**Response:** `DeploymentStatus` (see below)

#### List Deployments

```
GET /api/fleet/deployments?limit=20
```

Returns an array of `DeploymentStatus` objects, most recent first.

#### Get Deployment

```
GET /api/fleet/deployments/{deployment_id}
```

**Response:**

```json
{
  "id": "abc-123",
  "version": "1.3.0",
  "status": "in_progress",
  "batch_size": 1,
  "target_clients": ["sensor-node-1", "sensor-node-2"],
  "created_at": "2025-01-15T10:30:00",
  "started_at": "2025-01-15T10:30:01",
  "completed_at": null,
  "error": null,
  "client_statuses": [
    {
      "client_name": "sensor-node-1",
      "batch_number": 0,
      "status": "healthy",
      "previous_version": "1.2.0",
      "started_at": "2025-01-15T10:30:01",
      "completed_at": "2025-01-15T10:30:45",
      "error": null
    },
    {
      "client_name": "sensor-node-2",
      "batch_number": 1,
      "status": "pending",
      "previous_version": null,
      "started_at": null,
      "completed_at": null,
      "error": null
    }
  ]
}
```

Deployment `status` values: `pending`, `in_progress`, `completed`, `failed`, `rolling_back`, `rolled_back`.

Per-client `status` values: `pending`, `deploying`, `deployed`, `healthy`, `failed`, `rolled_back`.

#### Cancel Deployment

```
POST /api/fleet/deployments/{deployment_id}/cancel
```

**Response:** `{"success": true, "message": "Deployment cancelled"}`

## Client API

Base URL: `http://<client-host>:<port>/api` (default port 9100)

### Health Check

```
GET /api/health
```

**Response:** `{"status": "ok", "version": "0.1.0"}`

### List Workloads

```
GET /api/list
```

**Response:**

```json
{
  "workloads": [
    {
      "name": "data_collector",
      "type": "agent",
      "run_mode": "schedule",
      "status": "running",
      "pid": 1234,
      "run_count": 42,
      "last_started": "2025-01-15T10:25:00",
      "last_error": null,
      "version": "1.2.0",
      "memory_limit_mb": 256,
      "cpu_nice": 10
    }
  ]
}
```

### Workload Status

```
GET /api/status/{name}
```

Returns detailed workload info including `schedule`, `max_runs`, `module`, `entry_point`, and `tags`.

### Start / Stop / Restart

```
POST /api/start/{name}
POST /api/stop/{name}
POST /api/restart/{name}
```

**Response:** `{"success": true, "message": "..."}`

### Reload Configs

```
POST /api/reload
```

Hot-reloads workload configurations from disk without restarting the daemon.

**Response:** `{"success": true, "changes": {...}}`

### Workload Logs

```
GET /api/logs/{name}?lines=50
```

**Response:** `{"name": "data_collector", "lines": [...]}`

## Web Dashboard

The central API also serves a web dashboard with server-side rendered pages:

| Route                    | Description            |
|--------------------------|------------------------|
| `/`                      | Fleet overview         |
| `/clients/{name}`        | Client detail page     |
| `/deployments`           | Deployment history     |
| `/deployments/{id}`      | Deployment detail page |

The dashboard is available at the same host and port as the central API (default `http://localhost:8080/`).

## Error Responses

All API errors return a JSON body with a `detail` field:

```json
{
  "detail": "Client not found: unknown-node"
}
```

Common HTTP status codes:

| Code | Meaning                              |
|------|--------------------------------------|
| 400  | Bad request (invalid parameters)     |
| 404  | Resource not found                   |
| 502  | Client daemon unreachable            |
| 500  | Internal server error                |
