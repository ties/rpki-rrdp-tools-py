import click

from rrdp_tools.loop_over_deltas import loop_over_deltas
from rrdp_tools.reconstruct import reconstruct_repo
from rrdp_tools.rrdp_content_filter import rrdp_content_filter
from rrdp_tools.snapshot_rrdp import snapshot_rrdp

@click.group()
def cli():
    pass

cli.add_command(loop_over_deltas)
cli.add_command(reconstruct_repo)
cli.add_command(rrdp_content_filter)
cli.add_command(snapshot_rrdp)

if __name__ == "__main__":
    cli()