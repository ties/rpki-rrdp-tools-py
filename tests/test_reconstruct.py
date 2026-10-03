import logging
import pathlib

import pytest

from rrdp_tools.reconstruct import output_file_path, reconstruct_repo


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


@pytest.mark.parametrize(
    "uri, expected",
    [
        ("rsync://rpki.example.org/repo/a.roa", "repo/a.roa"),
        ("rsync://rpki.example.org/repo/ca/sub/b.mft", "repo/ca/sub/b.mft"),
        ("rsync://rpki.example.org//repo/a.roa", "repo/a.roa"),
        ("rsync://rpki.example.org/repo/x/../a.roa", "repo/a.roa"),
        ("rsync://rpki.example.org/repo/a.roa-0123abcd", "repo/a.roa-0123abcd"),
    ],
)
def test_output_file_path_inside(tmp_path: pathlib.Path, uri: str, expected: str):
    assert output_file_path(tmp_path, uri) == tmp_path.resolve() / expected


@pytest.mark.parametrize(
    "uri",
    [
        "rsync://rpki.example.org/../victim",
        "rsync://rpki.example.org/repo/../../victim",
        "rsync://rpki.example.org//../../victim",
        "rsync://rpki.example.org/repo/a/../../../victim",
        # the output directory itself is not a file below it
        "rsync://rpki.example.org/",
        "rsync://rpki.example.org/repo/..",
    ],
)
def test_output_file_path_traversal(tmp_path: pathlib.Path, uri: str):
    output = tmp_path / "output"
    output.mkdir()

    with pytest.raises(ValueError, match="outside of"):
        output_file_path(output, uri)


def test_output_file_path_symlink_escape(tmp_path: pathlib.Path):
    output = tmp_path / "output"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (output / "repo").symlink_to(outside)

    with pytest.raises(ValueError, match="outside of"):
        output_file_path(output, "rsync://rpki.example.org/repo/a.roa")


def test_output_file_path_relative_output_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)

    assert (
        output_file_path(pathlib.Path("."), "rsync://rpki.example.org/repo/a.roa")
        == tmp_path.resolve() / "repo/a.roa"
    )
    with pytest.raises(ValueError, match="outside of"):
        output_file_path(pathlib.Path("."), "rsync://rpki.example.org/../a.roa")
