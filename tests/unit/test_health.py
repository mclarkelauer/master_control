"""Tests for the health checker."""

import asyncio
import os
from unittest.mock import MagicMock

from master_control.health.checks import HealthChecker
from master_control.models.workload import (
    RunMode,
    WorkloadSpec,
    WorkloadState,
    WorkloadStatus,
    WorkloadType,
)


def _make_state(name: str, status: WorkloadStatus, pid: int | None = None) -> WorkloadState:
    spec = WorkloadSpec(
        name=name,
        workload_type=WorkloadType.AGENT,
        run_mode=RunMode.SCHEDULE,
        module_path="agents.test",
    )
    state = WorkloadState(spec=spec, status=status, pid=pid)
    return state


class TestHealthChecker:
    def test_is_process_alive_current_process(self):
        assert HealthChecker._is_process_alive(os.getpid()) is True

    def test_is_process_alive_nonexistent(self):
        # Use a very high PID unlikely to exist
        assert HealthChecker._is_process_alive(999999999) is False

    async def test_start_and_stop(self):
        orch = MagicMock()
        orch.list_workloads.return_value = []
        checker = HealthChecker(orch, interval=0.1)
        await checker.start()
        assert checker._running is True
        await asyncio.sleep(0.05)
        await checker.stop()
        assert checker._running is False

    async def test_check_marks_dead_process_failed(self):
        dead_state = _make_state("dead-wl", WorkloadStatus.RUNNING, pid=999999999)
        orch = MagicMock()
        orch.list_workloads.return_value = [dead_state]
        checker = HealthChecker(orch)
        await checker._check_all()
        assert dead_state.status == WorkloadStatus.FAILED
        assert "not found" in dead_state.last_error

    async def test_check_ignores_non_running(self):
        state = _make_state("stopped-wl", WorkloadStatus.STOPPED, pid=None)
        orch = MagicMock()
        orch.list_workloads.return_value = [state]
        checker = HealthChecker(orch)
        await checker._check_all()
        assert state.status == WorkloadStatus.STOPPED

    async def test_check_ignores_running_without_pid(self):
        state = _make_state("no-pid", WorkloadStatus.RUNNING, pid=None)
        orch = MagicMock()
        orch.list_workloads.return_value = [state]
        checker = HealthChecker(orch)
        await checker._check_all()
        assert state.status == WorkloadStatus.RUNNING

    async def test_check_keeps_alive_process_running(self):
        state = _make_state("alive-wl", WorkloadStatus.RUNNING, pid=os.getpid())
        orch = MagicMock()
        orch.list_workloads.return_value = [state]
        checker = HealthChecker(orch)
        await checker._check_all()
        assert state.status == WorkloadStatus.RUNNING
