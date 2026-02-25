"""Plugin registry — discovers and holds plugin instances via entry points."""

from __future__ import annotations

import importlib.metadata

import structlog

from master_control.plugins.protocols import (
    HealthCheckPlugin,
    LogProcessorPlugin,
    WorkloadTypePlugin,
)

log = structlog.get_logger()

BUILTIN_WORKLOAD_TYPES = frozenset({"agent", "script", "service"})

ENTRY_POINT_GROUPS = {
    "workload_types": "master_control.workload_types",
    "health_checks": "master_control.health_checks",
    "log_processors": "master_control.log_processors",
}


class PluginRegistry:
    """Discovers, validates, and stores plugin instances."""

    def __init__(self) -> None:
        self.workload_types: dict[str, WorkloadTypePlugin] = {}
        self.health_checks: dict[str, HealthCheckPlugin] = {}
        self.log_processors: dict[str, LogProcessorPlugin] = {}

    def discover(self) -> None:
        """Load all plugins from installed package entry points."""
        for kind, group in ENTRY_POINT_GROUPS.items():
            eps = importlib.metadata.entry_points(group=group)
            for ep in eps:
                try:
                    plugin_cls = ep.load()
                    plugin = plugin_cls()
                    target = getattr(self, kind)
                    target[plugin.name] = plugin
                    log.info("plugin loaded", kind=kind, name=plugin.name)
                except Exception:
                    log.exception(
                        "failed to load plugin", kind=kind, entry_point=ep.name
                    )

    def register_workload_type(self, plugin: WorkloadTypePlugin) -> None:
        """Manually register a workload type plugin (useful for testing)."""
        self.workload_types[plugin.name] = plugin

    def register_health_check(self, plugin: HealthCheckPlugin) -> None:
        """Manually register a health check plugin."""
        self.health_checks[plugin.name] = plugin

    def register_log_processor(self, plugin: LogProcessorPlugin) -> None:
        """Manually register a log processor plugin."""
        self.log_processors[plugin.name] = plugin

    def get_workload_type(self, name: str) -> WorkloadTypePlugin | None:
        """Look up a workload type plugin by name."""
        return self.workload_types.get(name)

    def known_workload_types(self) -> set[str]:
        """Return all valid workload type names (built-in + plugins)."""
        return BUILTIN_WORKLOAD_TYPES | set(self.workload_types.keys())
