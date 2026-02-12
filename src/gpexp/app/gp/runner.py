"""GPRunner — extends base Runner with GP session state."""

from __future__ import annotations

from gpexp.app.generic.commands import COMMAND_MODULES as GENERIC_MODULES
from gpexp.app.generic.runner import Runner
from gpexp.app.gp.cardinfo import GPCardInfo
from gpexp.app.gp.commands import COMMAND_MODULES as GP_MODULES
from gpexp.core.gp import GPTerminal

GP_DEFAULT_KEY = bytes.fromhex("404142434445464748494A4B4C4D4E4F")


class GPRunner(Runner):
    """Runner with GP session state."""

    def __init__(self, terminal: GPTerminal) -> None:
        super().__init__(terminal, GENERIC_MODULES + GP_MODULES)
        self._info = GPCardInfo()
        self._key = GP_DEFAULT_KEY
