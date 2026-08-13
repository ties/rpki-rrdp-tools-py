import importlib.metadata

import aiohttp

DEFAULT_REQUEST_TIMEOUT = 60


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
