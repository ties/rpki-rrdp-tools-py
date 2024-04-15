import logging
import re
from pathlib import Path
from typing import Counter

import pytest

from rrdp_tools.rrdp_content_filter import (
    ManifestMatch,
    PublishMatch,
    filter_rrdp_content,
    process_file,
)


@pytest.mark.asyncio
async def test_filter_sample_content(caplog):
    caplog.set_level(logging.DEBUG)
    dir = Path(__file__).parent / "data/rrdp-content"

    await filter_rrdp_content(dir, re.compile(r".*\\.mft"), True, True)


@pytest.mark.asyncio
async def test_filter_files(caplog):
    caplog.set_level(logging.DEBUG)
    dir = Path(__file__).parent / "data/rrdp-content"

    matches = Counter()

    for file_name in dir.glob("**/*.xml"):
        for f in process_file(file_name, re.compile(r".*")):
            matches[type(f)] += 1

    assert matches[ManifestMatch] > 5
    assert matches[PublishMatch] > 5

    # Now filter for mft
    for file_name in dir.glob("**/*.xml"):
        for f in process_file(file_name, re.compile(r".*\\.mft")):
            matches[type(f)] += 1

    assert matches[ManifestMatch] > 5
    assert matches[PublishMatch] == 0
