import asyncio
import hashlib

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from rrdp_tools.http_client import client_session
from rrdp_tools.snapshot_rrdp import get_and_check

CONTENT = b"<delta/>" * 100


@pytest_asyncio.fixture
async def server():
    async def delta(request: web.Request) -> web.Response:
        return web.Response(body=CONTENT)

    app = web.Application()
    app.router.add_get("/1.xml", delta)

    async with TestServer(app) as test_server:
        yield test_server


async def _get(server, tmp_path, sha256):
    async with client_session() as session:
        return await get_and_check(
            asyncio.Semaphore(1),
            session,
            tmp_path,
            "1.xml",
            str(server.make_url("/1.xml")),
            sha256,
            override_host=None,
        )


@pytest.mark.asyncio
async def test_get_and_check_writes_file(server, tmp_path):
    assert await _get(server, tmp_path, hashlib.sha256(CONTENT).hexdigest())

    assert (tmp_path / "1.xml").read_bytes() == CONTENT
    assert [p.name for p in tmp_path.iterdir()] == ["1.xml"]


@pytest.mark.asyncio
async def test_get_and_check_hash_mismatch_keeps_existing_file(server, tmp_path):
    (tmp_path / "1.xml").write_bytes(b"old")

    with pytest.raises(ValueError, match="Hash mismatch"):
        await _get(server, tmp_path, "00" * 32)

    # The streamed download is discarded, the existing file is left alone.
    assert (tmp_path / "1.xml").read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["1.xml"]
