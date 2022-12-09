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
from rrdp import validate
import requests

logging.basicConfig()
LOG = logging.getLogger(__name__)

NS_RRDP = "http://www.ripe.net/rpki/rrdp"


class RrdpOperation(Enum):
    PUBLISH = 1
    WITHDRAW = 2

    @staticmethod
    def from_tag(xml_tag: str) -> "RrdpOperation":
        if xml_tag in ("withdraw", "{http://www.ripe.net/rpki/rrdp}withdraw"):
            return RrdpOperation.WITHDRAW
        elif xml_tag in ("publish", "{http://www.ripe.net/rpki/rrdp}publish"):
            return RrdpOperation.PUBLISH

        raise ValueError(f"Unknown RRDP tag: '{xml_tag}'")


class RrdpElement(NamedTuple):
    uri: str
    hash: str
    operation: RrdpOperation

    def __repr__(self) -> str:
        if self.operation is RrdpOperation.PUBLISH:
            return f"publish uri={self.uri} hash={self.hash}"
        elif self.operation is RrdpOperation.WITHDRAW:
            return f"withdraw uri={self.uri} hash={self.hash}"


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
    huge_parser = etree.XMLParser(encoding="utf-8", recover=False, huge_tree=True)
    doc = etree.parse(rrdp_file, parser=huge_parser)
    validate(doc)
    # Document is valid,

    def match(uri) -> bool:
        """Match against the regex in `filter_match` (default: accept)."""
        if filter_match:
            filename_pattern = re.compile(filter_match)
            return filename_pattern.search(uri)
        return True

    root = doc.xpath("/rrdp:snapshot | /rrdp:delta", namespaces={"rrdp": NS_RRDP})
    if not root:
        raise ValueError(
            "XML is missing <snapshot> or <delta> tag in correct namespace."
        )
    elems = root[0].getchildren()
    wrote = 0

    seen_objects: Dict[str, Set[RrdpElement]] = defaultdict(set)
    for elem in elems:
        uri = elem.attrib["uri"]
        hash = elem.attrib.get("hash", None)
        operation = RrdpOperation.from_tag(elem.tag)
        # Take the path component of the URI and build the directory for it
        tokens = urllib.parse.urlparse(uri)
        content = base64.b64decode(elem.text) if elem.text else b""

        h = hashlib.sha256()
        h.update(content)
        h_content = h.hexdigest()

        if hash and h_content.lower() != hash:
            LOG.error("Hash mismatch: h(content)=%s attrib=%s", h_content, hash)
        if operation is RrdpOperation.WITHDRAW and not hash:
            LOG.error("withdraw uri=%s without hash.", uri)

        if uri in seen_objects:
            LOG.error(
                "Repeated entry for uri=%s.  h=%s. previous entries: %s",
                uri,
                h_content,
                seen_objects[uri],
            )

        seen_objects[uri].add(RrdpElement(uri, hash if hash else h_content, operation))

        file_path = output_path / f"./{tokens.path}"
        if match(uri):
            # Ensure that output dir is a subdirectory and create if necessary
            assert output_path in file_path.parents
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "wb") as f:
                # Accept empty publish tags/empty files
                f.write(content)

            LOG.debug("Wrote '%s' to '%s'", uri, file_path)
            wrote += 1
        else:
            LOG.debug("skipped '%s': did not match filter.", uri)

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
