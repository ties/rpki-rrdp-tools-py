"""
https://tools.ietf.org/html/rfc8182
"""
import base64
import hashlib
import logging

from lxml import etree
from lxml.etree import RelaxNG
from dataclasses import dataclass, InitVar
from typing import Generator, Optional, TextIO, Union


LOG = logging.getLogger(__name__)

NS_RRDP = "http://www.ripe.net/rpki/rrdp"

SCHEMA = RelaxNG.from_rnc_string(
    """#
# RELAX NG schema for the RPKI Repository Delta Protocol (RRDP).
#

default namespace = "http://www.ripe.net/rpki/rrdp"

version = xsd:positiveInteger   { maxInclusive="1" }
serial  = xsd:positiveInteger
uri     = xsd:anyURI
uuid    = xsd:string            { pattern = "[\-0-9a-fA-F]+" }
hash    = xsd:string            { pattern = "[0-9a-fA-F]+" }
base64  = xsd:base64Binary

# Notification File: lists current snapshots and deltas.

start |= element notification {
  attribute version    { version },
  attribute session_id { uuid },
  attribute serial     { serial },
  element snapshot {
    attribute uri  { uri },
    attribute hash { hash }
  },
  element delta {
    attribute serial { serial },
    attribute uri    { uri },
    attribute hash   { hash }
  }*
}

# Snapshot segment: think DNS AXFR.

start |= element snapshot {
  attribute version    { version },
  attribute session_id { uuid },
  attribute serial     { serial },
  element publish      {
    attribute uri { uri },
    base64
  }*
}

# Delta segment: think DNS IXFR.

start |= element delta {
 attribute version    { version },
 attribute session_id { uuid },
 attribute serial     { serial },
 delta_element+
}

delta_element |= element publish  {
 attribute uri  { uri },
 attribute hash { hash }?,
 base64
}

delta_element |= element withdraw {
 attribute uri  { uri },
 attribute hash { hash }
}

# Local Variables:
# indent-tabs-mode: nil
# comment-start: "# "
# comment-start-skip: "#[ \\t]*"
# End:
"""
)


def validate(doc) -> None:
    SCHEMA.assert_(doc)


@dataclass(unsafe_hash=True)
class PublishElement:
    uri: str
    hash: Optional[str]
    content: bytes
    h_content: Union[str, None] = None

    def __post_init__(self) -> None:
        h = hashlib.sha256()
        h.update(self.content)
        self.h_content = h.hexdigest()

    def __repr__(self) -> str:
        return f"PublishElement[uri={self.uri}, hash={self.hash.hex() if self.hash else 'N/A'}, sha256(content)={self.h_content}b"


@dataclass(unsafe_hash=True)
class WithdrawElement:
    uri: str
    hash: str

    def __repr__(self) -> str:
        return f"WithdrawElement[uri={self.uri}, hash={self.hash.hex()}"


@dataclass
class SnapshotElement:
    hash: str
    uri: str


@dataclass
class DeltaElement:
    hash: str
    uri: str


@dataclass
class NotificationElement:
    snapshot: SnapshotElement
    deltas: list[DeltaElement]
    serial: int
    session_id: str


RrdpElement = Union[PublishElement, WithdrawElement]


def parse_notification_file(notificiation_file: TextIO) -> NotificationElement:
    doc = etree.fromstring(notificiation_file)
    validate(doc)

    snapshot_elem = doc.find("{http://www.ripe.net/rpki/rrdp}snapshot")
    snapshot = SnapshotElement(
        uri=snapshot_elem.attrib["uri"], hash=snapshot_elem.attrib["hash"]
    )

    delta_elements = doc.findall("{http://www.ripe.net/rpki/rrdp}delta")
    deltas = []

    assert doc.tag == "{http://www.ripe.net/rpki/rrdp}notification"

    for delta in delta_elements:
        deltas.append(
            DeltaElement(
                hash=delta.attrib["hash"],
                uri=delta.attrib["uri"],
            )
        )

    return NotificationElement(
        snapshot=snapshot,
        deltas=deltas,
        serial=int(doc.attrib["serial"]),
        session_id=doc.attrib["session_id"],
    )


def parse_snapshot_or_delta(
    snapshot_or_delta: TextIO,
) -> Generator[Union[WithdrawElement, PublishElement], None, None]:
    huge_parser = etree.XMLParser(encoding="utf-8", recover=False, huge_tree=True)
    doc = etree.parse(snapshot_or_delta, parser=huge_parser)
    validate(doc)
    # Document is valid

    nodes = doc.xpath("/rrdp:snapshot | /rrdp:delta", namespaces={"rrdp": NS_RRDP})
    assert len(nodes) == 1
    root = nodes[0]

    for elem in root.getchildren():
        uri = elem.attrib["uri"]
        hash = elem.get("hash", None)

        content = base64.b64decode(elem.text) if elem.text else b""

        if elem.tag == "{http://www.ripe.net/rpki/rrdp}withdraw":
            if not hash:
                LOG.error("withdraw uri=%s without hash provided.", uri)
            yield WithdrawElement(uri, hash)
        elif elem.tag == "{http://www.ripe.net/rpki/rrdp}publish":
            pe = PublishElement(uri, hash, content)

            if hash and hash.lower() != pe.h_content:
                LOG.error(
                    "Hash mismatch for %s: h(content)=%s attrib=%s",
                    uri,
                    pe.h_content,
                    hash,
                )

            yield pe
