"""State display and configuration commands."""

from __future__ import annotations

import logging

from gpexp.app.gp.display import format_card_info

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = set()

# Parameter names always parsed as hex.
_hex_params: set[str] = set()


def cmd_display(runner) -> bool:
    """Display collected card information."""
    lg.info("\n%s", format_card_info(runner._info))
    return True


def cmd_set(runner, **kwargs: int | str | bool) -> bool:
    """Set runner configuration (key=HEX, stop_on_error=BOOL)."""
    for k, v in kwargs.items():
        if k == "key":
            if isinstance(v, str):
                runner._key = bytes.fromhex(v)
            elif isinstance(v, int):
                # Interpret as hex string without prefix
                runner._key = bytes.fromhex(f"{v:X}")
            lg.info("key set to %s", runner._key.hex().upper())
        elif k == "stop_on_error":
            runner._stop_on_error = bool(v)
            lg.info("stop_on_error = %s", runner._stop_on_error)
        else:
            lg.warning("unknown setting: %s", k)
    return True
