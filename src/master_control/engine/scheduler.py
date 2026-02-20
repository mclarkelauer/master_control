"""ScheduleManager — cron-based trigger management using croniter."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Coroutine

import structlog
from croniter import croniter

log = structlog.get_logger()


class ScheduleEntry:
    """A single scheduled workload with its cron iterator and callback."""

    def __init__(
        self,
        name: str,
        cron_expr: str,
        callback: Callable[[], Coroutine],
    ) -> None:
        self.name = name
        self.cron_expr = cron_expr
        self.callback = callback
        self._cron = croniter(cron_expr, datetime.now())
        self.next_run: datetime = self._cron.get_next(datetime)

    def advance(self) -> None:
        """Compute the next run time."""
        self.next_run = self._cron.get_next(datetime)


class ScheduleManager:
    """Manages cron triggers for schedule-mode workloads."""

    def __init__(self) -> None:
        self._entries: dict[str, ScheduleEntry] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    def add(
        self,
        name: str,
        cron_expr: str,
        callback: Callable[[], Coroutine],
    ) -> None:
        """Register a scheduled workload."""
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"Invalid cron expression: {cron_expr}")
        self._entries[name] = ScheduleEntry(name, cron_expr, callback)
        log.info(
            "schedule registered",
            workload=name,
            cron=cron_expr,
            next_run=self._entries[name].next_run.isoformat(),
        )

    def remove(self, name: str) -> None:
        """Unregister a scheduled workload."""
        self._entries.pop(name, None)
        log.info("schedule removed", workload=name)

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main loop: check for due entries every second."""
        try:
            while self._running:
                now = datetime.now()
                for entry in list(self._entries.values()):
                    if now >= entry.next_run:
                        log.info("schedule triggered", workload=entry.name)
                        try:
                            await entry.callback()
                        except Exception:
                            log.exception(
                                "schedule callback error", workload=entry.name
                            )
                        entry.advance()
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    @property
    def entries(self) -> dict[str, ScheduleEntry]:
        return dict(self._entries)
