import asyncio
import logging
import multiprocessing
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import click

from .http_client import client_session, restrict_origin, write_limited
from .logging_config import LOG_LEVELS, configure_logging
from .workers import run_workers

LOG = logging.getLogger(__name__)


@dataclass
class Download:
    target_file: Path
    uri: str


async def get_and_check(session: aiohttp.ClientSession, download: Download) -> None:
    t0 = time.time()
    async with session.get(
        download.uri, middlewares=(restrict_origin(download.uri),)
    ) as response:
        LOG.debug("%s: HTTP %d %.3fs", download.uri, response.status, time.time() - t0)
        if response.status == 200:
            with download.target_file.open("wb") as f:
                await write_limited(response, f)
            LOG.info(
                "Downloaded %s to %s in %.3fs",
                download.uri,
                download.target_file,
                time.time() - t0,
            )
        else:
            raise ValueError(f"Got status {response.status} for {download.uri}")


async def attempt_delta_download(
    url_template: str, base_path: Path, min_delta: int, max_delta: int
) -> None:
    downloads = [
        Download(base_path / f"{delta_number}.xml", url_template.format(delta_number))
        for delta_number in range(min_delta, max_delta)
    ]

    async with client_session() as session:
        _, failures = await run_workers(
            downloads,
            lambda download: get_and_check(session, download),
            multiprocessing.cpu_count(),
        )

    for _, e in failures:
        LOG.error(e)
    LOG.info("Processed %d downloads, %d failed", len(downloads), len(failures))


@click.command()
@click.argument("url_template", type=str)
@click.argument("start", type=int)
@click.argument("end", type=int)
@click.argument(
    "output_dir",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, writable=True, path_type=Path
    ),
)
@click.option("-v", "--verbose", count=True, help="-v: debug, -vv: also aiohttp etc.")
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    envvar="RRDP_LOG_LEVEL",
    default=None,
    help="Set an explicit level for all loggers, overriding -v",
)
def loop_over_deltas(
    url_template: str,
    start: int,
    end: int,
    output_dir: Path,
    verbose: int,
    log_level: str | None,
):
    """Loop over all the static guesses for the delta URL

    URL_TEMPLATE: URL to template the delta number into, {} will be replaced with delta number (e.g. https://rrdp.ripe.net/66221b75-cf14-4693-99e4-96ce9717c874/{}/delta.xml)
    START: Minimum number to template
    END: Final number to template
    OUTPUT_DIR: Directory to write files to
    """
    configure_logging(verbose, log_level=log_level)

    if not output_dir.is_dir():
        LOG.error("Output directory %s does not exist", output_dir)
        sys.exit(2)

    asyncio.run(attempt_delta_download(url_template, output_dir, start, end))


if __name__ == "__main__":
    loop_over_deltas()
