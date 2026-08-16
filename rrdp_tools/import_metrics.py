import os
import re
from pathlib import Path

import click

from .sharding import Shard
from .sync_config import (
    config_from_notification_urls,
    format_toml,
    notification_url_error,
)


def parse_metrics_file(content: str) -> list[str]:
    """Extract unique notify= URLs from rpki-client metrics lines."""
    urls = dict.fromkeys(re.findall(r'notify="([^"]+)"', content))
    return sorted(urls)


def write_atomically(path: Path, content: str) -> None:
    """Replace `path` without exposing partial content to readers."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(content)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@click.command("import-rrdp-repos-from-metrics")
@click.argument("metrics_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path. Defaults to stdout.",
)
@click.option(
    "--base-dir",
    type=str,
    default="/data/rrdp",
    help="base_dir value in generated config",
)
@click.option(
    "--shard",
    type=click.Choice([s.value for s in Shard]),
    default=Shard.NONE.value,
    help="shard value in generated config: split output by date below base_dir",
)
@click.option(
    "--log-to-file/--no-log-to-file",
    default=False,
    help="log_to_file value in generated config: sync-rrdp appends to "
    "<output dir>/YYYYMMDD.log",
)
@click.option(
    "--user-agent",
    type=str,
    default=None,
    help="user_agent value in generated config (default: rrdp-tools/<version>)",
)
@click.option(
    "--parallel-connections",
    type=int,
    default=16,
    help="parallel_connections value in generated config",
)
@click.option(
    "--timeout",
    "total_timeout",
    type=int,
    default=None,
    help="total_timeout value in generated config (seconds)",
)
@click.option(
    "--request-timeout",
    type=int,
    default=None,
    help="request_timeout value in generated config (seconds)",
)
def import_rrdp_repos_from_metrics_command(
    metrics_file: Path,
    output: Path | None,
    base_dir: str,
    parallel_connections: int,
    total_timeout: int | None,
    request_timeout: int | None,
    shard: str,
    log_to_file: bool,
    user_agent: str | None,
):
    """Generate a sync-rrdp TOML config from rpki-client metrics.

    Options set values in the generated config, not this command.

    METRICS_FILE    Path to rpki-client metrics file.
    """
    content = metrics_file.read_text()
    urls = parse_metrics_file(content)

    if not urls:
        click.echo("No notify URLs found in metrics file.", err=True)
        raise SystemExit(1)

    usable = []
    for url in urls:
        if error := notification_url_error(url):
            click.echo(f"Skipping notify URL {url}: {error}", err=True)
        else:
            usable.append(url)

    if not usable:
        click.echo("No usable notify URLs in metrics file.", err=True)
        raise SystemExit(1)

    config = config_from_notification_urls(
        usable,
        base_dir=base_dir,
        parallel_connections=parallel_connections,
        request_timeout=request_timeout,
        total_timeout=total_timeout,
        user_agent=user_agent,
        shard=Shard(shard),
        log_to_file=log_to_file,
    )
    toml_str = format_toml(config)

    if output:
        write_atomically(output, toml_str)
        click.echo(f"Wrote config with {len(usable)} repositories to {output}")
    else:
        click.echo(toml_str, nl=False)
