import asyncio
import email.utils
import hashlib
import logging
import os
import time
import urllib.parse
from pathlib import Path

import aiohttp
import click

from .http_client import client_session
from .rrdp import parse_notification_file

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
    except Exception as e:  # noqa: BLE001
        LOG.warning("Failed to set mtime on %s: %s", target_file, e)


async def get_and_check(
    sem: asyncio.Semaphore,
    session: aiohttp.ClientSession,
    base_dir: Path,
    file_name: str,
    uri: str,
    sha256: str,
    override_host: str | None,
    hash_in_name: bool = False,
) -> bool:
    """
    Get a file if needed and check the hash compared to the download.

    If a file exists and the hash should be added to the name, do so.
    """
    expected_hash = sha256.lower()

    target_file = base_dir / file_name
    if not target_file.resolve().is_relative_to(base_dir.resolve()):
        raise ValueError(
            f"Target file {target_file} is not relative to base directory {base_dir}: Potential path traversal."
        )
    if hash_in_name:
        target_file = (
            target_file.parent
            / f"{target_file.stem}-{expected_hash}{target_file.suffix}"
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
    override_host: str | None = None,
    skip_snapshot: bool = False,
    include_session: bool = False,
    threads: int = 4,
    limit_deltas: int | None = None,
    include_hash: bool = False,
    store_notification: bool = True,
    sem: asyncio.Semaphore | None = None,
    session: aiohttp.ClientSession | None = None,
):
    """Snapshot RRDP content."""
    sem = sem or asyncio.Semaphore(threads)
    owns_session = session is None
    if owns_session:
        session = client_session()
    try:
        LOG.debug("GET %s", notification_url)
        res = await session.get(notification_url)
        if res.status != 200:
            click.echo(
                f"HTTP {res.status} from RRDP server for {notification_url}, aborting"
            )
            click.echo(f"reason: {await res.text()}")
            return

        notification = parse_notification_file(await res.text())

        LOG.info(
            "%s serial=%s session_id=%s",
            notification_url,
            notification.serial,
            notification.session_id,
        )

        if not notification.session_id:
            raise ValueError(
                f"No session_id in notification file for {notification_url}"
            )

        if include_session:
            output_path = output_path / notification.session_id
            output_path.mkdir(parents=True, exist_ok=True)

        # Document is valid, store notification
        notification_content = await res.read()
        if store_notification:
            if include_hash:
                notification_hash = hashlib.sha256(notification_content).hexdigest()
                notification_file = (
                    output_path
                    / f"notification.{notification.serial}.{notification_hash}.xml"
                )
            else:
                notification_file = (
                    output_path / f"notification.{notification.serial}.xml"
                )
        else:
            notification_file = output_path / "notification.xml"
        with notification_file.open("wb") as f:
            f.write(notification_content)
        set_time_from_headers(res, notification_file)

        queue = []

        if not skip_snapshot:
            file_name = f"snapshot-{notification.serial}.xml"
            queue.append(
                get_and_check(
                    sem,
                    session,
                    output_path,
                    file_name,
                    notification.snapshot.uri,
                    notification.snapshot.hash,
                    override_host=override_host,
                    hash_in_name=include_hash,
                )
            )

        for idx, delta in enumerate(notification.deltas):
            if limit_deltas is not None and idx >= limit_deltas:
                break
            file_name = f"{delta.serial}.xml"
            queue.append(
                get_and_check(
                    sem,
                    session,
                    output_path,
                    file_name,
                    delta.uri,
                    delta.hash,
                    override_host=override_host,
                    hash_in_name=include_hash,
                )
            )

        status_per_file = await asyncio.gather(*queue)
        click.echo(
            f"{notification_url}: {len(queue)} files are present. Downloaded {sum(status_per_file)} files."
        )
    finally:
        if owns_session:
            await session.close()


@click.command("snapshot-rrdp")
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
    "--store-notification/--no-store-notification",
    help="Store notification.xml with serial in filename",
    default=True,
)
@click.option(
    "--threads", help="Number of download threads", type=int, default=os.cpu_count()
)
@click.option(
    "--limit-deltas", help="Number of deltas to include", type=int, default=None
)
def snapshot_rrdp_command(
    notification_url: str,
    output_dir: Path,
    override_host: str | None = None,
    include_session: bool = False,
    verbose: bool = False,
    skip_snapshot: bool = True,
    threads: int = 4,
    limit_deltas: int | None = None,
    create_target: bool = False,
    include_hash: bool = True,
    store_notification: bool = True,
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
            store_notification=store_notification,
        )
    )


if __name__ == "__main__":
    snapshot_rrdp_command()
