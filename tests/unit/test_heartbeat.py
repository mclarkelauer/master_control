"""Tests for the heartbeat reporter — payload building and lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from master_control.api.models import HeartbeatPayload
from master_control.config.schema import FleetConfig
from master_control.fleet.heartbeat import HeartbeatReporter
from master_control.models.workload import (
    RunMode,
    WorkloadSpec,
    WorkloadState,
    WorkloadStatus,
    WorkloadType,
)


def _make_orchestrator_mock(
    workloads: list[WorkloadState] | None = None,
    deployed_version: str | None = None,
) -> MagicMock:
    orch = MagicMock()
    orch.list_workloads.return_value = workloads or []
    type(orch).deployed_version = PropertyMock(return_value=deployed_version)
    return orch


def _make_fleet_config(**kwargs) -> FleetConfig:
    defaults = {
        "enabled": True,
        "client_name": "pi-1",
        "central_api_url": "http://central:8080",
        "heartbeat_interval_seconds": 0.1,
    }
    defaults.update(kwargs)
    return FleetConfig(**defaults)


class TestBuildPayload:
    def test_empty_workloads(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config()
        reporter = HeartbeatReporter(orch, config)

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 10.0,
                "memory_used_mb": 256.0,
                "memory_total_mb": 1024.0,
                "disk_used_gb": 5.0,
                "disk_total_gb": 32.0,
            }
            payload = reporter._build_payload()

        assert payload.client_name == "pi-1"
        assert payload.workloads == []
        assert payload.system.cpu_percent == 10.0

    def test_includes_deployed_version(self) -> None:
        orch = _make_orchestrator_mock(deployed_version="v1.2.3")
        config = _make_fleet_config()
        reporter = HeartbeatReporter(orch, config)

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 0, "memory_used_mb": 0, "memory_total_mb": 0,
                "disk_used_gb": 0, "disk_total_gb": 0,
            }
            payload = reporter._build_payload()

        assert payload.deployed_version == "v1.2.3"

    def test_includes_workloads(self) -> None:
        spec = WorkloadSpec(
            name="test_agent",
            workload_type=WorkloadType.AGENT,
            run_mode=RunMode.FOREVER,
            module_path="agents.test",
        )
        state = WorkloadState(
            spec=spec,
            status=WorkloadStatus.RUNNING,
            pid=1234,
            run_count=5,
            last_started=datetime(2025, 1, 1, 12, 0, 0),
        )
        orch = _make_orchestrator_mock(workloads=[state])
        config = _make_fleet_config()
        reporter = HeartbeatReporter(orch, config)

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 0, "memory_used_mb": 0, "memory_total_mb": 0,
                "disk_used_gb": 0, "disk_total_gb": 0,
            }
            payload = reporter._build_payload()

        assert len(payload.workloads) == 1
        wl = payload.workloads[0]
        assert wl.name == "test_agent"
        assert wl.type == "agent"
        assert wl.run_mode == "forever"
        assert wl.status == "running"
        assert wl.pid == 1234
        assert wl.run_count == 5

    def test_fallback_client_name(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config(client_name=None)
        reporter = HeartbeatReporter(orch, config)

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 0, "memory_used_mb": 0, "memory_total_mb": 0,
                "disk_used_gb": 0, "disk_total_gb": 0,
            }
            payload = reporter._build_payload()

        assert payload.client_name == "unknown"


class TestLifecycle:
    async def test_start_and_stop(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config()
        reporter = HeartbeatReporter(orch, config)

        await reporter.start()
        assert reporter._running is True
        assert reporter._task is not None
        assert reporter._client is not None

        await reporter.stop()
        assert reporter._running is False
        assert reporter._client is None

    async def test_sends_heartbeat(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config(heartbeat_interval_seconds=0.05)
        reporter = HeartbeatReporter(orch, config)

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 0, "memory_used_mb": 0, "memory_total_mb": 0,
                "disk_used_gb": 0, "disk_total_gb": 0,
            }
            with patch.object(reporter, "_send_heartbeat", new_callable=AsyncMock) as mock_send:
                await reporter.start()
                await asyncio.sleep(0.15)
                await reporter.stop()

                assert mock_send.call_count >= 1

    async def test_skips_when_no_central_url(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config(central_api_url=None)
        reporter = HeartbeatReporter(orch, config)

        # _send_heartbeat should return early without making requests
        reporter._client = AsyncMock()
        await reporter._send_heartbeat()
        # No exception raised, no HTTP call made


class TestSendHeartbeat:
    async def test_handles_http_error_gracefully(self) -> None:
        import httpx

        orch = _make_orchestrator_mock()
        config = _make_fleet_config()
        reporter = HeartbeatReporter(orch, config)

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        reporter._client = mock_client

        with patch("master_control.fleet.heartbeat.collect_system_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "cpu_percent": 0, "memory_used_mb": 0, "memory_total_mb": 0,
                "disk_used_gb": 0, "disk_total_gb": 0,
            }
            # Should not raise
            await reporter._send_heartbeat()

    async def test_includes_auth_header(self) -> None:
        orch = _make_orchestrator_mock()
        config = _make_fleet_config(api_token="my-secret-token")
        reporter = HeartbeatReporter(orch, config)

        await reporter.start()
        assert reporter._client is not None
        assert reporter._client.headers.get("Authorization") == "Bearer my-secret-token"
        await reporter.stop()
