import pytest

from rrdp_tools.http_client import client_session, default_user_agent


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
