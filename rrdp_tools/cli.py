import click

from rrdp_tools.loop_over_deltas import loop_over_deltas
from rrdp_tools.reconstruct import reconstruct_repo_command
from rrdp_tools.rrdp_content_filter import filter_rrdp_content_command
from rrdp_tools.snapshot_rrdp import snapshot_rrdp_command


@click.group()
def cli():
    pass


cli.add_command(loop_over_deltas)
cli.add_command(reconstruct_repo_command)
cli.add_command(filter_rrdp_content_command)
cli.add_command(snapshot_rrdp_command)

if __name__ == "__main__":
    cli()
