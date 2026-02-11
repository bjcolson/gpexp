# filename : main.py
# created  : 06/23/2025


import logging

from gpexp.app import gp

lg = logging.getLogger(__name__)


def main(scenario: int | None = None, opts: dict | None = None):
    lg.debug("gpexp v1")
    gp.session(scenario=scenario, opts=opts)
