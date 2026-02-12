"""Generic state settings."""

from __future__ import annotations

import logging

lg = logging.getLogger(__name__)

# No commands that receive raw string kwargs.
_raw_commands: set[str] = set()

# No hex params.
_hex_params: set[str] = set()


def _set_stop_on_error(runner, value: str) -> None:
    runner._stop_on_error = value.lower() in ("true", "yes", "1")
    lg.info("stop_on_error = %s", runner._stop_on_error)


_settings: dict[str, callable] = {
    "stop_on_error": _set_stop_on_error,
}
