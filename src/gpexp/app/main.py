# filename : main.py
# created  : 06/23/2025


import logging

from gpexp.app import generic, gp, template

lg = logging.getLogger(__name__)

_SESSIONS = {
    "generic": generic.session,
    "gp": gp.session,
    "template": template.session,
}


def main(
    file: str | None = None,
    runner: str = "gp",
):
    lg.debug("gpexp v1")
    _SESSIONS[runner](file=file)
