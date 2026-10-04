import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer


@pytest_asyncio.fixture
async def other_origin():
    """A server on another port (so another origin), recording requested paths.

    Answers every path, so tests can check that it was never contacted.
    """
    requests: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        requests.append(request.path)
        return web.Response(body=b"other origin")

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)

    async with TestServer(app) as test_server:
        test_server.requests = requests
        yield test_server
