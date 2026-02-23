import asyncio
from pathlib import Path

import pytest

from master_control.db.connection import Database
from master_control.db.repository import RunHistoryRepo, WorkloadStateRepo
from master_control.engine.runner import WorkloadRunner
from master_control.models.workload import RunMode, WorkloadSpec, WorkloadStatus, WorkloadType


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def run_history(db: Database) -> RunHistoryRepo:
    return RunHistoryRepo(db)


@pytest.fixture
def state_repo(db: Database) -> WorkloadStateRepo:
    return WorkloadStateRepo(db)


async def _seed_workload(state_repo: WorkloadStateRepo, name: str) -> None:
    await state_repo.save_state(
        name=name, workload_type="agent", run_mode="forever", status="registered"
    )


def _make_spec(
    name: str = "test_agent",
    run_mode: RunMode = RunMode.FOREVER,
    max_runs: int | None = None,
    restart_delay: float = 0.1,
    timeout: float | None = None,
) -> WorkloadSpec:
    return WorkloadSpec(
        name=name,
        workload_type=WorkloadType.AGENT,
        run_mode=run_mode,
        module_path="agents.examples.hello_agent",
        entry_point="run",
        max_runs=max_runs,
        restart_delay_seconds=restart_delay,
        timeout_seconds=timeout,
    )


class TestWorkloadRunner:
    async def test_n_times_stops_after_n_runs(
        self, run_history: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        spec = _make_spec(name="counter", run_mode=RunMode.N_TIMES, max_runs=3, restart_delay=0.0)
        await _seed_workload(state_repo, "counter")
        runner = WorkloadRunner(spec, run_history)
        await runner.start()

        # Wait for completion
        for _ in range(50):
            if runner.state.status == WorkloadStatus.COMPLETED:
                break
            await asyncio.sleep(0.1)

        assert runner.state.status == WorkloadStatus.COMPLETED
        assert runner.state.run_count == 3

    async def test_schedule_mode_single_run(
        self, run_history: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        spec = _make_spec(name="oneshot", run_mode=RunMode.SCHEDULE)
        await _seed_workload(state_repo, "oneshot")
        runner = WorkloadRunner(spec, run_history)
        await runner.start()

        for _ in range(50):
            if not runner.is_running:
                break
            await asyncio.sleep(0.1)

        assert runner.state.run_count == 1
        assert runner.state.status == WorkloadStatus.COMPLETED

    async def test_stop_running_workload(
        self, run_history: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        spec = _make_spec(
            name="service",
            run_mode=RunMode.FOREVER,
            restart_delay=0.0,
        )
        # Use ticker_service which runs forever
        spec = WorkloadSpec(
            name="service",
            workload_type=WorkloadType.SERVICE,
            run_mode=RunMode.FOREVER,
            module_path="agents.examples.ticker_service",
            entry_point="run",
            params={"interval": 1},
            restart_delay_seconds=0.1,
        )
        await _seed_workload(state_repo, "service")
        runner = WorkloadRunner(spec, run_history)
        await runner.start()

        # Wait for it to be running
        for _ in range(30):
            if runner.state.status == WorkloadStatus.RUNNING:
                break
            await asyncio.sleep(0.1)

        assert runner.state.status == WorkloadStatus.RUNNING
        assert runner.state.pid is not None

        await runner.stop(timeout=5.0)
        assert runner.state.status == WorkloadStatus.STOPPED

    async def test_records_run_history(
        self, run_history: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        spec = _make_spec(name="history_test", run_mode=RunMode.N_TIMES, max_runs=1, restart_delay=0.0)
        await _seed_workload(state_repo, "history_test")
        runner = WorkloadRunner(spec, run_history)
        await runner.start()

        for _ in range(30):
            if runner.state.status == WorkloadStatus.COMPLETED:
                break
            await asyncio.sleep(0.1)

        records = await run_history.get_history("history_test")
        assert len(records) == 1
        assert records[0].exit_code == 0

    async def test_workload_with_resource_limits(
        self, run_history: RunHistoryRepo, state_repo: WorkloadStateRepo
    ) -> None:
        spec = WorkloadSpec(
            name="limited",
            workload_type=WorkloadType.AGENT,
            run_mode=RunMode.N_TIMES,
            module_path="agents.examples.hello_agent",
            entry_point="run",
            max_runs=1,
            restart_delay_seconds=0.0,
            memory_limit_mb=512,
            cpu_nice=10,
        )
        await _seed_workload(state_repo, "limited")
        runner = WorkloadRunner(spec, run_history)
        await runner.start()

        for _ in range(50):
            if runner.state.status == WorkloadStatus.COMPLETED:
                break
            await asyncio.sleep(0.1)

        assert runner.state.status == WorkloadStatus.COMPLETED
        assert runner.state.run_count == 1
