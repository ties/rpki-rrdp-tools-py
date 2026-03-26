import re
from pathlib import Path

import click

from .sync_config import config_from_notification_urls, format_toml


def parse_metrics_file(content: str) -> list[str]:
    """Extract unique notify= URLs from rpki-client metrics lines."""
    urls = dict.fromkeys(re.findall(r'notify="([^"]+)"', content))
    return sorted(urls)


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
    "--parallel-connections",
    type=int,
    default=4,
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
):
    """Generate a sync-rrdp TOML config from rpki-client metrics.

    METRICS_FILE    Path to rpki-client metrics file.
    """
    content = metrics_file.read_text()
    urls = parse_metrics_file(content)

    if not urls:
        click.echo("No notify URLs found in metrics file.", err=True)
        raise SystemExit(1)

    config = config_from_notification_urls(
        urls,
        base_dir=base_dir,
        parallel_connections=parallel_connections,
        request_timeout=request_timeout,
        total_timeout=total_timeout,
    )
    toml_str = format_toml(config)

    if output:
        output.write_text(toml_str)
        click.echo(f"Wrote config with {len(urls)} repositories to {output}")
    else:
        click.echo(toml_str, nl=False)
