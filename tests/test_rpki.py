import datetime
import logging
import pathlib

import pytest

from rrdp_tools.rpki import parse_file_time

LOG = logging.getLogger(__name__)


def test_parse_file_time(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        minutes=1
    )

    sample_files = pathlib.Path(__file__).parent / "data/"
    for file in (
        "FnzdKKjxPmamPX_NCy-vbob58nw.roa",
        "GOOD-profile-15-draft-ietf-sidrops-profile-15-sample.asa",
        "NKcuY5DvQmG0vwsI6MT4nqcBcoI.gbr",
        "ripe-ncc-ta.cer",
        "ripe-ncc-ta.crl",
        "ripe-ncc-ta.mft",
    ):
        LOG.info("Processing %s", file)
        with (sample_files / file).open("rb") as f:
            parsed_time = parse_file_time(file, f.read())
            assert parsed_time < yesterday
