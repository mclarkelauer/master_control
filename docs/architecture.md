# Architecture & Design

## Overview

Master Control is a distributed workload orchestrator. Each machine in the fleet runs an independent daemon that manages local workload processes. A central control host deploys configuration and code to clients over SSH and optionally runs a fleet management API for centralized monitoring and control.

```
┌─────────────────────────────────────┐
│         Control Host                │
│                                     │
│  inventory.yaml ──► deploy-clients  │
│  Central API    ◄── heartbeats     │
│  Web Dashboard  ──► commands       │
│  Fleet Database                     │
│                      │  │  │        │
│                      ▼  ▼  ▼        │
│          SSH + rsync to clients     │
└─────────────────────────────────────┘
         │              │              │
         ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Client A    │ │  Client B    │ │  Client C    │
│  (Pi / SBC)  │ │  (Pi / SBC)  │ │  (Pi / SBC)  │
│              │ │              │ │              │
│  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │
│  │ Daemon │  │ │  │ Daemon │  │ │  │ Daemon │  │
│  │        │  │ │  │        │  │ │  │        │  │
│  │ W1  W2 │  │ │  │ W3     │  │ │  │ W4  W5 │  │
│  └────────┘  │ │  └────────┘  │ │  └────────┘  │
│  HTTP :9100  │ │  HTTP :9100  │ │  HTTP :9100  │
└──────────────┘ └──────────────┘ └──────────────┘
```

Each daemon is self-contained — it loads its own configs, manages its own processes, and persists state to a local SQLite database. There is no runtime dependency on the control host.

## Daemon Architecture

When the daemon starts (`master-control up`), it initializes these components:

```
┌───────────────────────────────────────────────────────────┐
│                      Orchestrator                         │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐           │
│  │ Config   │  │ Registry │  │  IPC Server   │           │
│  │ Loader   ├─►│          │  │ (Unix Socket) │           │
│  └──────────┘  └────┬─────┘  └───────┬───────┘           │
│                     │                │                    │
│           ┌─────────▼─────────┐      │                    │
│           │     Runners       │◄─────┘                    │
│           │  ┌─────┐ ┌─────┐ │                            │
│           │  │ W1  │ │ W2  │ │                            │
│           │  └──┬──┘ └──┬──┘ │                            │
│           └─────┼───────┼────┘                            │
│                 │       │                                 │
│  ┌──────────┐   │       │   ┌────────────────┐            │
│  │Scheduler │───┘       └───│ Health Checker │            │
│  │ (cron)   │               │  (periodic)    │            │
│  └──────────┘               └────────────────┘            │
│                                                           │
│  ┌────────────────────┐  ┌──────────────────────────┐     │
│  │  Client HTTP API   │  │  Heartbeat Reporter      │     │
│  │  (FastAPI :9100)   │  │  (→ Central API)         │     │
│  └────────────────────┘  └──────────────────────────┘     │
│                                                           │
│  ┌──────────────────────────────────────────┐             │
│  │           SQLite Database                │             │
│  │  workload_state  │  run_history          │             │
│  └──────────────────────────────────────────┘             │
└───────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**Orchestrator** (`engine/orchestrator.py`)
- Top-level coordinator. Owns the startup and shutdown sequence.
- Loads configs, populates the registry, creates runners, starts the scheduler and health checker, opens the IPC socket.
- Manages fleet components (client HTTP API, heartbeat reporter) when fleet mode is enabled.
- Supports config hot-reload: re-scans configs, adds/removes/updates workloads without restart.

**Config Loader** (`config/loader.py`)
- Scans the config directory for YAML files.
- Validates each file against Pydantic schemas (`config/schema.py`).
- Produces `WorkloadSpec` objects — immutable descriptions of what to run.
- Also loads `daemon.yaml` for fleet/central configuration.

**Registry** (`config/registry.py`)
- Thread-safe in-memory index of all registered `WorkloadSpec` objects.
- Lookup by name, list all, register/unregister.

**Runner** (`engine/runner.py`)
- One runner per workload. Manages the subprocess lifecycle.
- Spawns the workload as a child process, tracks PID, run count, timestamps, errors.
- Applies resource limits (`memory_limit_mb`, `cpu_nice`) via a `preexec_fn` on the child process (see `engine/rlimits.py`).
- Applies the run mode strategy (forever, n_times, schedule) to decide whether to restart.
- Graceful shutdown: SIGTERM with timeout, then SIGKILL.

**Resource Limits** (`engine/rlimits.py`)
- Builds a `preexec_fn` closure that runs in the child process before exec.
- Sets `RLIMIT_AS` for memory limits (address space cap in bytes).
- Calls `os.nice()` for CPU scheduling priority adjustment.
- Returns `None` if no limits are configured (no overhead).

**Scheduler** (`engine/scheduler.py`)
- Manages workloads in `schedule` mode.
- Uses `croniter` to compute the next fire time for each cron expression.
- Triggers the runner's `start()` when a schedule fires.

**Health Checker** (`health/checks.py`)
- Periodically polls running workloads.
- Verifies process existence via `os.kill(pid, 0)`.
- Marks workloads as `FAILED` if their process has disappeared.
- Monitors RSS memory usage and warns when a workload approaches its `memory_limit_mb` (90% threshold, requires `psutil`).
- Collects system metrics (CPU, memory, disk) for heartbeat reporting.

**IPC Server** (`engine/orchestrator.py` + `engine/ipc.py`)
- Unix domain socket accepting JSON commands from the CLI.
- Commands: `list`, `start`, `stop`, `restart`, `status`, `logs`, `shutdown`, `reload-configs`.
- The CLI sends commands via `ipc.send_command()` and prints the response.

**Client HTTP API** (`api/client_app.py` + `api/client_routes.py`)
- FastAPI application running on each client daemon (default port 9100).
- Mirrors the IPC socket protocol over HTTP for remote access.
- Endpoints: health check, workload list/status, start/stop/restart, config reload, logs.
- Used by the central API to proxy fleet commands to clients.

**Heartbeat Reporter** (`fleet/heartbeat.py`)
- Periodically POSTs client status to the central API.
- Payload includes: client name, timestamp, deployed version, all workload states, system metrics.
- Uses Bearer token authentication when configured.
- Runs as an async background task within the daemon.

**Database** (`db/connection.py`, `db/repository.py`)
- Async SQLite via `aiosqlite`.
- Two tables: `workload_state` (current status snapshot) and `run_history` (per-run log with exit codes and durations).
- Provides persistence across daemon restarts.

## Central API Architecture

The control host optionally runs a central API for fleet-wide management.

```
┌─────────────────────────────────────────────────────────┐
│                  Central API Server                     │
│                                                         │
│  ┌──────────────────┐   ┌──────────────────────────┐    │
│  │  FastAPI App      │   │  Fleet State Store       │    │
│  │                   │   │  (SQLite)                │    │
│  │  /api/heartbeat  ─┼──►│  fleet_clients           │    │
│  │  /api/fleet/*    ─┼──►│  fleet_workloads         │    │
│  │  /api/fleet/     ─┼──►│  deployments             │    │
│  │    deployments    │   └──────────────────────────┘    │
│  └──────────────────┘                                   │
│                                                         │
│  ┌──────────────────┐   ┌──────────────────────────┐    │
│  │  Fleet Client     │   │  Rolling Deployer        │    │
│  │  (httpx)          │   │                          │    │
│  │  Proxies commands │   │  Batched deploy          │    │
│  │  to client APIs   │   │  Health checks           │    │
│  └──────────────────┘   │  Auto-rollback            │    │
│                          └──────────────────────────┘    │
│  ┌──────────────────┐                                   │
│  │  Web Dashboard    │                                   │
│  │  (Jinja2 SSR)    │                                   │
│  └──────────────────┘                                   │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Background Tasks                                │   │
│  │  - Stale client detection                        │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Fleet State Store** (`fleet/store.py`)
- Persists client heartbeats, workload state, and deployment records to SQLite.
- Resolves client endpoints (host + port) for command proxying.
- Marks clients as `stale` or `offline` when heartbeats stop arriving.

**Fleet Client** (`api/fleet_client.py`)
- HTTP client (httpx) for communicating with individual client daemons.
- Proxies start/stop/restart commands, config reloads, health checks, and log retrieval.

**Rolling Deployer** (`fleet/deployer.py`)
- Orchestrates deployments across fleet clients in configurable batches.
- For each batch: deploy files (rsync via deploy script) → reload configs → health check.
- Automatic rollback on failure: re-deploys the previous version to affected clients.
- Tracks deployment status and per-client progress in the fleet database.

**Web Dashboard** (`api/web_routes.py` + `templates/`)
- Server-side rendered HTML pages using Jinja2.
- Fleet overview, client details, deployment history and progress.

## Data Model

```
WorkloadSpec (immutable, from YAML)
├── name: str
├── type: agent | script | service
├── run_mode: schedule | forever | n_times
├── module: str              # Python module path
├── entry_point: str         # Function name
├── params: dict             # Passed to the function
├── schedule: str            # Cron expression (schedule mode)
├── max_runs: int            # Run limit (n_times mode)
├── timeout: int             # Max execution seconds
├── restart_delay: int       # Seconds between restarts
├── memory_limit_mb: int     # Address space limit (RLIMIT_AS)
├── cpu_nice: int            # CPU scheduling priority (-20..19)
├── tags: list[str]
└── version: str

WorkloadState (mutable, runtime)
├── spec: WorkloadSpec
├── status: registered | starting | running | stopping | stopped | failed | completed
├── pid: int | None
├── run_count: int
├── last_started: datetime
├── last_stopped: datetime
├── last_heartbeat: datetime
├── last_error: str | None
└── consecutive_failures: int

WorkloadEvent
├── workload_name: str
├── event_type: started | stopped | failed | completed | heartbeat | ...
├── timestamp: datetime
└── details: dict
```

### Fleet Data Model

```
HeartbeatPayload
├── client_name: str
├── timestamp: datetime
├── deployed_version: str | None
├── workloads: list[WorkloadInfo]
└── system: SystemMetrics

ClientOverview
├── name: str
├── host: str
├── api_port: int
├── status: online | offline | stale
├── last_seen: datetime
├── workload_count: int
├── workloads_running: int
├── workloads_failed: int
├── deployed_version: str | None
└── system: SystemMetrics | None

DeploymentStatus
├── id: str
├── version: str
├── status: pending | in_progress | completed | failed | rolling_back | rolled_back
├── batch_size: int
├── target_clients: list[str]
├── created_at: datetime
├── started_at: datetime | None
├── completed_at: datetime | None
├── error: str | None
└── client_statuses: list[DeploymentClientStatus]

SystemMetrics
├── cpu_percent: float
├── memory_used_mb: float
├── memory_total_mb: float
├── disk_used_gb: float
└── disk_total_gb: float
```

## Run Mode Strategies

Each run mode has a strategy object (`engine/modes.py`) that answers two questions:

1. **should_restart(state) → bool** — After a workload exits, should it be restarted?
2. **is_complete(state) → bool** — Has the workload fulfilled its purpose?

| Mode     | should_restart               | is_complete                      |
|----------|------------------------------|----------------------------------|
| forever  | Always (unless manually stopped) | Never                        |
| n_times  | If run_count < max_runs      | When run_count >= max_runs       |
| schedule | Never (next run is cron-triggered) | Never                      |

## CLI ↔ Daemon Communication

The CLI and daemon communicate over a Unix domain socket using a simple JSON protocol:

```
CLI                          Daemon
 │                             │
 │ {"command": "list"}         │
 │ ──────────────────────────► │
 │                             │
 │ {"status": "ok",            │
 │  "workloads": [...]}        │
 │ ◄────────────────────────── │
```

The socket path defaults to `/tmp/master_control.sock`. Commands are one-shot: connect, send, receive, close.

## Rolling Deployment Flow

```
                    ┌─────────────┐
                    │ API Request │
                    │ POST /api/  │
                    │ deployments │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │Create batch │
                    │assignments  │
                    └──────┬──────┘
                           │
          ┌────────────────▼────────────────┐
          │         For each batch:         │
          │                                 │
          │  1. Deploy files (rsync/SSH)    │
          │     parallel within batch       │
          │                                 │
          │  2. Reload configs on clients   │
          │     POST /api/reload            │
          │                                 │
          │  3. Wait for health checks      │
          │     GET /api/health             │
          │                                 │
          │  ──► On failure + auto_rollback │
          │      rollback all prior batches │
          └────────────────┬────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Completed  │
                    │  or Failed  │
                    └─────────────┘
```

## Deployment Model

Deployment follows a push model from the control host:

1. **Inventory** (`inventory.yaml`) lists clients with SSH connection details, workload assignments, and environment overrides.
2. **deploy-clients.sh** iterates over clients:
   - Validates SSH connectivity.
   - Rsyncs project files (code, scripts, dependencies) excluding runtime artifacts.
   - Syncs only the workload configs assigned to that client.
   - Runs `remote-bootstrap.sh` on the client via SSH.
3. **remote-bootstrap.sh** (runs on the client):
   - Installs Python 3.12+ and uv if missing.
   - Runs `uv sync` to install Python dependencies.
   - Writes a `.env` file with client-specific environment overrides.
   - Validates configs and starts the daemon.

Each client runs its own independent daemon. There is no runtime coordination between clients.

### Client Hardware Assumptions

Clients are small, resource-constrained devices (Raspberry Pi, similar ARM SBCs):

- Limited CPU and RAM — workloads should be lightweight.
- SD card or eMMC storage — SQLite is appropriate, but large write volumes should be avoided.
- Network connectivity may be intermittent — the daemon operates fully offline once deployed.
- Headless operation — no display, managed entirely via SSH.

## Technology Choices

| Choice        | Rationale                                                  |
|---------------|------------------------------------------------------------|
| Python 3.12+  | Modern async support, available on ARM via apt/dnf         |
| uv            | Fast dependency resolution, no system-wide pip conflicts   |
| SQLite        | Zero-config, single-file, perfect for embedded devices     |
| Unix sockets  | Fast local IPC, no TCP overhead, file-based permissions    |
| structlog     | Structured JSON logs, easy to parse and ship               |
| Click + Rich  | Clean CLI with minimal dependencies                       |
| Pydantic      | Config validation with clear error messages                |
| croniter      | Lightweight cron parsing without external schedulers       |
| rsync + SSH   | Reliable, resumable file transfer to constrained networks  |
| FastAPI       | Async HTTP framework for fleet APIs, auto-generated docs   |
| httpx         | Async HTTP client for inter-service communication          |
| Jinja2        | Server-side HTML templating for the web dashboard          |
| psutil        | Cross-platform system metrics (optional, fallback to /proc)|

## Logging

Each workload gets its own log file under `logs/`. The daemon itself also logs to `logs/daemon.log`. All logging uses `structlog` for structured JSON output, making it straightforward to aggregate logs from multiple clients.

## Error Handling and Recovery

- **Process crashes**: The health checker detects missing PIDs and marks the workload as `FAILED`. The runner's mode strategy decides whether to restart.
- **Memory limit exceeded**: The process receives `MemoryError` from the kernel. The health checker warns when RSS approaches 90% of the configured limit.
- **Daemon restart**: On startup, the daemon reads persisted `workload_state` from SQLite and resumes management.
- **Graceful shutdown**: `master-control down` sends a shutdown command via IPC. The orchestrator stops all workloads (SIGTERM → timeout → SIGKILL), then exits.
- **Deployment failures**: `deploy-clients.sh` validates SSH connectivity before transferring files. Failed clients are reported but don't block other deployments.
- **Rolling deployment failures**: If a batch fails health checks, the rolling deployer automatically rolls back all affected clients to their previous version (when `auto_rollback` is enabled).
- **Heartbeat failures**: Transient network issues are tolerated — the central API marks clients as `stale` only after `stale_threshold_seconds` (default 90s) without a heartbeat.
