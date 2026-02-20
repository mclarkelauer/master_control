"""Health checker — periodically verifies workload processes are alive."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import structlog

from master_control.models.workload import WorkloadStatus

if TYPE_CHECKING:
    from master_control.engine.orchestrator import Orchestrator

log = structlog.get_logger()


class HealthChecker:
    """Periodically checks each running workload's process is alive."""

    def __init__(self, orchestrator: Orchestrator, interval: float = 10.0) -> None:
        self._orchestrator = orchestrator
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())
        log.info("health checker started", interval=self._interval)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        try:
            while self._running:
                await self._check_all()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            pass

    async def _check_all(self) -> None:
        for state in self._orchestrator.list_workloads():
            if state.status != WorkloadStatus.RUNNING:
                continue
            if state.pid is None:
                continue
            if not self._is_process_alive(state.pid):
                log.warning(
                    "health check failed: process not found",
                    workload=state.spec.name,
                    pid=state.pid,
                )
                state.status = WorkloadStatus.FAILED
                state.last_error = f"Process {state.pid} not found"

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we can't signal it
            return True
