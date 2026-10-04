import hashlib
import importlib.metadata
from collections.abc import AsyncIterator
from typing import BinaryIO

import aiohttp
from aiohttp import ClientHandlerType, ClientMiddlewareType, ClientRequest
from yarl import URL

DEFAULT_REQUEST_TIMEOUT = 60

# Maximum (decompressed) response body size, as MAX_CONTENTLEN in rpki-client's
# http.c.
MAX_CONTENTLEN = 2 * 1024**3
# Notifications are parsed in memory (rpki-client streams them instead). A few
# MB of delta URLs is fine; larger notifications are not plausible.
MAX_NOTIFICATION_SIZE = 16 * 1024**2
CHUNK_SIZE = 64 * 1024
# Error bodies are only logged.
MAX_ERROR_BODY_SIZE = 1024


class ResponseTooLargeError(ValueError):
    pass


class CrossOriginError(ValueError):
    pass


def same_origin(a: str | URL, b: str | URL) -> bool:
    """Whether two URLs have the same scheme, host and (effective) port.

    As valid_origin in rpki-client. Compares the parts rather than
    URL.origin(), which treats an explicit default port as different.
    """
    a, b = URL(a), URL(b)
    return (a.scheme, a.host, a.port) == (b.scheme, b.host, b.port)


def restrict_origin(url: str | URL) -> ClientMiddlewareType:
    """Client middleware that rejects requests outside the origin of `url`.

    Middlewares run for every request in a redirect chain, so this also
    rejects cross-origin redirects before they are followed.
    """

    async def middleware(
        req: ClientRequest, handler: ClientHandlerType
    ) -> aiohttp.ClientResponse:
        if not same_origin(req.url, url):
            raise CrossOriginError(f"{req.url} is not in the origin of {url}")
        return await handler(req)

    return middleware


def default_user_agent() -> str:
    try:
        version = importlib.metadata.version("rrdp-tools")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"
    return f"rrdp-tools/{version}"


def client_session(
    user_agent: str | None = None,
    request_timeout: int | None = None,
    **kwargs,
) -> aiohttp.ClientSession:
    """Create a ClientSession with rrdp-tools defaults.

    request_timeout: total timeout per request in seconds; 0 disables it,
    None uses DEFAULT_REQUEST_TIMEOUT.
    """
    if request_timeout == 0:
        timeout = aiohttp.ClientTimeout(total=None)
    else:
        timeout = aiohttp.ClientTimeout(
            total=request_timeout or DEFAULT_REQUEST_TIMEOUT
        )
    return aiohttp.ClientSession(
        headers={"User-Agent": user_agent or default_user_agent()},
        timeout=timeout,
        **kwargs,
    )


async def read_limited(
    response: aiohttp.ClientResponse, max_size: int = MAX_CONTENTLEN
) -> AsyncIterator[bytes]:
    """Yield chunks of the (decompressed) response body.

    Raises ResponseTooLargeError once more than `max_size` bytes are offered.
    """
    if response.content_length is not None and response.content_length > max_size:
        response.close()
        raise ResponseTooLargeError(
            f"{response.url}: Content-Length {response.content_length} exceeds limit of {max_size} bytes"
        )

    size = 0
    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
        size += len(chunk)
        if size > max_size:
            response.close()
            raise ResponseTooLargeError(
                f"{response.url}: body exceeds limit of {max_size} bytes"
            )
        yield chunk


async def write_limited(
    response: aiohttp.ClientResponse,
    f: BinaryIO,
    max_size: int = MAX_CONTENTLEN,
) -> tuple[str, int]:
    """Write the response body to `f`, returning its sha256 hex digest and size."""
    digest = hashlib.sha256()
    size = 0
    async for chunk in read_limited(response, max_size):
        digest.update(chunk)
        size += len(chunk)
        f.write(chunk)
    return digest.hexdigest(), size


async def read_error_body(response: aiohttp.ClientResponse) -> str:
    """Read the start of an error response body, for logging."""
    body = await response.content.read(MAX_ERROR_BODY_SIZE)
    response.close()
    return body.decode("utf-8", errors="replace")
