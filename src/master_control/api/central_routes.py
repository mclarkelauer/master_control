"""Central API routes — fleet management endpoints and heartbeat receiver."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from master_control.api.models import (
    ClientOverview,
    CommandResponse,
    HeartbeatPayload,
    WorkloadInfo,
)

router = APIRouter(prefix="/api")


def _get_store(request: Request):
    return request.app.state.fleet_store


def _get_fleet_client(request: Request):
    return request.app.state.fleet_client


# --- Heartbeat ---


@router.post("/heartbeat")
async def receive_heartbeat(request: Request, payload: HeartbeatPayload) -> dict:
    """Receive a heartbeat from a client daemon."""
    store = _get_store(request)
    # Use the client's IP as the host if we don't have it in inventory
    client_host = request.client.host if request.client else "unknown"
    await store.upsert_heartbeat(payload, host=client_host)
    return {"status": "ok"}


# --- Fleet Queries ---


@router.get("/fleet/clients", response_model=list[ClientOverview])
async def list_clients(request: Request) -> list[ClientOverview]:
    """List all known clients and their status."""
    store = _get_store(request)
    return await store.list_clients()


@router.get("/fleet/clients/{name}", response_model=ClientOverview)
async def get_client(request: Request, name: str) -> ClientOverview:
    """Get details for a specific client."""
    store = _get_store(request)
    client = await store.get_client(name)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client not found: {name}")
    return client


@router.get("/fleet/clients/{name}/workloads", response_model=list[WorkloadInfo])
async def get_client_workloads(request: Request, name: str) -> list[WorkloadInfo]:
    """List workloads on a specific client."""
    store = _get_store(request)
    return await store.get_workloads(name)


@router.get(
    "/fleet/clients/{client_name}/workloads/{workload_name}",
    response_model=WorkloadInfo,
)
async def get_workload(
    request: Request, client_name: str, workload_name: str
) -> WorkloadInfo:
    """Get details for a specific workload on a client."""
    store = _get_store(request)
    wl = await store.get_workload(client_name, workload_name)
    if not wl:
        raise HTTPException(
            status_code=404,
            detail=f"Workload '{workload_name}' not found on client '{client_name}'",
        )
    return wl


# --- Fleet Commands (proxied to client daemons) ---


async def _resolve_endpoint(request: Request, client_name: str) -> tuple[str, int]:
    """Resolve the (host, port) for a client, raising 404 if not found."""
    store = _get_store(request)
    endpoint = await store.resolve_client_endpoint(client_name)
    if not endpoint:
        raise HTTPException(
            status_code=404, detail=f"Client not found: {client_name}"
        )
    return endpoint


@router.post(
    "/fleet/clients/{client_name}/workloads/{workload_name}/start",
    response_model=CommandResponse,
)
async def start_workload(
    request: Request, client_name: str, workload_name: str
) -> CommandResponse:
    """Start a workload on a specific client."""
    host, port = await _resolve_endpoint(request, client_name)
    fc = _get_fleet_client(request)
    try:
        return await fc.start_workload(host, port, workload_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/fleet/clients/{client_name}/workloads/{workload_name}/stop",
    response_model=CommandResponse,
)
async def stop_workload(
    request: Request, client_name: str, workload_name: str
) -> CommandResponse:
    """Stop a workload on a specific client."""
    host, port = await _resolve_endpoint(request, client_name)
    fc = _get_fleet_client(request)
    try:
        return await fc.stop_workload(host, port, workload_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/fleet/clients/{client_name}/workloads/{workload_name}/restart",
    response_model=CommandResponse,
)
async def restart_workload(
    request: Request, client_name: str, workload_name: str
) -> CommandResponse:
    """Restart a workload on a specific client."""
    host, port = await _resolve_endpoint(request, client_name)
    fc = _get_fleet_client(request)
    try:
        return await fc.restart_workload(host, port, workload_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/fleet/clients/{client_name}/workloads/{workload_name}/logs")
async def get_workload_logs(
    request: Request,
    client_name: str,
    workload_name: str,
    lines: int = Query(default=50, ge=1, le=10000),
) -> dict:
    """Get recent log lines for a workload on a specific client."""
    host, port = await _resolve_endpoint(request, client_name)
    fc = _get_fleet_client(request)
    try:
        return await fc.get_logs(host, port, workload_name, lines)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
