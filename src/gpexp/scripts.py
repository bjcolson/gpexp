# filename : scripts.py
# created  : 06/23/2025


import logging

import click

from gpexp.core.smartcard.logging import PROTOCOL, TRACE


@click.command()
@click.option("-v", "--verbose", is_flag=True, help="TRACE level (show raw APDUs).")
@click.option(
    "-f",
    "--file",
    "file",
    type=click.Path(exists=True),
    default=None,
    help="Run commands from a scenario file.",
)
@click.option(
    "-r",
    "--runner",
    "runner",
    type=click.Choice(["gp", "generic", "template"]),
    default="gp",
    help="Runner type (default: gp).",
)
def gpexp(verbose, file, runner):

    logging.basicConfig(
        level=TRACE if verbose else PROTOCOL,
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    from gpexp.app.main import main
    main(file=file, runner=runner)
