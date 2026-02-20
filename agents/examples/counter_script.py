"""Example script that counts and exits."""

import structlog

log = structlog.get_logger()


def run(output_dir: str = "/tmp/reports", **kwargs: object) -> None:
    log.info("counter_script starting", output_dir=output_dir)
    for i in range(1, 6):
        log.info("counting", value=i)
    log.info("counter_script finished")
