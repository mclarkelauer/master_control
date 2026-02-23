"""WorkloadRunner — manages the lifecycle of a single workload subprocess."""

from __future__ import annotations

import asyncio
import json
import signal
import sys
from datetime import datetime
from pathlib import Path

import structlog

from master_control.db.repository import RunHistoryRepo
from master_control.engine.modes import RunModeStrategy, get_strategy
from master_control.engine.rlimits import make_preexec_fn
from master_control.models.workload import WorkloadSpec, WorkloadState, WorkloadStatus

log = structlog.get_logger()


class WorkloadRunner:
    """Manages the lifecycle of one workload as a subprocess."""

    def __init__(
        self,
        spec: WorkloadSpec,
        run_history: RunHistoryRepo,
        log_dir: Path | None = None,
    ) -> None:
        self.spec = spec
        self._run_history = run_history
        self._log_dir = log_dir
        self._strategy: RunModeStrategy = get_strategy(spec.run_mode)
        self._state = WorkloadState(spec=spec)
        self._process: asyncio.subprocess.Process | None = None
        self._supervise_task: asyncio.Task | None = None
        self._stop_requested = False

    @property
    def state(self) -> WorkloadState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state.status in (WorkloadStatus.RUNNING, WorkloadStatus.STARTING)

    async def start(self) -> None:
        """Start the workload subprocess and begin supervision."""
        if self.is_running:
            log.warning("workload already running", workload=self.spec.name)
            return

        self._stop_requested = False
        self._state.status = WorkloadStatus.STARTING
        self._supervise_task = asyncio.create_task(self._supervise())

    async def stop(self, timeout: float = 10.0) -> None:
        """Gracefully stop the workload."""
        self._stop_requested = True
        self._state.status = WorkloadStatus.STOPPING

        if self._process and self._process.returncode is None:
            try:
                self._process.send_signal(signal.SIGTERM)
                await asyncio.wait_for(self._process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                log.warning("workload did not stop gracefully, killing", workload=self.spec.name)
                self._process.kill()
                await self._process.wait()

        if self._supervise_task and not self._supervise_task.done():
            self._supervise_task.cancel()
            try:
                await self._supervise_task
            except asyncio.CancelledError:
                pass

        self._state.status = WorkloadStatus.STOPPED
        self._state.last_stopped = datetime.now()
        self._state.pid = None
        log.info("workload stopped", workload=self.spec.name)

    async def _launch_process(self) -> asyncio.subprocess.Process:
        """Launch the worker subprocess."""
        cmd = [
            sys.executable,
            "-m",
            "master_control.engine._worker",
            "--module",
            self.spec.module_path,
            "--entry-point",
            self.spec.entry_point,
            "--params-json",
            json.dumps(self.spec.params),
            "--workload-name",
            self.spec.name,
        ]

        if self._log_dir:
            log_file = self._log_dir / f"{self.spec.name}.log"
            cmd.extend(["--log-file", str(log_file)])

        preexec_fn = make_preexec_fn(self.spec.memory_limit_mb, self.spec.cpu_nice)
        if preexec_fn:
            log.info(
                "applying resource limits",
                workload=self.spec.name,
                memory_limit_mb=self.spec.memory_limit_mb,
                cpu_nice=self.spec.cpu_nice,
            )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=preexec_fn,
        )
        return process

    async def _supervise(self) -> None:
        """Main supervision loop: launch, wait, restart if needed."""
        try:
            while not self._stop_requested:
                self._process = await self._launch_process()
                self._state.status = WorkloadStatus.RUNNING
                self._state.pid = self._process.pid
                self._state.last_started = datetime.now()
                self._state.run_count += 1

                log.info(
                    "workload started",
                    workload=self.spec.name,
                    pid=self._process.pid,
                    run_count=self._state.run_count,
                )

                run_id = await self._run_history.record_start(
                    self.spec.name, self._process.pid
                )

                # Wait for process to finish, with optional timeout
                try:
                    if self.spec.timeout_seconds:
                        await asyncio.wait_for(
                            self._process.wait(), timeout=self.spec.timeout_seconds
                        )
                    else:
                        await self._process.wait()
                except asyncio.TimeoutError:
                    log.warning(
                        "workload timed out",
                        workload=self.spec.name,
                        timeout=self.spec.timeout_seconds,
                    )
                    self._process.kill()
                    await self._process.wait()

                exit_code = self._process.returncode or 0
                error_msg = None

                if exit_code != 0:
                    stderr_data = await self._process.stderr.read()
                    error_msg = stderr_data.decode().strip()[-500:] if stderr_data else None
                    self._state.last_error = error_msg
                    log.warning(
                        "workload exited with error",
                        workload=self.spec.name,
                        exit_code=exit_code,
                        error=error_msg,
                    )
                else:
                    log.info(
                        "workload exited cleanly",
                        workload=self.spec.name,
                        exit_code=exit_code,
                    )

                await self._run_history.record_finish(run_id, exit_code, error_msg)

                if self._stop_requested:
                    break

                if self._strategy.is_complete(self.spec, self._state.run_count):
                    self._state.status = WorkloadStatus.COMPLETED
                    log.info("workload completed all runs", workload=self.spec.name)
                    break

                if self._strategy.should_restart(
                    self.spec, self._state.run_count, exit_code
                ):
                    log.info(
                        "restarting workload",
                        workload=self.spec.name,
                        delay=self.spec.restart_delay_seconds,
                    )
                    await asyncio.sleep(self.spec.restart_delay_seconds)
                else:
                    break

        except asyncio.CancelledError:
            pass
        except Exception:
            self._state.status = WorkloadStatus.FAILED
            log.exception("workload supervision error", workload=self.spec.name)
        finally:
            self._process = None
