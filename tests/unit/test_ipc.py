"""Tests for the IPC client."""

import pytest
from pathlib import Path

from master_control.engine.ipc import IPCError, send_command


class TestIPCClient:
    async def test_raises_when_socket_missing(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.sock"
        with pytest.raises(IPCError, match="not running"):
            await send_command({"command": "list"}, socket_path=missing)
