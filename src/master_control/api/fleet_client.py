"""HTTP client for proxying commands from the central API to client daemons."""

from __future__ import annotations

import httpx
import structlog

from master_control.api.models import CommandResponse

log = structlog.get_logger()


class FleetClient:
    """Sends commands to client HTTP APIs on behalf of the central server."""

    def __init__(self, api_token: str | None = None, timeout: float = 15.0) -> None:
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        response = await self._client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def _base_url(self, host: str, port: int) -> str:
        return f"http://{host}:{port}"

    async def list_workloads(self, host: str, port: int) -> dict:
        return await self._request("GET", f"{self._base_url(host, port)}/api/list")

    async def get_status(self, host: str, port: int, name: str) -> dict:
        return await self._request(
            "GET", f"{self._base_url(host, port)}/api/status/{name}"
        )

    async def start_workload(
        self, host: str, port: int, name: str
    ) -> CommandResponse:
        data = await self._request(
            "POST", f"{self._base_url(host, port)}/api/start/{name}"
        )
        return CommandResponse(**data)

    async def stop_workload(self, host: str, port: int, name: str) -> CommandResponse:
        data = await self._request(
            "POST", f"{self._base_url(host, port)}/api/stop/{name}"
        )
        return CommandResponse(**data)

    async def restart_workload(
        self, host: str, port: int, name: str
    ) -> CommandResponse:
        data = await self._request(
            "POST", f"{self._base_url(host, port)}/api/restart/{name}"
        )
        return CommandResponse(**data)

    async def health_check(self, host: str, port: int) -> dict:
        return await self._request("GET", f"{self._base_url(host, port)}/api/health")

    async def reload_configs(self, host: str, port: int) -> dict:
        return await self._request("POST", f"{self._base_url(host, port)}/api/reload")

    async def get_logs(
        self, host: str, port: int, name: str, lines: int = 50
    ) -> dict:
        return await self._request(
            "GET",
            f"{self._base_url(host, port)}/api/logs/{name}",
            params={"lines": lines},
        )
