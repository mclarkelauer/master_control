"""Tests for fleet-related Pydantic models and config schema additions."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from master_control.api.models import (
    ClientOverview,
    CommandResponse,
    DeploymentClientStatus,
    DeploymentRequest,
    DeploymentStatus,
    HeartbeatPayload,
    SystemMetrics,
    WorkloadInfo,
)
from master_control.config.schema import CentralConfig, DaemonConfig, FleetConfig, WorkloadConfig


class TestHeartbeatPayload:
    def test_minimal(self) -> None:
        payload = HeartbeatPayload(client_name="pi-1", timestamp=datetime.now())
        assert payload.client_name == "pi-1"
        assert payload.deployed_version is None
        assert payload.workloads == []

    def test_with_deployed_version(self) -> None:
        payload = HeartbeatPayload(
            client_name="pi-1",
            timestamp=datetime.now(),
            deployed_version="v1.2.3",
        )
        assert payload.deployed_version == "v1.2.3"

    def test_with_workloads_and_metrics(self) -> None:
        payload = HeartbeatPayload(
            client_name="pi-1",
            timestamp=datetime.now(),
            workloads=[
                WorkloadInfo(name="a", type="agent", run_mode="forever", status="running"),
            ],
            system=SystemMetrics(cpu_percent=50.0, memory_used_mb=512),
        )
        assert len(payload.workloads) == 1
        assert payload.system.cpu_percent == 50.0

    def test_missing_client_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatPayload(timestamp=datetime.now())


class TestClientOverview:
    def test_defaults(self) -> None:
        client = ClientOverview(name="pi-1", host="10.0.0.1")
        assert client.api_port == 9100
        assert client.status == "unknown"
        assert client.deployed_version is None
        assert client.workload_count == 0
        assert client.system is None

    def test_with_version(self) -> None:
        client = ClientOverview(
            name="pi-1", host="10.0.0.1", deployed_version="v1.0.0"
        )
        assert client.deployed_version == "v1.0.0"


class TestDeploymentRequest:
    def test_defaults(self) -> None:
        req = DeploymentRequest(version="v1.0.0")
        assert req.target_clients is None
        assert req.batch_size == 1
        assert req.health_check_timeout == 60.0
        assert req.auto_rollback is True

    def test_custom_values(self) -> None:
        req = DeploymentRequest(
            version="v2.0.0",
            target_clients=["pi-1", "pi-2"],
            batch_size=3,
            health_check_timeout=120.0,
            auto_rollback=False,
        )
        assert req.version == "v2.0.0"
        assert req.target_clients == ["pi-1", "pi-2"]
        assert req.batch_size == 3
        assert req.auto_rollback is False

    def test_missing_version_raises(self) -> None:
        with pytest.raises(ValidationError):
            DeploymentRequest()


class TestDeploymentStatus:
    def test_full(self) -> None:
        status = DeploymentStatus(
            id="dep-1",
            version="v1.0.0",
            status="completed",
            batch_size=2,
            target_clients=["pi-1", "pi-2"],
            created_at="2025-01-01T00:00:00",
            started_at="2025-01-01T00:00:01",
            completed_at="2025-01-01T00:01:00",
            client_statuses=[
                DeploymentClientStatus(client_name="pi-1", batch_number=0, status="healthy"),
                DeploymentClientStatus(client_name="pi-2", batch_number=1, status="healthy"),
            ],
        )
        assert status.id == "dep-1"
        assert len(status.client_statuses) == 2

    def test_defaults(self) -> None:
        status = DeploymentStatus(
            id="dep-1",
            version="v1.0.0",
            status="pending",
            batch_size=1,
            target_clients=["pi-1"],
            created_at="2025-01-01T00:00:00",
        )
        assert status.started_at is None
        assert status.error is None
        assert status.client_statuses == []


class TestDeploymentClientStatus:
    def test_defaults(self) -> None:
        cs = DeploymentClientStatus(client_name="pi-1")
        assert cs.batch_number == 0
        assert cs.status == "pending"
        assert cs.previous_version is None


class TestFleetConfig:
    def test_defaults(self) -> None:
        config = FleetConfig()
        assert config.enabled is False
        assert config.client_name is None
        assert config.api_host == "0.0.0.0"
        assert config.api_port == 9100
        assert config.central_api_url is None
        assert config.heartbeat_interval_seconds == 30.0
        assert config.api_token is None

    def test_custom_values(self) -> None:
        config = FleetConfig(
            enabled=True,
            client_name="pi-1",
            api_port=9200,
            central_api_url="http://central:8080",
            api_token="secret",
        )
        assert config.enabled is True
        assert config.client_name == "pi-1"
        assert config.api_port == 9200


class TestCentralConfig:
    def test_defaults(self) -> None:
        config = CentralConfig()
        assert config.enabled is False
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.db_path == "./fleet.db"
        assert config.inventory_path == "./inventory.yaml"
        assert config.deploy_script_path is None
        assert config.stale_threshold_seconds == 90.0

    def test_with_deploy_script(self) -> None:
        config = CentralConfig(deploy_script_path="/opt/scripts/deploy.sh")
        assert config.deploy_script_path == "/opt/scripts/deploy.sh"


class TestDaemonConfig:
    def test_defaults(self) -> None:
        config = DaemonConfig()
        assert config.fleet.enabled is False
        assert config.central.enabled is False

    def test_nested(self) -> None:
        config = DaemonConfig(
            fleet=FleetConfig(enabled=True, client_name="pi-1"),
            central=CentralConfig(enabled=True, port=9000),
        )
        assert config.fleet.client_name == "pi-1"
        assert config.central.port == 9000


class TestWorkloadConfigVersion:
    def test_version_field_default_none(self) -> None:
        config = WorkloadConfig(
            name="test", type="agent", run_mode="forever", module="agents.test"
        )
        assert config.version is None

    def test_version_field_set(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            version="1.2.3",
        )
        assert config.version == "1.2.3"

    def test_version_passed_to_spec(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            version="2.0.0",
        )
        spec = config.to_spec()
        assert spec.version == "2.0.0"
