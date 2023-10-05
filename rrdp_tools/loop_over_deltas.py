import argparse
import base64
import logging
import sys
import time
import urllib.parse
from pathlib import Path
from typing import TextIO

import requests
from lxml import etree

from .rrdp import validate

logging.basicConfig()

LOG = logging.getLogger(Path(__file__).name)
LOG.setLevel(logging.INFO)


def get_and_check(target_file: Path, uri: str) -> None:
    if not target_file.exists():
        LOG.debug("Getting %s target_file=%s", uri, target_file)

        t0 = time.time()
        res = requests.get(uri)
        LOG.info("%d %s in %fs", res.status_code, uri, time.time() - t0)

        if res.status_code != 200:
            raise ValueError("HTTP %d for %s", res.status_code, uri)

        with target_file.open("wb") as f:
            f.write(res.content)


def attempt_delta_download(
    url_template: str, base_path: Path, min_delta: int, max_delta: int
) -> None:
    for delta_number in range(min_delta, max_delta):
        try:
            get_and_check(
                base_path / f"{delta_number}.xml", url_template.format(delta_number)
            )
        except ValueError as e:
            LOG.error(e)


def main():
    parser = argparse.ArgumentParser(
        description="""Loop over all the static guesses for the delta URL"""
    )

    parser.add_argument(
        "url_template",
        help="URL to template the delta number into, {} will be replaced with delta number (e.g. https://rrdp.ripe.net/66221b75-cf14-4693-99e4-96ce9717c874/{}/delta.xml)",
        type=str,
    )
    parser.add_argument("start", help="Minimum number to template", type=int)
    parser.add_argument("end", help="Final number to template", type=int)
    parser.add_argument(
        "output_dir",
        help="output directory",
    )
    parser.add_argument("-v", "--verbose", help="verbose", action="store_true")

    args = parser.parse_args()
    if args.verbose:
        LOG.setLevel(logging.DEBUG)
    output_dir = Path(args.output_dir).resolve()

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    attempt_delta_download(args.url_template, output_dir, args.start, args.end)


if __name__ == "__main__":
    main()
