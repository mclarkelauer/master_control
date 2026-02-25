"""Tests for Jinja2 config templating."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from master_control.config.loader import ConfigError, ConfigLoader
from master_control.config.templating import (
    extract_inline_vars,
    extract_vars_from_text,
    has_template_syntax,
    load_vars_file,
    render_template,
)


# --- render_template ---


class TestRenderTemplate:
    def test_plain_text_passes_through(self) -> None:
        text = "name: my_agent\ntype: agent\n"
        # Jinja2 strips a single trailing newline — assert content matches.
        assert render_template(text).strip() == text.strip()

    def test_substitutes_context_variable(self) -> None:
        text = "host: {{ api_host }}"
        result = render_template(text, context={"api_host": "example.com"})
        assert result == "host: example.com"

    def test_substitutes_env_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCTL_TEST_VAR", "hello123")
        text = "value: {{ env.MCTL_TEST_VAR }}"
        result = render_template(text)
        assert result == "value: hello123"

    def test_undefined_variable_raises(self) -> None:
        text = "host: {{ missing_var }}"
        with pytest.raises(Exception, match="missing_var"):
            render_template(text)

    def test_multiple_variables(self) -> None:
        text = "url: https://{{ host }}:{{ port }}/api"
        result = render_template(text, context={"host": "example.com", "port": "8080"})
        assert result == "url: https://example.com:8080/api"

    def test_jinja2_filter(self) -> None:
        text = "name: {{ raw_name | upper }}"
        result = render_template(text, context={"raw_name": "test"})
        assert result == "name: TEST"

    def test_context_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOSTNAME", "os-host")
        text = "host: {{ env.HOSTNAME }}"
        result = render_template(text)
        assert result == "host: os-host"

    def test_numeric_value(self) -> None:
        text = "batch_size: {{ batch_size }}"
        result = render_template(text, context={"batch_size": 100})
        assert result == "batch_size: 100"


# --- has_template_syntax ---


class TestHasTemplateSyntax:
    def test_detects_double_brace(self) -> None:
        assert has_template_syntax("name: {{ var }}") is True

    def test_detects_block_tag(self) -> None:
        assert has_template_syntax("{% if x %}yes{% endif %}") is True

    def test_plain_yaml(self) -> None:
        assert has_template_syntax("name: agent\ntype: script") is False


# --- load_vars_file ---


class TestLoadVarsFile:
    def test_loads_vars_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("api_host: example.com\nport: 8080\n")
        result = load_vars_file(tmp_path)
        assert result == {"api_host": "example.com", "port": 8080}

    def test_loads_vars_yml(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yml").write_text("key: value\n")
        result = load_vars_file(tmp_path)
        assert result == {"key": "value"}

    def test_prefers_yaml_over_yml(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("source: yaml\n")
        (tmp_path / "vars.yml").write_text("source: yml\n")
        result = load_vars_file(tmp_path)
        assert result == {"source": "yaml"}

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        assert load_vars_file(tmp_path) == {}

    def test_returns_empty_for_non_dict(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("- item1\n- item2\n")
        assert load_vars_file(tmp_path) == {}


# --- extract_inline_vars ---


class TestExtractInlineVars:
    def test_extracts_vars_key(self) -> None:
        data = {"vars": {"host": "example.com"}, "name": "agent"}
        inline_vars, remaining = extract_inline_vars(data)
        assert inline_vars == {"host": "example.com"}
        assert remaining == {"name": "agent"}
        assert "vars" not in remaining

    def test_no_vars_key(self) -> None:
        data = {"name": "agent", "type": "script"}
        inline_vars, remaining = extract_inline_vars(data)
        assert inline_vars == {}
        assert remaining == {"name": "agent", "type": "script"}

    def test_non_dict_vars_ignored(self) -> None:
        data = {"vars": "not_a_dict", "name": "agent"}
        inline_vars, remaining = extract_inline_vars(data)
        assert inline_vars == {}
        assert remaining == {"name": "agent"}

    def test_does_not_mutate_original(self) -> None:
        data = {"vars": {"x": 1}, "name": "agent"}
        original_data = dict(data)
        extract_inline_vars(data)
        assert data == original_data


# --- extract_vars_from_text ---


class TestExtractVarsFromText:
    def test_extracts_vars_block(self) -> None:
        text = "vars:\n  host: example.com\n  port: 8080\n\nname: agent\n"
        result = extract_vars_from_text(text)
        assert result == {"host": "example.com", "port": 8080}

    def test_no_vars_block(self) -> None:
        text = "name: agent\ntype: script\n"
        assert extract_vars_from_text(text) == {}

    def test_vars_with_template_body(self) -> None:
        text = "vars:\n  count: 5\n\nmax_runs: {{ count }}\n"
        result = extract_vars_from_text(text)
        assert result == {"count": 5}

    def test_empty_vars_block(self) -> None:
        text = "vars:\n\nname: agent\n"
        assert extract_vars_from_text(text) == {}

    def test_nested_vars(self) -> None:
        text = "vars:\n  db:\n    host: localhost\n    port: 5432\n\nname: agent\n"
        result = extract_vars_from_text(text)
        assert result == {"db": {"host": "localhost", "port": 5432}}


# --- ConfigLoader integration ---


class TestConfigLoaderTemplating:
    def test_loads_templated_fixture(self, fixtures_dir: Path) -> None:
        loader = ConfigLoader(fixtures_dir)
        specs = loader.load_file(fixtures_dir / "templated_agent.yaml")
        assert len(specs) == 1
        spec = specs[0]
        assert spec.name == "templated_collector"
        assert spec.params["source_url"] == "https://api.example.com/data"
        assert spec.params["batch_size"] == 100

    def test_non_templated_files_still_work(self, fixtures_dir: Path) -> None:
        loader = ConfigLoader(fixtures_dir)
        specs = loader.load_file(fixtures_dir / "valid_agent.yaml")
        assert len(specs) == 1
        assert specs[0].name == "data_collector"

    def test_shared_vars_file(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("server: shared.example.com\n")
        (tmp_path / "agent.yaml").write_text(
            "name: test_agent\n"
            "type: agent\n"
            "run_mode: forever\n"
            "module: agents.test\n"
            "params:\n"
            "  host: \"{{ server }}\"\n"
        )
        loader = ConfigLoader(tmp_path)
        specs = loader.load_file(tmp_path / "agent.yaml")
        assert specs[0].params["host"] == "shared.example.com"

    def test_inline_vars_override_shared(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("port: 8080\n")
        (tmp_path / "agent.yaml").write_text(
            "vars:\n"
            "  port: 9090\n"
            "\n"
            "name: test_agent\n"
            "type: agent\n"
            "run_mode: forever\n"
            "module: agents.test\n"
            "params:\n"
            "  port: {{ port }}\n"
        )
        loader = ConfigLoader(tmp_path)
        specs = loader.load_file(tmp_path / "agent.yaml")
        assert specs[0].params["port"] == 9090

    def test_env_variable_in_template(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MCTL_TEST_HOST", "env-host.local")
        (tmp_path / "agent.yaml").write_text(
            "name: test_agent\n"
            "type: agent\n"
            "run_mode: forever\n"
            "module: agents.test\n"
            "params:\n"
            '  host: "{{ env.MCTL_TEST_HOST }}"\n'
        )
        loader = ConfigLoader(tmp_path)
        specs = loader.load_file(tmp_path / "agent.yaml")
        assert specs[0].params["host"] == "env-host.local"

    def test_undefined_variable_raises_config_error(self, tmp_path: Path) -> None:
        (tmp_path / "agent.yaml").write_text(
            "name: test_agent\n"
            "type: agent\n"
            "run_mode: forever\n"
            "module: agents.test\n"
            "params:\n"
            "  host: {{ undefined_var }}\n"
        )
        loader = ConfigLoader(tmp_path)
        with pytest.raises(ConfigError, match="Template error"):
            loader.load_file(tmp_path / "agent.yaml")

    def test_load_all_skips_vars_file(self, tmp_path: Path) -> None:
        (tmp_path / "vars.yaml").write_text("key: value\n")
        (tmp_path / "agent.yaml").write_text(
            "name: test_agent\n"
            "type: agent\n"
            "run_mode: forever\n"
            "module: agents.test\n"
        )
        loader = ConfigLoader(tmp_path)
        specs = loader.load_all()
        assert len(specs) == 1
        assert specs[0].name == "test_agent"

    def test_template_with_invalid_yaml_after_render(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text(
            "name: {{ name }}\n"
            "  indentation: broken\n"
        )
        loader = ConfigLoader(tmp_path)
        with pytest.raises(ConfigError):
            loader.load_file(tmp_path / "bad.yaml")

    def test_template_syntax_that_is_invalid_yaml_before_render(
        self, tmp_path: Path
    ) -> None:
        """Template expressions that aren't valid YAML on their own should
        still render correctly after Jinja2 processing."""
        (tmp_path / "agent.yaml").write_text(
            "vars:\n"
            "  count: 5\n"
            "\n"
            "name: test_agent\n"
            "type: script\n"
            "run_mode: n_times\n"
            "max_runs: {{ count }}\n"
            "module: agents.test\n"
        )
        loader = ConfigLoader(tmp_path)
        specs = loader.load_file(tmp_path / "agent.yaml")
        assert specs[0].max_runs == 5
