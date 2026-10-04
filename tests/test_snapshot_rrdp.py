import asyncio
import hashlib

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from rrdp_tools.http_client import (
    MAX_NOTIFICATION_SIZE,
    CrossOriginError,
    ResponseTooLargeError,
    client_session,
)
from rrdp_tools.snapshot_rrdp import get_and_check, snapshot_rrdp

CONTENT = b"<delta/>" * 100


@pytest_asyncio.fixture
async def server():
    async def delta(request: web.Request) -> web.Response:
        return web.Response(body=CONTENT)

    async def redirect(request: web.Request) -> web.Response:
        raise web.HTTPFound(request.query["to"])

    async def notification(request: web.Request) -> web.Response:
        # Snapshot on this server, the delta wherever ?delta= points.
        body = (
            '<notification xmlns="http://www.ripe.net/rpki/rrdp" version="1"'
            ' session_id="1c33ba5d-4e16-448d-9a22-b12599ef1cba" serial="2">'
            f'<snapshot uri="{request.url.with_path("/snapshot.xml").with_query(None)}"'
            f' hash="{"00" * 32}"/>'
            f'<delta serial="2" uri="{request.query["delta"]}" hash="{"00" * 32}"/>'
            "</notification>"
        )
        return web.Response(body=body.encode())

    app = web.Application()
    app.router.add_get("/1.xml", delta)
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/notification.xml", notification)

    async with TestServer(app) as test_server:
        yield test_server


async def _get(server, tmp_path, sha256, path="/1.xml"):
    async with client_session() as session:
        return await get_and_check(
            asyncio.Semaphore(1),
            session,
            tmp_path,
            "1.xml",
            str(server.make_url(path)),
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


@pytest.mark.asyncio
async def test_get_and_check_follows_same_origin_redirect(server, tmp_path):
    path = f"/redirect?to={server.make_url('/1.xml')}"
    assert await _get(server, tmp_path, hashlib.sha256(CONTENT).hexdigest(), path)

    assert (tmp_path / "1.xml").read_bytes() == CONTENT


@pytest.mark.asyncio
async def test_get_and_check_rejects_cross_origin_redirect(
    server, other_origin, tmp_path
):
    path = f"/redirect?to={other_origin.make_url('/1.xml')}"
    with pytest.raises(CrossOriginError):
        await _get(server, tmp_path, hashlib.sha256(CONTENT).hexdigest(), path)

    assert other_origin.requests == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_snapshot_rrdp_rejects_cross_origin_delta(server, other_origin, tmp_path):
    url = server.make_url("/notification.xml").with_query(
        delta=str(other_origin.make_url("/2.xml"))
    )

    with pytest.raises(CrossOriginError, match="not in the origin"):
        await snapshot_rrdp(str(url), tmp_path, skip_snapshot=True)

    # Rejected as a whole: nothing fetched, notification not stored.
    assert other_origin.requests == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_snapshot_rrdp_limit_deltas_skips_cross_origin_delta(
    server, other_origin, tmp_path
):
    # Only files that will be fetched are checked, as with skip_snapshot.
    url = server.make_url("/notification.xml").with_query(
        delta=str(other_origin.make_url("/2.xml"))
    )

    await snapshot_rrdp(str(url), tmp_path, skip_snapshot=True, limit_deltas=0)

    assert other_origin.requests == []
    assert [p.name for p in tmp_path.iterdir()] == ["notification.2.xml"]


DELTAS = 20


def _delta_content(serial: int) -> bytes:
    return f"<delta serial='{serial}'/>".encode()


@pytest_asyncio.fixture
async def repository():
    """A repository with DELTAS deltas, tracking concurrent delta requests.

    ?bad=<serial> advertises a wrong hash for that delta, ?pad=<bytes> pads
    the notification with whitespace.
    """
    state = {"active": 0, "max_active": 0}

    async def notification(request: web.Request) -> web.Response:
        bad = int(request.query.get("bad", 0))
        deltas = "".join(
            f'<delta serial="{serial}"'
            f' uri="{request.url.with_path(f"/d/{serial}.xml").with_query(None)}"'
            f' hash="{"00" * 32 if serial == bad else hashlib.sha256(_delta_content(serial)).hexdigest()}"/>'
            for serial in range(DELTAS, 0, -1)
        )
        body = (
            '<notification xmlns="http://www.ripe.net/rpki/rrdp" version="1"'
            f' session_id="1c33ba5d-4e16-448d-9a22-b12599ef1cba" serial="{DELTAS}">'
            f'<snapshot uri="{request.url.with_path("/snapshot.xml").with_query(None)}"'
            f' hash="{"00" * 32}"/>'
            f"{deltas}{' ' * int(request.query.get('pad', 0))}</notification>"
        )
        return web.Response(body=body.encode())

    async def delta(request: web.Request) -> web.Response:
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        try:
            await asyncio.sleep(0.01)
            return web.Response(body=_delta_content(int(request.match_info["serial"])))
        finally:
            state["active"] -= 1

    app = web.Application()
    app.router.add_get("/notification.xml", notification)
    app.router.add_get("/d/{serial}.xml", delta)

    async with TestServer(app) as test_server:
        test_server.state = state
        yield test_server


@pytest.mark.asyncio
async def test_snapshot_rrdp_fetches_all_deltas_with_bounded_workers(
    repository, tmp_path
):
    await snapshot_rrdp(
        str(repository.make_url("/notification.xml")),
        tmp_path,
        skip_snapshot=True,
        threads=3,
    )

    for serial in range(1, DELTAS + 1):
        assert (tmp_path / f"{serial}.xml").read_bytes() == _delta_content(serial)
    assert 1 <= repository.state["max_active"] <= 3


@pytest.mark.asyncio
async def test_snapshot_rrdp_failure_does_not_stop_other_downloads(
    repository, tmp_path
):
    url = repository.make_url("/notification.xml").with_query(bad=5)
    with pytest.raises(ValueError, match=f"1/{DELTAS} files failed"):
        await snapshot_rrdp(str(url), tmp_path, skip_snapshot=True, threads=3)

    assert not (tmp_path / "5.xml").exists()
    present = {p.name for p in tmp_path.glob("[0-9]*.xml")}
    assert present == {f"{s}.xml" for s in range(1, DELTAS + 1) if s != 5}


@pytest.mark.asyncio
async def test_snapshot_rrdp_rejects_large_notification(repository, tmp_path):
    url = repository.make_url("/notification.xml").with_query(pad=MAX_NOTIFICATION_SIZE)
    with pytest.raises(ResponseTooLargeError):
        await snapshot_rrdp(str(url), tmp_path, skip_snapshot=True)

    assert list(tmp_path.iterdir()) == []
