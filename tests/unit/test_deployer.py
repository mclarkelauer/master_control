"""Tests for the rolling deployer — batching, execution, rollback, cancellation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from master_control.api.models import (
    ClientOverview,
    DeploymentClientStatus,
    DeploymentRequest,
    SystemMetrics,
)
from master_control.fleet.deployer import RollingDeployer


def _make_store_mock() -> AsyncMock:
    """Create a mock FleetStateStore with all required methods."""
    store = AsyncMock()
    store.create_deployment = AsyncMock()
    store.create_deployment_clients = AsyncMock()
    store.update_deployment_status = AsyncMock()
    store.update_deployment_client_status = AsyncMock()
    store.set_deployment_client_previous_version = AsyncMock()
    store.update_client_deployed_version = AsyncMock()
    store.get_client = AsyncMock(return_value=ClientOverview(
        name="pi-1", host="10.0.0.1", deployed_version="v0.9.0",
    ))
    store.resolve_client_endpoint = AsyncMock(return_value=("10.0.0.1", 9100))
    store.get_deployment_clients = AsyncMock(return_value=[])
    store.list_clients = AsyncMock(return_value=[
        ClientOverview(name="pi-1", host="10.0.0.1", status="online"),
        ClientOverview(name="pi-2", host="10.0.0.2", status="online"),
        ClientOverview(name="pi-3", host="10.0.0.3", status="offline"),
    ])
    return store


def _make_fleet_client_mock(healthy: bool = True) -> AsyncMock:
    """Create a mock FleetClient."""
    client = AsyncMock()
    client.reload_configs = AsyncMock(return_value={"success": True})
    client.health_check = AsyncMock(
        return_value={"status": "ok"} if healthy else {"status": "error"}
    )
    return client


def _make_deployer(
    store: AsyncMock | None = None,
    fleet_client: AsyncMock | None = None,
) -> RollingDeployer:
    return RollingDeployer(
        fleet_store=store or _make_store_mock(),
        fleet_client=fleet_client or _make_fleet_client_mock(),
        deploy_script_path=Path("/fake/deploy.sh"),
        inventory_path=Path("/fake/inventory.yaml"),
    )


class TestCreateBatches:
    def test_single_batch(self) -> None:
        batches = RollingDeployer._create_batches(["a", "b", "c"], batch_size=5)
        assert batches == [["a", "b", "c"]]

    def test_multiple_batches(self) -> None:
        batches = RollingDeployer._create_batches(["a", "b", "c", "d"], batch_size=2)
        assert batches == [["a", "b"], ["c", "d"]]

    def test_uneven_batches(self) -> None:
        batches = RollingDeployer._create_batches(["a", "b", "c"], batch_size=2)
        assert batches == [["a", "b"], ["c"]]

    def test_batch_size_one(self) -> None:
        batches = RollingDeployer._create_batches(["a", "b"], batch_size=1)
        assert batches == [["a"], ["b"]]

    def test_empty_list(self) -> None:
        batches = RollingDeployer._create_batches([], batch_size=2)
        assert batches == []


class TestStartDeployment:
    async def test_creates_deployment_record(self) -> None:
        store = _make_store_mock()
        deployer = _make_deployer(store=store)
        request = DeploymentRequest(version="v1.0.0", target_clients=["pi-1"], batch_size=1)

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            # Let background task start
            await asyncio.sleep(0.05)

        assert dep_id is not None
        store.create_deployment.assert_called_once_with(
            dep_id, "v1.0.0", ["pi-1"], 1
        )
        store.create_deployment_clients.assert_called_once_with(
            dep_id, [("pi-1", 0)]
        )

    async def test_resolves_online_clients_when_no_targets(self) -> None:
        store = _make_store_mock()
        deployer = _make_deployer(store=store)
        request = DeploymentRequest(version="v1.0.0", batch_size=1)

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            await asyncio.sleep(0.05)

        # Should only include online clients (pi-1, pi-2), not offline pi-3
        call_args = store.create_deployment.call_args
        target_clients = call_args[0][2]
        assert "pi-1" in target_clients
        assert "pi-2" in target_clients
        assert "pi-3" not in target_clients

    async def test_raises_when_no_targets_available(self) -> None:
        store = _make_store_mock()
        store.list_clients = AsyncMock(return_value=[
            ClientOverview(name="pi-1", host="10.0.0.1", status="offline"),
        ])
        deployer = _make_deployer(store=store)
        request = DeploymentRequest(version="v1.0.0", batch_size=1)

        with pytest.raises(ValueError, match="No target clients"):
            await deployer.start_deployment(request)


class TestDeployExecution:
    async def test_successful_single_client_deploy(self) -> None:
        store = _make_store_mock()
        fleet_client = _make_fleet_client_mock(healthy=True)
        deployer = _make_deployer(store=store, fleet_client=fleet_client)
        request = DeploymentRequest(
            version="v1.0.0", target_clients=["pi-1"], batch_size=1
        )

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            # Wait for background task to complete
            task = deployer._active.get(dep_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)

        # Should have marked deployment completed
        store.update_deployment_status.assert_any_call(dep_id, "completed")
        store.update_client_deployed_version.assert_called_with("pi-1", "v1.0.0")

    async def test_deploy_script_failure_marks_failed(self) -> None:
        store = _make_store_mock()
        deployer = _make_deployer(store=store)
        request = DeploymentRequest(
            version="v1.0.0",
            target_clients=["pi-1"],
            batch_size=1,
            auto_rollback=False,
        )

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b"rsync failed"))
            proc.returncode = 1
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            task = deployer._active.get(dep_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)

        # Should have called update with "failed" status
        failed_calls = [
            c for c in store.update_deployment_status.call_args_list
            if c[0][1] == "failed"
        ]
        assert len(failed_calls) > 0

    async def test_deploy_passes_correct_args_to_subprocess(self) -> None:
        store = _make_store_mock()
        fleet_client = _make_fleet_client_mock()
        deploy_script = Path("/opt/scripts/deploy-clients.sh")
        inventory = Path("/opt/configs/inventory.yaml")
        deployer = RollingDeployer(
            fleet_store=store,
            fleet_client=fleet_client,
            deploy_script_path=deploy_script,
            inventory_path=inventory,
        )
        request = DeploymentRequest(
            version="v2.0.0", target_clients=["pi-1"], batch_size=1
        )

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            task = deployer._active.get(dep_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)

        mock_proc.assert_called()
        call_args = mock_proc.call_args[0]
        assert str(deploy_script) in call_args
        assert "--client" in call_args
        assert "pi-1" in call_args
        assert "--inventory" in call_args
        assert str(inventory) in call_args
        assert "--sync-only" in call_args
        assert "--version" in call_args
        assert "v2.0.0" in call_args

    async def test_records_previous_version_for_rollback(self) -> None:
        store = _make_store_mock()
        store.get_client = AsyncMock(return_value=ClientOverview(
            name="pi-1", host="10.0.0.1", deployed_version="v0.9.0",
        ))
        fleet_client = _make_fleet_client_mock()
        deployer = _make_deployer(store=store, fleet_client=fleet_client)
        request = DeploymentRequest(
            version="v1.0.0", target_clients=["pi-1"], batch_size=1
        )

        with patch("asyncio.create_subprocess_exec") as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            dep_id = await deployer.start_deployment(request)
            task = deployer._active.get(dep_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)

        store.set_deployment_client_previous_version.assert_called_once_with(
            dep_id, "pi-1", "v0.9.0"
        )


class TestRollback:
    async def test_auto_rollback_on_deploy_failure(self) -> None:
        store = _make_store_mock()
        store.get_deployment_clients = AsyncMock(return_value=[
            DeploymentClientStatus(
                client_name="pi-1",
                batch_number=0,
                status="failed",
                previous_version="v0.9.0",
            ),
        ])
        fleet_client = _make_fleet_client_mock()
        deployer = _make_deployer(store=store, fleet_client=fleet_client)
        request = DeploymentRequest(
            version="v1.0.0",
            target_clients=["pi-1"],
            batch_size=1,
            auto_rollback=True,
        )

        call_count = 0

        async def mock_create_proc(*args, **kwargs):
            nonlocal call_count
            proc = AsyncMock()
            if call_count == 0:
                # First call: deploy fails
                proc.communicate = AsyncMock(return_value=(b"", b"error"))
                proc.returncode = 1
            else:
                # Rollback call: succeeds
                proc.communicate = AsyncMock(return_value=(b"ok", b""))
                proc.returncode = 0
            call_count += 1
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_create_proc):
            dep_id = await deployer.start_deployment(request)
            task = deployer._active.get(dep_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)

        # Should have attempted rollback
        store.update_deployment_status.assert_any_call(dep_id, "rolling_back")
        store.update_deployment_status.assert_any_call(dep_id, "rolled_back")


class TestCancelDeployment:
    async def test_cancel_running_deployment(self) -> None:
        store = _make_store_mock()
        deployer = _make_deployer(store=store)

        # Create a long-running deployment
        request = DeploymentRequest(
            version="v1.0.0", target_clients=["pi-1"], batch_size=1
        )

        async def slow_proc(*args, **kwargs):
            proc = AsyncMock()
            async def slow_communicate():
                await asyncio.sleep(10)
                return (b"", b"")
            proc.communicate = slow_communicate
            proc.returncode = 0
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=slow_proc):
            dep_id = await deployer.start_deployment(request)
            await asyncio.sleep(0.05)  # Let it start
            await deployer.cancel_deployment(dep_id)

        store.update_deployment_status.assert_any_call(
            dep_id, "failed", error="Cancelled by user"
        )
        assert dep_id not in deployer._active


class TestHealthCheckWait:
    async def test_healthy_returns_true(self) -> None:
        fleet_client = _make_fleet_client_mock(healthy=True)
        store = _make_store_mock()
        deployer = _make_deployer(store=store, fleet_client=fleet_client)

        result = await deployer._wait_for_health("dep-1", ["pi-1"], timeout=5.0)
        assert result is True

    async def test_unhealthy_times_out(self) -> None:
        fleet_client = _make_fleet_client_mock(healthy=False)
        store = _make_store_mock()
        deployer = _make_deployer(store=store, fleet_client=fleet_client)

        result = await deployer._wait_for_health("dep-1", ["pi-1"], timeout=0.1)
        assert result is False

    async def test_no_endpoint_times_out(self) -> None:
        store = _make_store_mock()
        store.resolve_client_endpoint = AsyncMock(return_value=None)
        deployer = _make_deployer(store=store)

        result = await deployer._wait_for_health("dep-1", ["pi-1"], timeout=0.1)
        assert result is False
