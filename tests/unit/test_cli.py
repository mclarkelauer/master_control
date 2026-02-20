"""Tests for CLI entry point and commands."""

from pathlib import Path

from click.testing import CliRunner

from master_control.cli.main import cli


class TestCli:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "master-control" in result.output
        assert "0.1.0" in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "orchestrator" in result.output.lower()

    def test_no_args_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, [])
        assert "master-control" in result.output.lower() or "usage" in result.output.lower()


class TestValidateCommand:
    def test_validate_valid_only(self, tmp_path: Path, fixtures_dir: Path) -> None:
        for name in ("valid_agent.yaml", "valid_service.yaml", "valid_script.yaml"):
            (tmp_path / name).write_text((fixtures_dir / name).read_text())
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(tmp_path), "validate"])
        assert result.exit_code == 0
        assert "valid" in result.output

    def test_validate_with_invalid(self, fixtures_dir: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(fixtures_dir), "validate"])
        assert result.exit_code == 1
        assert "invalid" in result.output

    def test_validate_nonexistent_dir(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", "/nonexistent", "validate"])
        assert result.exit_code == 1


class TestListCommand:
    def test_list_requires_running_orchestrator(self, tmp_path: Path) -> None:
        """list command uses IPC, so it fails when no orchestrator is running."""
        socket_path = tmp_path / "nonexistent.sock"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--socket-path", str(socket_path), "list"]
        )
        assert result.exit_code == 1
        assert "not running" in result.output.lower()


class TestRunCommand:
    def test_run_nonexistent_workload(self, tmp_path: Path, fixtures_dir: Path) -> None:
        (tmp_path / "agent.yaml").write_text((fixtures_dir / "valid_agent.yaml").read_text())
        runner = CliRunner()
        result = runner.invoke(cli, ["--config-dir", str(tmp_path), "run", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output
