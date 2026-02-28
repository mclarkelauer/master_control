"""Chaos testing utilities for resilience testing of Master Control fleets."""

from __future__ import annotations

import random
import subprocess

import structlog

log = structlog.get_logger()


class ChaosRunner:
    """Runs chaos experiments against a simulated or live fleet."""

    def __init__(self, project_name: str = "mctl-sim") -> None:
        self.project_name = project_name

    def _compose_cmd(self) -> list[str]:
        return ["docker", "compose", "-p", self.project_name]

    def _get_client_containers(self) -> list[str]:
        """List running client container IDs."""
        cmd = self._compose_cmd() + [
            "ps", "-q", "client",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return [c.strip() for c in result.stdout.strip().splitlines() if c.strip()]

    def kill_random_workload(self, container: str | None = None) -> dict:
        """Send SIGKILL to a random python process inside a client container.

        If *container* is None, picks a random client container.
        """
        containers = self._get_client_containers()
        if not containers:
            return {"error": "No client containers running"}
        target = container or random.choice(containers)

        # Find python PIDs inside the container
        cmd = ["docker", "exec", target, "pgrep", "-f", "master_control.engine._worker"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]

        if not pids:
            return {"container": target, "action": "kill_workload", "result": "no workload processes found"}

        victim_pid = random.choice(pids)
        kill_cmd = ["docker", "exec", target, "kill", "-9", victim_pid]
        subprocess.run(kill_cmd, capture_output=True, text=True)
        log.info("chaos.kill_workload", container=target, pid=victim_pid)
        return {"container": target, "action": "kill_workload", "pid": victim_pid}

    def pause_container(self, container: str | None = None, duration: float = 10.0) -> dict:
        """Pause a client container to simulate network partition.

        The container is paused (frozen) for *duration* seconds, then unpaused.
        """
        containers = self._get_client_containers()
        if not containers:
            return {"error": "No client containers running"}
        target = container or random.choice(containers)

        subprocess.run(["docker", "pause", target], capture_output=True, text=True, check=True)
        log.info("chaos.pause_container", container=target, duration=duration)
        return {
            "container": target,
            "action": "pause",
            "duration": duration,
            "note": f"Container paused. Run 'docker unpause {target}' after {duration}s or use the unpause method.",
        }

    def unpause_container(self, container: str) -> dict:
        """Unpause a previously paused container."""
        subprocess.run(["docker", "unpause", container], capture_output=True, text=True, check=True)
        log.info("chaos.unpause_container", container=container)
        return {"container": container, "action": "unpause"}

    def fill_disk(self, container: str | None = None, size_mb: int = 50) -> dict:
        """Create a large file inside a client container to simulate disk pressure."""
        containers = self._get_client_containers()
        if not containers:
            return {"error": "No client containers running"}
        target = container or random.choice(containers)

        cmd = [
            "docker", "exec", target,
            "dd", "if=/dev/zero", "of=/tmp/chaos_fill",
            "bs=1M", f"count={size_mb}",
        ]
        subprocess.run(cmd, capture_output=True, text=True)
        log.info("chaos.fill_disk", container=target, size_mb=size_mb)
        return {"container": target, "action": "fill_disk", "size_mb": size_mb}

    def clean_disk(self, container: str | None = None) -> dict:
        """Remove chaos-generated files from a container."""
        containers = self._get_client_containers()
        if not containers:
            return {"error": "No client containers running"}
        target = container or random.choice(containers)

        cmd = ["docker", "exec", target, "rm", "-f", "/tmp/chaos_fill"]
        subprocess.run(cmd, capture_output=True, text=True)
        log.info("chaos.clean_disk", container=target)
        return {"container": target, "action": "clean_disk"}

    def run_scenario(self, scenario: str = "random") -> list[dict]:
        """Run a predefined chaos scenario.

        Scenarios:
        - ``random``: pick one random action
        - ``cascade``: kill a workload, then pause a container
        - ``disk_pressure``: fill disk on a random client
        """
        results: list[dict] = []
        if scenario == "random":
            actions = [self.kill_random_workload, self.pause_container, self.fill_disk]
            action = random.choice(actions)
            results.append(action())
        elif scenario == "cascade":
            results.append(self.kill_random_workload())
            results.append(self.pause_container())
        elif scenario == "disk_pressure":
            results.append(self.fill_disk())
        else:
            return [{"error": f"Unknown scenario: {scenario}"}]
        log.info("chaos.scenario_complete", scenario=scenario, actions=len(results))
        return results
