"""Rolling deployer — orchestrates batched deployments across fleet clients."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from master_control.api.models import DeploymentRequest

if TYPE_CHECKING:
    from master_control.api.fleet_client import FleetClient
    from master_control.fleet.store import FleetStateStore

log = structlog.get_logger()


class RollingDeployer:
    """Orchestrates rolling deployments across fleet clients.

    Uses the existing deploy-clients.sh script for file transfer (rsync/SSH)
    and the client HTTP API for config hot-reload and health checks.
    """

    def __init__(
        self,
        fleet_store: FleetStateStore,
        fleet_client: FleetClient,
        deploy_script_path: Path,
        inventory_path: Path,
    ) -> None:
        self._store = fleet_store
        self._fleet_client = fleet_client
        self._deploy_script = deploy_script_path
        self._inventory_path = inventory_path
        self._active: dict[str, asyncio.Task] = {}

    async def start_deployment(self, request: DeploymentRequest) -> str:
        """Create and start a rolling deployment. Returns deployment ID."""
        deployment_id = str(uuid.uuid4())

        # Resolve target clients
        if request.target_clients:
            targets = request.target_clients
        else:
            clients = await self._store.list_clients()
            targets = [c.name for c in clients if c.status == "online"]

        if not targets:
            raise ValueError("No target clients available for deployment")

        # Persist deployment record
        await self._store.create_deployment(
            deployment_id, request.version, targets, request.batch_size
        )

        # Assign batch numbers (single transaction to avoid race with background task)
        batches = self._create_batches(targets, request.batch_size)
        all_clients = [
            (client_name, batch_num)
            for batch_num, batch_clients in enumerate(batches)
            for client_name in batch_clients
        ]
        await self._store.create_deployment_clients(deployment_id, all_clients)

        # Launch as background task
        task = asyncio.create_task(
            self._execute_deployment(deployment_id, request, batches)
        )
        self._active[deployment_id] = task
        return deployment_id

    async def cancel_deployment(self, deployment_id: str) -> None:
        """Cancel an in-progress deployment."""
        task = self._active.get(deployment_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._store.update_deployment_status(
            deployment_id, "failed", error="Cancelled by user"
        )
        self._active.pop(deployment_id, None)

    async def _execute_deployment(
        self,
        deployment_id: str,
        request: DeploymentRequest,
        batches: list[list[str]],
    ) -> None:
        """Execute the rolling deployment batch by batch."""
        await self._store.update_deployment_status(deployment_id, "in_progress")

        try:
            for batch_num, batch_clients in enumerate(batches):
                log.info(
                    "deploying batch",
                    deployment=deployment_id,
                    batch=batch_num,
                    clients=batch_clients,
                )

                # Step 1: Deploy files to this batch (parallel within batch)
                results = await asyncio.gather(
                    *[
                        self._deploy_single_client(
                            deployment_id, name, request.version
                        )
                        for name in batch_clients
                    ],
                    return_exceptions=True,
                )

                # Check for failures
                failed = [
                    name
                    for name, result in zip(batch_clients, results)
                    if isinstance(result, Exception) or result is False
                ]
                if failed:
                    log.error(
                        "batch deploy failed",
                        deployment=deployment_id,
                        failed_clients=failed,
                    )
                    if request.auto_rollback:
                        await self._rollback(deployment_id, batch_num)
                        return
                    await self._store.update_deployment_status(
                        deployment_id,
                        "failed",
                        error=f"Deploy failed for: {', '.join(failed)}",
                    )
                    return

                # Step 2: Tell each client to reload configs
                reload_failed = []
                for name in batch_clients:
                    endpoint = await self._store.resolve_client_endpoint(name)
                    if not endpoint:
                        reload_failed.append(name)
                        continue
                    host, port = endpoint
                    try:
                        await self._fleet_client.reload_configs(host, port)
                        await self._store.update_deployment_client_status(
                            deployment_id, name, "deployed"
                        )
                    except Exception as e:
                        log.warning("reload failed", client=name, error=str(e))
                        await self._store.update_deployment_client_status(
                            deployment_id, name, "failed", error=f"Reload: {e}"
                        )
                        reload_failed.append(name)

                if reload_failed:
                    if request.auto_rollback:
                        await self._rollback(deployment_id, batch_num)
                        return
                    await self._store.update_deployment_status(
                        deployment_id,
                        "failed",
                        error=f"Reload failed for: {', '.join(reload_failed)}",
                    )
                    return

                # Step 3: Wait for health checks to pass
                healthy = await self._wait_for_health(
                    deployment_id,
                    batch_clients,
                    timeout=request.health_check_timeout,
                )
                if not healthy:
                    if request.auto_rollback:
                        await self._rollback(deployment_id, batch_num)
                        return
                    await self._store.update_deployment_status(
                        deployment_id,
                        "failed",
                        error="Health check timeout",
                    )
                    return

                # Mark clients as healthy and update their deployed version
                for name in batch_clients:
                    await self._store.update_deployment_client_status(
                        deployment_id, name, "healthy"
                    )
                    await self._store.update_client_deployed_version(
                        name, request.version
                    )

                log.info(
                    "batch complete",
                    deployment=deployment_id,
                    batch=batch_num,
                )

            await self._store.update_deployment_status(deployment_id, "completed")
            log.info("deployment completed", deployment=deployment_id)

        except asyncio.CancelledError:
            log.warning("deployment cancelled", deployment=deployment_id)
            raise
        except Exception as e:
            log.error("deployment failed", deployment=deployment_id, error=str(e))
            await self._store.update_deployment_status(
                deployment_id, "failed", error=str(e)
            )
        finally:
            self._active.pop(deployment_id, None)

    async def _deploy_single_client(
        self, deployment_id: str, client_name: str, version: str
    ) -> bool:
        """Run the deploy script for a single client. Returns True on success."""
        await self._store.update_deployment_client_status(
            deployment_id, client_name, "deploying"
        )

        # Record previous version for rollback
        client = await self._store.get_client(client_name)
        if client:
            await self._store.set_deployment_client_previous_version(
                deployment_id, client_name, client.deployed_version
            )

        # Invoke the deploy script as subprocess
        cmd = [
            str(self._deploy_script),
            "--client",
            client_name,
            "--inventory",
            str(self._inventory_path),
            "--sync-only",
            "--version",
            version,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()[-500:] or stdout.decode().strip()[-500:]
            log.error(
                "deploy script failed",
                client=client_name,
                exit_code=proc.returncode,
                error=error_msg,
            )
            await self._store.update_deployment_client_status(
                deployment_id, client_name, "failed", error=error_msg
            )
            return False

        return True

    async def _wait_for_health(
        self,
        deployment_id: str,
        client_names: list[str],
        timeout: float,
    ) -> bool:
        """Poll client health endpoints until all pass or timeout expires."""
        deadline = asyncio.get_running_loop().time() + timeout

        while asyncio.get_running_loop().time() < deadline:
            all_healthy = True
            for name in client_names:
                endpoint = await self._store.resolve_client_endpoint(name)
                if not endpoint:
                    all_healthy = False
                    continue
                host, port = endpoint
                try:
                    resp = await self._fleet_client.health_check(host, port)
                    if resp.get("status") != "ok":
                        all_healthy = False
                except Exception:
                    all_healthy = False

            if all_healthy:
                return True
            await asyncio.sleep(5.0)

        return False

    async def _rollback(self, deployment_id: str, failed_batch: int) -> None:
        """Rollback all batches up to and including the failed batch."""
        log.warning(
            "rolling back deployment",
            deployment=deployment_id,
            failed_batch=failed_batch,
        )
        await self._store.update_deployment_status(deployment_id, "rolling_back")

        clients = await self._store.get_deployment_clients(deployment_id)
        to_rollback = [
            c
            for c in clients
            if c.batch_number <= failed_batch
            and c.status in ("deployed", "healthy", "deploying", "failed")
        ]

        for client_status in to_rollback:
            if client_status.previous_version:
                # Re-deploy previous version
                try:
                    cmd = [
                        str(self._deploy_script),
                        "--client",
                        client_status.client_name,
                        "--inventory",
                        str(self._inventory_path),
                        "--sync-only",
                        "--version",
                        client_status.previous_version,
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()

                    # Reload configs on the client
                    endpoint = await self._store.resolve_client_endpoint(
                        client_status.client_name
                    )
                    if endpoint:
                        host, port = endpoint
                        await self._fleet_client.reload_configs(host, port)

                    log.info(
                        "rolled back client",
                        client=client_status.client_name,
                        version=client_status.previous_version,
                    )
                except Exception as e:
                    log.error(
                        "rollback failed for client",
                        client=client_status.client_name,
                        error=str(e),
                    )

            await self._store.update_deployment_client_status(
                deployment_id, client_status.client_name, "rolled_back"
            )

        await self._store.update_deployment_status(deployment_id, "rolled_back")

    @staticmethod
    def _create_batches(clients: list[str], batch_size: int) -> list[list[str]]:
        return [clients[i : i + batch_size] for i in range(0, len(clients), batch_size)]
