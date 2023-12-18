import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

import asn1tools
from asn1crypto import cms, crl, x509

LOG = logging.getLogger(__name__)

asn1_src = Path(__file__).parent / "rfc9286.asn"
assert asn1_src.exists()
RFC_9286_ASN1 = asn1tools.compile_files(str(asn1_src), cache_dir="asn1")


@dataclass
class FileAndHash:
    file_name: str
    hash: bytes


@dataclass
class ManifestInfo:
    manifest_number: int
    signing_time: datetime
    ee_certificate: x509.Certificate
    file_list: List[FileAndHash]


def parse_manifest(content: bytes) -> ManifestInfo:
    info = cms.ContentInfo.load(content)
    assert info["content_type"].native == "signed_data"
    signed_data = info["content"]
    signer = signed_data["signer_infos"][0]

    signing_time = None

    for attr in signer["signed_attrs"]:
        if attr["type"].native == "signing_time":
            signing_time = attr["values"][0].native

    mft = RFC_9286_ASN1.decode(
        "Manifest", signed_data["encap_content_info"]["content"].native
    )

    return ManifestInfo(
        manifest_number=mft["manifestNumber"],
        signing_time=signing_time,
        ee_certificate=signed_data["certificates"][0].chosen,
        file_list=[
            FileAndHash(file_name=entry["file"], hash=entry["hash"][0])
            for entry in mft["fileList"]
        ],
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
