import logging
import multiprocessing
import sys
import time
import asyncio
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import click

logging.basicConfig()

LOG = logging.getLogger(Path(__file__).name)
LOG.setLevel(logging.INFO)


@dataclass
class Download:
    target_file: Path
    uri: str

async def get_and_check(i: int, session: aiohttp.ClientSession, download: Download) -> None:
    t0 = time.time()
    async with session.get(download.uri) as response:
        LOG.debug("[%d] HTTP %d %.3fs", i, response.status, time.time() - t0)
        if response.status == 200:
            with open(download.target_file, "wb") as f:
                f.write(await response.read())
            LOG.info("[%d] Downloaded %s to %s in %.3fs", i, download.uri, download.target_file, time.time() - t0)
        else:
            raise ValueError(f"Got status {response.status} for {download.uri}")

async def worker(i: int, session: aiohttp.ClientSession, queue: asyncio.Queue[Download]) -> int:
    processed = 0
    while not queue.empty():
        download = await queue.get()
        processed += 1
        try:
            await get_and_check(i, session, download)
        except Exception as e:
            LOG.error(e)
        finally:
            queue.task_done()

    return processed


async def attempt_delta_download(
    url_template: str, base_path: Path, min_delta: int, max_delta: int
) -> None:
    queue = asyncio.Queue()
    
    for delta_number in range(min_delta, max_delta):
        await queue.put(Download(base_path / f"{delta_number}.xml", url_template.format(delta_number)))

    async with aiohttp.ClientSession() as session:
            workers = [worker(i, session, queue) for i in range(multiprocessing.cpu_count())]

            statuses = await asyncio.gather(*workers)
            await queue.join()

            for status in statuses:
                LOG.info("Processed %d downloads", status)

@click.command()
@click.argument("url_template", type=str)
@click.argument("start", type=int)
@click.argument("end", type=int)
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True, writable=True, path_type=Path))
@click.option("--verbose", help="verbose", count=True)
def main(url_template: str, start: int, end: int, output_dir: Path, verbose: bool):
    """Loop over all the static guesses for the delta URL

    URL_TEMPLATE: URL to template the delta number into, {} will be replaced with delta number (e.g. https://rrdp.ripe.net/66221b75-cf14-4693-99e4-96ce9717c874/{}/delta.xml)
    START: Minimum number to template
    END: Final number to template
    OUTPUT_DIR: Directory to write files to
    """
    if verbose:
        LOG.setLevel(logging.DEBUG)

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", output_dir)
        sys.exit(2)

    asyncio.run(attempt_delta_download(url_template, output_dir, start, end))


if __name__ == "__main__":
    main()
