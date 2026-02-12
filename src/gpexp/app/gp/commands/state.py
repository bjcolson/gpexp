"""GP state display and configuration."""

from __future__ import annotations

import logging

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
