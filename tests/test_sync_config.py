import tomllib

import pytest

from rrdp_tools.sharding import Shard
from rrdp_tools.sync_config import (
    RepositoryConfig,
    SyncConfig,
    config_from_notification_urls,
    format_toml,
    load_config,
)

SAMPLE_TOML = """\
parallel_connections = 8
base_dir = "/data/rrdp"

[[repository]]
notification_url = "https://rrdp.ripe.net/notification.xml"
name = "ripe"

[[repository]]
notification_url = "https://rpki.example.com/rrdp/notification.xml"
"""


class TestRepositoryConfig:
    def test_effective_name_with_name(self):
        repo = RepositoryConfig(
            notification_url="https://rrdp.ripe.net/notification.xml",
            name="ripe",
        )
        assert repo.effective_name == "ripe"

    def test_effective_name_from_hostname(self):
        repo = RepositoryConfig(
            notification_url="https://rrdp.ripe.net/notification.xml",
        )
        assert repo.effective_name == "rrdp.ripe.net"

    def test_effective_name_includes_path(self):
        repo = RepositoryConfig(
            notification_url="https://rpki-rrdp.us-east-2.amazonaws.com/rrdp/f703696e-e47b-4c20-bd93-6f80904e42d2/notification.xml",
        )
        assert (
            repo.effective_name
            == "rpki-rrdp.us-east-2.amazonaws.com/rrdp/f703696e-e47b-4c20-bd93-6f80904e42d2"
        )

    def test_effective_name_preserves_path_segments(self):
        """Path traversal protection happens in sync_rrdp, not here."""
        repo = RepositoryConfig(
            notification_url="https://evil.com/../../etc/notification.xml",
        )
        # effective_name preserves raw path; sync_rrdp checks containment
        assert repo.effective_name == "evil.com/../../etc"


class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_TOML)

        config = load_config(config_file)
        assert config.parallel_connections == 8
        assert config.base_dir == "/data/rrdp"
        assert len(config.repositories) == 2
        assert config.repositories[0].name == "ripe"
        assert config.repositories[1].effective_name == "rpki.example.com/rrdp"

    def test_load_missing_base_dir(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        with pytest.raises(ValueError, match="base_dir"):
            load_config(config_file)

    def test_load_no_repositories(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('base_dir = "/data"\n')

        with pytest.raises(ValueError, match="at least one"):
            load_config(config_file)

    def test_load_missing_notification_url(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('base_dir = "/data"\n\n[[repository]]\nname = "test"\n')

        with pytest.raises(ValueError, match="notification_url"):
            load_config(config_file)

    def test_default_parallel_connections(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\n\n[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        config = load_config(config_file)
        assert config.parallel_connections == 16

    def test_user_agent(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\nuser_agent = "example-agent/1.0"\n\n'
            '[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        config = load_config(config_file)
        assert config.user_agent == "example-agent/1.0"

    def test_user_agent_defaults_to_none(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\n\n[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        config = load_config(config_file)
        assert config.user_agent is None

    def test_shard_and_log_to_file(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\nshard = "year-month"\nlog_to_file = true\n\n'
            '[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        config = load_config(config_file)
        assert config.shard is Shard.YEAR_MONTH
        assert config.log_to_file is True
        assert config.base_dir == "/data"

    def test_shard_and_log_to_file_defaults(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\n\n[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        config = load_config(config_file)
        assert config.shard is Shard.NONE
        assert config.log_to_file is False

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("notaurl", "scheme"),
            ("/rrdp/notification.xml", "scheme"),
            ("rsync://rpki.example.com/repo", "scheme"),
            ("https:///notification.xml", "no hostname"),
            ("https://[::1/notification.xml", "IPv6"),
        ],
    )
    def test_invalid_notification_url(self, tmp_path, url, expected):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'base_dir = "/data"\n\n[[repository]]\nnotification_url = "{url}"\n'
        )

        with pytest.raises(ValueError, match="Invalid notification_url") as excinfo:
            load_config(config_file)
        assert expected in str(excinfo.value)
        assert url in str(excinfo.value)

    @pytest.mark.parametrize(
        "url",
        [
            "https://rrdp.ripe.net/notification.xml",
            "http://localhost:8080/notification.xml",
            "https://[::1]:8443/notification.xml",
        ],
    )
    def test_accepts_usable_notification_urls(self, tmp_path, url):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            f'base_dir = "/data"\n\n[[repository]]\nnotification_url = "{url}"\n'
        )

        assert load_config(config_file).repositories[0].notification_url == url

    def test_unknown_shard(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'base_dir = "/data"\nshard = "fortnightly"\n\n'
            '[[repository]]\nnotification_url = "https://x.com/n.xml"\n'
        )

        with pytest.raises(ValueError, match="Unknown 'shard' value"):
            load_config(config_file)


class TestFormatToml:
    def test_round_trip(self):
        config = SyncConfig(
            base_dir="/data/rrdp",
            parallel_connections=8,
            repositories=[
                RepositoryConfig(
                    notification_url="https://rrdp.ripe.net/notification.xml",
                    name="ripe",
                ),
                RepositoryConfig(
                    notification_url="https://rpki.example.com/rrdp/notification.xml",
                ),
            ],
        )

        toml_str = format_toml(config)
        parsed = tomllib.loads(toml_str)

        assert parsed["parallel_connections"] == 8
        assert parsed["base_dir"] == "/data/rrdp"
        assert len(parsed["repository"]) == 2
        # RIR repo (ripe.net) comes first
        assert parsed["repository"][0]["name"] == "ripe"
        # Non-RIR repo second
        assert (
            parsed["repository"][1]["notification_url"]
            == "https://rpki.example.com/rrdp/notification.xml"
        )

    def test_rir_before_non_rir(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://zebra.example.com/n.xml"),
                RepositoryConfig(notification_url="https://rrdp.arin.net/n.xml"),
                RepositoryConfig(notification_url="https://alpha.example.com/n.xml"),
                RepositoryConfig(notification_url="https://rrdp.ripe.net/n.xml"),
                RepositoryConfig(notification_url="https://rrdp.apnic.net/n.xml"),
            ],
        )

        toml_str = format_toml(config)
        parsed = tomllib.loads(toml_str)

        urls = [r["notification_url"] for r in parsed["repository"]]
        assert urls == [
            "https://rrdp.apnic.net/n.xml",
            "https://rrdp.arin.net/n.xml",
            "https://rrdp.ripe.net/n.xml",
            "https://alpha.example.com/n.xml",
            "https://zebra.example.com/n.xml",
        ]

    def test_separator_comment(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://rrdp.ripe.net/n.xml"),
                RepositoryConfig(notification_url="https://example.com/n.xml"),
            ],
        )

        toml_str = format_toml(config)
        assert "# Non-RIR repositories:" in toml_str

    def test_no_separator_when_only_rir(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://rrdp.ripe.net/n.xml"),
            ],
        )

        toml_str = format_toml(config)
        assert "Non-RIR" not in toml_str

    def test_no_separator_when_only_non_rir(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://example.com/n.xml"),
            ],
        )

        toml_str = format_toml(config)
        assert "Non-RIR" not in toml_str

    def test_optional_fields(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(
                    notification_url="https://x.com/n.xml",
                    skip_snapshot=False,
                    include_hash=False,
                    limit_deltas=10,
                ),
            ],
        )

        toml_str = format_toml(config)
        parsed = tomllib.loads(toml_str)

        repo = parsed["repository"][0]
        assert repo["skip_snapshot"] is False
        assert repo["include_hash"] is False
        assert repo["limit_deltas"] == 10

    def test_user_agent_round_trip(self):
        config = SyncConfig(
            base_dir="/data",
            user_agent="example-agent/1.0",
            repositories=[
                RepositoryConfig(notification_url="https://x.com/n.xml"),
            ],
        )

        parsed = tomllib.loads(format_toml(config))
        assert parsed["user_agent"] == "example-agent/1.0"

    def test_user_agent_omitted_when_unset(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://x.com/n.xml"),
            ],
        )

        assert "user_agent" not in format_toml(config)

    def test_shard_and_log_to_file_round_trip(self, tmp_path):
        config = SyncConfig(
            base_dir="/data",
            shard=Shard.YEAR_MONTH,
            log_to_file=True,
            repositories=[
                RepositoryConfig(notification_url="https://x.com/n.xml"),
            ],
        )

        config_file = tmp_path / "config.toml"
        config_file.write_text(format_toml(config))
        reloaded = load_config(config_file)

        assert reloaded.shard is Shard.YEAR_MONTH
        assert reloaded.log_to_file is True
        assert reloaded.base_dir == "/data"

    def test_shard_and_log_to_file_omitted_when_default(self):
        config = SyncConfig(
            base_dir="/data",
            repositories=[
                RepositoryConfig(notification_url="https://x.com/n.xml"),
            ],
        )

        toml_str = format_toml(config)
        assert "shard" not in toml_str
        assert "log_to_file" not in toml_str


class TestConfigFromUrls:
    def test_creates_config(self):
        urls = [
            "https://rrdp.ripe.net/notification.xml",
            "https://rpki.example.com/rrdp/notification.xml",
        ]
        config = config_from_notification_urls(urls, base_dir="/tmp/rrdp")

        assert config.base_dir == "/tmp/rrdp"
        assert config.parallel_connections == 16
        assert len(config.repositories) == 2
        assert config.repositories[0].notification_url == urls[0]

    def test_passes_through_shard_and_log_to_file(self):
        config = config_from_notification_urls(
            ["https://x.com/n.xml"],
            shard=Shard.YEAR_MONTH,
            log_to_file=True,
            user_agent="example-agent/1.0",
        )

        assert config.shard is Shard.YEAR_MONTH
        assert config.log_to_file is True
        assert config.user_agent == "example-agent/1.0"
