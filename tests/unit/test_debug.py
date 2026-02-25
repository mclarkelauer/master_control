"""Tests for interactive debugging utilities."""

from __future__ import annotations

import json
import sys

from master_control.engine.debug import (
    build_shell_args,
    build_workload_env,
    exec_in_workload_env,
)
from master_control.models.workload import RunMode, WorkloadSpec


def _make_spec(**overrides) -> WorkloadSpec:
    defaults = {
        "name": "test_agent",
        "workload_type": "agent",
        "run_mode": RunMode.FOREVER,
        "module_path": "agents.examples.hello_agent",
        "entry_point": "run",
        "params": {"key": "value"},
    }
    defaults.update(overrides)
    return WorkloadSpec(**defaults)


# --- build_workload_env ---


class TestBuildWorkloadEnv:
    def test_includes_workload_vars(self) -> None:
        spec = _make_spec()
        env = build_workload_env(spec)
        assert env["MCTL_WORKLOAD_NAME"] == "test_agent"
        assert env["MCTL_WORKLOAD_TYPE"] == "agent"
        assert env["MCTL_MODULE_PATH"] == "agents.examples.hello_agent"
        assert env["MCTL_ENTRY_POINT"] == "run"
        assert json.loads(env["MCTL_PARAMS_JSON"]) == {"key": "value"}

    def test_includes_os_env(self) -> None:
        spec = _make_spec()
        env = build_workload_env(spec)
        # PATH should always be present from OS env.
        assert "PATH" in env

    def test_includes_pythonpath(self) -> None:
        spec = _make_spec()
        env = build_workload_env(spec)
        assert "PYTHONPATH" in env

    def test_custom_type(self) -> None:
        spec = _make_spec(workload_type="container")
        env = build_workload_env(spec)
        assert env["MCTL_WORKLOAD_TYPE"] == "container"

    def test_empty_params(self) -> None:
        spec = _make_spec(params={})
        env = build_workload_env(spec)
        assert json.loads(env["MCTL_PARAMS_JSON"]) == {}


# --- exec_in_workload_env ---


class TestExecInWorkloadEnv:
    async def test_runs_python_command(self) -> None:
        spec = _make_spec()
        stdout, stderr, exit_code = await exec_in_workload_env(
            spec, [sys.executable, "-c", "print('hello')"]
        )
        assert stdout.strip() == "hello"
        assert exit_code == 0

    async def test_captures_stderr(self) -> None:
        spec = _make_spec()
        stdout, stderr, exit_code = await exec_in_workload_env(
            spec, [sys.executable, "-c", "import sys; sys.stderr.write('err\\n')"]
        )
        assert "err" in stderr
        assert exit_code == 0

    async def test_nonzero_exit_code(self) -> None:
        spec = _make_spec()
        stdout, stderr, exit_code = await exec_in_workload_env(
            spec, [sys.executable, "-c", "raise SystemExit(42)"]
        )
        assert exit_code == 42

    async def test_timeout_kills_command(self) -> None:
        spec = _make_spec()
        stdout, stderr, exit_code = await exec_in_workload_env(
            spec, [sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.5
        )
        assert "timed out" in stderr.lower()
        assert exit_code == -1

    async def test_workload_env_vars_available(self) -> None:
        spec = _make_spec()
        stdout, stderr, exit_code = await exec_in_workload_env(
            spec,
            [sys.executable, "-c", "import os; print(os.environ['MCTL_WORKLOAD_NAME'])"],
        )
        assert stdout.strip() == "test_agent"
        assert exit_code == 0


# --- build_shell_args ---


class TestBuildShellArgs:
    def test_returns_python_interactive(self) -> None:
        spec = _make_spec()
        argv, env = build_shell_args(spec)
        assert argv[0] == sys.executable
        assert "-i" in argv
        assert "-c" in argv

    def test_startup_imports_module(self) -> None:
        spec = _make_spec()
        argv, env = build_shell_args(spec)
        startup_code = argv[argv.index("-c") + 1]
        assert "import agents.examples.hello_agent" in startup_code

    def test_env_includes_workload_vars(self) -> None:
        spec = _make_spec()
        argv, env = build_shell_args(spec)
        assert env["MCTL_WORKLOAD_NAME"] == "test_agent"
