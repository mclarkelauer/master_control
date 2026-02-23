"""Central API application factory — runs on the control host."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from master_control.api.central_routes import router as api_router
from master_control.api.fleet_client import FleetClient
from master_control.config.schema import CentralConfig
from master_control.fleet.deployer import RollingDeployer
from master_control.fleet.store import FleetDatabase, FleetStateStore

log = structlog.get_logger()


def create_central_app(config: CentralConfig) -> FastAPI:
    """Create the central fleet management API application."""
    stale_task: asyncio.Task | None = None
    mdns_advertiser = None
    mdns_browser = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal stale_task, mdns_advertiser, mdns_browser
        # Initialize fleet database
        db = FleetDatabase(Path(config.db_path))
        await db.connect()
        app.state.fleet_db = db
        app.state.fleet_store = FleetStateStore(db)
        app.state.fleet_client = FleetClient(api_token=config.api_token)

        # Initialize rolling deployer
        deploy_script = (
            Path(config.deploy_script_path)
            if config.deploy_script_path
            else (Path(__file__).parent.parent.parent.parent / "scripts" / "deploy-clients.sh")
        )
        app.state.deployer = RollingDeployer(
            fleet_store=app.state.fleet_store,
            fleet_client=app.state.fleet_client,
            deploy_script_path=deploy_script,
            inventory_path=Path(config.inventory_path),
        )

        # Start stale-client detection background task
        async def check_stale():
            while True:
                try:
                    await asyncio.sleep(config.stale_threshold_seconds / 2)
                    count = await app.state.fleet_store.mark_stale_clients(
                        config.stale_threshold_seconds
                    )
                    if count > 0:
                        log.info("marked clients offline", count=count)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning("stale check error", error=str(e))

        stale_task = asyncio.create_task(check_stale())

        # Start mDNS discovery if enabled
        if config.mdns_enabled:
            try:
                from master_control.fleet.discovery import (
                    CENTRAL_SERVICE_TYPE,
                    CLIENT_SERVICE_TYPE,
                    ServiceAdvertiser,
                    ServiceDiscovery,
                )

                # Advertise the central API so clients can find us.
                props = {"token_required": str(bool(config.api_token)).lower()}
                mdns_advertiser = ServiceAdvertiser(
                    service_type=CENTRAL_SERVICE_TYPE,
                    name="mctl-central",
                    port=config.port,
                    properties=props,
                )
                await mdns_advertiser.start()

                # Browse for client services and auto-register them.
                store = app.state.fleet_store

                def _on_client_found(
                    name: str, host: str, port: int, properties: dict[str, str]
                ) -> None:
                    asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: asyncio.create_task(
                            store.register_discovered_client(name, host, port)
                        )
                    )

                mdns_browser = ServiceDiscovery(
                    service_type=CLIENT_SERVICE_TYPE,
                    on_found=_on_client_found,
                )
                await mdns_browser.start()
            except ImportError:
                log.warning("mdns discovery requires 'zeroconf' — skipping")

        yield

        # Cleanup
        if mdns_browser:
            await mdns_browser.stop()
        if mdns_advertiser:
            await mdns_advertiser.stop()
        if stale_task and not stale_task.done():
            stale_task.cancel()
            try:
                await stale_task
            except asyncio.CancelledError:
                pass
        await app.state.fleet_client.close()
        await db.close()

    app = FastAPI(title="Master Control Central", lifespan=lifespan)
    app.state.config = config

    # Auth middleware
    if config.api_token:

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next) -> Response:
            # Allow heartbeats and web pages without extra auth considerations
            # (heartbeat has its own token in payload, web uses same token)
            path = request.url.path
            if path.startswith("/api/"):
                auth_header = request.headers.get("Authorization", "")
                if auth_header != f"Bearer {config.api_token}":
                    return Response(
                        content='{"detail":"Unauthorized"}',
                        status_code=401,
                        media_type="application/json",
                    )
            return await call_next(request)

    # Mount API routes
    app.include_router(api_router)

    # Mount web UX routes (lazy import to avoid errors if templates don't exist yet)
    try:
        from master_control.api.web_routes import create_web_router

        templates_dir = Path(__file__).parent.parent / "templates"
        static_dir = Path(__file__).parent.parent / "static"

        if templates_dir.exists():
            templates = Jinja2Templates(directory=str(templates_dir))
            app.include_router(create_web_router(templates))

        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    except ImportError:
        pass

    return app
