"""Tests for simulation and chaos testing utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from master_control.testing.chaos import ChaosRunner
from master_control.testing.simulation import SimulationManager


# --- SimulationManager ---


class TestSimulationManager:
    def test_base_cmd_includes_compose_file_and_project(self) -> None:
        mgr = SimulationManager(compose_file=Path("test.yaml"), project_name="test-proj")
        cmd = mgr._base_cmd()
        assert cmd == ["docker", "compose", "-f", "test.yaml", "-p", "test-proj"]

    @patch("master_control.testing.simulation.subprocess.run")
    def test_up_calls_docker_compose(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        mgr.up(clients=5)
        args = mock_run.call_args[0][0]
        assert "up" in args
        assert "-d" in args
        assert "--scale" in args
        assert "client=5" in args

    @patch("master_control.testing.simulation.subprocess.run")
    def test_up_no_detach(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        mgr.up(clients=2, detach=False)
        args = mock_run.call_args[0][0]
        assert "-d" not in args

    @patch("master_control.testing.simulation.subprocess.run")
    def test_down_calls_docker_compose(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        mgr.down()
        args = mock_run.call_args[0][0]
        assert "down" in args
        assert "-v" not in args

    @patch("master_control.testing.simulation.subprocess.run")
    def test_down_with_volumes(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        mgr.down(volumes=True)
        args = mock_run.call_args[0][0]
        assert "-v" in args

    @patch("master_control.testing.simulation.subprocess.run")
    def test_status_returns_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="NAME  STATUS\ncentral  Up\n", stderr=""
        )
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        output = mgr.status()
        assert "central" in output

    @patch("master_control.testing.simulation.subprocess.run")
    def test_logs_with_service(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="log line\n", stderr=""
        )
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        output = mgr.logs(service="central", tail=10)
        args = mock_run.call_args[0][0]
        assert "central" in args
        assert "--tail" in args
        assert "10" in args
        assert "log line" in output

    @patch("master_control.testing.simulation.subprocess.run")
    def test_logs_without_service(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="all logs\n", stderr=""
        )
        mgr = SimulationManager(compose_file=Path("test.yaml"))
        mgr.logs()
        args = mock_run.call_args[0][0]
        # No service appended
        assert args[-1] != "central"


# --- ChaosRunner ---


class TestChaosRunner:
    @patch("master_control.testing.chaos.subprocess.run")
    def test_get_client_containers(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abc123\ndef456\n", stderr=""
        )
        runner = ChaosRunner(project_name="test-proj")
        containers = runner._get_client_containers()
        assert containers == ["abc123", "def456"]

    @patch("master_control.testing.chaos.subprocess.run")
    def test_get_client_containers_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        runner = ChaosRunner()
        containers = runner._get_client_containers()
        assert containers == []

    @patch("master_control.testing.chaos.subprocess.run")
    def test_kill_random_workload_no_containers(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        runner = ChaosRunner()
        result = runner.kill_random_workload()
        assert "error" in result

    @patch("master_control.testing.chaos.subprocess.run")
    def test_kill_random_workload_no_pids(self, mock_run: MagicMock) -> None:
        # First call: get containers, second call: pgrep (no PIDs)
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
        ]
        runner = ChaosRunner()
        result = runner.kill_random_workload()
        assert result["result"] == "no workload processes found"

    @patch("master_control.testing.chaos.subprocess.run")
    def test_kill_random_workload_kills_pid(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="42\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        runner = ChaosRunner()
        result = runner.kill_random_workload(container="abc123")
        assert result["action"] == "kill_workload"
        assert result["pid"] == "42"
        # Third call should be the kill
        kill_call = mock_run.call_args_list[2]
        assert "kill" in kill_call[0][0]
        assert "-9" in kill_call[0][0]

    @patch("master_control.testing.chaos.subprocess.run")
    def test_pause_container_no_containers(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        runner = ChaosRunner()
        result = runner.pause_container()
        assert "error" in result

    @patch("master_control.testing.chaos.subprocess.run")
    def test_pause_container(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        runner = ChaosRunner()
        result = runner.pause_container(container="abc123", duration=5.0)
        assert result["action"] == "pause"
        assert result["duration"] == 5.0

    @patch("master_control.testing.chaos.subprocess.run")
    def test_unpause_container(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        runner = ChaosRunner()
        result = runner.unpause_container("abc123")
        assert result["action"] == "unpause"

    @patch("master_control.testing.chaos.subprocess.run")
    def test_fill_disk(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        runner = ChaosRunner()
        result = runner.fill_disk(container="abc123", size_mb=100)
        assert result["action"] == "fill_disk"
        assert result["size_mb"] == 100

    @patch("master_control.testing.chaos.subprocess.run")
    def test_clean_disk(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        runner = ChaosRunner()
        result = runner.clean_disk(container="abc123")
        assert result["action"] == "clean_disk"

    @patch("master_control.testing.chaos.subprocess.run")
    def test_run_scenario_random(self, mock_run: MagicMock) -> None:
        # All calls return empty containers → error results
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        runner = ChaosRunner()
        results = runner.run_scenario("random")
        assert len(results) == 1

    @patch("master_control.testing.chaos.subprocess.run")
    def test_run_scenario_unknown(self, mock_run: MagicMock) -> None:
        runner = ChaosRunner()
        results = runner.run_scenario("nonexistent")
        assert results[0]["error"] == "Unknown scenario: nonexistent"

    @patch("master_control.testing.chaos.subprocess.run")
    def test_run_scenario_cascade(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
        runner = ChaosRunner()
        results = runner.run_scenario("cascade")
        assert len(results) == 2
