"""Tests for deployment and installation scripts."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
LIB_DIR = SCRIPTS_DIR / "lib"


class TestDeployClientsScript:
    script = SCRIPTS_DIR / "deploy-clients.sh"

    def test_exists_and_executable(self):
        assert self.script.exists()
        assert os.access(self.script, os.X_OK)

    def test_has_bash_shebang(self):
        first_line = self.script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_has_strict_mode(self):
        content = self.script.read_text()
        assert "set -euo pipefail" in content

    def test_help_output(self):
        result = subprocess.run(
            ["bash", str(self.script), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--inventory" in result.stdout
        assert "--client" in result.stdout
        assert "--parallel" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--sync-only" in result.stdout
        assert "--version" in result.stdout

    def test_unknown_option_fails(self):
        result = subprocess.run(
            ["bash", str(self.script), "--nonexistent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_supports_version_flag(self):
        content = self.script.read_text()
        assert "DEPLOY_VERSION" in content
        assert ".mctl-version" in content

    def test_supports_env_vars(self):
        content = self.script.read_text()
        assert "MCTL_INVENTORY" in content
        assert "MCTL_DEPLOY_PARALLEL" in content
        assert "MCTL_INSTALL_DIR" in content
        assert "MCTL_SSH_TIMEOUT" in content


class TestSetupControlHostScript:
    script = SCRIPTS_DIR / "setup-control-host.sh"

    def test_exists_and_executable(self):
        assert self.script.exists()
        assert os.access(self.script, os.X_OK)

    def test_has_bash_shebang(self):
        first_line = self.script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_has_strict_mode(self):
        content = self.script.read_text()
        assert "set -euo pipefail" in content

    def test_help_output(self):
        result = subprocess.run(
            ["bash", str(self.script), "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--local-only" in result.stdout
        assert "--deploy-only" in result.stdout
        assert "--inventory" in result.stdout


class TestRemoteBootstrapScript:
    script = LIB_DIR / "remote-bootstrap.sh"

    def test_exists_and_executable(self):
        assert self.script.exists()
        assert os.access(self.script, os.X_OK)

    def test_has_bash_shebang(self):
        first_line = self.script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_has_strict_mode(self):
        content = self.script.read_text()
        assert "set -euo pipefail" in content

    def test_detects_distro(self):
        content = self.script.read_text()
        assert "/etc/os-release" in content

    def test_handles_common_distros(self):
        content = self.script.read_text()
        for distro in ["ubuntu", "debian", "fedora", "rhel", "centos"]:
            assert distro in content


class TestCommonLib:
    script = LIB_DIR / "common.sh"

    def test_exists(self):
        assert self.script.exists()

    def test_has_bash_shebang(self):
        first_line = self.script.read_text().splitlines()[0]
        assert first_line == "#!/usr/bin/env bash"

    def test_defines_helpers(self):
        content = self.script.read_text()
        assert "info()" in content
        assert "warn()" in content
        assert "error()" in content
        assert "die()" in content
        assert "require_cmd()" in content

    def test_defines_env_vars(self):
        content = self.script.read_text()
        assert "MCTL_INVENTORY" in content
        assert "MCTL_DEPLOY_PARALLEL" in content
        assert "MCTL_INSTALL_DIR" in content


class TestInventoryHelper:
    helper = LIB_DIR / "inventory_helper.py"
    example_inventory = PROJECT_ROOT / "configs" / "examples" / "inventory.yaml"

    def test_exists(self):
        assert self.helper.exists()

    def test_validate_example_inventory(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "validate",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_count_clients(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "count",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "3"

    def test_list_clients(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "list-clients",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 3
        assert "web-worker-1" in lines[0]
        assert "batch-runner-1" in lines[1]

    def test_get_field_with_override(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "get-field", "0", "ssh_user",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "admin"  # overrides default "deploy"

    def test_get_field_with_default(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "get-field", "1", "ssh_user",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "deploy"  # falls back to default

    def test_get_workloads(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "get-workloads", "0",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 2
        assert "ticker_service.yaml" in lines[0]
        assert "hello_agent.yaml" in lines[1]

    def test_get_env(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "get-env", "0",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "MCTL_SOCKET_PATH=/var/run/mctl.sock" in result.stdout

    def test_invalid_command(self):
        result = subprocess.run(
            [
                "uv", "run", "python3", str(self.helper),
                "--inventory", str(self.example_inventory),
                "nonexistent",
            ],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 1


class TestExampleInventory:
    example = PROJECT_ROOT / "configs" / "examples" / "inventory.yaml"

    def test_exists(self):
        assert self.example.exists()

    def test_valid_yaml(self):
        data = yaml.safe_load(self.example.read_text())
        assert "defaults" in data
        assert "clients" in data
        assert isinstance(data["clients"], list)
        assert len(data["clients"]) > 0

    def test_clients_have_required_fields(self):
        data = yaml.safe_load(self.example.read_text())
        for client in data["clients"]:
            assert "host" in client


class TestMakefileDeployTargets:
    def test_has_deploy_targets(self):
        content = (PROJECT_ROOT / "Makefile").read_text()
        for target in ["setup:", "setup-local:", "deploy:", "deploy-client:", "deploy-dry-run:", "deploy-sync:"]:
            assert target in content
