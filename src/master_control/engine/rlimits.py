"""Resource limits — builds preexec_fn for subprocess memory and CPU constraints."""

from __future__ import annotations

from collections.abc import Callable

import structlog

log = structlog.get_logger()


def make_preexec_fn(
    memory_limit_mb: int | None = None,
    cpu_nice: int | None = None,
) -> Callable[[], None] | None:
    """Return a preexec_fn that sets resource limits in the child process.

    Returns None if no limits are configured.
    """
    if memory_limit_mb is None and cpu_nice is None:
        return None

    def _apply_limits() -> None:
        import os
        import resource

        if memory_limit_mb is not None:
            limit_bytes = memory_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

        if cpu_nice is not None:
            os.nice(cpu_nice)

    return _apply_limits
