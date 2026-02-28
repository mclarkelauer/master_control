"""Client-side HTTP API routes — mirrors the IPC socket protocol."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query

from master_control.api.models import CommandResponse

if TYPE_CHECKING:
    from master_control.engine.orchestrator import Orchestrator

router = APIRouter(prefix="/api")

# The orchestrator is attached to app.state by the client_app factory.
# Each route accesses it via the request.


def _get_orchestrator(request) -> Orchestrator:
    return request.app.state.orchestrator


@router.get("/health")
async def health(request):
    """Basic health check endpoint."""
    return {"status": "ok", "version": "0.1.0"}


@router.get("/list")
async def list_workloads(request) -> dict:
    """List all workloads and their status."""
    orch = _get_orchestrator(request)
    states = orch.list_workloads()
    return {"workloads": [s.to_dict() for s in states]}


@router.get("/status/{name}")
async def workload_status(request, name: str) -> dict:
    """Get detailed status of a specific workload."""
    orch = _get_orchestrator(request)
    state = orch.get_status(name)
    if not state:
        raise HTTPException(status_code=404, detail=f"Unknown workload: {name}")
    result = state.to_dict()
    result.update(
        {
            "schedule": state.spec.schedule,
            "max_runs": state.spec.max_runs,
            "module": state.spec.module_path,
            "entry_point": state.spec.entry_point,
            "tags": state.spec.tags,
        }
    )
    return result


@router.post("/start/{name}")
async def start_workload(request, name: str) -> CommandResponse:
    """Start a specific workload."""
    orch = _get_orchestrator(request)
    msg = await orch.start_workload(name)
    success = "Started" in msg
    return CommandResponse(success=success, message=msg)


@router.post("/stop/{name}")
async def stop_workload(request, name: str) -> CommandResponse:
    """Stop a specific workload."""
    orch = _get_orchestrator(request)
    msg = await orch.stop_workload(name)
    success = "Stopped" in msg
    return CommandResponse(success=success, message=msg)


@router.post("/restart/{name}")
async def restart_workload(request, name: str) -> CommandResponse:
    """Restart a specific workload."""
    orch = _get_orchestrator(request)
    msg = await orch.restart_workload(name)
    success = "Started" in msg
    return CommandResponse(success=success, message=msg)


@router.post("/reload")
async def reload_configs(request) -> dict:
    """Hot-reload workload configs from disk."""
    orch = _get_orchestrator(request)
    result = await orch.reload_configs()
    return {"success": True, "changes": result}


@router.get("/logs/{name}")
async def workload_logs(
    request, name: str, lines: int = Query(default=50, ge=1, le=10000)
) -> dict:
    """Get recent log lines for a workload."""
    orch = _get_orchestrator(request)
    # Validate workload exists
    if name not in orch.registry:
        raise HTTPException(status_code=404, detail=f"Unknown workload: {name}")

    log_dir = orch.log_dir or Path("./logs")
    log_file = log_dir / f"{name}.log"
    if not log_file.exists():
        return {"name": name, "lines": []}

    with open(log_file) as f:
        all_lines = f.readlines()
        tail = all_lines[-lines:]
    return {"name": name, "lines": [line.rstrip() for line in tail]}
