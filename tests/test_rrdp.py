import logging
import pathlib
from xml.etree import ElementTree as ET

import pytest

from rrdp_tools.rrdp import NS_RRDP, parse_notification_file, parse_snapshot_or_delta


def test_parse_and_serialise_delta(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    delta_path = pathlib.Path(__file__).parent / "data/rrdp-content/26293.xml"

    doc = parse_snapshot_or_delta(delta_path)
    assert ET.tostring(doc.to_xml(), default_namespace=NS_RRDP).decode("utf-8") == str(
        doc
    )


def test_parse_and_serialise_snapshot(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    snapshot_path = pathlib.Path(__file__).parent / "data/sample-snapshot.xml"

    doc = parse_snapshot_or_delta(snapshot_path)
    assert ET.tostring(doc.to_xml(), default_namespace=NS_RRDP).decode("utf-8") == str(
        doc
    )


def test_parse_and_serialise_notification(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    notification_path = (
        pathlib.Path(__file__).parent / "data/rrdp-content/notification.xml"
    )

    with notification_path.open("r") as f:
        doc = parse_notification_file(f.read())
        assert ET.tostring(doc.to_xml(), default_namespace=NS_RRDP).decode(
            "utf-8"
        ) == str(doc)
