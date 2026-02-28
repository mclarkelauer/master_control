# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Master Control is a Python-based workload orchestrator for distributed fleets of resource-constrained devices (Raspberry Pi, SBCs). It manages services, agents, and scripts with optional fleet management via a central API server.

## Common Commands

```bash
make install              # Install deps via uv
make test                 # Run all tests (uv run pytest -v)
make lint                 # Run ruff linter on src/ tests/ agents/
make validate             # Validate workload YAML configs
make start / stop / restart  # Daemon control (background)
make status               # Daemon status + workload list
make logs                 # Last 50 lines of daemon log
```

Run a single test:
```bash
uv run pytest tests/unit/test_runner.py -v
uv run pytest -k test_name
```

Lint auto-fix:
```bash
uv run ruff check --fix src/ tests/ agents/
```

## Architecture

**Package:** `src/master_control/` installed via `uv` with entry point `master-control`.

**Core daemon components (in `engine/`):**
- **Orchestrator** — top-level coordinator; starts/stops all subsystems
- **Runner** — one per workload, manages subprocess lifecycle
- **Scheduler** — cron-triggered workload execution (croniter)
- **IPC Server** — Unix socket (`/tmp/master_control.sock`) for CLI↔daemon communication

**Data flow:**
```
YAML configs → ConfigLoader → Registry → Orchestrator → Runners → Subprocesses
                                             ↕
                                        IPC Server ← CLI
                                             ↕
                                        HTTP API ← Central API / Web Dashboard
```

**Key model split:** `WorkloadSpec` (immutable, from YAML via Pydantic) vs `WorkloadState` (mutable runtime state).

**Workload types:** `agent` (periodic), `script` (batch/N-times), `service` (long-running).
**Run modes:** `schedule` (cron), `forever` (auto-restart), `n_times` (fixed count).

**Fleet components (optional, requires `api` dependency group):**
- `fleet/` — heartbeat reporter, rolling deployer, fleet state store
- `api/` — FastAPI HTTP APIs (client on port 9100, central server)
- Web dashboard with Jinja2 templates in `templates/` and `static/`

**Persistence:** Async SQLite via `aiosqlite` (`db/`). Tables: `workload_state`, `run_history`, `fleet_clients`, `fleet_workloads`, `deployments`.

**Deployment:** SSH + rsync push from control host to clients. Scripts in `scripts/`. Inventory-based with rolling deploys, health checks, and rollback.

## Code Conventions

- Python 3.12+, async-first (`asyncio` throughout)
- `ruff` for linting, line length 100, target `py312`
- `structlog` for structured JSON logging
- `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions work without decorators
- CLI built with `click`, output formatted with `rich`
- Configs are YAML files in `configs/`, validated by Pydantic models in `config/`
