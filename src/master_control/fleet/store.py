"""Fleet state store — persists client heartbeats and fleet status centrally."""

from __future__ import annotations

from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import aiosqlite

from master_control.api.models import (
    ClientOverview,
    HeartbeatPayload,
    SystemMetrics,
    WorkloadInfo,
)


class FleetDatabase:
    """Async SQLite connection for the fleet state database."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        schema_sql = resources.files("master_control.fleet").joinpath("schema.sql").read_text()
        await self._conn.executescript(schema_sql)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("FleetDatabase not connected. Call connect() first.")
        return self._conn


class FleetStateStore:
    """Repository for fleet client state, backed by SQLite."""

    def __init__(self, db: FleetDatabase) -> None:
        self._db = db

    async def upsert_heartbeat(self, payload: HeartbeatPayload, host: str) -> None:
        """Store a heartbeat from a client, updating client and workload records."""
        now = datetime.now().isoformat()
        conn = self._db.conn

        await conn.execute(
            """INSERT INTO fleet_clients
                   (name, host, api_port, status, last_seen,
                    cpu_percent, memory_used_mb, memory_total_mb,
                    disk_used_gb, disk_total_gb, updated_at)
               VALUES (?, ?, ?, 'online', ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   host = excluded.host,
                   status = 'online',
                   last_seen = excluded.last_seen,
                   cpu_percent = excluded.cpu_percent,
                   memory_used_mb = excluded.memory_used_mb,
                   memory_total_mb = excluded.memory_total_mb,
                   disk_used_gb = excluded.disk_used_gb,
                   disk_total_gb = excluded.disk_total_gb,
                   updated_at = excluded.updated_at""",
            (
                payload.client_name,
                host,
                9100,  # default, could come from inventory
                now,
                payload.system.cpu_percent,
                payload.system.memory_used_mb,
                payload.system.memory_total_mb,
                payload.system.disk_used_gb,
                payload.system.disk_total_gb,
                now,
            ),
        )

        # Upsert workload records
        for wl in payload.workloads:
            await conn.execute(
                """INSERT INTO fleet_workloads
                       (client_name, workload_name, workload_type, run_mode,
                        status, pid, run_count, last_started, last_error, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(client_name, workload_name) DO UPDATE SET
                       workload_type = excluded.workload_type,
                       run_mode = excluded.run_mode,
                       status = excluded.status,
                       pid = excluded.pid,
                       run_count = excluded.run_count,
                       last_started = excluded.last_started,
                       last_error = excluded.last_error,
                       updated_at = excluded.updated_at""",
                (
                    payload.client_name,
                    wl.name,
                    wl.type,
                    wl.run_mode,
                    wl.status,
                    wl.pid,
                    wl.run_count,
                    wl.last_started,
                    wl.last_error,
                    now,
                ),
            )

        # Remove workloads no longer reported by this client
        reported_names = {wl.name for wl in payload.workloads}
        if reported_names:
            placeholders = ",".join("?" for _ in reported_names)
            await conn.execute(
                f"""DELETE FROM fleet_workloads
                    WHERE client_name = ? AND workload_name NOT IN ({placeholders})""",
                (payload.client_name, *reported_names),
            )
        else:
            await conn.execute(
                "DELETE FROM fleet_workloads WHERE client_name = ?",
                (payload.client_name,),
            )

        await conn.commit()

    async def list_clients(self) -> list[ClientOverview]:
        """Return overview of all known clients."""
        conn = self._db.conn
        rows = await conn.execute_fetchall(
            """SELECT c.*,
                      COUNT(w.id) as workload_count,
                      SUM(CASE WHEN w.status = 'running' THEN 1 ELSE 0 END) as workloads_running,
                      SUM(CASE WHEN w.status = 'failed' THEN 1 ELSE 0 END) as workloads_failed
               FROM fleet_clients c
               LEFT JOIN fleet_workloads w ON w.client_name = c.name
               GROUP BY c.name
               ORDER BY c.name"""
        )
        return [self._row_to_client_overview(row) for row in rows]

    async def get_client(self, name: str) -> ClientOverview | None:
        """Return overview of a single client."""
        conn = self._db.conn
        cursor = await conn.execute(
            """SELECT c.*,
                      COUNT(w.id) as workload_count,
                      SUM(CASE WHEN w.status = 'running' THEN 1 ELSE 0 END) as workloads_running,
                      SUM(CASE WHEN w.status = 'failed' THEN 1 ELSE 0 END) as workloads_failed
               FROM fleet_clients c
               LEFT JOIN fleet_workloads w ON w.client_name = c.name
               WHERE c.name = ?
               GROUP BY c.name""",
            (name,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_client_overview(row)

    async def get_workloads(self, client_name: str) -> list[WorkloadInfo]:
        """Return all workloads for a specific client."""
        conn = self._db.conn
        cursor = await conn.execute(
            """SELECT workload_name, workload_type, run_mode, status,
                      pid, run_count, last_started, last_error
               FROM fleet_workloads
               WHERE client_name = ?
               ORDER BY workload_name""",
            (client_name,),
        )
        rows = await cursor.fetchall()
        return [
            WorkloadInfo(
                name=row["workload_name"],
                type=row["workload_type"],
                run_mode=row["run_mode"],
                status=row["status"],
                pid=row["pid"],
                run_count=row["run_count"],
                last_started=row["last_started"],
                last_error=row["last_error"],
            )
            for row in rows
        ]

    async def get_workload(
        self, client_name: str, workload_name: str
    ) -> WorkloadInfo | None:
        """Return a single workload for a specific client."""
        conn = self._db.conn
        cursor = await conn.execute(
            """SELECT workload_name, workload_type, run_mode, status,
                      pid, run_count, last_started, last_error
               FROM fleet_workloads
               WHERE client_name = ? AND workload_name = ?""",
            (client_name, workload_name),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return WorkloadInfo(
            name=row["workload_name"],
            type=row["workload_type"],
            run_mode=row["run_mode"],
            status=row["status"],
            pid=row["pid"],
            run_count=row["run_count"],
            last_started=row["last_started"],
            last_error=row["last_error"],
        )

    async def mark_stale_clients(self, threshold_seconds: float) -> int:
        """Mark clients as offline if their last heartbeat exceeds the threshold."""
        conn = self._db.conn
        cutoff = (datetime.now() - timedelta(seconds=threshold_seconds)).isoformat()
        cursor = await conn.execute(
            """UPDATE fleet_clients SET status = 'offline', updated_at = datetime('now')
               WHERE status = 'online' AND last_seen < ?""",
            (cutoff,),
        )
        await conn.commit()
        return cursor.rowcount

    async def resolve_client_endpoint(self, name: str) -> tuple[str, int] | None:
        """Return (host, api_port) for a client, or None if not found."""
        conn = self._db.conn
        cursor = await conn.execute(
            "SELECT host, api_port FROM fleet_clients WHERE name = ?",
            (name,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return (row["host"], row["api_port"])

    @staticmethod
    def _row_to_client_overview(row: aiosqlite.Row) -> ClientOverview:
        last_seen = None
        if row["last_seen"]:
            last_seen = datetime.fromisoformat(row["last_seen"])

        system = None
        if row["cpu_percent"] is not None:
            system = SystemMetrics(
                cpu_percent=row["cpu_percent"],
                memory_used_mb=row["memory_used_mb"] or 0,
                memory_total_mb=row["memory_total_mb"] or 0,
                disk_used_gb=row["disk_used_gb"] or 0,
                disk_total_gb=row["disk_total_gb"] or 0,
            )

        return ClientOverview(
            name=row["name"],
            host=row["host"],
            api_port=row["api_port"],
            status=row["status"],
            last_seen=last_seen,
            workload_count=row["workload_count"],
            workloads_running=row["workloads_running"] or 0,
            workloads_failed=row["workloads_failed"] or 0,
            system=system,
        )
