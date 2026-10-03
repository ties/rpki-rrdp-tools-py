import gzip
import hashlib
import io

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from rrdp_tools.http_client import (
    CHUNK_SIZE,
    MAX_CONTENTLEN,
    MAX_ERROR_BODY_SIZE,
    CrossOriginError,
    ResponseTooLargeError,
    client_session,
    default_user_agent,
    read_error_body,
    read_limited,
    restrict_origin,
    same_origin,
    write_limited,
)


def test_default_user_agent():
    assert default_user_agent().startswith("rrdp-tools/")


@pytest.mark.asyncio
async def test_session_default_user_agent():
    session = client_session()
    try:
        assert session.headers["User-Agent"] == default_user_agent()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_session_custom_user_agent():
    session = client_session("example-agent/1.0")
    try:
        assert session.headers["User-Agent"] == "example-agent/1.0"
    finally:
        await session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_timeout,expected_total",
    [(None, 60), (0, None), (30, 30)],
)
async def test_session_timeout(request_timeout, expected_total):
    session = client_session(request_timeout=request_timeout)
    try:
        assert session.timeout.total == expected_total
    finally:
        await session.close()


@pytest_asyncio.fixture
async def server():
    async def fixed(request: web.Request) -> web.Response:
        return web.Response(body=b"x" * 100)

    async def chunked(request: web.Request) -> web.StreamResponse:
        # No Content-Length: only the streamed byte count can stop it.
        response = web.StreamResponse()
        response.enable_chunked_encoding()
        await response.prepare(request)
        for _ in range(10):
            await response.write(b"x" * 100)
        await response.write_eof()
        return response

    async def gzipped(request: web.Request) -> web.Response:
        # Small on the wire, 1000 bytes once decompressed.
        return web.Response(
            body=gzip.compress(b"x" * 1000), headers={"Content-Encoding": "gzip"}
        )

    async def large(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.enable_chunked_encoding()
        await response.prepare(request)
        for _ in range(10):
            await response.write(b"x" * CHUNK_SIZE)
        await response.write_eof()
        return response

    async def error(request: web.Request) -> web.Response:
        return web.Response(status=500, body=b"e" * 10_000)

    async def redirect(request: web.Request) -> web.Response:
        raise web.HTTPFound(request.query["to"])

    app = web.Application()
    app.router.add_get("/redirect", redirect)
    app.router.add_get("/fixed", fixed)
    app.router.add_get("/chunked", chunked)
    app.router.add_get("/gzipped", gzipped)
    app.router.add_get("/large", large)
    app.router.add_get("/error", error)

    async with TestServer(app) as test_server:
        yield test_server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, size", [("/fixed", 100), ("/chunked", 1000), ("/gzipped", 1000)]
)
async def test_read_limited_within_limit(server, path, size):
    async with client_session() as session, session.get(server.make_url(path)) as res:
        chunks = [chunk async for chunk in read_limited(res, max_size=size)]
        assert b"".join(chunks) == b"x" * size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, match",
    [
        ("/fixed", "Content-Length 100 exceeds"),
        ("/chunked", "body exceeds"),
        ("/gzipped", "body exceeds"),
    ],
)
async def test_read_limited_too_large(server, path, match):
    async with client_session() as session, session.get(server.make_url(path)) as res:
        with pytest.raises(ResponseTooLargeError, match=match):
            async for _ in read_limited(res, max_size=99):
                pass


@pytest.mark.asyncio
async def test_read_limited_yields_before_limit(server):
    max_size = 3 * CHUNK_SIZE
    chunks = []
    async with (
        client_session() as session,
        session.get(server.make_url("/large")) as res,
    ):
        with pytest.raises(ResponseTooLargeError, match="body exceeds"):
            async for chunk in read_limited(res, max_size=max_size):
                chunks.append(len(chunk))

    # Chunks are passed on as they arrive, at most CHUNK_SIZE each, and
    # never beyond the limit.
    assert chunks
    assert max(chunks) <= CHUNK_SIZE
    assert sum(chunks) <= max_size


@pytest.mark.asyncio
async def test_write_limited(server):
    f = io.BytesIO()
    async with (
        client_session() as session,
        session.get(server.make_url("/gzipped")) as res,
    ):
        digest, size = await write_limited(res, f)

    assert f.getvalue() == b"x" * 1000
    assert size == 1000
    assert digest == hashlib.sha256(b"x" * 1000).hexdigest()


@pytest.mark.asyncio
async def test_read_error_body_is_truncated(server):
    async with (
        client_session() as session,
        session.get(server.make_url("/error")) as res,
    ):
        assert await read_error_body(res) == "e" * MAX_ERROR_BODY_SIZE


def test_max_contentlen_matches_rpki_client():
    assert MAX_CONTENTLEN == 2 * 1024 * 1024 * 1024


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ("https://rrdp.example.org/n.xml", "https://rrdp.example.org/s/1.xml", True),
        ("https://RRDP.example.org/n.xml", "https://rrdp.example.org/", True),
        ("https://rrdp.example.org:443/n.xml", "https://rrdp.example.org/", True),
        ("http://rrdp.example.org:80/n.xml", "http://rrdp.example.org/", True),
        ("https://rrdp.example.org/n.xml", "http://rrdp.example.org/n.xml", False),
        ("https://rrdp.example.org/n.xml", "https://rrdp.example.org:8443/", False),
        ("https://rrdp.example.org/n.xml", "https://example.org/n.xml", False),
        ("https://rrdp.example.org/n.xml", "https://rrdp.example.org.evil/", False),
    ],
)
def test_same_origin(a, b, expected):
    assert same_origin(a, b) is expected
    assert same_origin(b, a) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("absolute", [True, False])
async def test_restrict_origin_follows_same_origin_redirect(server, absolute):
    target = server.make_url("/fixed") if absolute else "/fixed"
    url = server.make_url("/redirect").with_query(to=str(target))

    async with (
        client_session() as session,
        session.get(url, middlewares=(restrict_origin(url),)) as res,
    ):
        assert res.status == 200
        assert res.url == server.make_url("/fixed")
        assert len(res.history) == 1


@pytest.mark.asyncio
async def test_restrict_origin_rejects_cross_origin_redirect(server, other_origin):
    url = server.make_url("/redirect").with_query(
        to=str(other_origin.make_url("/secret"))
    )

    async with client_session() as session:
        with pytest.raises(CrossOriginError, match="not in the origin"):
            await session.get(url, middlewares=(restrict_origin(url),))

    assert other_origin.requests == []


@pytest.mark.asyncio
async def test_restrict_origin_rejects_initial_request(server, other_origin):
    async with client_session() as session:
        with pytest.raises(CrossOriginError):
            await session.get(
                other_origin.make_url("/secret"),
                middlewares=(restrict_origin(server.make_url("/")),),
            )

    assert other_origin.requests == []
