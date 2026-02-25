import pytest
from pydantic import ValidationError

from master_control.config.schema import MultiWorkloadConfig, WorkloadConfig
from master_control.models.workload import RunMode, WorkloadType


class TestWorkloadConfig:
    def test_valid_scheduled_agent(self) -> None:
        config = WorkloadConfig(
            name="test_agent",
            type="agent",
            run_mode="schedule",
            schedule="*/5 * * * *",
            module="agents.test",
        )
        assert config.name == "test_agent"
        spec = config.to_spec()
        assert spec.workload_type == WorkloadType.AGENT
        assert spec.run_mode == RunMode.SCHEDULE
        assert spec.schedule == "*/5 * * * *"
        assert spec.entry_point == "run"

    def test_valid_forever_service(self) -> None:
        config = WorkloadConfig(
            name="my_service",
            type="service",
            run_mode="forever",
            module="agents.service",
            restart_delay=10.0,
        )
        spec = config.to_spec()
        assert spec.workload_type == WorkloadType.SERVICE
        assert spec.run_mode == RunMode.FOREVER
        assert spec.restart_delay_seconds == 10.0

    def test_valid_n_times_script(self) -> None:
        config = WorkloadConfig(
            name="my_script",
            type="script",
            run_mode="n_times",
            max_runs=5,
            module="agents.script",
        )
        spec = config.to_spec()
        assert spec.run_mode == RunMode.N_TIMES
        assert spec.max_runs == 5

    def test_schedule_mode_requires_schedule(self) -> None:
        with pytest.raises(ValidationError, match="schedule.*required"):
            WorkloadConfig(
                name="bad",
                type="agent",
                run_mode="schedule",
                module="agents.test",
            )

    def test_n_times_mode_requires_max_runs(self) -> None:
        with pytest.raises(ValidationError, match="max_runs.*required"):
            WorkloadConfig(
                name="bad",
                type="script",
                run_mode="n_times",
                module="agents.test",
            )

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            WorkloadConfig(
                type="agent",
                run_mode="forever",
                module="agents.test",
            )

    def test_custom_type_accepted(self) -> None:
        """Custom workload types are accepted at the schema level
        (validated against plugin registry at orchestrator startup)."""
        config = WorkloadConfig(
            name="custom_wl",
            type="container",
            run_mode="forever",
            module="agents.test",
        )
        spec = config.to_spec()
        assert spec.workload_type == "container"

    def test_params_and_tags(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            params={"key": "value"},
            tags=["a", "b"],
        )
        spec = config.to_spec()
        assert spec.params == {"key": "value"}
        assert spec.tags == ["a", "b"]

    def test_defaults(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
        )
        assert config.entry_point == "run"
        assert config.restart_delay == 5.0
        assert config.timeout is None
        assert config.params == {}
        assert config.tags == []
        assert config.memory_limit_mb is None
        assert config.cpu_nice is None

    def test_memory_limit_valid(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            memory_limit_mb=128,
        )
        spec = config.to_spec()
        assert spec.memory_limit_mb == 128

    def test_memory_limit_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="memory_limit_mb.*positive"):
            WorkloadConfig(
                name="test",
                type="agent",
                run_mode="forever",
                module="agents.test",
                memory_limit_mb=0,
            )

    def test_memory_limit_negative_raises(self) -> None:
        with pytest.raises(ValidationError, match="memory_limit_mb.*positive"):
            WorkloadConfig(
                name="test",
                type="agent",
                run_mode="forever",
                module="agents.test",
                memory_limit_mb=-10,
            )

    def test_cpu_nice_valid(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            cpu_nice=10,
        )
        spec = config.to_spec()
        assert spec.cpu_nice == 10

    def test_cpu_nice_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError, match="cpu_nice.*-20.*19"):
            WorkloadConfig(
                name="test",
                type="agent",
                run_mode="forever",
                module="agents.test",
                cpu_nice=20,
            )

    def test_cpu_nice_too_low_raises(self) -> None:
        with pytest.raises(ValidationError, match="cpu_nice.*-20.*19"):
            WorkloadConfig(
                name="test",
                type="agent",
                run_mode="forever",
                module="agents.test",
                cpu_nice=-21,
            )

    def test_resource_limits_in_spec(self) -> None:
        config = WorkloadConfig(
            name="test",
            type="agent",
            run_mode="forever",
            module="agents.test",
            memory_limit_mb=256,
            cpu_nice=5,
        )
        spec = config.to_spec()
        assert spec.memory_limit_mb == 256
        assert spec.cpu_nice == 5


class TestMultiWorkloadConfig:
    def test_valid_multi(self) -> None:
        multi = MultiWorkloadConfig(
            workloads=[
                WorkloadConfig(
                    name="a", type="agent", run_mode="forever", module="agents.a"
                ),
                WorkloadConfig(
                    name="b",
                    type="script",
                    run_mode="n_times",
                    max_runs=1,
                    module="agents.b",
                ),
            ]
        )
        assert len(multi.workloads) == 2
