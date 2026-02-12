"""GP card session orchestrator."""

from __future__ import annotations

import logging

from gpexp.app.gp.runner import GPRunner
from gpexp.core.base import Agent
from gpexp.core.gp import GPTerminal
from gpexp.core.smartcard import Card

lg = logging.getLogger(__name__)


def session(
    file: str | None = None,
) -> None:
    """Open a card session and run a scenario file or interactive REPL."""
    card = Card()
    agent = Agent(card)
    terminal = GPTerminal(agent)
    runner = GPRunner(terminal)

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
