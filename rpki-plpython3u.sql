--
-- SELECT (UNNEST((mft_files.mft).file_list)).* from (SELECT parse_manifest(content) as mft FROM objects WHERE uri LIKE 'rsync://rpki.ripe.net/repository/aca/%.mft') as mft_files;
-- -> file_name, url, hash for all files on manifest

--
-- SELECT parse_manifest(content) AS mft, visibleon, disappearedon, hash, uri, publicationpoint FROM objects WHERE uri LIKE 'rsync://rpki.ripe.net/repository/aca/%.mft' limit 1;
--

--
-- SELECT manifest_sia(content) AS sia, manifest_aia(content) AS aia, visibleon, disappearedon FROM objects WHERE uri LIKE 'rsync://rpki.ripe.net/repository/ripe-ncc-ta.mft' limit 1;
--
CREATE EXTENSION IF NOT EXISTS plpython3u;

DROP TYPE IF EXISTS manifest_entry CASCADE;
CREATE TYPE manifest_entry AS (
    file_name text,
    url text,
    hash bytea
);
DROP TYPE manifest CASCADE;
CREATE TYPE manifest AS (
    authority_information_access text,
    file_list manifest_entry[]
);

DROP FUNCTION IF EXISTS parse_manifest;
CREATE FUNCTION parse_manifest(content text)
  RETURNS manifest
AS $$
import base64
from urllib.parse import urlparse

from rrdp_tools.rpki import parse_manifest

mft = parse_manifest(base64.b64decode(content))
sia = mft.subject_information_access

sia_url = urlparse(sia)

def relative_url(name: str) -> str:
    path = sia_url.path
    tokens = path.split("/")
    tokens[-1] = name

    return sia_url._replace(path="/".join(tokens)).geturl()

return {
    "authority_information_access": mft.authority_information_access,
    "subject_information_access": mft.subject_information_access,
    # add url to the objects to allow for further joins
    "file_list": [
        {
            "file_name": file.file_name,
            "hash": file.hash,
            "url": relative_url(file.file_name)
        } for file in mft.file_list
    ]
}
$$ LANGUAGE plpython3u;

DROP FUNCTION IF EXISTS manifest_sia;
CREATE FUNCTION manifest_sia(content text)
  RETURNS text
AS $$
import base64
from urllib.parse import urlparse

from rrdp_tools.rpki import parse_manifest

mft = parse_manifest(base64.b64decode(content))
return mft.subject_information_access
$$ LANGUAGE plpython3u;

DROP FUNCTION IF EXISTS manifest_aia;
CREATE FUNCTION manifest_aia(content text)
  RETURNS text
AS $$
import base64
from urllib.parse import urlparse

from rrdp_tools.rpki import parse_manifest

mft = parse_manifest(base64.b64decode(content))
return mft.authority_information_access
$$ LANGUAGE plpython3u;