import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import FrozenSet, Optional, Set

import asn1tools
import netaddr
from asn1crypto import cms, crl, x509

LOG = logging.getLogger(__name__)

asn1_src = Path(__file__).parent / "rpki_rfc.asn"
assert asn1_src.exists()
RPKI_RFC_ASN1 = asn1tools.compile_files(str(asn1_src), cache_dir="asn1")
#
# https://datatracker.ietf.org/doc/rfc3779/
#
OID_PE = "1.3.6.1.5.5.7.1"
OID_PE_IPADDR_BLOCKS = OID_PE + ".7"
OID_PE_AUTONOMOUS_SYS_IDS = OID_PE + ".8"

AFI_IPv4 = b"\x00\x01"
AFI_IPv6 = b"\x00\x02"


@dataclass(frozen=True, order=True)
class FileAndHash:
    file_name: str
    hash: bytes

    def __str__(self) -> str:
        return f"{self.file_name:} sha256={self.hash.hex()}"


@dataclass
class CertificateInfo:
    ip_resources: netaddr.IPSet
    as_resources: Set[str]


@dataclass
class ManifestInfo:
    manifest_number: int
    signing_time: datetime
    ee_certificate: x509.Certificate
    file_list: FrozenSet[FileAndHash]

    @property
    def authority_information_access(self) -> str:
        aia = self.ee_certificate.authority_information_access_value
        assert len(aia) == 1
        return aia[0].native["access_location"]


def parse_manifest(content: bytes) -> ManifestInfo:
    info = cms.ContentInfo.load(content)
    assert info["content_type"].native == "signed_data"
    signed_data = info["content"]
    signer = signed_data["signer_infos"][0]

    signing_time = None

    for attr in signer["signed_attrs"]:
        if attr["type"].native == "signing_time":
            signing_time = attr["values"][0].native

    mft = RPKI_RFC_ASN1.decode(
        "Manifest", signed_data["encap_content_info"]["content"].native
    )

    return ManifestInfo(
        manifest_number=mft["manifestNumber"],
        signing_time=signing_time,
        ee_certificate=signed_data["certificates"][0].chosen,
        file_list=frozenset(
            FileAndHash(file_name=entry["file"], hash=bytes(entry["hash"][0]))
            for entry in mft["fileList"]
        ),
    )


def extension_by_type(cert: x509.Certificate, oid: str) -> bytes:
    for ext in cert["tbs_certificate"]["extensions"]:
        if ext["extn_id"].native == oid:
            return ext["extn_value"].native
    raise ValueError(f"Extension {oid} not found")


class Afi(Enum):
    IPv4 = 1
    IPv6 = 2
    ASN = 3


@dataclass
class Rfc3779Extension:
    ipv4_resources: Optional[netaddr.IPSet]
    ipv6_resources: Optional[netaddr.IPSet]
    asn_resources: Set[str]

    inherit: Set[Afi]

    def __post_init__(self):
        # Inherit is mutually exclusive with the other types
        if Afi.ASN in self.inherit:
            assert not self.asn_resources
        if Afi.IPv4 in self.inherit:
            assert not self.ipv4_resources
        if Afi.IPv6 in self.inherit:
            assert not self.ipv6_resources

        # One type of resources needs to be present
        assert self.inherit or (
            self.ipv4_resources or self.ipv6_resources or self.asn_resources
        )


def parse_rfc3779_extension(ipaddr_extension: bytes) -> Rfc3779Extension:
    ipaddr_ext = RPKI_RFC_ASN1.decode("IPAddrBlocks", ipaddr_extension)

    for block in ipaddr_ext:
        afi, safi = block["addressFamily"][0:2], block["addressFamily"][2:]
        choice_type, choice_content = block["ipAddressChoice"]

        assert safi == b""
        assert afi in (AFI_IPv4, AFI_IPv6)
        ip_version = 4 if afi == AFI_IPv4 else 6

        ip_set = netaddr.IPSet()

        match choice_type:
            case "addressesOrRanges":
                for range in choice_content:
                    address_type, address_content = range
                    match address_type:
                        case "addressPrefix":
                            bits, mask = address_content
                            # expand bits to correct length
                            target_len = 128 // 8 if ip_version == 6 else 32 // 8
                            bits += b"\x00" * (target_len - len(bits))
                            # invariant
                            assert len(bits) == target_len

                            ip_as_int = int.from_bytes(
                                bits, byteorder="big", signed=False
                            )
                            # ensure that mask length matches prefix length
                            assert len(bin(ip_as_int)[2:].rstrip("0")) <= mask

                            addr = netaddr.IPNetwork(
                                (ip_as_int, mask), version=ip_version
                            )
                            ip_set.add(addr)
                        case "addressRange":
                            pass
                        case _:
                            raise ValueError("Unknown addressesOrRanges payload")
            case "inherit":
                pass
            case _:
                raise ValueError("Unknown RFC3779 structure")


def parse_certificate(content: bytes) -> CertificateInfo:
    cert = x509.Certificate.load(content)
    # extensions = cert.native['tbs_certificate']['extensions']
    # for ext in extensions:
    #     print(extensions)

    ipaddr_extension = extension_by_type(cert, OID_PE_IPADDR_BLOCKS)
    if ipaddr_extension:
        ipaddr = parse_rfc3779_extension(ipaddr_extension)
        print(ipaddr)

    return CertificateInfo(netaddr.IPSet(), set())


def parse_file_time(file_name: str, content: bytes) -> datetime:
    """
    Extract the file modification time (according to the current RPKI interpretation) from signed objects.
    """
    extension = file_name.split(".")[-1]

    match extension:
        case "crl":
            parsed_crl = crl.CertificateList.load(content)
            return parsed_crl["tbs_cert_list"]["this_update"].native
        case "cer":
            cert = x509.Certificate.load(content)

            return cert.not_valid_before
        case "mft" | "roa" | "asa" | "gbr" | "sig":
            info = cms.ContentInfo.load(content)
            signed_data = info["content"]
            signer = signed_data["signer_infos"][0]

            for attr in signer["signed_attrs"]:
                if attr["type"].native == "signing_time":
                    return attr["values"][0].native
    # Fallback to current time
    return datetime.now()
