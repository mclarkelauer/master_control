import asyncio
from pathlib import Path

import pytest

from master_control.engine.ipc import send_command
from master_control.engine.orchestrator import Orchestrator
from master_control.models.workload import WorkloadStatus


@pytest.fixture
def config_dir(tmp_path: Path, fixtures_dir: Path) -> Path:
    """Create a config dir with just the valid service and script configs."""
    cfg = tmp_path / "configs"
    cfg.mkdir()
    # Use hello_agent (exits quickly) for testing
    (cfg / "agent.yaml").write_text(
        """
name: test_agent
type: agent
run_mode: n_times
max_runs: 1
module: agents.examples.hello_agent
entry_point: run
"""
    )
    (cfg / "service.yaml").write_text(
        """
name: test_service
type: service
run_mode: forever
module: agents.examples.ticker_service
entry_point: run
restart_delay: 0.5
params:
  interval: 1
"""
    )
    return cfg


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent.parent / "fixtures"


class TestOrchestrator:
    async def test_start_and_list_workloads(
        self, config_dir: Path, tmp_path: Path
    ) -> None:
        socket_path = tmp_path / "test.sock"
        orch = Orchestrator(
            config_dir=config_dir,
            db_path=tmp_path / "test.db",
            socket_path=socket_path,
        )
        await orch.start()

        try:
            states = orch.list_workloads()
            assert len(states) == 2
            names = {s.spec.name for s in states}
            assert names == {"test_agent", "test_service"}
        finally:
            await orch.shutdown()

    async def test_stop_workload(self, config_dir: Path, tmp_path: Path) -> None:
        socket_path = tmp_path / "test.sock"
        orch = Orchestrator(
            config_dir=config_dir,
            db_path=tmp_path / "test.db",
            socket_path=socket_path,
        )
        await orch.start()

        try:
            # Wait for service to be running
            for _ in range(30):
                state = orch.get_status("test_service")
                if state and state.status == WorkloadStatus.RUNNING:
                    break
                await asyncio.sleep(0.1)

            result = await orch.stop_workload("test_service")
            assert "Stopped" in result

            state = orch.get_status("test_service")
            assert state.status == WorkloadStatus.STOPPED
        finally:
            await orch.shutdown()

    async def test_ipc_list(self, config_dir: Path, tmp_path: Path) -> None:
        socket_path = tmp_path / "test.sock"
        orch = Orchestrator(
            config_dir=config_dir,
            db_path=tmp_path / "test.db",
            socket_path=socket_path,
        )
        await orch.start()

        try:
            # Give workloads a moment to start
            await asyncio.sleep(0.5)

            response = await send_command(
                {"command": "list"}, socket_path=socket_path
            )
            assert "workloads" in response
            assert len(response["workloads"]) == 2
        finally:
            await orch.shutdown()

    async def test_ipc_start_stop(self, config_dir: Path, tmp_path: Path) -> None:
        socket_path = tmp_path / "test.sock"
        orch = Orchestrator(
            config_dir=config_dir,
            db_path=tmp_path / "test.db",
            socket_path=socket_path,
        )
        await orch.start()

        try:
            await asyncio.sleep(0.5)

            # Stop the service via IPC
            response = await send_command(
                {"command": "stop", "name": "test_service"},
                socket_path=socket_path,
            )
            assert "Stopped" in response.get("message", "")

            # Start it again via IPC
            response = await send_command(
                {"command": "start", "name": "test_service"},
                socket_path=socket_path,
            )
            assert "Started" in response.get("message", "")
        finally:
            await orch.shutdown()
