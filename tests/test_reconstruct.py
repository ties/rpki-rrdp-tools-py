import logging
import pathlib

import pytest

from rrdp_tools.reconstruct import reconstruct_repo


def test_reconstruct(tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    snapshot_path = pathlib.Path(__file__).parent / "data/sample-snapshot.xml"

    # reconstruct the snapshot
    reconstruct_repo(snapshot_path.open("r"), tmp_path, [])

    repo_parent = tmp_path / "repository"
    assert repo_parent.is_dir()
    assert len(list(repo_parent.iterdir())) > 0

    roas = list(repo_parent.rglob("*.roa"))
    assert len(roas) > 25


def test_reconstruct_filter(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    snapshot_path = pathlib.Path(__file__).parent / "data/sample-snapshot.xml"

    # reconstruct the snapshot
    reconstruct_repo(snapshot_path.open("r"), tmp_path, [".*\\.cer"])

    # there are no certificates -> no files in the directory
    files = list(tmp_path.rglob("*"))
    assert len(files) == 0
