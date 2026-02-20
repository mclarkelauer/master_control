"""IPC client for CLI-to-orchestrator communication via Unix domain socket."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

DEFAULT_SOCKET_PATH = Path("/tmp/master_control.sock")


class IPCError(Exception):
    pass


async def send_command(
    command: dict,
    socket_path: Path = DEFAULT_SOCKET_PATH,
    timeout: float = 10.0,
) -> dict:
    """Send a JSON command to the orchestrator and return the response."""
    if not socket_path.exists():
        raise IPCError(
            "Orchestrator is not running. Start it with: master-control up"
        )

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(str(socket_path)),
            timeout=timeout,
        )
    except (ConnectionRefusedError, FileNotFoundError) as e:
        raise IPCError(
            "Cannot connect to orchestrator. Start it with: master-control up"
        ) from e

    try:
        writer.write(json.dumps(command).encode() + b"\n")
        await writer.drain()

        data = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not data:
            raise IPCError("Empty response from orchestrator")

        return json.loads(data.decode())
    finally:
        writer.close()
        await writer.wait_closed()
