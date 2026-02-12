"""Generic card session orchestrator."""

from __future__ import annotations

import logging

from gpexp.app.generic.commands import COMMAND_MODULES
from gpexp.app.generic.runner import Runner
from gpexp.core.base import Agent
from gpexp.core.generic import GenericTerminal
from gpexp.core.smartcard import Card

lg = logging.getLogger(__name__)


def session(
    file: str | None = None,
) -> None:
    """Open a card session and run a scenario file or interactive REPL."""
    card = Card()
    agent = Agent(card)
    terminal = GenericTerminal(agent)
    runner = Runner(terminal, COMMAND_MODULES)

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
