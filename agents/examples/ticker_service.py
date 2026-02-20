"""Example service that ticks forever."""

import time

import structlog

log = structlog.get_logger()


def run(watch_url: str = "https://example.com", interval: int = 5, **kwargs: object) -> None:
    log.info("ticker_service starting", watch_url=watch_url, interval=interval)
    tick = 0
    while True:
        tick += 1
        log.info("tick", count=tick, watch_url=watch_url)
        time.sleep(interval)
