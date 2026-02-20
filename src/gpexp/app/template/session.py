"""Template card session orchestrator.

Constructs the full stack (Card -> Agent -> Terminal -> Runner),
connects, runs the scenario or REPL, and disconnects.
"""

from __future__ import annotations

import logging

from gpexp.app.template.runner import TemplateRunner
from gpexp.core.base import Agent
from gpexp.core.smartcard import Card
from gpexp.core.template import TemplateTerminal

lg = logging.getLogger(__name__)


def session(
    file: str | None = None,
) -> None:
    """Open a template card session."""
    card = Card()
    agent = Agent(card)
    terminal = TemplateTerminal(agent)
    runner = TemplateRunner(terminal)

    try:
        terminal.connect()
        if file:
            runner.run_file(file)
        else:
            runner.run_interactive()
    except Exception as exc:
        terminal.on_error(exc)
    finally:
        terminal.disconnect()
