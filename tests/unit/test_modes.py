"""Tests for run mode strategies."""

import pytest

from master_control.engine.modes import (
    ForeverStrategy,
    NTimesStrategy,
    ScheduleStrategy,
    get_strategy,
)
from master_control.models.workload import RunMode, WorkloadSpec, WorkloadType


def _make_spec(**kwargs):
    defaults = dict(
        name="test",
        workload_type=WorkloadType.AGENT,
        run_mode=RunMode.SCHEDULE,
        module_path="agents.test",
    )
    defaults.update(kwargs)
    return WorkloadSpec(**defaults)


class TestForeverStrategy:
    def test_should_always_restart(self):
        strategy = ForeverStrategy()
        spec = _make_spec(run_mode=RunMode.FOREVER)
        assert strategy.should_restart(spec, run_count=0, exit_code=0) is True
        assert strategy.should_restart(spec, run_count=100, exit_code=1) is True

    def test_never_complete(self):
        strategy = ForeverStrategy()
        spec = _make_spec(run_mode=RunMode.FOREVER)
        assert strategy.is_complete(spec, run_count=0) is False
        assert strategy.is_complete(spec, run_count=999) is False


class TestNTimesStrategy:
    def test_restart_until_max(self):
        strategy = NTimesStrategy()
        spec = _make_spec(run_mode=RunMode.N_TIMES, max_runs=3)
        assert strategy.should_restart(spec, run_count=1, exit_code=0) is True
        assert strategy.should_restart(spec, run_count=2, exit_code=0) is True
        assert strategy.should_restart(spec, run_count=3, exit_code=0) is False

    def test_complete_at_max(self):
        strategy = NTimesStrategy()
        spec = _make_spec(run_mode=RunMode.N_TIMES, max_runs=3)
        assert strategy.is_complete(spec, run_count=2) is False
        assert strategy.is_complete(spec, run_count=3) is True
        assert strategy.is_complete(spec, run_count=4) is True

    def test_defaults_to_one_when_no_max_runs(self):
        strategy = NTimesStrategy()
        spec = _make_spec(run_mode=RunMode.N_TIMES)
        assert strategy.should_restart(spec, run_count=1, exit_code=0) is False
        assert strategy.is_complete(spec, run_count=1) is True


class TestScheduleStrategy:
    def test_never_restart(self):
        strategy = ScheduleStrategy()
        spec = _make_spec()
        assert strategy.should_restart(spec, run_count=1, exit_code=0) is False

    def test_always_complete(self):
        strategy = ScheduleStrategy()
        spec = _make_spec()
        assert strategy.is_complete(spec, run_count=0) is True
        assert strategy.is_complete(spec, run_count=1) is True


class TestGetStrategy:
    def test_returns_forever(self):
        assert isinstance(get_strategy("forever"), ForeverStrategy)

    def test_returns_n_times(self):
        assert isinstance(get_strategy("n_times"), NTimesStrategy)

    def test_returns_schedule(self):
        assert isinstance(get_strategy("schedule"), ScheduleStrategy)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown run mode"):
            get_strategy("invalid")
