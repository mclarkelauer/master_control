"""Tests for the fleet state store — heartbeats, client queries, and deployment CRUD."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from master_control.api.models import (
    HeartbeatPayload,
    SystemMetrics,
    WorkloadInfo,
)
from master_control.fleet.store import FleetDatabase, FleetStateStore


@pytest.fixture
async def fleet_db(tmp_path: Path) -> FleetDatabase:
    db = FleetDatabase(tmp_path / "fleet_test.db")
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def store(fleet_db: FleetDatabase) -> FleetStateStore:
    return FleetStateStore(fleet_db)


def _make_heartbeat(
    client_name: str = "pi-1",
    deployed_version: str | None = None,
    workloads: list[WorkloadInfo] | None = None,
) -> HeartbeatPayload:
    return HeartbeatPayload(
        client_name=client_name,
        timestamp=datetime.now(),
        deployed_version=deployed_version,
        workloads=workloads or [],
        system=SystemMetrics(
            cpu_percent=12.5,
            memory_used_mb=256.0,
            memory_total_mb=1024.0,
            disk_used_gb=5.0,
            disk_total_gb=32.0,
        ),
    )


class TestUpsertHeartbeat:
    async def test_inserts_new_client(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="192.168.1.10")
        clients = await store.list_clients()
        assert len(clients) == 1
        assert clients[0].name == "pi-1"
        assert clients[0].host == "192.168.1.10"
        assert clients[0].status == "online"

    async def test_updates_existing_client(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="192.168.1.10")
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="192.168.1.11")
        clients = await store.list_clients()
        assert len(clients) == 1
        assert clients[0].host == "192.168.1.11"

    async def test_stores_system_metrics(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.system is not None
        assert client.system.cpu_percent == 12.5
        assert client.system.memory_used_mb == 256.0

    async def test_stores_deployed_version(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", deployed_version="1.2.3"), host="10.0.0.1"
        )
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.deployed_version == "1.2.3"

    async def test_preserves_existing_version_when_heartbeat_has_none(
        self, store: FleetStateStore
    ) -> None:
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", deployed_version="1.0.0"), host="10.0.0.1"
        )
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", deployed_version=None), host="10.0.0.1"
        )
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.deployed_version == "1.0.0"

    async def test_upserts_workloads(self, store: FleetStateStore) -> None:
        workloads = [
            WorkloadInfo(name="agent_a", type="agent", run_mode="forever", status="running"),
            WorkloadInfo(name="script_b", type="script", run_mode="n_times", status="stopped"),
        ]
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", workloads=workloads), host="10.0.0.1"
        )
        wl_list = await store.get_workloads("pi-1")
        assert len(wl_list) == 2
        names = {w.name for w in wl_list}
        assert names == {"agent_a", "script_b"}

    async def test_removes_stale_workloads(self, store: FleetStateStore) -> None:
        wl1 = [WorkloadInfo(name="a", type="agent", run_mode="forever", status="running")]
        wl2 = [WorkloadInfo(name="b", type="agent", run_mode="forever", status="running")]
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", workloads=wl1), host="10.0.0.1"
        )
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", workloads=wl2), host="10.0.0.1"
        )
        wl_list = await store.get_workloads("pi-1")
        assert len(wl_list) == 1
        assert wl_list[0].name == "b"


class TestClientQueries:
    async def test_get_client_not_found(self, store: FleetStateStore) -> None:
        result = await store.get_client("nonexistent")
        assert result is None

    async def test_list_clients_empty(self, store: FleetStateStore) -> None:
        result = await store.list_clients()
        assert result == []

    async def test_list_multiple_clients(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        await store.upsert_heartbeat(_make_heartbeat("pi-2"), host="10.0.0.2")
        clients = await store.list_clients()
        assert len(clients) == 2
        names = {c.name for c in clients}
        assert names == {"pi-1", "pi-2"}

    async def test_get_workload_single(self, store: FleetStateStore) -> None:
        workloads = [
            WorkloadInfo(name="agent_a", type="agent", run_mode="forever", status="running", pid=123),
        ]
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", workloads=workloads), host="10.0.0.1"
        )
        wl = await store.get_workload("pi-1", "agent_a")
        assert wl is not None
        assert wl.name == "agent_a"
        assert wl.pid == 123

    async def test_get_workload_not_found(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        result = await store.get_workload("pi-1", "nonexistent")
        assert result is None

    async def test_resolve_client_endpoint(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        endpoint = await store.resolve_client_endpoint("pi-1")
        assert endpoint == ("10.0.0.1", 9100)

    async def test_resolve_client_endpoint_not_found(self, store: FleetStateStore) -> None:
        result = await store.resolve_client_endpoint("nonexistent")
        assert result is None

    async def test_workload_count_in_overview(self, store: FleetStateStore) -> None:
        workloads = [
            WorkloadInfo(name="a", type="agent", run_mode="forever", status="running"),
            WorkloadInfo(name="b", type="agent", run_mode="forever", status="running"),
            WorkloadInfo(name="c", type="agent", run_mode="forever", status="failed"),
        ]
        await store.upsert_heartbeat(
            _make_heartbeat("pi-1", workloads=workloads), host="10.0.0.1"
        )
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.workload_count == 3
        assert client.workloads_running == 2
        assert client.workloads_failed == 1


class TestMarkStaleClients:
    async def test_marks_old_clients_offline(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        # Manually backdate last_seen
        conn = store._db.conn
        old_time = (datetime.now() - timedelta(seconds=120)).isoformat()
        await conn.execute(
            "UPDATE fleet_clients SET last_seen = ? WHERE name = ?", (old_time, "pi-1")
        )
        await conn.commit()

        count = await store.mark_stale_clients(threshold_seconds=60)
        assert count == 1
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.status == "offline"

    async def test_does_not_mark_recent_clients(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        count = await store.mark_stale_clients(threshold_seconds=60)
        assert count == 0
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.status == "online"


class TestDeploymentCRUD:
    async def test_create_and_get_deployment(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1", "pi-2"], batch_size=1)
        deployment = await store.get_deployment("dep-1")
        assert deployment is not None
        assert deployment.id == "dep-1"
        assert deployment.version == "v1.0.0"
        assert deployment.status == "pending"
        assert deployment.target_clients == ["pi-1", "pi-2"]
        assert deployment.batch_size == 1

    async def test_get_deployment_not_found(self, store: FleetStateStore) -> None:
        result = await store.get_deployment("nonexistent")
        assert result is None

    async def test_create_deployment_clients_batch(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1", "pi-2"], batch_size=1)
        await store.create_deployment_clients("dep-1", [("pi-1", 0), ("pi-2", 1)])
        clients = await store.get_deployment_clients("dep-1")
        assert len(clients) == 2
        assert clients[0].client_name == "pi-1"
        assert clients[0].batch_number == 0
        assert clients[0].status == "pending"
        assert clients[1].client_name == "pi-2"
        assert clients[1].batch_number == 1

    async def test_update_deployment_status_in_progress(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.update_deployment_status("dep-1", "in_progress")
        dep = await store.get_deployment("dep-1")
        assert dep is not None
        assert dep.status == "in_progress"
        assert dep.started_at is not None

    async def test_update_deployment_status_completed(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.update_deployment_status("dep-1", "completed")
        dep = await store.get_deployment("dep-1")
        assert dep is not None
        assert dep.status == "completed"
        assert dep.completed_at is not None

    async def test_update_deployment_status_failed_with_error(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.update_deployment_status("dep-1", "failed", error="Health check timeout")
        dep = await store.get_deployment("dep-1")
        assert dep is not None
        assert dep.status == "failed"
        assert dep.error == "Health check timeout"

    async def test_update_deployment_client_status(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.create_deployment_clients("dep-1", [("pi-1", 0)])
        await store.update_deployment_client_status("dep-1", "pi-1", "deploying")
        clients = await store.get_deployment_clients("dep-1")
        assert clients[0].status == "deploying"
        assert clients[0].started_at is not None

    async def test_update_deployment_client_status_failed(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.create_deployment_clients("dep-1", [("pi-1", 0)])
        await store.update_deployment_client_status(
            "dep-1", "pi-1", "failed", error="SSH timeout"
        )
        clients = await store.get_deployment_clients("dep-1")
        assert clients[0].status == "failed"
        assert clients[0].error == "SSH timeout"
        assert clients[0].completed_at is not None

    async def test_set_previous_version(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v2.0.0", ["pi-1"], batch_size=1)
        await store.create_deployment_clients("dep-1", [("pi-1", 0)])
        await store.set_deployment_client_previous_version("dep-1", "pi-1", "v1.0.0")
        clients = await store.get_deployment_clients("dep-1")
        assert clients[0].previous_version == "v1.0.0"

    async def test_list_deployments(self, store: FleetStateStore) -> None:
        await store.create_deployment("dep-1", "v1.0.0", ["pi-1"], batch_size=1)
        await store.create_deployment("dep-2", "v2.0.0", ["pi-1", "pi-2"], batch_size=2)
        deployments = await store.list_deployments()
        assert len(deployments) == 2
        # Most recent first
        assert deployments[0].id == "dep-2"

    async def test_list_deployments_limit(self, store: FleetStateStore) -> None:
        for i in range(5):
            await store.create_deployment(f"dep-{i}", f"v{i}", ["pi-1"], batch_size=1)
        deployments = await store.list_deployments(limit=3)
        assert len(deployments) == 3

    async def test_update_client_deployed_version(self, store: FleetStateStore) -> None:
        await store.upsert_heartbeat(_make_heartbeat("pi-1"), host="10.0.0.1")
        await store.update_client_deployed_version("pi-1", "v2.0.0")
        client = await store.get_client("pi-1")
        assert client is not None
        assert client.deployed_version == "v2.0.0"


class TestMigrations:
    async def test_migrations_applied(self, fleet_db: FleetDatabase) -> None:
        """Verify that the 001_deployments migration was applied on connect."""
        cursor = await fleet_db.conn.execute("SELECT name FROM _migrations")
        rows = await cursor.fetchall()
        names = {row[0] for row in rows}
        assert "001_deployments.sql" in names

    async def test_migrations_idempotent(self, tmp_path: Path) -> None:
        """Connecting twice should not fail (migrations already applied)."""
        db = FleetDatabase(tmp_path / "fleet_test.db")
        await db.connect()
        await db.close()
        # Second connect should not raise
        db2 = FleetDatabase(tmp_path / "fleet_test.db")
        await db2.connect()
        await db2.close()
