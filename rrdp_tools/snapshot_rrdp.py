import asyncio
import email.utils
import hashlib
import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import aiohttp
import click
from lxml import etree

from .rrdp import validate

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def set_time_from_headers(res: aiohttp.ClientResponse, target_file: Path) -> None:
    last_modified = res.headers.get("Last-Modified", None)
    try:
        if last_modified:
            last_modified_date = email.utils.parsedate_to_datetime(last_modified)
            os.utime(
                target_file,
                (last_modified_date.timestamp(), last_modified_date.timestamp()),
            )
    except Exception as e:
        LOG.warning("Failed to set mtime on %s: %s", target_file, e)


async def get_and_check(
    sem: asyncio.Semaphore,
    session: aiohttp.ClientSession,
    base_file_name: Path,
    uri: str,
    sha256: str,
    override_host: Optional[str],
    hash_in_name: bool = False,
) -> bool:
    """
    Get a file if needed and check the hash compared to the download.

    If a file exists and the hash should be added to the name, do so.
    """
    expected_hash = sha256.lower()

    target_file = base_file_name
    if hash_in_name:
        target_file = (
            base_file_name.parent
            / f"{base_file_name.stem}-{expected_hash}{base_file_name.suffix}"
        )
        if target_file.exists():
            LOG.debug("Already have %s as %s", uri, target_file)
            return False
    else:
        if target_file.exists():
            with target_file.open("rb") as f:
                cur_hash = hashlib.sha256(f.read()).hexdigest()
                if cur_hash == expected_hash:
                    LOG.debug("Already have %s as %s", uri, target_file)
                    return False
                else:
                    LOG.info(
                        "Hash for %s does not match, downloading %s", target_file, uri
                    )

    async with sem:
        if override_host:
            # override the URI
            tokens = list(urllib.parse.urlparse(uri))
            override_tokens = urllib.parse.urlparse(override_host)
            # [scheme, host, ...]
            tokens[0] = override_tokens[0]
            tokens[1] = override_tokens[1]

            uri = urllib.parse.urlunparse(tokens)

        LOG.debug("Getting %s h=%s target_file=%s", uri, expected_hash, target_file)

        t0 = time.time()
        res = await session.get(uri)
        if res.status != 200:
            reason = await res.read()
            LOG.error("HTTP %d for %s: %s", res.status, uri, reason)
            raise ValueError(f"HTTP {res.status} for {uri}")
        content = await res.read()
        LOG.debug("%s %.2f %db", uri, time.time() - t0, len(content))

        digest = hashlib.sha256(content).hexdigest()

        if digest != expected_hash:
            raise ValueError(
                f"Hash mismatch for {uri}. Expected {expected_hash} actual {digest}"
            )

    with target_file.open("wb") as f:
        f.write(content)
    set_time_from_headers(res, target_file)
    return True


async def snapshot_rrdp(
    notification_url: str,
    output_path: Path,
    override_host: Optional[str] = None,
    skip_snapshot: bool = False,
    include_session: bool = False,
    threads: int = 4,
    limit_deltas: Optional[int] = None,
    include_hash: bool = False,
):
    """Snapshot RRDP content."""
    sem = asyncio.Semaphore(threads)

    async with aiohttp.ClientSession() as session:
        LOG.debug("GET %s", notification_url)
        res = await session.get(notification_url)
        if res.status != 200:
            click.echo(f"HTTP {res.status} from RRDP server, aborting")
            click.echo(f"reason: {await res.text()}")
            return
        doc = etree.fromstring(await res.text())
        validate(doc)

        assert doc.tag == "{http://www.ripe.net/rpki/rrdp}notification"
        session_id = doc.attrib["session_id"]
        serial = doc.attrib["serial"]

        LOG.info("%s serial=%s session_id=%s", notification_url, serial, session_id)

        if not session_id:
            print("No session_id in notification file!")
            sys.exit(1)

        if include_session:
            output_path = output_path / session_id
            output_path.mkdir(parents=True, exist_ok=True)

        # Document is valid,
        with (output_path / "notification.xml").open("wb") as f:
            f.write(await res.read())
        set_time_from_headers(res, output_path / "notification.xml")

        queue = []

        snapshot = doc.find("{http://www.ripe.net/rpki/rrdp}snapshot")
        if not skip_snapshot:
            snapshot_hash = snapshot.attrib["hash"]
            file_name = f"snapshot-{serial}.xml"
            queue.append(
                get_and_check(
                    sem,
                    session,
                    output_path / file_name,
                    snapshot.attrib["uri"],
                    snapshot_hash,
                    override_host=override_host,
                    hash_in_name=include_hash,
                )
            )

        deltas = doc.findall("{http://www.ripe.net/rpki/rrdp}delta")
        for idx, delta in enumerate(deltas):
            if limit_deltas is not None and idx >= limit_deltas:
                break
            serial = delta.attrib["serial"]
            delta_hash = delta.attrib["hash"]
            file_name = f"{serial}.xml"
            queue.append(
                get_and_check(
                    sem,
                    session,
                    output_path / file_name,
                    delta.attrib["uri"],
                    delta_hash,
                    override_host=override_host,
                    hash_in_name=include_hash,
                )
            )

        status_per_file = await asyncio.gather(*queue)
        click.echo(
            f"Update completed. {len(queue)} files are present. Downloaded {sum(status_per_file)} files."
        )


@click.command("snapshot_rrd")
@click.argument("notification_url", type=str)
@click.argument("output_dir", type=click.Path(path_type=Path))
@click.option("--override-host", help="[protocol]://hostname to override", type=str)
@click.option("--include-session", help="Include session ID in path", is_flag=True)
@click.option("--create-target", help="Create target dir", is_flag=True)
@click.option("-v", "--verbose", help="verbose", is_flag=True)
@click.option("--skip_snapshot", help="Skip download of the RRDP snaphot", is_flag=True)
@click.option(
    "--include-hash/--no-include-hash", help="Include hash in filenames", is_flag=True
)
@click.option(
    "--threads", help="Number of download threads", type=int, default=os.cpu_count()
)
@click.option(
    "--limit-deltas", help="Number of deltas to include", type=int, default=None
)
def main(
    notification_url: str,
    output_dir: Path,
    override_host: Optional[str] = None,
    include_session: bool = False,
    verbose: bool = False,
    skip_snapshot: bool = True,
    threads: int = 4,
    limit_deltas: Optional[int] = None,
    create_target: bool = False,
    include_hash: bool = True,
):
    """
    Snapshot RRDP content

    NOTIFICATION_URL    URL to notifcation.xml file.
    OUTPUT_DIR          Directory to save content in.
    """
    if verbose:
        LOG.setLevel(logging.DEBUG)
    output_dir = output_dir.resolve()

    if not output_dir.is_dir():
        do_exit = False

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
                do_exit = True
        else:
            click.echo(
                click.style(
                    f"Output directory {output_dir} does not exist", fg="red", bold=True
                )
            )
            do_exit = True

        if do_exit:
            ctx = click.get_current_context()
            click.echo(ctx.get_help())
            ctx.exit(2)

    asyncio.run(
        snapshot_rrdp(
            notification_url,
            output_dir,
            override_host=override_host,
            skip_snapshot=skip_snapshot,
            include_session=include_session,
            threads=threads,
            limit_deltas=limit_deltas,
            include_hash=include_hash,
        )
    )


if __name__ == "__main__":
    main()
