"""Heartbeat reporter — periodically sends client status to the central API."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
import structlog

from master_control.api.models import HeartbeatPayload, SystemMetrics, WorkloadInfo
from master_control.health.checks import collect_system_metrics

if TYPE_CHECKING:
    from master_control.config.schema import FleetConfig
    from master_control.engine.orchestrator import Orchestrator

log = structlog.get_logger()


class HeartbeatReporter:
    """Periodically POSTs client status to the central API."""

    def __init__(self, orchestrator: Orchestrator, config: FleetConfig) -> None:
        self._orchestrator = orchestrator
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        headers = {}
        if self._config.api_token:
            headers["Authorization"] = f"Bearer {self._config.api_token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=10.0)
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info(
            "heartbeat reporter started",
            central_url=self._config.central_api_url,
            interval=self._config.heartbeat_interval_seconds,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _run(self) -> None:
        try:
            while self._running:
                await self._send_heartbeat()
                await asyncio.sleep(self._config.heartbeat_interval_seconds)
        except asyncio.CancelledError:
            pass

    async def _send_heartbeat(self) -> None:
        if not self._client or not self._config.central_api_url:
            return
        try:
            payload = self._build_payload()
            url = f"{self._config.central_api_url.rstrip('/')}/api/heartbeat"
            response = await self._client.post(url, json=payload.model_dump(mode="json"))
            if response.status_code != 200:
                log.warning(
                    "heartbeat rejected",
                    status=response.status_code,
                    url=url,
                )
        except httpx.HTTPError as e:
            log.warning("heartbeat failed", error=str(e))
        except Exception as e:
            log.warning("heartbeat error", error=str(e))

    def _build_payload(self) -> HeartbeatPayload:
        states = self._orchestrator.list_workloads()
        metrics = collect_system_metrics()
        return HeartbeatPayload(
            client_name=self._config.client_name or "unknown",
            timestamp=datetime.now(),
            workloads=[
                WorkloadInfo(
                    name=s.spec.name,
                    type=s.spec.workload_type.value,
                    run_mode=s.spec.run_mode.value,
                    status=s.status.value,
                    pid=s.pid,
                    run_count=s.run_count,
                    last_started=s.last_started.isoformat() if s.last_started else None,
                    last_error=s.last_error,
                )
                for s in states
            ],
            system=SystemMetrics(**metrics),
        )
