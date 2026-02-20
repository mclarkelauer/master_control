"""Tests for Database async SQLite connection manager."""

import pytest
from pathlib import Path

from master_control.db.connection import Database


class TestDatabase:
    async def test_connect_and_close(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        await db.connect()
        assert db.conn is not None
        await db.close()

    async def test_conn_raises_when_not_connected(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="not connected"):
            _ = db.conn

    async def test_close_when_not_connected(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        # Should not raise
        await db.close()

    async def test_schema_initialized(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        await db.connect()
        try:
            # workload_state and run_history tables should exist
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = [row["name"] for row in rows]
            assert "workload_state" in table_names
            assert "run_history" in table_names
        finally:
            await db.close()

    async def test_wal_mode_enabled(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        await db.connect()
        try:
            row = await db.fetchone("PRAGMA journal_mode")
            assert row[0] == "wal"
        finally:
            await db.close()

    async def test_execute_and_fetchone(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        await db.connect()
        try:
            await db.execute(
                "INSERT INTO workload_state (name, workload_type, run_mode, status) VALUES (?, ?, ?, ?)",
                ("test-wl", "agent", "schedule", "registered"),
            )
            await db.commit()
            row = await db.fetchone(
                "SELECT name, status FROM workload_state WHERE name = ?", ("test-wl",)
            )
            assert row["name"] == "test-wl"
            assert row["status"] == "registered"
        finally:
            await db.close()

    async def test_fetchall(self, tmp_path: Path):
        db = Database(tmp_path / "test.db")
        await db.connect()
        try:
            for name in ["a", "b", "c"]:
                await db.execute(
                    "INSERT INTO workload_state (name, workload_type, run_mode, status) VALUES (?, ?, ?, ?)",
                    (name, "agent", "schedule", "registered"),
                )
            await db.commit()
            rows = await db.fetchall("SELECT name FROM workload_state ORDER BY name")
            assert len(rows) == 3
            assert [row["name"] for row in rows] == ["a", "b", "c"]
        finally:
            await db.close()
