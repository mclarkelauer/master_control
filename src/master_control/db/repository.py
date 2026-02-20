from dataclasses import dataclass
from datetime import datetime

from master_control.db.connection import Database


@dataclass
class RunRecord:
    id: int
    workload_name: str
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    error_message: str | None
    duration_ms: int | None


class RunHistoryRepo:
    """CRUD for the run_history table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record_start(self, workload_name: str, pid: int) -> int:
        now = datetime.now().isoformat()
        cursor = await self._db.execute(
            "INSERT INTO run_history (workload_name, started_at) VALUES (?, ?)",
            (workload_name, now),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def record_finish(
        self, run_id: int, exit_code: int, error_message: str | None = None
    ) -> None:
        now = datetime.now().isoformat()
        await self._db.execute(
            """UPDATE run_history
               SET finished_at = ?, exit_code = ?, error_message = ?,
                   duration_ms = CAST(
                       (julianday(?) - julianday(started_at)) * 86400000 AS INTEGER
                   )
               WHERE id = ?""",
            (now, exit_code, error_message, now, run_id),
        )
        await self._db.commit()

    async def get_history(
        self, workload_name: str, limit: int = 50
    ) -> list[RunRecord]:
        rows = await self._db.fetchall(
            """SELECT id, workload_name, started_at, finished_at,
                      exit_code, error_message, duration_ms
               FROM run_history
               WHERE workload_name = ?
               ORDER BY started_at DESC
               LIMIT ?""",
            (workload_name, limit),
        )
        return [
            RunRecord(
                id=row["id"],
                workload_name=row["workload_name"],
                started_at=datetime.fromisoformat(row["started_at"]),
                finished_at=(
                    datetime.fromisoformat(row["finished_at"])
                    if row["finished_at"]
                    else None
                ),
                exit_code=row["exit_code"],
                error_message=row["error_message"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]


class WorkloadStateRepo:
    """Persists WorkloadState snapshots for recovery after restart."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_state(
        self,
        name: str,
        workload_type: str,
        run_mode: str,
        status: str,
        pid: int | None = None,
        run_count: int = 0,
        max_runs: int | None = None,
        last_started: datetime | None = None,
        last_stopped: datetime | None = None,
        last_heartbeat: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        await self._db.execute(
            """INSERT INTO workload_state
                   (name, workload_type, run_mode, status, pid, run_count, max_runs,
                    last_started, last_stopped, last_heartbeat, last_error, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   status = excluded.status,
                   pid = excluded.pid,
                   run_count = excluded.run_count,
                   last_started = excluded.last_started,
                   last_stopped = excluded.last_stopped,
                   last_heartbeat = excluded.last_heartbeat,
                   last_error = excluded.last_error,
                   updated_at = excluded.updated_at""",
            (
                name,
                workload_type,
                run_mode,
                status,
                pid,
                run_count,
                max_runs,
                last_started.isoformat() if last_started else None,
                last_stopped.isoformat() if last_stopped else None,
                last_heartbeat.isoformat() if last_heartbeat else None,
                last_error,
                now,
            ),
        )
        await self._db.commit()

    async def load_all_states(self) -> list[dict]:
        rows = await self._db.fetchall("SELECT * FROM workload_state")
        return [dict(row) for row in rows]

    async def delete_state(self, name: str) -> None:
        await self._db.execute("DELETE FROM workload_state WHERE name = ?", (name,))
        await self._db.commit()
