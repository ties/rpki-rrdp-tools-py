import argparse
import base64
import io
import logging
import re
import sys
import urllib.parse

from pathlib import Path
from typing import TextIO

from lxml import etree
from rrdp import validate
import requests


logging.basicConfig()
LOG = logging.getLogger(__name__)


def reconstruct_repo(rrdp_file: TextIO, output_path: Path, filter_match: str):
    huge_parser = etree.XMLParser(encoding='utf-8',
                                  recover=False,
                                  huge_tree=True)
    doc = etree.parse(rrdp_file, parser=huge_parser)
    validate(doc)
    # Document is valid,

    def match(uri) -> bool:
        """Match against the regex in `filter_match` (default: accept)."""
        if filter_match:
            filename_pattern = re.compile(filter_match)
            return filename_pattern.search(uri)
        return True

    elems = doc.xpath("//*[local-name() = 'publish']")
    wrote = 0
    for elem in elems:
        uri = elem.attrib['uri']
        # Take the path component of the URI and build the directory for it
        tokens = urllib.parse.urlparse(uri)

        file_path = output_path / f"./{tokens.path}"
        if match(uri):
            # Ensure that output dir is a subdirectory and create if necessary
            assert output_path in file_path.parents
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'wb') as f:
                # Accept empty publish tags/empty files
                f.write(base64.b64decode(elem.text) if elem.text else b'')

            LOG.debug("Wrote '%s' to '%s'", uri, file_path)
            wrote += 1
        else:
            LOG.debug("skipped '%s': did not match filter.", uri)

    LOG.info("Wrote %i files to %s", wrote, output_path)


def main():
    parser = argparse.ArgumentParser(
            description="""Reconstruct repo state from snapshot xml.""")

    parser.add_argument('infile',
                        help='Name of the file containing the snapshot or delta',
                        type=str,
                        )
    parser.add_argument('--filename_pattern',
                        help='optional regular expression to filter filenames against',
                        type=str,
                        default=''
                        )
    parser.add_argument('output_dir',
                        help='output directory',
                        )
    parser.add_argument('-v',
                        '--verbose',
                        help='verbose',
                        action='store_true'
                        )



    args = parser.parse_args()
    output_dir = Path(args.output_dir).resolve()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)


    if re.match('^http(s)?://', args.infile):
        LOG.info("Downloading snapshot from %s", args.infile)
        req = requests.get(args.infile)
        assert req.status_code == 200
        infile = io.StringIO(req.text)
        LOG.info("snapshot has a size of %ib", len(req.content))
    else:
        infile = args.infile

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    reconstruct_repo(infile,
                     output_dir,
                     args.filename_pattern)


if __name__ == "__main__":
    main()
