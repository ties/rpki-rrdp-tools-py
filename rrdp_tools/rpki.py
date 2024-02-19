import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import FrozenSet, Optional

import asn1tools
from asn1crypto import cms, crl, x509

LOG = logging.getLogger(__name__)

RFC9286_ASN1_SRC = Path(__file__).parent / "rfc9286.asn"
assert RFC9286_ASN1_SRC.exists()
RFC_9286_ASN1 = asn1tools.compile_files(str(RFC9286_ASN1_SRC), cache_dir="asn1")

DRAFT_SIGNED_PREFIX_LIST_ASN1_SRC = (
    Path(__file__).parent / "draft-ietf-sidrops-rpki-prefixlist-02-no-class-keyword.asa"
)
assert DRAFT_SIGNED_PREFIX_LIST_ASN1_SRC.exists()
DRAFT_SIGNED_PREFIX_LIST_ASN1 = asn1tools.compile_files(
    str(DRAFT_SIGNED_PREFIX_LIST_ASN1_SRC), cache_dir="asn1"
)


@dataclass
class RpkiSignedObject:
    signing_time: Optional[datetime]
    ee_certificate: x509.Certificate
    content: bytes


@dataclass(frozen=True, order=True)
class FileAndHash:
    """A file entry on a manifest"""

    file_name: str
    hash: bytes

    def __str__(self) -> str:
        return f"{self.file_name:} sha256={self.hash.hex()}"


@dataclass
class ManifestInfo:
    """A RPKI manifest"""

    manifest_number: int
    signing_time: datetime
    this_update: datetime
    next_update: datetime
    ee_certificate: x509.Certificate
    file_list: FrozenSet[FileAndHash]

    @property
    def authority_information_access(self) -> str:
        aia = self.ee_certificate.authority_information_access_value
        assert len(aia) == 1
        return aia[0].native["access_location"]


def parse_rpki_signed_object(content: bytes) -> RpkiSignedObject:
    info = cms.ContentInfo.load(content)
    assert info["content_type"].native == "signed_data"
    signed_data = info["content"]
    signer = signed_data["signer_infos"][0]

    signing_time = None

    for attr in signer["signed_attrs"]:
        if attr["type"].native == "signing_time":
            signing_time = attr["values"][0].native

    return RpkiSignedObject(
        signing_time,
        signed_data["certificates"][0].chosen,
        signed_data["encap_content_info"]["content"].native,
    )


def parse_manifest(content: bytes) -> ManifestInfo:
    so = parse_rpki_signed_object(content)

    mft = RFC_9286_ASN1.decode(
        "Manifest",
        so.content,
    )

    return ManifestInfo(
        manifest_number=mft["manifestNumber"],
        signing_time=so.signing_time,
        this_update=mft["thisUpdate"],
        next_update=mft["nextUpdate"],
        ee_certificate=so.ee_certificate,
        file_list=frozenset(
            FileAndHash(file_name=entry["file"], hash=bytes(entry["hash"][0]))
            for entry in mft["fileList"]
        ),
    )


def parse_signed_prefix_list(content: bytes) -> object:
    so = parse_rpki_signed_object(content)

    spl = DRAFT_SIGNED_PREFIX_LIST_ASN1.decode(
        "RpkiSignedPrefixList",
        so.content,
    )

    #
    # TODO:
    # * extract ASN
    # * use rfc3779 parser to get the payload
    # * apply extra validation to restrict it to the valid subset of rfc3779.
    #

    return spl


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
