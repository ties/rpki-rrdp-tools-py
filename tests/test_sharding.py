from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from rrdp_tools.sharding import Shard, daily_log_file, resolve_output_dir

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


class TestResolveOutputDir:
    def test_none_returns_base_dir(self):
        assert resolve_output_dir(Path("/data"), Shard.NONE, NOW) == Path("/data")

    def test_year_month(self):
        assert resolve_output_dir(Path("/data"), Shard.YEAR_MONTH, NOW) == Path(
            "/data/2026/08"
        )

    def test_month_is_zero_padded(self):
        january = NOW.replace(month=1)
        assert resolve_output_dir(Path("/data"), Shard.YEAR_MONTH, january) == Path(
            "/data/2026/01"
        )

    def test_uses_the_utc_date_of_an_offset_datetime(self):
        """Late on the 31st in +02:00 is already the next month in UTC."""
        # 2026-09-01 00:30 +02:00 == 2026-08-31 22:30 UTC
        offset = datetime(2026, 9, 1, 0, 30, tzinfo=timezone(timedelta(hours=2)))
        assert resolve_output_dir(
            Path("/data"), Shard.YEAR_MONTH, offset.astimezone(UTC)
        ) == Path("/data/2026/08")


class TestDailyLogFile:
    def test_name(self):
        assert daily_log_file(Path("/data/2026/08"), NOW) == Path(
            "/data/2026/08/20260816.log"
        )

    def test_uses_the_utc_date_of_an_offset_datetime(self):
        offset = datetime(2026, 9, 1, 0, 30, tzinfo=timezone(timedelta(hours=2)))
        assert daily_log_file(Path("/data"), offset.astimezone(UTC)) == Path(
            "/data/20260831.log"
        )
