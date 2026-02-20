"""Example agent that logs a greeting and exits."""

import structlog

log = structlog.get_logger()


def run(source_url: str = "https://example.com", batch_size: int = 10, **kwargs: object) -> None:
    log.info("hello_agent starting", source_url=source_url, batch_size=batch_size)
    log.info("hello_agent collected data", items=batch_size)
    log.info("hello_agent finished")
