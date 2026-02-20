from datetime import datetime
from pathlib import Path

import pytest

from master_control.db.connection import Database
from master_control.db.repository import RunHistoryRepo, WorkloadStateRepo


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def run_repo(db: Database) -> RunHistoryRepo:
    return RunHistoryRepo(db)


@pytest.fixture
def state_repo(db: Database) -> WorkloadStateRepo:
    return WorkloadStateRepo(db)


async def _seed_workload(state_repo: WorkloadStateRepo, name: str) -> None:
    """Insert a workload_state row so FK constraints are satisfied."""
    await state_repo.save_state(
        name=name, workload_type="agent", run_mode="forever", status="running"
    )


class TestRunHistoryRepo:
    async def test_record_start_and_finish(
        self, run_repo: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        await _seed_workload(state_repo, "test_agent")
        run_id = await run_repo.record_start("test_agent", pid=1234)
        assert run_id is not None
        assert run_id > 0

        await run_repo.record_finish(run_id, exit_code=0)

        history = await run_repo.get_history("test_agent")
        assert len(history) == 1
        record = history[0]
        assert record.workload_name == "test_agent"
        assert record.exit_code == 0
        assert record.finished_at is not None
        assert record.duration_ms is not None
        assert record.duration_ms >= 0

    async def test_record_finish_with_error(
        self, run_repo: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        await _seed_workload(state_repo, "failing_agent")
        run_id = await run_repo.record_start("failing_agent", pid=5678)
        await run_repo.record_finish(run_id, exit_code=1, error_message="Crashed")

        history = await run_repo.get_history("failing_agent")
        assert len(history) == 1
        assert history[0].exit_code == 1
        assert history[0].error_message == "Crashed"

    async def test_get_history_limit(
        self, run_repo: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        await _seed_workload(state_repo, "agent")
        for _ in range(5):
            run_id = await run_repo.record_start("agent", pid=100)
            await run_repo.record_finish(run_id, exit_code=0)

        history = await run_repo.get_history("agent", limit=3)
        assert len(history) == 3

    async def test_get_history_empty(self, run_repo: RunHistoryRepo) -> None:
        history = await run_repo.get_history("nonexistent")
        assert history == []

    async def test_unfinished_run(
        self, run_repo: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        await _seed_workload(state_repo, "agent")
        await run_repo.record_start("agent", pid=100)
        history = await run_repo.get_history("agent")
        assert len(history) == 1
        assert history[0].finished_at is None
        assert history[0].exit_code is None


class TestWorkloadStateRepo:
    async def test_save_and_load(self, state_repo: WorkloadStateRepo) -> None:
        now = datetime.now()
        await state_repo.save_state(
            name="test_agent",
            workload_type="agent",
            run_mode="forever",
            status="running",
            pid=1234,
            run_count=5,
            last_started=now,
        )

        states = await state_repo.load_all_states()
        assert len(states) == 1
        state = states[0]
        assert state["name"] == "test_agent"
        assert state["status"] == "running"
        assert state["pid"] == 1234
        assert state["run_count"] == 5

    async def test_upsert(self, state_repo: WorkloadStateRepo) -> None:
        await state_repo.save_state(
            name="agent", workload_type="agent", run_mode="forever", status="running"
        )
        await state_repo.save_state(
            name="agent", workload_type="agent", run_mode="forever", status="stopped"
        )

        states = await state_repo.load_all_states()
        assert len(states) == 1
        assert states[0]["status"] == "stopped"

    async def test_delete_state(self, state_repo: WorkloadStateRepo) -> None:
        await state_repo.save_state(
            name="agent", workload_type="agent", run_mode="forever", status="running"
        )
        await state_repo.delete_state("agent")
        states = await state_repo.load_all_states()
        assert len(states) == 0

    async def test_load_empty(self, state_repo: WorkloadStateRepo) -> None:
        states = await state_repo.load_all_states()
        assert states == []
