import pytest
from click.testing import CliRunner

from rrdp_tools.import_metrics import (
    import_rrdp_repos_from_metrics_command,
    parse_metrics_file,
    write_atomically,
)
from rrdp_tools.sharding import Shard
from rrdp_tools.sync_config import load_config

SAMPLE_METRICS = """\
rpki_client_repository_protos{rpki_client_repository_protos="https",carepo="rsync://rpki-01.pdxnet.uk/repo",notify="https://rpki-01.pdxnet.uk/rrdp/notification.xml"} 0
rpki_client_repository_protos{rpki_client_repository_protos="rrdp",carepo="rsync://repo.rpki.space/repo",notify="https://repo.rpki.space/rrdp/notification.xml"} 1
rpki_client_repository_protos{rpki_client_repository_protos="rsync",carepo="rsync://repo.rpki.space/repo",notify="https://repo.rpki.space/rrdp/notification.xml"} 0
rpki_client_repository_protos{rpki_client_repository_protos="https",carepo="rsync://repo.rpki.space/repo",notify="https://repo.rpki.space/rrdp/notification.xml"} 0
rpki_client_repository_protos{rpki_client_repository_protos="rrdp",carepo="rsync://rpki.axivora.net/repo",notify="https://rpki.axivora.net/rrdp/notification.xml"} 1
"""


class TestParseMetricsFile:
    def test_extracts_unique_urls(self):
        urls = parse_metrics_file(SAMPLE_METRICS)
        assert len(urls) == 3
        assert "https://repo.rpki.space/rrdp/notification.xml" in urls
        assert "https://rpki-01.pdxnet.uk/rrdp/notification.xml" in urls
        assert "https://rpki.axivora.net/rrdp/notification.xml" in urls

    def test_sorted_output(self):
        urls = parse_metrics_file(SAMPLE_METRICS)
        assert urls == sorted(urls)

    def test_empty_input(self):
        assert parse_metrics_file("") == []

    def test_no_notify_urls(self):
        content = 'rpki_client_some_other_metric{foo="bar"} 42\n'
        assert parse_metrics_file(content) == []

    def test_deduplication(self):
        content = (
            'rpki_client_repository_protos{notify="https://x.com/n.xml"} 1\n'
            'rpki_client_repository_protos{notify="https://x.com/n.xml"} 0\n'
        )
        urls = parse_metrics_file(content)
        assert len(urls) == 1


class TestWriteAtomically:
    def test_writes_content(self, tmp_path):
        target = tmp_path / "config.toml"
        write_atomically(target, "hello")

        assert target.read_text() == "hello"
        assert list(tmp_path.iterdir()) == [target]

    def test_replaces_existing_content(self, tmp_path):
        target = tmp_path / "config.toml"
        target.write_text("old")
        write_atomically(target, "new")

        assert target.read_text() == "new"

    def test_leaves_no_temporary_file_behind_on_failure(self, tmp_path, monkeypatch):
        target = tmp_path / "config.toml"
        target.write_text("old")

        def boom(*args, **kwargs):
            raise OSError("disk on fire")

        monkeypatch.setattr("rrdp_tools.import_metrics.os.replace", boom)

        with pytest.raises(OSError, match="disk on fire"):
            write_atomically(target, "new")

        assert target.read_text() == "old"
        assert list(tmp_path.iterdir()) == [target]


class TestImportCommand:
    def _invoke(self, tmp_path, *args, metrics_content=SAMPLE_METRICS):
        metrics = tmp_path / "metrics"
        metrics.write_text(metrics_content)
        output = tmp_path / "config.toml"

        result = CliRunner().invoke(
            import_rrdp_repos_from_metrics_command,
            [str(metrics), "-o", str(output), *args],
        )
        return result, output

    def _run(self, tmp_path, *args):
        result, output = self._invoke(tmp_path, *args)
        assert result.exit_code == 0, result.output
        return output

    def test_generated_config_reloads_unchanged(self, tmp_path):
        output = self._run(
            tmp_path,
            "--base-dir",
            "/data",
            "--shard",
            "year-month",
            "--log-to-file",
            "--user-agent",
            "example-agent/1.0",
        )

        config = load_config(output)
        assert config.base_dir == "/data"
        assert config.shard is Shard.YEAR_MONTH
        assert config.log_to_file is True
        assert config.user_agent == "example-agent/1.0"

    def test_defaults(self, tmp_path):
        config = load_config(self._run(tmp_path))

        assert config.shard is Shard.NONE
        assert config.log_to_file is False
        assert config.user_agent is None

    def test_leaves_no_temporary_file_behind(self, tmp_path):
        self._run(tmp_path, "--shard", "year-month")

        assert not list(tmp_path.glob("*.tmp"))

    def test_unusable_urls_are_dropped_not_fatal(self, tmp_path):
        result, output = self._invoke(
            tmp_path,
            metrics_content=(
                'x{notify="https://rrdp.ripe.net/notification.xml"} 1\n'
                'x{notify="notaurl"} 1\n'
                'x{notify="https:///notification.xml"} 1\n'
                'x{notify="https://rpki.example.com/rrdp/notification.xml"} 1\n'
            ),
        )

        assert result.exit_code == 0, result.output
        assert "Skipping notify URL notaurl" in result.output
        assert "Skipping notify URL https:///notification.xml" in result.output
        assert "Wrote config with 2 repositories" in result.output

        config = load_config(output)
        assert [r.notification_url for r in config.repositories] == [
            "https://rrdp.ripe.net/notification.xml",
            "https://rpki.example.com/rrdp/notification.xml",
        ]

    def test_all_urls_unusable(self, tmp_path):
        result, output = self._invoke(
            tmp_path, metrics_content='x{notify="notaurl"} 1\n'
        )

        assert result.exit_code == 1
        assert "No usable notify URLs" in result.output
        assert not output.exists()

    def test_no_urls_at_all(self, tmp_path):
        result, output = self._invoke(tmp_path, metrics_content="nothing here\n")

        assert result.exit_code == 1
        assert "No notify URLs found" in result.output
        assert not output.exists()
