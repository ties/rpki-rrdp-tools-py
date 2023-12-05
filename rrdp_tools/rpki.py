import logging
from datetime import datetime

from asn1crypto import cms, crl, x509

LOG = logging.getLogger(__name__)


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
