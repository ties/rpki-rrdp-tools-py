import argparse
import base64
import hashlib
import logging
import sys
import time
import urllib.parse

from pathlib import Path

from lxml import etree
from rrdp import validate

from typing import TextIO

import requests

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)

def get_and_check(target_file: Path, uri: str, sha256: str) -> None:
    expected_hash = sha256.lower()

    if target_file.exists():
        with target_file.open("rb") as f:
            cur_hash = hashlib.sha256(f.read()).hexdigest()
            if cur_hash == expected_hash:
                LOG.debug("Already have %s as %s", uri, target_file)
                return
            else:
                LOG.info("Hash mismatch for %s", uri)

    LOG.debug("Getting %s h=%s target_file=%s", uri, expected_hash, target_file)

    t0 = time.time()
    res = requests.get(uri)
    LOG.info("Downloaded %s in %fs", uri, time.time()-t0)

    assert res.status_code == 200

    digest = hashlib.sha256(res.content).hexdigest()

    if digest != expected_hash:
        raise ValueError("Hash mismatch for %s, expected %s was %s", uri, expected_hash, digest)

    with target_file.open("wb") as f:
        f.write(res.content)

def snapshot_rrdp(notification_url: str, output_path: Path):
    res = requests.get(notification_url)
    doc = etree.fromstring(res.text)
    validate(doc)
    # Document is valid,
    snapshot = doc.find("{http://www.ripe.net/rpki/rrdp}snapshot")
    get_and_check(output_path / "snapshot.xml", snapshot.attrib["uri"], snapshot.attrib["hash"])

    LOG.info("Storing snapshot.xml")
    with (output_path / "notification.xml").open("w") as f:
        f.write(res.text)

    deltas = doc.findall("{http://www.ripe.net/rpki/rrdp}delta")
    for delta in deltas:
        uri = delta.attrib['uri']
        hash = delta.attrib['hash']
        serial = delta.attrib['serial']

        get_and_check(output_path / f"{serial}.xml", uri, hash)


def main():
    parser = argparse.ArgumentParser(
            description="""Save an RRDP repositories state (snapshot + deltas)"""
    )

    parser.add_argument('notification_url',
                        help='URL to notification.xml',
                        type=str
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
    if args.verbose:
        LOG.setLevel(logging.DEBUG)
    output_dir = Path(args.output_dir).resolve()

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    snapshot_rrdp(args.notification_url,
                     output_dir)


if __name__ == "__main__":
    main()
