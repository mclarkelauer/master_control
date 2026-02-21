"""Orchestrator — central coordinator for all workloads."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import structlog

from master_control.config.loader import ConfigLoader
from master_control.config.registry import WorkloadRegistry
from master_control.db.connection import Database
from master_control.db.repository import RunHistoryRepo, WorkloadStateRepo
from master_control.engine.runner import WorkloadRunner
from master_control.engine.scheduler import ScheduleManager
from master_control.health.checks import HealthChecker
from master_control.logging_config import configure_logging
from master_control.models.workload import RunMode, WorkloadState, WorkloadStatus

log = structlog.get_logger()


class Orchestrator:
    """Central coordinator. Owns the registry, runners, scheduler, and database."""

    def __init__(
        self,
        config_dir: Path,
        db_path: Path,
        log_dir: Path | None = None,
        socket_path: Path | None = None,
        daemon_config: object | None = None,
    ) -> None:
        self.config_dir = config_dir
        self.db_path = db_path
        self.log_dir = log_dir
        self.socket_path = socket_path or Path("/tmp/master_control.sock")
        self._daemon_config = daemon_config
        self._registry = WorkloadRegistry()
        self._db: Database | None = None
        self._run_history: RunHistoryRepo | None = None
        self._state_repo: WorkloadStateRepo | None = None
        self._scheduler = ScheduleManager()
        self._runners: dict[str, WorkloadRunner] = {}
        self._health_checker = HealthChecker(self)
        self._ipc_server: asyncio.Server | None = None
        self._http_server = None
        self._http_task: asyncio.Task | None = None
        self._heartbeat = None
        self._deployed_version: str | None = None

    @property
    def registry(self) -> WorkloadRegistry:
        return self._registry

    @property
    def deployed_version(self) -> str | None:
        return self._deployed_version

    async def start(self) -> None:
        """Boot: load configs, init DB, start all workloads per their run_mode."""
        configure_logging(self.log_dir)
        log.info("orchestrator starting", config_dir=str(self.config_dir))

        # Init database
        self._db = Database(self.db_path)
        await self._db.connect()
        self._run_history = RunHistoryRepo(self._db)
        self._state_repo = WorkloadStateRepo(self._db)

        # Read deployed version if available
        version_file = self.config_dir.parent / ".mctl-version"
        if version_file.exists():
            self._deployed_version = version_file.read_text().strip() or None

        # Load configs
        loader = ConfigLoader(self.config_dir)
        specs = loader.load_all()
        for spec in specs:
            self._registry.register(spec)
        log.info("loaded workloads", count=len(specs))

        # Start all workloads
        for spec in self._registry.list_all():
            await self._start_workload(spec.name)

        # Start scheduler
        await self._scheduler.start()

        # Start health checker
        await self._health_checker.start()

        # Start IPC server
        await self._start_ipc_server()

        # Start fleet HTTP API and heartbeat if configured
        await self._start_fleet_services()

        log.info("orchestrator ready")

    async def shutdown(self) -> None:
        """Graceful shutdown: stop all runners, scheduler, IPC, fleet services, DB."""
        log.info("orchestrator shutting down")

        # Stop fleet services
        await self._stop_fleet_services()

        # Stop IPC server
        if self._ipc_server:
            self._ipc_server.close()
            await self._ipc_server.wait_closed()
            if self.socket_path.exists():
                self.socket_path.unlink()

        # Stop health checker
        await self._health_checker.stop()

        # Stop scheduler
        await self._scheduler.stop()

        # Stop all runners
        stop_tasks = [runner.stop() for runner in self._runners.values()]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Close DB
        if self._db:
            await self._db.close()

        log.info("orchestrator stopped")

    async def start_workload(self, name: str) -> str:
        """Start a specific workload by name. Returns status message."""
        if name not in self._registry:
            return f"Unknown workload: {name}"
        if name in self._runners and self._runners[name].is_running:
            return f"Workload '{name}' is already running"
        await self._start_workload(name)
        return f"Started '{name}'"

    async def stop_workload(self, name: str) -> str:
        """Stop a specific workload by name. Returns status message."""
        runner = self._runners.get(name)
        if not runner or not runner.is_running:
            return f"Workload '{name}' is not running"
        await runner.stop()
        return f"Stopped '{name}'"

    async def restart_workload(self, name: str) -> str:
        """Stop then start a workload."""
        await self.stop_workload(name)
        return await self.start_workload(name)

    def get_status(self, name: str) -> WorkloadState | None:
        """Get the current state of a workload."""
        runner = self._runners.get(name)
        if runner:
            return runner.state
        if name in self._registry:
            return WorkloadState(spec=self._registry.get(name))
        return None

    def list_workloads(self) -> list[WorkloadState]:
        """List states for all registered workloads."""
        states = []
        for spec in self._registry.list_all():
            runner = self._runners.get(spec.name)
            if runner:
                states.append(runner.state)
            else:
                states.append(WorkloadState(spec=spec))
        return states

    async def reload_configs(self) -> dict:
        """Re-read config files and reconcile with running workloads.

        Returns a summary: {added: [...], removed: [...], restarted: [...], unchanged: [...]}.
        """
        loader = ConfigLoader(self.config_dir)
        new_specs = loader.load_all()
        new_specs_by_name = {s.name: s for s in new_specs}
        old_names = {s.name for s in self._registry.list_all()}
        new_names = set(new_specs_by_name.keys())

        added = sorted(new_names - old_names)
        removed = sorted(old_names - new_names)
        common = old_names & new_names

        restarted = []
        unchanged = []

        # Stop removed workloads
        for name in removed:
            runner = self._runners.get(name)
            if runner and runner.is_running:
                await runner.stop()
            self._runners.pop(name, None)
            self._scheduler.remove(name)
            self._registry.unregister(name)
            log.info("workload removed", workload=name)

        # Start new workloads
        for name in added:
            self._registry.register(new_specs_by_name[name])
            await self._start_workload(name)
            log.info("workload added", workload=name)

        # Check for changes in existing workloads
        for name in sorted(common):
            old_spec = self._registry.get(name)
            new_spec = new_specs_by_name[name]
            if old_spec != new_spec:
                runner = self._runners.get(name)
                if runner and runner.is_running:
                    await runner.stop()
                self._runners.pop(name, None)
                self._scheduler.remove(name)
                self._registry.unregister(name)
                self._registry.register(new_spec)
                await self._start_workload(name)
                restarted.append(name)
                log.info("workload restarted (config changed)", workload=name)
            else:
                unchanged.append(name)

        # Re-read version file in case it changed
        version_file = self.config_dir.parent / ".mctl-version"
        if version_file.exists():
            self._deployed_version = version_file.read_text().strip() or None

        result = {
            "added": added,
            "removed": removed,
            "restarted": restarted,
            "unchanged": unchanged,
        }
        log.info("configs reloaded", **result)
        return result

    async def _start_workload(self, name: str) -> None:
        """Internal: create a runner and start it."""
        spec = self._registry.get(name)

        # Save initial state
        if self._state_repo:
            await self._state_repo.save_state(
                name=spec.name,
                workload_type=spec.workload_type,
                run_mode=spec.run_mode,
                status=WorkloadStatus.STARTING,
            )

        runner = WorkloadRunner(spec, self._run_history, self.log_dir)
        self._runners[name] = runner

        if spec.run_mode == RunMode.SCHEDULE:
            # Register with scheduler instead of starting immediately
            self._scheduler.add(
                name,
                spec.schedule,
                lambda n=name: self._run_scheduled(n),
            )
            log.info("workload scheduled", workload=name, cron=spec.schedule)
        else:
            await runner.start()

    async def _run_scheduled(self, name: str) -> None:
        """Callback for scheduled workloads: run once."""
        runner = self._runners.get(name)
        if runner and runner.is_running:
            log.warning("skipping scheduled run, still running", workload=name)
            return
        spec = self._registry.get(name)
        runner = WorkloadRunner(spec, self._run_history, self.log_dir)
        self._runners[name] = runner
        await runner.start()

    # --- Fleet HTTP API & Heartbeat ---

    async def _start_fleet_services(self) -> None:
        """Start the client HTTP API and heartbeat reporter if fleet is enabled."""
        if not self._daemon_config:
            return

        fleet_config = getattr(self._daemon_config, "fleet", None)
        if not fleet_config or not fleet_config.enabled:
            return

        try:
            import uvicorn

            from master_control.api.client_app import create_client_app

            app = create_client_app(self, fleet_config.api_token)
            config = uvicorn.Config(
                app,
                host=fleet_config.api_host,
                port=fleet_config.api_port,
                log_level="warning",
            )
            self._http_server = uvicorn.Server(config)
            self._http_task = asyncio.create_task(self._http_server.serve())
            log.info(
                "fleet http api started",
                host=fleet_config.api_host,
                port=fleet_config.api_port,
            )
        except ImportError:
            log.warning("fleet http api requires 'fastapi' and 'uvicorn' — skipping")
            return

        # Start heartbeat reporter if central_api_url is set
        if fleet_config.central_api_url:
            try:
                from master_control.fleet.heartbeat import HeartbeatReporter

                self._heartbeat = HeartbeatReporter(self, fleet_config)
                await self._heartbeat.start()
            except ImportError:
                log.warning("heartbeat reporter requires 'httpx' — skipping")

    async def _stop_fleet_services(self) -> None:
        """Stop the HTTP API server and heartbeat reporter."""
        if self._heartbeat:
            await self._heartbeat.stop()
            self._heartbeat = None

        if self._http_server:
            self._http_server.should_exit = True
            if self._http_task and not self._http_task.done():
                try:
                    await asyncio.wait_for(self._http_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._http_task.cancel()
            self._http_server = None
            self._http_task = None

    # --- IPC Server ---

    async def _start_ipc_server(self) -> None:
        """Start a Unix domain socket server for CLI communication."""
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._ipc_server = await asyncio.start_unix_server(
            self._handle_ipc_client, path=str(self.socket_path)
        )
        log.info("ipc server listening", socket=str(self.socket_path))

    async def _handle_ipc_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single IPC client connection."""
        try:
            data = await reader.readline()
            if not data:
                return

            request = json.loads(data.decode())
            response = await self._handle_ipc_command(request)
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except Exception as e:
            error_resp = {"error": str(e)}
            writer.write(json.dumps(error_resp).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_ipc_command(self, request: dict) -> dict:
        """Dispatch an IPC command and return a response dict."""
        cmd = request.get("command")
        name = request.get("name")

        if cmd == "list":
            states = self.list_workloads()
            return {
                "workloads": [
                    {
                        "name": s.spec.name,
                        "type": s.spec.workload_type.value,
                        "run_mode": s.spec.run_mode.value,
                        "status": s.status.value,
                        "pid": s.pid,
                        "run_count": s.run_count,
                        "last_started": s.last_started.isoformat() if s.last_started else None,
                        "last_error": s.last_error,
                    }
                    for s in states
                ]
            }

        if cmd == "status" and name:
            state = self.get_status(name)
            if not state:
                return {"error": f"Unknown workload: {name}"}
            return {
                "name": state.spec.name,
                "type": state.spec.workload_type.value,
                "run_mode": state.spec.run_mode.value,
                "status": state.status.value,
                "pid": state.pid,
                "run_count": state.run_count,
                "last_started": state.last_started.isoformat() if state.last_started else None,
                "last_stopped": state.last_stopped.isoformat() if state.last_stopped else None,
                "last_error": state.last_error,
                "schedule": state.spec.schedule,
                "max_runs": state.spec.max_runs,
                "module": state.spec.module_path,
                "entry_point": state.spec.entry_point,
                "tags": state.spec.tags,
            }

        if cmd == "start" and name:
            msg = await self.start_workload(name)
            return {"message": msg}

        if cmd == "stop" and name:
            msg = await self.stop_workload(name)
            return {"message": msg}

        if cmd == "restart" and name:
            msg = await self.restart_workload(name)
            return {"message": msg}

        if cmd == "reload":
            result = await self.reload_configs()
            return {"changes": result}

        if cmd == "shutdown":
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.create_task(self.shutdown())
            )
            return {"message": "Shutting down"}

        return {"error": f"Unknown command: {cmd}"}
