"""
https://tools.ietf.org/html/rfc8182
"""
import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Generator, List, Optional, TextIO, Union
from xml.etree import ElementTree as ET

from lxml import etree
from lxml.etree import RelaxNG

LOG = logging.getLogger(__name__)

NS_RRDP = "http://www.ripe.net/rpki/rrdp"
NS_ET = f"{{{NS_RRDP}}}"

SCHEMA = RelaxNG.from_rnc_string(
    """
#
# RELAX NG schema for the RPKI Repository Delta Protocol (RRDP).
#

default namespace = "http://www.ripe.net/rpki/rrdp"

version = xsd:positiveInteger   { maxInclusive="1" }
serial  = xsd:positiveInteger
uri     = xsd:anyURI
uuid    = xsd:string            { pattern = "[\\-0-9a-fA-F]+" }
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


class UnexpectedDocumentException(Exception):
    pass


class ValidationException(Exception):
    pass


def validate(doc) -> None:
    try:
        SCHEMA.assert_(doc)
    except AssertionError as e:
        raise ValidationException(e)


@dataclass(unsafe_hash=True)
class PublishElement:
    uri: str
    previous_hash: Optional[str]
    content: bytes
    h_content: Union[str, None] = None

    def __post_init__(self) -> None:
        self.h_content = hashlib.sha256(self.content).hexdigest()

    def __repr__(self) -> str:
        return f"PublishElement[uri={self.uri}, previous_hash={self.previous_hash if self.previous_hash else 'N/A'}, sha256(content)={self.h_content}b"

    def to_xml(self, parent: ET.Element) -> None:
        attribs = {NS_ET + "uri": self.uri}
        if self.previous_hash:
            attribs[NS_ET + "hash"] = self.previous_hash

        node = ET.SubElement(parent, "{http://www.ripe.net/rpki/rrdp}publish", attribs)
        node.text = base64.b64encode(self.content).decode("utf-8")


@dataclass(unsafe_hash=True)
class WithdrawElement:
    uri: str
    hash: str

    def __repr__(self) -> str:
        return f"WithdrawElement[uri={self.uri}, hash={self.hash}"

    def to_xml(self, parent: ET.Element) -> None:
        attribs = {NS_ET + "uri": self.uri, NS_ET + "hash": self.hash}
        ET.SubElement(parent, "{http://www.ripe.net/rpki/rrdp}withdraw", attribs)


RrdpElement = Union[PublishElement, WithdrawElement]


@dataclass
class SnapshotElement:
    hash: str
    uri: str

    def to_xml(self, parent: ET.Element) -> None:
        attribs = {NS_ET + "uri": self.uri, NS_ET + "hash": self.hash}
        ET.SubElement(parent, "{http://www.ripe.net/rpki/rrdp}snapshot", attribs)


@dataclass
class DeltaDocument:
    serial: int
    session_id: str
    content: List[RrdpElement]

    def to_xml(self) -> ET.Element:
        attribs = {
            NS_ET + "serial": str(self.serial),
            NS_ET + "session_id": self.session_id,
            NS_ET + "version": "1",
        }
        root = ET.Element("{http://www.ripe.net/rpki/rrdp}delta", attribs)
        for elem_content in self.content:
            elem_content.to_xml(root)
        return root

    def __str__(self) -> str:
        return ET.tostring(self.to_xml(), default_namespace=NS_RRDP).decode("utf-8")


@dataclass
class SnapshotDocument:
    serial: int
    session_id: str
    content: List[PublishElement]

    def to_xml(self) -> ET.Element:
        attribs = {
            NS_ET + "serial": str(self.serial),
            NS_ET + "session_id": self.session_id,
            NS_ET + "version": "1",
        }
        root = ET.Element("{http://www.ripe.net/rpki/rrdp}snapshot", attribs)
        for elem_content in self.content:
            elem_content.to_xml(root)
        return root

    def __str__(self) -> str:
        return ET.tostring(self.to_xml(), default_namespace=NS_RRDP).decode("utf-8")


@dataclass
class DeltaElement:
    serial: int
    hash: str
    uri: str

    def to_xml(self, parent: ET.Element) -> None:
        attribs = {
            NS_ET + "serial": self.serial,
            NS_ET + "hash": self.hash,
            NS_ET + "uri": self.uri,
        }

        ET.SubElement(parent, "{http://www.ripe.net/rpki/rrdp}delta", attribs)


@dataclass
class NotificationDocument:
    snapshot: SnapshotElement
    deltas: list[DeltaElement]
    serial: int
    session_id: str

    def to_xml(self) -> ET.Element:
        attribs = {
            NS_ET + "serial": str(self.serial),
            NS_ET + "session_id": self.session_id,
            NS_ET + "version": "1",
        }
        root = ET.Element("{http://www.ripe.net/rpki/rrdp}notification", attribs)
        self.snapshot.to_xml(root)
        for delta in self.deltas:
            delta.to_xml(root)
        return root

    def __str__(self) -> str:
        return ET.tostring(self.to_xml(), default_namespace=NS_RRDP).decode("utf-8")


def parse_notification_file(notificiation_file: TextIO) -> NotificationDocument:
    huge_parser = etree.XMLParser(encoding="utf-8", recover=False, huge_tree=True)
    doc = etree.fromstring(notificiation_file, parser=huge_parser)
    validate(doc)

    snapshot_elem = doc.find("{http://www.ripe.net/rpki/rrdp}snapshot")
    snapshot = SnapshotElement(
        uri=snapshot_elem.attrib["uri"], hash=snapshot_elem.attrib["hash"]
    )

    delta_elements = doc.findall("{http://www.ripe.net/rpki/rrdp}delta")

    assert doc.tag == "{http://www.ripe.net/rpki/rrdp}notification"

    deltas = [
        DeltaElement(
            serial=delta.attrib["serial"],
            hash=delta.attrib["hash"],
            uri=delta.attrib["uri"],
        )
        for delta in delta_elements
    ]

    return NotificationDocument(
        snapshot=snapshot,
        deltas=deltas,
        serial=int(doc.attrib["serial"]),
        session_id=doc.attrib["session_id"],
    )


def parse_snapshot_or_delta(
    snapshot_or_delta: TextIO,
) -> DeltaDocument | SnapshotDocument:
    huge_parser = etree.XMLParser(encoding="utf-8", recover=False, huge_tree=True)
    doc = etree.parse(snapshot_or_delta, parser=huge_parser)
    validate(doc)
    # Document is valid

    nodes = doc.xpath("/rrdp:snapshot | /rrdp:delta", namespaces={"rrdp": NS_RRDP})
    if len(nodes) != 1:
        raise UnexpectedDocumentException(
            "document does not have <snapshot> or <delta> root tags"
        )
    root = nodes[0]
    serial = root.attrib["serial"]
    session_id = root.attrib["session_id"]

    if root.tag == "{http://www.ripe.net/rpki/rrdp}snapshot":
        return SnapshotDocument(
            serial=int(serial),
            session_id=session_id,
            content=list(parse_publish_withdraw(root)),
        )
    elif root.tag == "{http://www.ripe.net/rpki/rrdp}delta":
        return DeltaDocument(
            serial=int(serial),
            session_id=session_id,
            content=list(parse_publish_withdraw(root)),
        )


def parse_publish_withdraw(root: etree.Element) -> Generator[RrdpElement, None, None]:
    for elem in root.getchildren():
        elem_uri = elem.attrib["uri"]
        elem_hash = elem.get("hash", None)

        elem_content = base64.b64decode(elem.text) if elem.text else b""

        if elem.tag == "{http://www.ripe.net/rpki/rrdp}withdraw":
            if not elem_hash:
                LOG.error("withdraw uri=%s without hash provided.", elem_uri)
            yield WithdrawElement(elem_uri, elem_hash)
        elif elem.tag == "{http://www.ripe.net/rpki/rrdp}publish":
            pe = PublishElement(elem_uri, elem_hash, elem_content)
            # If the hash is present it is for replacing an element: can not compare it to content.

            yield pe
