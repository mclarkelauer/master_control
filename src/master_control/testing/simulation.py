"""Docker Compose-based fleet simulation for local testing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger()

# Default compose file path relative to project root.
DEFAULT_COMPOSE_FILE = Path("simulation/docker-compose.sim.yaml")


class SimulationManager:
    """Wraps docker compose operations for the simulated fleet."""

    def __init__(self, compose_file: Path = DEFAULT_COMPOSE_FILE, project_name: str = "mctl-sim") -> None:
        self.compose_file = compose_file
        self.project_name = project_name

    def _base_cmd(self) -> list[str]:
        return [
            "docker", "compose",
            "-f", str(self.compose_file),
            "-p", self.project_name,
        ]

    def up(self, *, clients: int = 3, detach: bool = True) -> subprocess.CompletedProcess:
        """Start the simulated fleet."""
        cmd = self._base_cmd() + ["up"]
        if detach:
            cmd.append("-d")
        cmd.extend(["--scale", f"client={clients}"])
        log.info("simulation.up", clients=clients, compose_file=str(self.compose_file))
        return subprocess.run(cmd, check=True, capture_output=True, text=True)

    def down(self, *, volumes: bool = False) -> subprocess.CompletedProcess:
        """Tear down the simulated fleet."""
        cmd = self._base_cmd() + ["down"]
        if volumes:
            cmd.append("-v")
        log.info("simulation.down")
        return subprocess.run(cmd, check=True, capture_output=True, text=True)

    def status(self) -> str:
        """Return container status for the simulated fleet."""
        cmd = self._base_cmd() + ["ps", "--format", "table"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout

    def logs(self, *, service: str | None = None, tail: int = 50) -> str:
        """Fetch logs from the simulated fleet."""
        cmd = self._base_cmd() + ["logs", "--tail", str(tail)]
        if service:
            cmd.append(service)
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.stdout + result.stderr
