import asyncio
import base64
import dataclasses
import datetime
import itertools
import logging
import multiprocessing
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Generator, List, Optional, Union

import asn1crypto
import click
from alive_progress import alive_bar

from rrdp_tools.rpki import FileAndHash, parse_file_time, parse_manifest
from rrdp_tools.rrdp import (
    PublishElement,
    UnexpectedDocumentException,
    ValidationException,
    parse_snapshot_or_delta,
)

LOG = logging.getLogger(__name__)


@dataclass
class ManifestMatch:
    """Union of Delta/Snapshotdoccument, PublishElement and ManifestInfo"""

    serial: int
    session_id: str

    uri: str
    content: bytes

    manifest_number: int
    signing_time: datetime
    ee_certificate: asn1crypto.x509.Certificate
    file_list: FrozenSet[FileAndHash]

    previous_hash: Optional[str]
    h_content: Union[str, None] = None

    authority_information_access: Optional[str] = None
    this_update: Optional[str] = None
    next_update: Optional[str] = None


@dataclass
class PublishMatch:
    """Union of Delta/SnapshotDocument, PublishElement, and parsed date time"""

    serial: int
    session_id: str

    uri: str
    previous_hash: Optional[str]
    content: bytes

    modification_time: datetime

    h_content: Union[str, None] = None


def process_file(
    xml_file: Path,
    file_match: re.Pattern,
    log_content: bool = False,
    progress_bar: Optional[alive_bar] = None,
) -> Generator[ManifestMatch | PublishMatch, None, None]:
    LOG.debug("processing %s", xml_file)

    with xml_file.open("r") as f:
        try:
            doc = parse_snapshot_or_delta(f)
            for elem in doc.content:
                match elem:
                    case PublishElement(uri=uri, content=content):
                        if file_match.match(uri):
                            if uri.endswith(".mft"):
                                mft = parse_manifest(content)
                                yield ManifestMatch(
                                    serial=doc.serial,
                                    session_id=doc.session_id,
                                    **dataclasses.asdict(elem),
                                    **dataclasses.asdict(mft),
                                    authority_information_access=mft.authority_information_access,
                                )
                            else:
                                time = parse_file_time(uri, content)
                                yield PublishMatch(
                                    serial=doc.serial,
                                    session_id=doc.session_id,
                                    modification_time=time,
                                    **dataclasses.asdict(elem),
                                )
        except ValidationException:
            LOG.error("%s is not a valid RRDP document", xml_file)
        except UnexpectedDocumentException:
            LOG.info("Skipping %s: not a snapshot or delta document", xml_file)
        finally:
            if progress_bar:
                progress_bar()


def process_file_to_list(
    xml_file: Path, file_match: re.Pattern, log_content: bool = False
) -> List[ManifestMatch | PublishMatch]:
    return list(process_file(xml_file, file_match, log_content))


async def filter_rrdp_content(
    path: Path,
    file_match: re.Pattern,
    log_content: bool,
    print_manifest_diff: bool,
    store_content: Optional[Path] = None,
):
    files = list(path.glob("**/*.xml"))
    LOG.info("found %d files", len(files))

    with multiprocessing.Pool() as pool:
        match_lists = pool.starmap(
            process_file_to_list,
            [(xml_file, file_match, log_content) for xml_file in files],
        )
    matches = list(itertools.chain.from_iterable(match_lists))

    # map uri -> previous manifest
    previous_manifest: Dict[str, ManifestMatch] = {}

    for entry in sorted(matches, key=lambda x: x.serial):
        if store_content:
            file_name = entry.uri.split("/")[-1]
            with (store_content / f"{entry.serial:06d}_{file_name}").open("wb") as f:
                f.write(entry.content)

        match entry:
            case ManifestMatch():
                click.echo(
                    f"{entry.serial:>6} {entry.uri} {entry.h_content} {entry.manifest_number:>4} {entry.signing_time:%Y-%m-%d %H:%M:%S} {entry.authority_information_access}"
                )
                previous = previous_manifest.get(entry.uri, None)
                previous_manifest[entry.uri] = entry

                if print_manifest_diff and previous:
                    added = entry.file_list - previous.file_list
                    removed = previous.file_list - entry.file_list

                    diff = list(added | removed)
                    diff.sort()

                    for file in diff:
                        if file in removed:
                            click.echo(click.style(f"      - {file}", fg="red"))
                        else:
                            click.echo(click.style(f"      + {file}", fg="green"))
            case PublishMatch():
                click.echo(
                    f"{entry.serial:>6} {entry.uri} {entry.h_content} {entry.modification_time:%Y-%m-%d %H:%M:%S}"
                )

        if log_content:
            click.echo(base64.b64encode(entry.content).decode("ascii"))


@click.command("filter-rrdp-content")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
)
@click.option("--file-match", type=str, default=".*\\.mft")
@click.option("--verbose", "-v", is_flag=True)
@click.option("--log-content", "-l", is_flag=True)
@click.option(
    "--store-content",
    type=click.Path(dir_okay=True, path_type=Path, exists=True, resolve_path=True),
    default=None,
)
@click.option(
    "--manifest-diff",
    "-m",
    is_flag=True,
    help="Log the difference in FileAndHash set between the manifests",
)
def filter_rrdp_content_command(
    path: Path,
    file_match: str,
    verbose: bool,
    log_content: bool,
    manifest_diff: bool,
    store_content: Optional[Path],
):
    """Scan a set of RRDP documents and print out matching files."""
    logging.basicConfig()
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    asyncio.run(
        filter_rrdp_content(
            path,
            re.compile(file_match),
            log_content,
            manifest_diff,
            store_content=store_content,
        )
    )


if __name__ == "__main__":
    filter_rrdp_content_command()
