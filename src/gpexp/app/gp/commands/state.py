"""GP state display and configuration."""

from __future__ import annotations

import logging

from gpexp.app.gp.display import format_card_info

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = set()

# Parameter names always parsed as hex.
_hex_params: set[str] = set()


def _set_key(runner, value: str) -> None:
    runner._key = bytes.fromhex(value)
    lg.info("key set to %s", runner._key.hex().upper())


_settings: dict[str, callable] = {
    "key": _set_key,
}


def cmd_display(runner) -> bool:
    """Display collected card information."""
    lg.info("\n%s", format_card_info(runner._info))
    return True
