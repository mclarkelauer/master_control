"""Client-side FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response

from master_control.api.client_routes import router

if TYPE_CHECKING:
    from master_control.engine.orchestrator import Orchestrator


def create_client_app(
    orchestrator: Orchestrator, api_token: str | None = None
) -> FastAPI:
    """Create the client HTTP API application.

    Args:
        orchestrator: The running Orchestrator instance.
        api_token: Optional bearer token for authentication. If None, auth is disabled.
    """
    app = FastAPI(title="Master Control Client API", docs_url=None, redoc_url=None)
    app.state.orchestrator = orchestrator

    if api_token:

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next) -> Response:
            # Allow health checks without auth
            if request.url.path == "/api/health":
                return await call_next(request)
            auth_header = request.headers.get("Authorization", "")
            if auth_header != f"Bearer {api_token}":
                return Response(
                    content='{"detail":"Unauthorized"}',
                    status_code=401,
                    media_type="application/json",
                )
            return await call_next(request)

    app.include_router(router)
    return app
