import asyncio
import logging
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import click

from .http_client import client_session
from .import_metrics import import_rrdp_repos_from_metrics_command
from .logging_config import LOG_LEVELS, configure_logging
from .sharding import Shard, daily_log_file, resolve_output_dir
from .snapshot_rrdp import snapshot_rrdp
from .sync_config import RepositoryConfig, SyncConfig, load_config

LOG = logging.getLogger(__name__)


def allowed_output_root(repo: RepositoryConfig, base_dir: Path) -> Path:
    """Return the root allowed by the name's trust level.

    Configured names are operator input; URL-derived names are confined to
    their hostname so path traversal cannot reach another repository.
    """
    if repo.name:
        return base_dir.resolve()
    hostname = urllib.parse.urlparse(repo.notification_url).hostname
    return (base_dir / hostname).resolve()


async def sync_rrdp(config: SyncConfig, base_dir: Path) -> None:
    """Sync configured repositories into the resolved output directory."""
    sem = asyncio.Semaphore(config.parallel_connections)

    async with (
        asyncio.timeout(config.total_timeout),
        client_session(config.user_agent, config.request_timeout) as session,
    ):
        tasks = []
        repo_names = []
        for repo in config.repositories:
            output_path = (base_dir / repo.effective_name).resolve()
            allowed_root = allowed_output_root(repo, base_dir)
            if not output_path.is_relative_to(allowed_root):
                LOG.error(
                    "Skipping %s: output path %s escapes %s",
                    repo.notification_url,
                    output_path,
                    allowed_root,
                )
                continue
            output_path.mkdir(parents=True, exist_ok=True)
            repo_names.append(repo.effective_name)
            tasks.append(
                snapshot_rrdp(
                    repo.notification_url,
                    output_path,
                    skip_snapshot=repo.skip_snapshot,
                    include_session=True,
                    include_hash=repo.include_hash,
                    store_notification=repo.store_notification,
                    limit_deltas=repo.limit_deltas,
                    sem=sem,
                    session=session,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

    failures = 0
    for name, result in zip(repo_names, results):
        if isinstance(result, Exception):
            failures += 1
            LOG.error("FAILED %s: %s", name, result)

    LOG.info(
        "Sync completed: %d/%d repositories succeeded.",
        len(results) - failures,
        len(results),
    )
    if failures:
        LOG.warning("%d/%d repositories failed", failures, len(results))


@click.group("sync-rrdp")
def sync_rrdp_command():
    """Sync RRDP repositories."""


@sync_rrdp_command.command("run")
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--parallel-connections",
    type=int,
    default=None,
    help="Override parallel_connections from config",
)
@click.option(
    "--base-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override base_dir from config",
)
@click.option("-v", "--verbose", count=True, help="-v: debug, -vv: also aiohttp etc.")
@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS, case_sensitive=False),
    envvar="RRDP_LOG_LEVEL",
    default=None,
    help="Set an explicit level for all loggers, overriding -v",
)
@click.option(
    "--timeout",
    "total_timeout",
    type=int,
    default=None,
    help="Total timeout in seconds for the entire sync run",
)
@click.option(
    "--request-timeout",
    type=int,
    default=None,
    help="Per-request timeout in seconds (default: 300, 0 to disable)",
)
@click.option(
    "--user-agent",
    type=str,
    default=None,
    help="Override user_agent from config (default: rrdp-tools/<version>)",
)
@click.option(
    "--shard",
    type=click.Choice([s.value for s in Shard]),
    default=None,
    help="Override shard from config: split output by date below base_dir",
)
@click.option(
    "--log-to-file/--no-log-to-file",
    default=None,
    help="Override log_to_file from config: append to <output dir>/YYYYMMDD.log",
)
def sync_rrdp_run_command(
    config_file: Path,
    parallel_connections: int | None,
    base_dir: Path | None,
    verbose: int,
    log_level: str | None,
    total_timeout: int | None,
    request_timeout: int | None,
    user_agent: str | None,
    shard: str | None,
    log_to_file: bool | None,
):
    """Sync all RRDP repositories defined in a TOML config file.

    CONFIG_FILE    Path to TOML config file.
    """
    try:
        config = load_config(config_file)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if parallel_connections is not None:
        config.parallel_connections = parallel_connections
    if base_dir is not None:
        config.base_dir = str(base_dir)
    if total_timeout is not None:
        config.total_timeout = total_timeout
    if request_timeout is not None:
        config.request_timeout = request_timeout
    if user_agent is not None:
        config.user_agent = user_agent
    if shard is not None:
        config.shard = Shard(shard)
    if log_to_file is not None:
        config.log_to_file = log_to_file

    # Keep repositories and the log in the same date shard.
    now = datetime.now(tz=UTC)
    output_dir = resolve_output_dir(Path(config.base_dir), config.shard, now)
    configure_logging(
        verbose,
        daily_log_file(output_dir, now) if config.log_to_file else None,
        log_level,
    )

    LOG.info(
        "Syncing %d repositories (parallel_connections=%d, output_dir=%s)",
        len(config.repositories),
        config.parallel_connections,
        output_dir,
    )

    try:
        asyncio.run(sync_rrdp(config, output_dir))
    except TimeoutError:
        LOG.error("Sync timed out after %ss", config.total_timeout)
        raise SystemExit(1)


# Register sub-commands
sync_rrdp_command.add_command(
    import_rrdp_repos_from_metrics_command, "import-from-metrics"
)
