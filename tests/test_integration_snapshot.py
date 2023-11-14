import pathlib
import re

import pytest

from rrdp_tools.snapshot_rrdp import snapshot_rrdp

DELTA_RE = re.compile(r"[0-9]+.xml")


@pytest.mark.asyncio
async def test_reconstruct(tmp_path: pathlib.Path) -> None:
    # Use a small RRDP repository to test the snapshot_rrdp function
    await snapshot_rrdp(
        "https://rrdp.paas.rpki.ripe.net/notification.xml",
        tmp_path,
        include_session=True,
    )

    files = list(tmp_path.iterdir())
    # just the session
    assert len(files) == 1

    session_dir = tmp_path / files[0]

    notification_files = set(p.name for p in session_dir.glob("*.xml"))

    assert any(map(lambda x: "snapshot" in x, notification_files))
    deltas = list(filter(DELTA_RE.match, notification_files))

    # assume there are 5 deltas
    assert len(deltas) > 5
