"""Tests for install and startup scripts."""

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


class TestInstallScript:
    def test_exists_and_executable(self):
        script = SCRIPTS_DIR / "install.sh"
        assert script.exists()
        assert os.access(script, os.X_OK)

    def test_has_bash_shebang(self):
        script = SCRIPTS_DIR / "install.sh"
        first_line = script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_has_strict_mode(self):
        content = (SCRIPTS_DIR / "install.sh").read_text()
        assert "set -euo pipefail" in content


class TestDaemonScript:
    def test_exists_and_executable(self):
        script = SCRIPTS_DIR / "mctl-daemon.sh"
        assert script.exists()
        assert os.access(script, os.X_OK)

    def test_has_bash_shebang(self):
        script = SCRIPTS_DIR / "mctl-daemon.sh"
        first_line = script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_help_output(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "mctl-daemon.sh"), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "start" in result.stdout
        assert "stop" in result.stdout
        assert "restart" in result.stdout
        assert "status" in result.stdout

    def test_unknown_command_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "mctl-daemon.sh"), "nonexistent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_supports_env_vars(self):
        content = (SCRIPTS_DIR / "mctl-daemon.sh").read_text()
        assert "MCTL_CONFIG_DIR" in content
        assert "MCTL_DB_PATH" in content
        assert "MCTL_SOCKET_PATH" in content


class TestClientScript:
    def test_exists_and_executable(self):
        script = SCRIPTS_DIR / "mctl-client.sh"
        assert script.exists()
        assert os.access(script, os.X_OK)

    def test_has_bash_shebang(self):
        script = SCRIPTS_DIR / "mctl-client.sh"
        first_line = script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_help_output(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "mctl-client.sh"), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "list" in result.stdout
        assert "status" in result.stdout
        assert "validate" in result.stdout

    def test_unknown_command_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "mctl-client.sh"), "nonexistent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_supports_env_vars(self):
        content = (SCRIPTS_DIR / "mctl-client.sh").read_text()
        assert "MCTL_CONFIG_DIR" in content
        assert "MCTL_SOCKET_PATH" in content


class TestMakefile:
    def test_exists(self):
        assert (PROJECT_ROOT / "Makefile").exists()

    def test_has_required_targets(self):
        content = (PROJECT_ROOT / "Makefile").read_text()
        for target in ["install", "start", "stop", "restart", "status", "test", "lint", "validate"]:
            assert f"{target}:" in content
