from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from master_control.config.schema import (
    DaemonConfig,
    MultiWorkloadConfig,
    WorkloadConfig,
)
from master_control.models.workload import WorkloadSpec


class ConfigError(Exception):
    """Raised when config loading or validation fails."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


class ConfigLoader:
    """Reads YAML config files from a directory, validates them, and returns WorkloadSpecs."""

    DAEMON_CONFIG_NAMES = {"daemon.yaml", "daemon.yml"}

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def load_all(self) -> list[WorkloadSpec]:
        """Load all .yaml/.yml files from the config directory (recursively).

        Skips daemon.yaml (fleet/central config) and inventory files.
        """
        if not self.config_dir.is_dir():
            raise ConfigError(self.config_dir, "Config directory does not exist")

        specs: list[WorkloadSpec] = []
        for path in sorted(self.config_dir.rglob("*.y*ml")):
            if path.suffix not in (".yaml", ".yml"):
                continue
            if path.name in self.DAEMON_CONFIG_NAMES:
                continue
            if path.name in ("inventory.yaml", "inventory.yml"):
                continue
            specs.extend(self.load_file(path))
        return specs

    def load_file(self, path: Path) -> list[WorkloadSpec]:
        """Load and validate a single YAML config file. Returns one or more WorkloadSpecs."""
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise ConfigError(path, f"Invalid YAML: {e}") from e

        if raw is None:
            return []

        if not isinstance(raw, dict):
            raise ConfigError(path, "Expected a YAML mapping at top level")

        try:
            if "workloads" in raw:
                multi = MultiWorkloadConfig.model_validate(raw)
                return [wc.to_spec() for wc in multi.workloads]
            else:
                single = WorkloadConfig.model_validate(raw)
                return [single.to_spec()]
        except ValidationError as e:
            raise ConfigError(path, f"Validation error: {e}") from e

    def load_daemon_config(self) -> DaemonConfig:
        """Load daemon.yaml from the config directory. Returns defaults if not found."""
        for name in self.DAEMON_CONFIG_NAMES:
            path = self.config_dir / name
            if path.exists():
                try:
                    raw = yaml.safe_load(path.read_text())
                except yaml.YAMLError as e:
                    raise ConfigError(path, f"Invalid YAML: {e}") from e
                if raw is None:
                    return DaemonConfig()
                try:
                    return DaemonConfig.model_validate(raw)
                except ValidationError as e:
                    raise ConfigError(path, f"Validation error: {e}") from e
        return DaemonConfig()
