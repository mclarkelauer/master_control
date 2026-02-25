"""Jinja2 config templating — renders workload YAML with variable substitution.

Supports three variable sources (in priority order):
  1. Inline ``vars:`` block at the top level of the YAML file
  2. Shared ``vars.yaml`` / ``vars.yml`` in the config directory
  3. OS environment variables via ``{{ env.VAR_NAME }}``
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError


def render_template(raw_text: str, context: dict[str, Any] | None = None) -> str:
    """Render a YAML string as a Jinja2 template.

    The template has access to:
      - Any keys from *context*
      - ``env`` dict containing ``os.environ``
    """
    env = Environment(undefined=StrictUndefined)
    template_context: dict[str, Any] = {"env": dict(os.environ)}
    if context:
        template_context.update(context)

    template = env.from_string(raw_text)
    return template.render(template_context)


def load_vars_file(config_dir: Path) -> dict[str, Any]:
    """Load shared variables from ``vars.yaml`` / ``vars.yml`` if present."""
    for name in ("vars.yaml", "vars.yml"):
        path = config_dir / name
        if path.exists():
            data = yaml.safe_load(path.read_text())
            if isinstance(data, dict):
                return data
    return {}


def has_template_syntax(text: str) -> bool:
    """Fast check for Jinja2 syntax markers."""
    return "{{" in text or "{%" in text


def extract_inline_vars(raw_data: dict) -> tuple[dict[str, Any], dict]:
    """Extract and remove a top-level ``vars`` key from parsed YAML.

    Returns ``(vars_dict, remaining_data)``.
    """
    data = dict(raw_data)
    inline_vars = data.pop("vars", {})
    if not isinstance(inline_vars, dict):
        inline_vars = {}
    return inline_vars, data


def extract_vars_from_text(raw_text: str) -> dict[str, Any]:
    """Extract the top-level ``vars:`` block from raw YAML text.

    This works even when the rest of the file contains Jinja2 syntax that
    would make the full document invalid YAML, because it isolates the
    ``vars:`` block by finding where the next top-level key begins.
    """
    lines = raw_text.splitlines()
    in_vars = False
    vars_lines: list[str] = []

    for line in lines:
        stripped = line.rstrip()
        if not in_vars:
            if stripped == "vars:":
                in_vars = True
                vars_lines.append(stripped)
            continue

        # Still inside vars block — collect indented lines and blank lines.
        if stripped == "" or line[0] in (" ", "\t"):
            vars_lines.append(stripped)
        else:
            # Reached a new top-level key — stop.
            break

    if not vars_lines:
        return {}

    try:
        data = yaml.safe_load("\n".join(vars_lines))
    except yaml.YAMLError:
        return {}

    if isinstance(data, dict):
        return data.get("vars", {}) if isinstance(data.get("vars"), dict) else {}
    return {}
