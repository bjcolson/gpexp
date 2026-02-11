"""Generic card session — probe UID, ATR, default applet."""

from __future__ import annotations

import logging

from gpexp.core.base import Agent
from gpexp.core.base.tags import TAG_NAMES
from gpexp.core.generic import GenericTerminal, ProbeMessage
from gpexp.core.smartcard import Card

lg = logging.getLogger(__name__)


def session() -> None:
    """Probe a card using the generic terminal."""
    card = Card()
    agent = Agent(card)
    terminal = GenericTerminal(agent)

    try:
        terminal.connect()
        result = terminal.send(ProbeMessage())

        if result.uid is not None:
            lg.info("UID: %s", result.uid.hex(" ").upper())
        lg.info("ATR: %s", result.atr.hex(" ").upper())
        for node in result.fci:
            lg.info("FCI:\n%s", node.format(TAG_NAMES))
    except Exception as exc:
        terminal.on_error(exc)
    finally:
        terminal.disconnect()
