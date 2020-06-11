import argparse
import base64
import logging
import os
import sys
import urllib.parse

from lxml import etree
from rrdp import validate

from typing import TextIO

logging.basicConfig()
LOG = logging.getLogger(__name__)


def reconstruct_repo(rrdp_file: TextIO, output_path: str):
    doc = etree.parse(rrdp_file)
    validate(doc)
    # Document is valid,

    elems = doc.xpath("//*[local-name() = 'publish']")
    for elem in elems:
        uri = elem.attrib['uri']
        # Take the path component of the URI and build the directory for it
        tokens = urllib.parse.urlparse(uri)
        file_path = os.path.normpath(os.path.join(output_path, f"./{tokens.path}"))

        target_dir = os.path.dirname(file_path)

        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        with open(file_path, 'wb') as f:
            f.write(base64.b64decode(elem.text))

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
    if not os.path.isdir(args.output_dir):
        parser.print_help()
        sys.exit(2)

    reconstruct_repo(args.infile,
                     os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
