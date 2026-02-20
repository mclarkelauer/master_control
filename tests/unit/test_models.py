"""Tests for core data models: WorkloadEvent, WorkloadSpec, WorkloadState, enums."""

from datetime import datetime

from master_control.models.events import WorkloadEvent
from master_control.models.workload import (
    RunMode,
    WorkloadSpec,
    WorkloadState,
    WorkloadStatus,
    WorkloadType,
)


class TestWorkloadType:
    def test_values(self):
        assert WorkloadType.AGENT == "agent"
        assert WorkloadType.SCRIPT == "script"
        assert WorkloadType.SERVICE == "service"

    def test_from_string(self):
        assert WorkloadType("agent") is WorkloadType.AGENT


class TestRunMode:
    def test_values(self):
        assert RunMode.SCHEDULE == "schedule"
        assert RunMode.FOREVER == "forever"
        assert RunMode.N_TIMES == "n_times"


class TestWorkloadStatus:
    def test_values(self):
        assert WorkloadStatus.REGISTERED == "registered"
        assert WorkloadStatus.STARTING == "starting"
        assert WorkloadStatus.RUNNING == "running"
        assert WorkloadStatus.STOPPING == "stopping"
        assert WorkloadStatus.STOPPED == "stopped"
        assert WorkloadStatus.FAILED == "failed"
        assert WorkloadStatus.COMPLETED == "completed"

    def test_all_members(self):
        assert len(WorkloadStatus) == 7


class TestWorkloadSpec:
    def test_minimal_spec(self):
        spec = WorkloadSpec(
            name="test",
            workload_type=WorkloadType.AGENT,
            run_mode=RunMode.SCHEDULE,
            module_path="agents.test",
        )
        assert spec.name == "test"
        assert spec.entry_point == "run"
        assert spec.schedule is None
        assert spec.max_runs is None
        assert spec.params == {}
        assert spec.restart_delay_seconds == 5.0
        assert spec.timeout_seconds is None
        assert spec.tags == []

    def test_full_spec(self):
        spec = WorkloadSpec(
            name="full",
            workload_type=WorkloadType.SERVICE,
            run_mode=RunMode.FOREVER,
            module_path="agents.svc",
            entry_point="start",
            schedule="*/5 * * * *",
            max_runs=10,
            params={"key": "value"},
            restart_delay_seconds=2.0,
            timeout_seconds=30.0,
            tags=["prod", "critical"],
        )
        assert spec.entry_point == "start"
        assert spec.max_runs == 10
        assert spec.params == {"key": "value"}
        assert spec.tags == ["prod", "critical"]

    def test_is_frozen(self):
        spec = WorkloadSpec(
            name="frozen",
            workload_type=WorkloadType.AGENT,
            run_mode=RunMode.SCHEDULE,
            module_path="agents.test",
        )
        try:
            spec.name = "changed"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass


class TestWorkloadState:
    def _make_spec(self):
        return WorkloadSpec(
            name="test",
            workload_type=WorkloadType.AGENT,
            run_mode=RunMode.SCHEDULE,
            module_path="agents.test",
        )

    def test_defaults(self):
        state = WorkloadState(spec=self._make_spec())
        assert state.status == WorkloadStatus.REGISTERED
        assert state.pid is None
        assert state.run_count == 0
        assert state.last_started is None
        assert state.last_stopped is None
        assert state.last_heartbeat is None
        assert state.last_error is None

    def test_mutable(self):
        state = WorkloadState(spec=self._make_spec())
        state.status = WorkloadStatus.RUNNING
        state.pid = 12345
        state.run_count = 3
        now = datetime.now()
        state.last_started = now
        assert state.status == WorkloadStatus.RUNNING
        assert state.pid == 12345
        assert state.run_count == 3
        assert state.last_started == now


class TestWorkloadEvent:
    def test_minimal_event(self):
        event = WorkloadEvent(workload_name="test", event_type="started")
        assert event.workload_name == "test"
        assert event.event_type == "started"
        assert event.payload == {}
        assert isinstance(event.timestamp, datetime)

    def test_event_with_payload(self):
        event = WorkloadEvent(
            workload_name="svc",
            event_type="failed",
            payload={"error": "timeout"},
        )
        assert event.payload == {"error": "timeout"}

    def test_is_frozen(self):
        event = WorkloadEvent(workload_name="test", event_type="started")
        try:
            event.workload_name = "changed"
            assert False, "Should have raised FrozenInstanceError"
        except AttributeError:
            pass
