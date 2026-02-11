"""GP card session orchestrator."""

from __future__ import annotations

import logging

from gpexp.app.gp.runner import Runner
from gpexp.app.gp.scenarios import SCENARIOS, run_scenario
from gpexp.core.base import Agent
from gpexp.core.gp import GPTerminal
from gpexp.core.smartcard import Card

lg = logging.getLogger(__name__)


def session(
    scenario: int | str | None = None,
    opts: dict | None = None,
    file: str | None = None,
    interactive: bool = False,
) -> None:
    """Open a card session and run a scenario, file, or interactive REPL."""
    card = Card()
    agent = Agent(card)
    terminal = GPTerminal(agent)
    runner = Runner(terminal)

    try:
        terminal.connect()
        if file:
            runner.run_file(file)
        elif interactive:
            runner.run_interactive()
        else:
            run_scenario(runner, scenario, opts)
    except Exception as exc:
        terminal.on_error(exc)
    finally:
        terminal.disconnect()
