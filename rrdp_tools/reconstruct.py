import argparse
import base64
import hashlib
import io
import logging
import re
import sys
import urllib.parse

from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import TextIO, Dict, NamedTuple, Set

from lxml import etree
from .rrdp import validate, NS_RRDP, parse_snapshot_or_delta, PublishElement
import requests


logging.basicConfig()
LOG = logging.getLogger(__name__)


def http_get_delta_or_snapshot(uri: str) -> TextIO:
    LOG.info("Downloading from %s", uri)
    req = requests.get(uri)
    assert req.status_code == 200

    huge_parser = etree.XMLParser(encoding="utf-8", recover=False, huge_tree=True)
    doc = etree.fromstring(req.text, parser=huge_parser)

    if doc.tag == "{http://www.ripe.net/rpki/rrdp}notification":
        # Get the snapshot
        elem = doc.find("rrdp:snapshot", namespaces={"rrdp": NS_RRDP})
        uri = elem.attrib["uri"]
        LOG.info("found notification.xml with snapshot at %s", uri)

        req = requests.get(uri)
        assert req.status_code == 200

    LOG.info("%s has a size of %ib", uri, len(req.text))
    return io.StringIO(req.text)


def reconstruct_repo(rrdp_file: TextIO, output_path: Path, filter_match: str):
    def match(uri) -> bool:
        """Match against the regex in `filter_match` (default: accept)."""
        if filter_match:
            filename_pattern = re.compile(filter_match)
            return filename_pattern.search(uri)
        return True

    seen_objects: Dict[str, RrdpElement] = defaultdict(set)
    wrote = 0

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

        if isinstance(elem, PublishElement):
            if match(elem.uri):
                tokens = urllib.parse.urlparse(effective_uri)
                file_path = output_path / f"./{tokens.path}"
                # Ensure that output dir is a subdirectory and create if necessary
                assert output_path in file_path.parents
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "wb") as f:
                    # Accept empty publish tags/empty files
                    f.write(elem.content)

                LOG.debug("Wrote '%s' to '%s'", elem.uri, file_path)
                wrote += 1
            else:
                LOG.debug("skipped '%s': did not match filter.", elem.uri)

    LOG.info("Wrote %i files to %s", wrote, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="""Reconstruct repo state from snapshot xml."""
    )

    parser.add_argument(
        "infile",
        help="Name of the file containing the snapshot or delta",
        type=str,
    )
    parser.add_argument(
        "--filename_pattern",
        help="optional regular expression to filter filenames against",
        type=str,
        default="",
    )
    parser.add_argument(
        "output_dir",
        help="output directory",
    )
    parser.add_argument("-v", "--verbose", help="verbose", action="store_true")

    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    if re.match("^http(s)?://", args.infile):
        infile = http_get_delta_or_snapshot(args.infile)
    else:
        infile = args.infile

    reconstruct_repo(infile, output_dir, args.filename_pattern)


if __name__ == "__main__":
    main()
