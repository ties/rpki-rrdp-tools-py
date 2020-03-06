import argparse
import logging
import os
import sys
import urllib

from lxml import etree


logging.basicConfig()
LOG = logging.getLogger(__name__)


def reconstruct_repo(snapshot_text: str, url_prefix: str, output_path: str):
    doc = etree.fromstring(snapshot_text)

    if not os.path.isdir(output_path):
        raise ValueError(f"{os.path.abspath(output_path)} is not a directory.")

    # Saved XML by chrome contains "http://www.ripe.net/rpki/rrdp" as prefix

    elems = doc.xpath("//*[local-name() = 'publish']")
    for elem in elems:
        uri = elem.attrib['uri']
        if not uri.startswith(url_prefix):
            raise ValueError(f"uri ({uri}) does not start with prefix {url_prefix}")

        tokens = urllib.parse.urlparse(uri)
        file_path = os.path.normpath(os.path.join(output_path, f"./{tokens.path}"))

        target_dir = os.path.dirname(file_path)

        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)

        with open(file_path, 'w') as f:
            f.write(elem.text)

        LOG.info("Wrote {} to {}", uri, file_path)


def main():
    parser = argparse.ArgumentParser(
            description="""Reconstruct repo state from snapshot xml.""")

    parser.add_argument('--snapshot',
                        help='Name of the file containing the snapshot',
                        default='snapshot.xml')
    parser.add_argument('--url-prefix',
                        dest="url_prefix",
                        help='URL prefix to cut off (e.g. rsync://rsync.ripe.net)'
                        )
    parser.add_argument('--output-dir',
                        dest="output_dir",
                        help='output directory'
                        )


    args = parser.parse_args()

    if not args.url_prefix or not args.output_dir:
        parser.print_help()
        sys.exit(2)
    else:
        with open(args.snapshot, 'rb') as f:
            reconstruct_repo(f.read(),
                             args.url_prefix,
                             os.path.abspath(args.output_dir))


if __name__ == "__main__":
    main()
