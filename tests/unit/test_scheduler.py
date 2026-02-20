import asyncio

import pytest

from master_control.engine.scheduler import ScheduleManager


class TestScheduleManager:
    def test_add_valid_cron(self) -> None:
        sm = ScheduleManager()

        async def noop() -> None:
            pass

        sm.add("test", "* * * * *", noop)
        assert "test" in sm.entries
        assert sm.entries["test"].next_run is not None

    def test_add_invalid_cron_raises(self) -> None:
        sm = ScheduleManager()

        async def noop() -> None:
            pass

        with pytest.raises(ValueError, match="Invalid cron"):
            sm.add("test", "not a cron", noop)

    def test_remove(self) -> None:
        sm = ScheduleManager()

        async def noop() -> None:
            pass

        sm.add("test", "* * * * *", noop)
        sm.remove("test")
        assert "test" not in sm.entries

    def test_remove_nonexistent_is_noop(self) -> None:
        sm = ScheduleManager()
        sm.remove("nope")  # Should not raise

    async def test_callback_fires(self) -> None:
        sm = ScheduleManager()
        fired = []

        async def callback() -> None:
            fired.append(True)

        # Use every-minute cron, but we'll manipulate next_run to trigger immediately
        sm.add("test", "* * * * *", callback)
        from datetime import datetime, timedelta

        sm.entries["test"].next_run = datetime.now() - timedelta(seconds=1)

        await sm.start()
        await asyncio.sleep(1.5)
        await sm.stop()

        assert len(fired) >= 1

    async def test_stop(self) -> None:
        sm = ScheduleManager()
        await sm.start()
        await sm.stop()
        # Should complete without error
