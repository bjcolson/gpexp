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
    help="Scenario number to run, or 'list' to show scenarios.",
)
@click.option(
    "-o",
    "--opt",
    multiple=True,
    help="Scenario option as key=value (repeatable).",
)
def gpexp(verbose, scenario, opt):

    logging.basicConfig(
        level=TRACE if verbose else PROTOCOL,
        format="%(levelname)-8s %(name)s: %(message)s",
    )

    from gpexp.app.gp.session import SCENARIOS

    if scenario == "list":
        for i, (name, desc, _, opt_defs) in enumerate(SCENARIOS, 1):
            click.echo(f"  {i}. {name:20s} {desc}")
            for oname, (otype, odefault, odesc) in opt_defs.items():
                default_str = f"{odefault:02X}" if otype == "hex" else str(odefault).lower()
                click.echo(f"       -o {oname}={default_str:10s} {odesc} ({otype})")
        return

    scenario_num = None
    if scenario is not None:
        try:
            scenario_num = int(scenario)
        except ValueError:
            raise click.BadParameter(f"expected a number, got '{scenario}'", param_hint="'-s'")

    opts = {}
    for item in opt:
        if "=" not in item:
            raise click.BadParameter(f"expected key=value, got '{item}'", param_hint="'-o'")
        k, v = item.split("=", 1)
        opts[k] = v

    from gpexp.app.main import main
    main(scenario=scenario_num, opts=opts)
