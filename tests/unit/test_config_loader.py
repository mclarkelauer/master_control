from pathlib import Path

import pytest

from master_control.config.loader import ConfigError, ConfigLoader
from master_control.models.workload import RunMode, WorkloadType


class TestConfigLoader:
    def test_load_single_agent(self, fixtures_dir: Path) -> None:
        loader = ConfigLoader(fixtures_dir)
        specs = loader.load_file(fixtures_dir / "valid_agent.yaml")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "data_collector"
        assert spec.workload_type == WorkloadType.AGENT
        assert spec.run_mode == RunMode.SCHEDULE
        assert spec.schedule == "*/5 * * * *"
        assert spec.params["batch_size"] == 100
        assert spec.timeout_seconds == 300
        assert "data" in spec.tags

    def test_load_single_service(self, fixtures_dir: Path) -> None:
        specs = ConfigLoader(fixtures_dir).load_file(fixtures_dir / "valid_service.yaml")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "web_watcher"
        assert spec.workload_type == WorkloadType.SERVICE
        assert spec.run_mode == RunMode.FOREVER
        assert spec.restart_delay_seconds == 10

    def test_load_single_script(self, fixtures_dir: Path) -> None:
        specs = ConfigLoader(fixtures_dir).load_file(fixtures_dir / "valid_script.yaml")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "report_generator"
        assert spec.run_mode == RunMode.N_TIMES
        assert spec.max_runs == 3

    def test_load_multi_workload(self, fixtures_dir: Path) -> None:
        specs = ConfigLoader(fixtures_dir).load_file(fixtures_dir / "valid_multi.yaml")
        assert len(specs) == 2
        assert specs[0].name == "agent_a"
        assert specs[1].name == "agent_b"

    def test_invalid_missing_schedule(self, fixtures_dir: Path) -> None:
        with pytest.raises(ConfigError, match="Validation error"):
            ConfigLoader(fixtures_dir).load_file(
                fixtures_dir / "invalid_missing_schedule.yaml"
            )

    def test_invalid_missing_name(self, fixtures_dir: Path) -> None:
        with pytest.raises(ConfigError, match="Validation error"):
            ConfigLoader(fixtures_dir).load_file(fixtures_dir / "invalid_missing_name.yaml")

    def test_load_all(self, fixtures_dir: Path, tmp_path: Path) -> None:
        # Copy only valid configs to a temp dir
        for name in ("valid_agent.yaml", "valid_service.yaml", "valid_script.yaml"):
            (tmp_path / name).write_text((fixtures_dir / name).read_text())
        specs = ConfigLoader(tmp_path).load_all()
        assert len(specs) == 3
        names = {s.name for s in specs}
        assert names == {"data_collector", "web_watcher", "report_generator"}

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="does not exist"):
            ConfigLoader(tmp_path / "nope").load_all()

    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        (tmp_path / "empty.yaml").write_text("")
        specs = ConfigLoader(tmp_path).load_all()
        assert specs == []
