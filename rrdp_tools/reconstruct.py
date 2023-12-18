import asyncio
import hashlib
import io
import logging
import os
import re
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, TextIO

import aiohttp
import click

from rrdp_tools.rpki import parse_file_time

from .rrdp import (
    PublishElement,
    RrdpElement,
    WithdrawElement,
    parse_notification_file,
    parse_snapshot_or_delta,
)

logging.basicConfig()
LOG = logging.getLogger(__name__)


async def http_get_delta_or_snapshot(uri: str) -> TextIO:
    LOG.info("Downloading from %s", uri)
    async with aiohttp.ClientSession() as session:
        response = await session.get(uri)
        assert response.status == 200

        notification = parse_notification_file(await response.text())
        uri = notification.snapshot.uri

        LOG.info(
            "found notification.xml for serial %d with snapshot at %s",
            notification.serial,
            uri,
        )

        response = await session.get(uri)
        assert response.status == 200

        text = await response.text()

        LOG.info("%s has a size of %ib", uri, len(text))
        return io.StringIO(text)


def reconstruct_repo(
    rrdp_file: TextIO,
    output_path: Path,
    filter_match: List[str],
    verify_only: bool = False,
    parse_for_time: bool = False,
):
    """Actually reconstruct the repository."""
    compiled_patterns = [re.compile(pattern) for pattern in filter_match]

    def match(uri) -> bool:
        """Match against the regex in `filter_match` (default: accept)."""
        if not compiled_patterns:
            return True

        for pattern in compiled_patterns:
            if pattern.search(uri):
                return True

        return False

    seen_objects: Dict[str, RrdpElement] = defaultdict(set)
    publishes, withdraws = 0, 0

    for elem in parse_snapshot_or_delta(rrdp_file):
        effective_uri = elem.uri

        if elem.uri in seen_objects:
            h = hashlib.sha256(elem.content).hexdigest()
            LOG.error(
                "Repeated entry: %s (appending hash to filename). previous entries: %s",
                elem,
                seen_objects[elem.uri],
            )
            effective_uri = f"{elem.uri}-{h}"

        seen_objects[elem.uri].add(elem)

        if match(elem.uri):
            match elem:
                case PublishElement():
                    handle_publish_element(
                        output_path, verify_only, parse_for_time, elem, effective_uri
                    )
                    publishes += 1
                case WithdrawElement():
                    handle_withdraw_element(
                        output_path, verify_only, elem, effective_uri
                    )
                    withdraws += 1
        else:
            LOG.debug("skipped '%s': did not match filter.", elem.uri)

    LOG.info(
        "Processed %i (%i published, %i withdrawn) files to %s",
        publishes + withdraws,
        publishes,
        withdraws,
        output_path,
    )


def handle_withdraw_element(
    output_path, verify_only, elem: WithdrawElement, effective_uri
):
    file_path = output_path / f"./{urllib.parse.urlparse(effective_uri).path}"
    if file_path.exists():
        h_disk = hashlib.sha256(file_path.read_bytes()).hexdigest()

        if h_disk != elem.hash:
            LOG.error(
                "Hash mismatch for %s: %s (disk) %s (withdraw)",
                elem.uri,
                h_disk,
                elem.hash,
            )

        if not verify_only:
            file_path.unlink()
            LOG.debug("Removed '%s'", file_path)
    else:
        LOG.error("withdraw %s %s: file not found.", elem.uri, elem.hash)


def handle_publish_element(
    output_path, verify_only, parse_for_time, elem: PublishElement, effective_uri
):
    tokens = urllib.parse.urlparse(effective_uri)
    file_path = output_path / f"./{tokens.path}"
    # Ensure that output dir is a subdirectory and create if necessary
    assert output_path in file_path.parents

    # publish with hash -> overwrite, check old hash
    if elem.previous_hash:
        if file_path.exists():
            h_disk = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if h_disk != elem.previous_hash:
                LOG.error(
                    "Hash mismatch for %s: %s (disk) %s (publish)",
                    elem.uri,
                    h_disk,
                    elem.previous_hash,
                )
        else:
            LOG.debug(
                "File %s sha256=%s in publish tag w/ hash not present on disk",
                elem.uri,
                elem.previous_hash,
            )

    if not verify_only:
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            # Accept empty publish tags/empty files
            f.write(elem.content)

        LOG.debug("Wrote '%s' to '%s'", elem.uri, file_path)

        # Update modification time
        if parse_for_time:
            file_date = parse_file_time(file_path.name, elem.content)
            os.utime(
                file_path,
                (
                    datetime.timestamp(file_date),
                    datetime.timestamp(file_date),
                ),
            )


def do_exit():
    """Exit and print help."""
    ctx = click.get_current_context()
    click.echo(ctx.get_help())
    ctx.exit(2)


@click.command("Reconstruct repo state from snapshot/delta XML.")
@click.argument("infile", type=str)
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--create-target", help="Create target directory", is_flag=True)
@click.option(
    "--filename-pattern",
    help="optional regular expression to filter filenames against",
    type=str,
    multiple=True,
)
@click.option("--verify-only", help="verify mode: do not write any files", is_flag=True)
@click.option("-v", "--verbose", help="verbose", is_flag=True)
@click.option(
    "--parse-for-time/--no-parse-for-time",
    help="Parse files for notBefore/signing time",
    is_flag=True,
    default=True,
)
def main(
    infile: str,
    output_dir: Path,
    create_target: bool,
    filename_pattern: List[str],
    verify_only: bool = False,
    verbose: bool = False,
    parse_for_time: bool = False,
):
    """Call the main reconstruct function with the correct arguments."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    output_dir = output_dir.resolve()

    if not output_dir.is_dir():
        if output_dir.exists():
            click.echo(
                click.style("Output ", fg="red")
                + click.style(f"file ({output_dir})", fg="red", bold=True)
                + click.style(" already exists and is not a directory", fg="red")
            )
            do_exit()

        if create_target:
            if output_dir.parent.is_dir():
                click.echo(
                    click.style(f"Creating output directory {output_dir}", fg="green")
                )
                output_dir.mkdir(parents=True)
            else:
                click.echo(
                    click.style(
                        f"Parent of output directory ({output_dir}) does not exist - and not creating recursively",
                        fg="red",
                        bold=True,
                    )
                )
                do_exit()
        else:
            click.echo(
                click.style(
                    f"Output directory {output_dir} does not exist", fg="red", bold=True
                )
            )
            do_exit()

    if re.match("^http(s)?://", infile):
        infile_io = asyncio.run(http_get_delta_or_snapshot(infile))
    else:
        p = Path(infile)
        if not p.is_file():
            click.echo(
                click.style(f"Input file {infile} does not exist", fg="red", bold=True)
            )
            do_exit()

        infile_io = p.open("r", encoding="utf-8")

    reconstruct_repo(
        infile_io,
        output_dir,
        filename_pattern,
        verify_only=verify_only,
        parse_for_time=parse_for_time,
    )


if __name__ == "__main__":
    main()
