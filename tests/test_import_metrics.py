from rrdp_tools.import_metrics import parse_metrics_file

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
