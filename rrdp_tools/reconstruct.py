import argparse
import base64
import logging
import sys
import urllib.parse

from pathlib import Path

from lxml import etree
from rrdp import validate

from typing import TextIO

logging.basicConfig()
LOG = logging.getLogger(__name__)


def reconstruct_repo(rrdp_file: TextIO, output_path: Path):
    huge_parser = etree.XMLParser(encoding='utf-8',
                                  recover=False,
                                  huge_tree=True)
    doc = etree.parse(rrdp_file, parser=huge_parser)
    validate(doc)
    # Document is valid,

    elems = doc.xpath("//*[local-name() = 'publish']")
    for elem in elems:
        uri = elem.attrib['uri']
        # Take the path component of the URI and build the directory for it
        tokens = urllib.parse.urlparse(uri)

        file_path = output_path / f"./{tokens.path}"
        # Ensure that output dir is a subdirectory and create if necessary
        assert output_path in file_path.parents
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'wb') as f:
            # Accept empty publish tags/empty files
            f.write(base64.b64decode(elem.text) if elem.text else b'')

        LOG.info("Wrote '%s' to '%s'", uri, file_path)


def main():
    parser = argparse.ArgumentParser(
            description="""Reconstruct repo state from snapshot xml.""")

    parser.add_argument('infile',
                        help='Name of the file containing the snapshot or delta',
                        type=argparse.FileType('r'),
                        )
    parser.add_argument('output_dir',
                        help='output directory',
                        )

    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    reconstruct_repo(args.infile,
                     output_dir)


if __name__ == "__main__":
    main()
