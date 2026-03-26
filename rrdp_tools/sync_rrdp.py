import asyncio
import logging
import urllib.parse
from pathlib import Path
from typing import Optional

import aiohttp
import click

from .snapshot_rrdp import snapshot_rrdp
from .sync_config import SyncConfig, load_config

LOG = logging.getLogger(__name__)


async def sync_rrdp(config: SyncConfig) -> None:
    """Run snapshot_rrdp for each configured repository."""
    base_dir = Path(config.base_dir)
    sem = asyncio.Semaphore(config.parallel_connections)

    if config.request_timeout == 0:
        client_timeout = aiohttp.ClientTimeout(total=None)
    elif config.request_timeout is not None:
        client_timeout = aiohttp.ClientTimeout(total=config.request_timeout)
    else:
        client_timeout = aiohttp.ClientTimeout(total=300)

    async with (
        asyncio.timeout(config.total_timeout),
        aiohttp.ClientSession(timeout=client_timeout) as session,
    ):
        tasks = []
        repo_names = []
        for repo in config.repositories:
            output_path = (base_dir / repo.effective_name).resolve()
            hostname_dir = (
                base_dir / urllib.parse.urlparse(repo.notification_url).hostname
            ).resolve()
            if not output_path.is_relative_to(hostname_dir):
                LOG.error(
                    "Skipping %s: output path %s escapes hostname directory %s",
                    repo.notification_url,
                    output_path,
                    hostname_dir,
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
            click.echo(click.style(f"FAILED {name}: {result}", fg="red"), err=True)

    click.echo(
        f"Sync completed: {len(results) - failures}/{len(results)} repositories succeeded."
    )
    if failures:
        raise SystemExit(1)


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
@click.option("-v", "--verbose", is_flag=True)
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
def sync_rrdp_run_command(
    config_file: Path,
    parallel_connections: Optional[int],
    base_dir: Optional[Path],
    verbose: bool,
    total_timeout: Optional[int],
    request_timeout: Optional[int],
):
    """Sync all RRDP repositories defined in a TOML config file.

    CONFIG_FILE    Path to TOML config file.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    config = load_config(config_file)

    if parallel_connections is not None:
        config.parallel_connections = parallel_connections
    if base_dir is not None:
        config.base_dir = str(base_dir)
    if total_timeout is not None:
        config.total_timeout = total_timeout
    if request_timeout is not None:
        config.request_timeout = request_timeout

    click.echo(
        f"Syncing {len(config.repositories)} repositories "
        f"(parallel_connections={config.parallel_connections}, base_dir={config.base_dir})"
    )

    try:
        asyncio.run(sync_rrdp(config))
    except TimeoutError:
        click.echo(
            click.style(f"Sync timed out after {config.total_timeout}s", fg="red"),
            err=True,
        )
        raise SystemExit(1)


# Register sub-commands
from .import_metrics import import_rrdp_repos_from_metrics_command  # noqa: E402

sync_rrdp_command.add_command(
    import_rrdp_repos_from_metrics_command, "import-from-metrics"
)
