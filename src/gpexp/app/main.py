# filename : main.py
# created  : 06/23/2025


import logging

from gpexp.app import gp

lg = logging.getLogger(__name__)


def main(
    scenario: int | str | None = None,
    opts: dict | None = None,
    file: str | None = None,
    interactive: bool = False,
):
    lg.debug("gpexp v1")
    gp.session(scenario=scenario, opts=opts, file=file, interactive=interactive)
