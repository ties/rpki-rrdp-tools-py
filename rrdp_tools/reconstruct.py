import asyncio
import hashlib
import io
import logging
import os
import re
import tempfile
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TextIO

import click

from rrdp_tools.rpki import parse_file_time

from .http_client import (
    CrossOriginError,
    client_session,
    read_limited,
    restrict_origin,
    same_origin,
    write_limited,
)
from .logging_config import LOG_LEVELS, configure_logging
from .rrdp import (
    PublishElement,
    RrdpElement,
    WithdrawElement,
    parse_notification_file,
    parse_snapshot_or_delta,
)

LOG = logging.getLogger(__name__)


async def http_get_delta_or_snapshot(uri: str) -> TextIO:
    LOG.info("Downloading from %s", uri)
    async with client_session() as session:
        response = await session.get(uri, middlewares=(restrict_origin(uri),))
        assert response.status == 200

        notification = parse_notification_file(
            b"".join([chunk async for chunk in read_limited(response)]).decode("utf-8")
        )
        notification_uri, uri = uri, notification.snapshot.uri

        LOG.info(
            "found notification.xml for serial %d with snapshot at %s",
            notification.serial,
            uri,
        )

        # As rpki-client: the snapshot must be in the origin of the notification.
        if not same_origin(uri, notification_uri):
            raise CrossOriginError(
                f"snapshot {uri} is not in the origin of {notification_uri}"
            )

        response = await session.get(uri, middlewares=(restrict_origin(uri),))
        assert response.status == 200

        # Stream to an anonymous temporary file instead of holding it in memory.
        # Returned open to the caller, closed below on failure.
        snapshot_file = tempfile.TemporaryFile()  # noqa: SIM115
        try:
            digest, size = await write_limited(response, snapshot_file)
            if digest != notification.snapshot.hash:
                raise ValueError(
                    "Hash mismatch for snapshot: %s != %s (expected)",
                    digest,
                    notification.snapshot.hash,
                )
        except BaseException:
            snapshot_file.close()
            raise

        LOG.info("%s has a size of %ib", uri, size)
        snapshot_file.seek(0)
        return io.TextIOWrapper(snapshot_file, encoding="utf-8")


def reconstruct_repo(
    rrdp_file: TextIO,
    output_path: Path,
    filter_match: list[str],
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

    seen_objects: dict[str, RrdpElement] = defaultdict(set)
    publishes, withdraws = 0, 0

    doc = parse_snapshot_or_delta(rrdp_file)
    LOG.info("processing serial %d for session %s", doc.serial, doc.session_id)
    for elem in doc.content:
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


def output_file_path(output_path: Path, uri: str) -> Path:
    """Map the path of an RRDP object URI to a file below `output_path`.

    The path is resolved (`..`, symlinks) before checking, so it can not
    escape `output_path`. Raises ValueError if it does.
    """
    root = output_path.resolve()
    file_path = (root / f"./{urllib.parse.urlparse(uri).path}").resolve()
    if root not in file_path.parents:
        raise ValueError(f"{uri!r} resolves to {file_path}, outside of {root}")
    return file_path


def handle_withdraw_element(
    output_path, verify_only, elem: WithdrawElement, effective_uri
):
    file_path = output_file_path(output_path, effective_uri)
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
    file_path = output_file_path(output_path, effective_uri)

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


@click.command("reconstruct-repo")
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
@click.option("-v", "--verbose", count=True, help="-v: debug, -vv: also aiohttp etc.")
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    envvar="RRDP_LOG_LEVEL",
    default=None,
    help="Set an explicit level for all loggers, overriding -v",
)
@click.option(
    "--parse-for-time/--no-parse-for-time",
    help="Parse files for notBefore/signing time",
    is_flag=True,
    default=True,
)
def reconstruct_repo_command(
    infile: str,
    output_dir: Path,
    create_target: bool,
    filename_pattern: list[str],
    verify_only: bool = False,
    verbose: int = 0,
    log_level: str | None = None,
    parse_for_time: bool = False,
):
    """Call the main reconstruct function with the correct arguments."""
    configure_logging(verbose, log_level=log_level)

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
    reconstruct_repo_command()
