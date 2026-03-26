import tomllib
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


@dataclass
class RepositoryConfig:
    notification_url: str
    name: str | None = None
    skip_snapshot: bool = True
    include_hash: bool = True
    store_notification: bool = True
    limit_deltas: int | None = None

    @property
    def effective_name(self) -> str:
        if self.name:
            return self.name
        parsed = urllib.parse.urlparse(self.notification_url)
        # Use hostname + parent path of notification.xml
        parent = PurePosixPath(parsed.path).parent
        parts = [p for p in parent.parts if p != "/"]
        if parts:
            return str(PurePosixPath(parsed.hostname, *parts))
        return parsed.hostname


@dataclass
class SyncConfig:
    base_dir: str
    repositories: list[RepositoryConfig] = field(default_factory=list)
    parallel_connections: int = 16
    request_timeout: int | None = 60
    total_timeout: int | None = 275


def load_config(path: Path) -> SyncConfig:
    with open(path, "rb") as f:
        data = tomllib.load(f)

    if "base_dir" not in data:
        raise ValueError("Config file must contain 'base_dir'")

    repos = []
    for repo_data in data.get("repository", []):
        if "notification_url" not in repo_data:
            raise ValueError("Each [[repository]] must contain 'notification_url'")
        repos.append(
            RepositoryConfig(
                notification_url=repo_data["notification_url"],
                name=repo_data.get("name"),
                skip_snapshot=repo_data.get("skip_snapshot", True),
                include_hash=repo_data.get("include_hash", True),
                store_notification=repo_data.get("store_notification", True),
                limit_deltas=repo_data.get("limit_deltas"),
            )
        )

    if not repos:
        raise ValueError("Config file must contain at least one [[repository]]")

    return SyncConfig(
        base_dir=str(Path(data["base_dir"]).expanduser()),
        parallel_connections=data.get("parallel_connections", 16),
        request_timeout=data.get("request_timeout", 60),
        total_timeout=data.get("total_timeout", 275),
        repositories=repos,
    )


RIR_DOMAINS = ("ripe.net", "arin.net", "afrinic.net", "apnic.net", "lacnic.net")


def _is_rir(repo: RepositoryConfig) -> bool:
    hostname = urllib.parse.urlparse(repo.notification_url).hostname or ""
    return any(
        hostname == domain or hostname.endswith("." + domain) for domain in RIR_DOMAINS
    )


def _format_repo(repo: RepositoryConfig) -> list[str]:
    lines = ["", "[[repository]]"]
    lines.append(f'notification_url = "{repo.notification_url}"')
    if repo.name:
        lines.append(f'name = "{repo.name}"')
    if not repo.skip_snapshot:
        lines.append("skip_snapshot = false")
    if not repo.include_hash:
        lines.append("include_hash = false")
    if not repo.store_notification:
        lines.append("store_notification = false")
    if repo.limit_deltas is not None:
        lines.append(f"limit_deltas = {repo.limit_deltas}")
    return lines


def format_toml(config: SyncConfig) -> str:
    lines = []
    lines.append(f"parallel_connections = {config.parallel_connections}")
    lines.append(f'base_dir = "{config.base_dir}"')
    if config.request_timeout is not None:
        lines.append(f"request_timeout = {config.request_timeout}")
    if config.total_timeout is not None:
        lines.append(f"total_timeout = {config.total_timeout}")

    rir_repos = sorted(
        (r for r in config.repositories if _is_rir(r)),
        key=lambda r: r.notification_url,
    )
    other_repos = sorted(
        (r for r in config.repositories if not _is_rir(r)),
        key=lambda r: r.notification_url,
    )

    for repo in rir_repos:
        lines.extend(_format_repo(repo))

    if rir_repos and other_repos:
        lines.append("")
        lines.append("#")
        lines.append("# Non-RIR repositories:")
        lines.append("#")

    for repo in other_repos:
        lines.extend(_format_repo(repo))

    lines.append("")
    return "\n".join(lines)


def config_from_notification_urls(
    urls: list[str],
    base_dir: str = "/data/rrdp",
    parallel_connections: int = 16,
    request_timeout: int | None = 60,
    total_timeout: int | None = 275,
) -> SyncConfig:
    repos = [RepositoryConfig(notification_url=url) for url in urls]
    return SyncConfig(
        base_dir=base_dir,
        parallel_connections=parallel_connections,
        request_timeout=request_timeout,
        total_timeout=total_timeout,
        repositories=repos,
    )
