"""Tests for logging configuration."""

from pathlib import Path

import structlog

from master_control.logging_config import (
    configure_logging,
    configure_worker_logging,
    get_logger,
)


class TestConfigureLogging:
    def test_configure_default(self):
        configure_logging()
        # Should not raise, structlog should be configured
        log = structlog.get_logger()
        assert log is not None

    def test_configure_with_log_dir(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        configure_logging(log_dir=log_dir)
        assert log_dir.exists()

    def test_configure_with_level(self):
        configure_logging(level="DEBUG")
        # Should not raise


class TestGetLogger:
    def test_basic_logger(self):
        configure_logging()
        log = get_logger()
        assert log is not None

    def test_logger_with_workload(self):
        configure_logging()
        log = get_logger(workload_name="test-wl")
        assert log is not None

    def test_logger_with_extra_kwargs(self):
        configure_logging()
        log = get_logger(workload_name="test-wl", component="scheduler")
        assert log is not None


class TestConfigureWorkerLogging:
    def test_configure_worker(self):
        configure_worker_logging("test-worker")
        # Should not raise

    def test_configure_worker_with_log_file(self, tmp_path: Path):
        log_file = tmp_path / "worker.log"
        configure_worker_logging("test-worker", log_file=log_file)
        # Log file parent should exist (it already does since tmp_path exists)

    def test_configure_worker_creates_parent_dirs(self, tmp_path: Path):
        log_file = tmp_path / "deep" / "nested" / "worker.log"
        configure_worker_logging("test-worker", log_file=log_file)
        assert log_file.parent.exists()
