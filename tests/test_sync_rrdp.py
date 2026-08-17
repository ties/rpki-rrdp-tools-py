import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from rrdp_tools.sharding import Shard, daily_log_file, resolve_output_dir
from rrdp_tools.sync_rrdp import sync_rrdp_run_command

CONFIG = """\
base_dir = "{base_dir}"
shard = "{shard}"
log_to_file = {log_to_file}

[[repository]]
notification_url = "{url}"
{name}
"""

HOST = "rrdp.ripe.net"


@pytest.fixture(autouse=True)
def restore_logging():
    root = logging.getLogger()
    tools = logging.getLogger("rrdp_tools")
    handlers, root_level, tools_level = root.handlers[:], root.level, tools.level
    yield
    for handler in root.handlers[:]:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(root_level)
    tools.setLevel(tools_level)


@pytest.fixture
def synced(monkeypatch):
    paths: list[Path] = []

    async def fake_snapshot_rrdp(notification_url, output_path, **kwargs):
        paths.append(output_path)

    monkeypatch.setattr("rrdp_tools.sync_rrdp.snapshot_rrdp", fake_snapshot_rrdp)
    return paths


def run(
    tmp_path,
    synced,
    *,
    shard="none",
    log_to_file="false",
    name=None,
    url=f"https://{HOST}/notification.xml",
    **kwargs,
):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        CONFIG.format(
            base_dir=tmp_path,
            shard=shard,
            log_to_file=log_to_file,
            url=url,
            name="" if name is None else f'name = "{name}"',
        )
    )
    result = CliRunner().invoke(sync_rrdp_run_command, [str(config_file)], **kwargs)
    assert result.exit_code == 0, result.output
    return result


class TestSharding:
    def test_no_shard_writes_directly_below_base_dir(self, tmp_path, synced):
        result = run(tmp_path, synced)

        assert synced == [tmp_path / HOST]
        assert "Syncing 1 repositories" in result.stdout
        assert "Sync completed: 1/1 repositories succeeded" in result.stdout
        assert result.stderr == ""

    def test_year_month_shard(self, tmp_path, synced):
        run(tmp_path, synced, shard="year-month")

        expected = resolve_output_dir(tmp_path, Shard.YEAR_MONTH, datetime.now(tz=UTC))
        assert synced == [expected / HOST]
        assert (expected / HOST).is_dir()

    def test_escaping_name_is_rejected_when_sharded(self, tmp_path, synced):
        run(tmp_path, synced, shard="year-month", name="../../../etc")

        assert synced == []
        assert not (tmp_path.parent / "etc").exists()


class TestOutputContainment:
    def test_configured_name_need_not_match_the_hostname(self, tmp_path, synced):
        run(tmp_path, synced, name="ripe")

        assert synced == [tmp_path / "ripe"]

    def test_configured_name_may_nest(self, tmp_path, synced):
        run(tmp_path, synced, name="rirs/ripe")

        assert synced == [tmp_path / "rirs" / "ripe"]

    def test_configured_name_may_not_escape_base_dir(self, tmp_path, synced):
        run(tmp_path, synced, name="../escaped")

        assert synced == []
        assert not (tmp_path.parent / "escaped").exists()

    def test_derived_name_may_not_escape_base_dir(self, tmp_path, synced):
        run(tmp_path, synced, url="https://evil.com/../../../etc/notification.xml")

        assert synced == []

    def test_derived_name_may_not_reach_another_hostname(self, tmp_path, synced):
        run(
            tmp_path,
            synced,
            url="https://evil.com/../rrdp.ripe.net/notification.xml",
        )

        assert synced == []
        assert not (tmp_path / "rrdp.ripe.net").exists()

    def test_derived_name_keeps_its_url_path(self, tmp_path, synced):
        run(tmp_path, synced, url="https://rpki.example.com/rrdp/notification.xml")

        assert synced == [tmp_path / "rpki.example.com" / "rrdp"]


class TestLogToFile:
    def test_writes_the_day_log_into_the_sharded_directory(self, tmp_path, synced):
        run(tmp_path, synced, shard="year-month", log_to_file="true")

        now = datetime.now(tz=UTC)
        log_file = daily_log_file(
            resolve_output_dir(tmp_path, Shard.YEAR_MONTH, now), now
        )
        contents = log_file.read_text()
        assert "Sync completed: 1/1 repositories succeeded" in contents
        assert "Syncing 1 repositories" in contents

    def test_no_file_written_when_disabled(self, tmp_path, synced):
        run(tmp_path, synced, shard="year-month")

        assert not list(tmp_path.rglob("*.log"))

    def test_appends_across_runs(self, tmp_path, synced):
        run(tmp_path, synced)
        for handler in logging.getLogger().handlers:
            handler.close()
        run(tmp_path, synced, log_to_file="true")
        for handler in logging.getLogger().handlers:
            handler.close()
        run(tmp_path, synced, log_to_file="true")

        now = datetime.now(tz=UTC)
        contents = daily_log_file(tmp_path, now).read_text()
        assert contents.count("Sync completed") == 2
