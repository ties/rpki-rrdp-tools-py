import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import FrozenSet, Optional

import asn1tools
from asn1crypto import cms, crl, x509

LOG = logging.getLogger(__name__)

THIS_DIR = Path(__file__).parent

asn1_src = THIS_DIR / "rfc9286.asn"
assert asn1_src.exists()
# Try to cache the ASN1 if possible
try:
    RFC_9286_ASN1 = asn1tools.compile_files(
        str(asn1_src), cache_dir=str(THIS_DIR / "asn1")
    )
except:  # noqa
    RFC_9286_ASN1 = asn1tools.compile_files(str(asn1_src), cache_dir=None)

ID_AD_SIGNED_OBJECT = "1.3.6.1.5.5.7.48.11"


@dataclass
class RpkiSignedObject:
    signing_time: Optional[datetime]
    ee_certificate: x509.Certificate
    content: bytes


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


@dataclass(frozen=True, order=True)
class FileAndHash:
    file_name: str
    hash: bytes

    def __str__(self) -> str:
        return f"{self.file_name:} sha256={self.hash.hex()}"


@dataclass
class ManifestInfo:
    manifest_number: int
    signing_time: datetime
    this_update: datetime
    next_update: datetime
    ee_certificate: x509.Certificate
    file_list: FrozenSet[FileAndHash]

    @property
    def authority_information_access(self) -> str:
        aias = self.ee_certificate.authority_information_access_value.native
        for aia in aias:
            if aia["access_method"] == "ca_issuers":
                return aia["access_location"]

    @property
    def subject_information_access(self) -> str:
        sias = self.ee_certificate.subject_information_access_value.native
        for sia in sias:
            if sia["access_method"] == ID_AD_SIGNED_OBJECT:
                return sia["access_location"]
        return None


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
