"""Debug utilities — exec and shell support for workloads."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from master_control.models.workload import WorkloadSpec


def build_workload_env(spec: WorkloadSpec) -> dict[str, str]:
    """Build an environment dict that mirrors the workload's runtime env.

    Includes the current OS environment plus workload-specific variables.
    """
    env = dict(os.environ)
    env["MCTL_WORKLOAD_NAME"] = spec.name
    env["MCTL_WORKLOAD_TYPE"] = spec.workload_type
    env["MCTL_MODULE_PATH"] = spec.module_path
    env["MCTL_ENTRY_POINT"] = spec.entry_point
    env["MCTL_PARAMS_JSON"] = json.dumps(spec.params)
    # Ensure cwd is on PYTHONPATH so workload modules can be imported.
    python_path = env.get("PYTHONPATH", "")
    cwd = os.getcwd()
    if cwd not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = f"{cwd}{os.pathsep}{python_path}" if python_path else cwd
    return env


async def exec_in_workload_env(
    spec: WorkloadSpec,
    command: list[str],
    timeout: float = 30.0,
) -> tuple[str, str, int]:
    """Run a command in the workload's environment.

    Returns ``(stdout, stderr, exit_code)``.
    """
    env = build_workload_env(spec)

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", "Command timed out", -1

    return (
        stdout_bytes.decode(errors="replace"),
        stderr_bytes.decode(errors="replace"),
        proc.returncode or 0,
    )


def build_shell_args(spec: WorkloadSpec) -> tuple[list[str], dict[str, str]]:
    """Build the args and env for an interactive Python shell.

    Returns ``(argv, env)`` suitable for ``os.execvpe()``.
    """
    env = build_workload_env(spec)
    startup_code = (
        f"import {spec.module_path} as _mod; "
        f"print('Loaded module: {spec.module_path}'); "
        f"print('Entry point: {spec.entry_point}'); "
        f"print('Params: {json.dumps(spec.params)}'); "
        f"print('---')"
    )
    argv = [sys.executable, "-i", "-c", startup_code]
    return argv, env
