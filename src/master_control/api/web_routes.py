"""Web dashboard routes — server-side rendered fleet management UI."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def create_web_router(templates: Jinja2Templates) -> APIRouter:
    """Create the web UI router with server-side rendered pages."""
    router = APIRouter(default_response_class=HTMLResponse)

    def _context(request: Request, **extra) -> dict:
        config = getattr(request.app.state, "config", None)
        token = config.api_token if config else None
        return {"request": request, "api_token": token, **extra}

    @router.get("/")
    async def fleet_overview(request: Request):
        return templates.TemplateResponse("index.html", _context(request))

    @router.get("/clients/{client_name}")
    async def client_detail(request: Request, client_name: str):
        return templates.TemplateResponse(
            "client_detail.html", _context(request, client_name=client_name)
        )

    @router.get("/deployments")
    async def deployments_list(request: Request):
        return templates.TemplateResponse("deployments.html", _context(request))

    @router.get("/deployments/{deployment_id}")
    async def deployment_detail(request: Request, deployment_id: str):
        return templates.TemplateResponse(
            "deployment_detail.html",
            _context(request, deployment_id=deployment_id),
        )

    return router
