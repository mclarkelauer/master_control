"""Tests for the plugin system."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from master_control.models.workload import RunMode, WorkloadSpec
from master_control.plugins.protocols import (
    HealthCheckPlugin,
    LogProcessorPlugin,
    WorkloadTypePlugin,
)
from master_control.plugins.registry import BUILTIN_WORKLOAD_TYPES, PluginRegistry


# --- Mock plugins for testing ---


class MockWorkloadTypePlugin:
    name = "container"

    def validate_config(self, params: dict[str, Any]) -> None:
        if "image" not in params:
            raise ValueError("'image' param is required for container type")

    def build_launch_command(self, spec: WorkloadSpec) -> list[str]:
        image = spec.params.get("image", "python:3.12")
        return ["docker", "run", "--rm", image, "python", "-m", spec.module_path]


class MockHealthCheckPlugin:
    name = "http_check"

    async def check(self, state) -> dict[str, Any]:
        return {"healthy": True, "details": "mock check passed"}


class MockLogProcessorPlugin:
    name = "json_shipper"

    async def process(self, workload_name: str, line: str) -> str | None:
        return f"[{workload_name}] {line}"


# --- Protocol conformance ---


class TestProtocolConformance:
    def test_workload_type_protocol(self) -> None:
        plugin = MockWorkloadTypePlugin()
        assert isinstance(plugin, WorkloadTypePlugin)

    def test_health_check_protocol(self) -> None:
        plugin = MockHealthCheckPlugin()
        assert isinstance(plugin, HealthCheckPlugin)

    def test_log_processor_protocol(self) -> None:
        plugin = MockLogProcessorPlugin()
        assert isinstance(plugin, LogProcessorPlugin)


# --- PluginRegistry ---


class TestPluginRegistry:
    def test_empty_registry(self) -> None:
        registry = PluginRegistry()
        assert registry.workload_types == {}
        assert registry.health_checks == {}
        assert registry.log_processors == {}

    def test_known_workload_types_builtin_only(self) -> None:
        registry = PluginRegistry()
        assert registry.known_workload_types() == BUILTIN_WORKLOAD_TYPES

    def test_register_workload_type(self) -> None:
        registry = PluginRegistry()
        plugin = MockWorkloadTypePlugin()
        registry.register_workload_type(plugin)
        assert "container" in registry.workload_types
        assert registry.get_workload_type("container") is plugin

    def test_known_workload_types_with_plugin(self) -> None:
        registry = PluginRegistry()
        registry.register_workload_type(MockWorkloadTypePlugin())
        types = registry.known_workload_types()
        assert "container" in types
        assert "agent" in types
        assert "script" in types
        assert "service" in types

    def test_get_workload_type_missing(self) -> None:
        registry = PluginRegistry()
        assert registry.get_workload_type("nonexistent") is None

    def test_register_health_check(self) -> None:
        registry = PluginRegistry()
        plugin = MockHealthCheckPlugin()
        registry.register_health_check(plugin)
        assert "http_check" in registry.health_checks

    def test_register_log_processor(self) -> None:
        registry = PluginRegistry()
        plugin = MockLogProcessorPlugin()
        registry.register_log_processor(plugin)
        assert "json_shipper" in registry.log_processors

    def test_discover_with_no_plugins(self) -> None:
        registry = PluginRegistry()
        # Should not raise even when no plugins are installed.
        registry.discover()
        assert registry.workload_types == {}

    def test_discover_loads_entry_points(self) -> None:
        registry = PluginRegistry()

        mock_ep = MagicMock()
        mock_ep.name = "container"
        mock_ep.load.return_value = MockWorkloadTypePlugin

        with patch("master_control.plugins.registry.importlib.metadata.entry_points") as mock_eps:
            mock_eps.return_value = []
            # First two calls return empty, third returns our mock.
            def side_effect(group=""):
                if group == "master_control.workload_types":
                    return [mock_ep]
                return []
            mock_eps.side_effect = side_effect

            registry.discover()

        assert "container" in registry.workload_types

    def test_discover_handles_load_failure(self) -> None:
        registry = PluginRegistry()

        mock_ep = MagicMock()
        mock_ep.name = "broken"
        mock_ep.load.side_effect = ImportError("module not found")

        with patch("master_control.plugins.registry.importlib.metadata.entry_points") as mock_eps:
            def side_effect(group=""):
                if group == "master_control.workload_types":
                    return [mock_ep]
                return []
            mock_eps.side_effect = side_effect

            # Should not raise — just log warning.
            registry.discover()

        assert "broken" not in registry.workload_types


# --- WorkloadTypePlugin behavior ---


class TestWorkloadTypePluginBehavior:
    def test_validate_config_passes(self) -> None:
        plugin = MockWorkloadTypePlugin()
        plugin.validate_config({"image": "python:3.12"})

    def test_validate_config_fails(self) -> None:
        plugin = MockWorkloadTypePlugin()
        with pytest.raises(ValueError, match="image"):
            plugin.validate_config({})

    def test_build_launch_command(self) -> None:
        plugin = MockWorkloadTypePlugin()
        spec = WorkloadSpec(
            name="test",
            workload_type="container",
            run_mode=RunMode.FOREVER,
            module_path="agents.test",
            params={"image": "myapp:latest"},
        )
        cmd = plugin.build_launch_command(spec)
        assert cmd == [
            "docker", "run", "--rm", "myapp:latest", "python", "-m", "agents.test"
        ]

    def test_build_launch_command_empty_falls_back(self) -> None:
        """A plugin returning [] means 'use the default launcher'."""

        class PassthroughPlugin:
            name = "passthrough"

            def validate_config(self, params: dict[str, Any]) -> None:
                pass

            def build_launch_command(self, spec: WorkloadSpec) -> list[str]:
                return []

        plugin = PassthroughPlugin()
        spec = WorkloadSpec(
            name="test",
            workload_type="passthrough",
            run_mode=RunMode.FOREVER,
            module_path="agents.test",
        )
        assert plugin.build_launch_command(spec) == []


# --- HealthCheckPlugin behavior ---


class TestHealthCheckPluginBehavior:
    async def test_check_returns_health_status(self) -> None:
        plugin = MockHealthCheckPlugin()
        result = await plugin.check(MagicMock())
        assert result["healthy"] is True


# --- LogProcessorPlugin behavior ---


class TestLogProcessorPluginBehavior:
    async def test_process_transforms_line(self) -> None:
        plugin = MockLogProcessorPlugin()
        result = await plugin.process("my_workload", "hello world")
        assert result == "[my_workload] hello world"
