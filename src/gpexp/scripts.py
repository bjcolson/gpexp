# filename : scripts.py
# created  : 06/23/2025


import logging

import click

from gpexp.core.smartcard.logging import PROTOCOL, TRACE

lg = logging.getLogger(__name__)


@click.command()
@click.option("-v", "--verbose", is_flag=True, help="TRACE level (show raw APDUs).")
@click.option(
    "-s",
    "--scenario",
    default=None,
    help="Scenario number or name to run, or 'list' to show scenarios.",
)
@click.option(
    "-o",
    "--opt",
    multiple=True,
    help="Scenario option as key=value (repeatable).",
)
@click.option(
    "-f",
    "--file",
    "file",
    type=click.Path(exists=True),
    default=None,
    help="Run commands from a scenario file.",
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    help="Interactive REPL.",
)
def gpexp(verbose, scenario, opt, file, interactive):

    logging.basicConfig(
        level=TRACE if verbose else PROTOCOL,
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    from gpexp.app.gp.scenarios import SCENARIOS

    if scenario == "list":
        for i, (name, desc, _, opt_defs) in enumerate(SCENARIOS, 1):
            click.echo(f"  {i}. {name:20s} {desc}")
            for oname, (otype, odefault, odesc) in opt_defs.items():
                default_str = f"{odefault:02X}" if otype == "hex" else str(odefault).lower()
                click.echo(f"       -o {oname}={default_str:10s} {odesc} ({otype})")
        return

    # Resolve scenario: try int first, then keep as name string
    scenario_ref = None
    if scenario is not None:
        try:
            scenario_ref = int(scenario)
        except ValueError:
            scenario_ref = scenario

    opts = {}
    for item in opt:
        if "=" not in item:
            raise click.BadParameter(f"expected key=value, got '{item}'", param_hint="'-o'")
        k, v = item.split("=", 1)
        opts[k] = v

    from gpexp.app.main import main
    main(scenario=scenario_ref, opts=opts, file=file, interactive=interactive)
