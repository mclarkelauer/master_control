import pytest

from master_control.config.registry import WorkloadRegistry
from master_control.models.workload import RunMode, WorkloadSpec, WorkloadType


def _make_spec(name: str = "test") -> WorkloadSpec:
    return WorkloadSpec(
        name=name,
        workload_type=WorkloadType.AGENT,
        run_mode=RunMode.FOREVER,
        module_path="agents.test",
    )


class TestWorkloadRegistry:
    def test_register_and_get(self) -> None:
        reg = WorkloadRegistry()
        spec = _make_spec("foo")
        reg.register(spec)
        assert reg.get("foo") is spec
        assert "foo" in reg
        assert len(reg) == 1

    def test_duplicate_register_raises(self) -> None:
        reg = WorkloadRegistry()
        reg.register(_make_spec("foo"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register(_make_spec("foo"))

    def test_unregister(self) -> None:
        reg = WorkloadRegistry()
        reg.register(_make_spec("foo"))
        reg.unregister("foo")
        assert "foo" not in reg
        assert len(reg) == 0

    def test_unregister_missing_raises(self) -> None:
        reg = WorkloadRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.unregister("nope")

    def test_get_missing_raises(self) -> None:
        reg = WorkloadRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nope")

    def test_list_all(self) -> None:
        reg = WorkloadRegistry()
        reg.register(_make_spec("a"))
        reg.register(_make_spec("b"))
        specs = reg.list_all()
        assert len(specs) == 2
        names = {s.name for s in specs}
        assert names == {"a", "b"}
