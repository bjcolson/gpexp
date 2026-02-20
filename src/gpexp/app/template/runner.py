"""Template card runner.

Extends the base Runner with template-card-specific session state and
settings. Combines the session commands (connect/disconnect/apdu) from
the generic package with the template-card-specific commands.

If your card does not need connect/disconnect/apdu at all, pass only
TEMPLATE_MODULES to super().__init__. If you need ISO 7816 commands
too (select, read_binary, etc.), add iso to GENERIC_MODULES — but then
your terminal must inherit from GenericTerminal.
"""

from __future__ import annotations

from gpexp.app.generic.commands import COMMAND_MODULES as GENERIC_MODULES
from gpexp.app.generic.runner import Runner
from gpexp.app.template.cardinfo import TemplateCardInfo
from gpexp.app.template.commands import COMMAND_MODULES as TEMPLATE_MODULES
from gpexp.core.template import TemplateTerminal


class TemplateRunner(Runner):
    """Runner for the template card."""

    def __init__(self, terminal: TemplateTerminal) -> None:
        # Generic session commands (connect, disconnect, apdu) plus
        # template-specific commands.
        super().__init__(terminal, GENERIC_MODULES + TEMPLATE_MODULES)
        self._info = TemplateCardInfo()
