import argparse
import hashlib
import logging
import sys
import time
import urllib.parse

from pathlib import Path
from typing import TextIO, Optional

from lxml import etree

import requests


from .rrdp import validate

logging.basicConfig()
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def get_and_check(
    target_file: Path, uri: str, sha256: str, override_host: Optional[str]
) -> None:
    expected_hash = sha256.lower()

    if target_file.exists():
        with target_file.open("rb") as f:
            cur_hash = hashlib.sha256(f.read()).hexdigest()
            if cur_hash == expected_hash:
                LOG.debug("Already have %s as %s", uri, target_file)
                return
            else:
                LOG.info("Hash for %s does not match, downloading %s", target_file, uri)

    if override_host:
        # override the URI
        tokens = list(urllib.parse.urlparse(uri))
        override_tokens = urllib.parse.urlparse(override_host)
        # [scheme, host, ...]
        tokens[0] = override_tokens[0]
        tokens[1] = override_tokens[1]

        uri = urllib.parse.urlunparse(tokens)

    LOG.debug("Getting %s h=%s target_file=%s", uri, expected_hash, target_file)

    t0 = time.time()
    res = requests.get(uri)
    print(f"  * {len(res.content):>11}b   {time.time() - t0:.3f}s   {uri}")

    assert res.status_code == 200

    digest = hashlib.sha256(res.content).hexdigest()

    if digest != expected_hash:
        raise ValueError(
            f"Hash mismatch for downloaded file. Expected {expected_hash} actual {digest} at {uri}"
        )

    with target_file.open("wb") as f:
        f.write(res.content)


def snapshot_rrdp(
    notification_url: str,
    output_path: Path,
    override_host: str,
    skip_snapshot: bool = False,
    include_session: bool = False
):
    """Snapshot RRDP content."""

    res = requests.get(notification_url)
    if res.status_code != 200:
        print(f"HTTP {res.status_code} from RRDP server, aborting")
        print(f"reason: {res.text}")
        return
    doc = etree.fromstring(res.text)
    validate(doc)

    if include_session:
        # If session_id is present in notification tag, add it to path
        assert doc.tag == "{http://www.ripe.net/rpki/rrdp}notification"
        session_id = doc.attrib.get("session_id")
        if session_id:
            output_path = output_path / session_id
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            print("Error: No session_id in notification file!")
            sys.exit(1)

    # Document is valid,
    with (output_path / "notification.xml").open("w") as f:
        f.write(res.text)

    snapshot = doc.find("{http://www.ripe.net/rpki/rrdp}snapshot")
    if not skip_snapshot:
        get_and_check(
            output_path / "snapshot.xml",
            snapshot.attrib["uri"],
            snapshot.attrib["hash"],
            override_host=override_host,
        )

    deltas = doc.findall("{http://www.ripe.net/rpki/rrdp}delta")
    for delta in deltas:
        serial = delta.attrib["serial"]
        get_and_check(
            output_path / f"{serial}.xml",
            delta.attrib["uri"],
            delta.attrib["hash"],
            override_host=override_host,
        )


def main():
    parser = argparse.ArgumentParser(
        description="""Save an RRDP repositories state (snapshot + deltas)"""
    )

    parser.add_argument("notification_url", help="URL to notification.xml", type=str)
    parser.add_argument(
        "output_dir",
        help="output directory",
    )
    parser.add_argument(
        "--override_host",
        help="[protocol]://hostname to override",
    )
    parser.add_argument(
        "--include-session",
        help="Include session ID in path",
        action="store_true"
    )
    parser.add_argument("-v", "--verbose", help="verbose", action="store_true")
    parser.add_argument("--skip_snapshot", help="verbose", action="store_true")

    args = parser.parse_args()
    if args.verbose:
        LOG.setLevel(logging.DEBUG)
    output_dir = Path(args.output_dir).resolve()

    if not output_dir.is_dir():
        LOG.error("Output directory {} does not exist", args.output_dir)
        parser.print_help()
        sys.exit(2)

    snapshot_rrdp(
        args.notification_url,
        output_dir,
        override_host=args.override_host,
        skip_snapshot=args.skip_snapshot,
        include_session=args.include_session,
    )


if __name__ == "__main__":
    main()
