"""Template card commands.

Each ``cmd_*`` function is automatically discovered and registered as a
REPL/scenario command. The function name minus the ``cmd_`` prefix
becomes the command name (e.g. ``cmd_get_version`` -> ``get_version``).

Rules:
- First argument is always ``runner``.
- Return ``True`` on success, ``False`` on error.
- First line of the docstring becomes the help text.
- Add parameter names to ``_hex_params`` if they should always be
  parsed as hex from the REPL/scenario files.
- Add command names to ``_raw_commands`` if they need all parameters
  as raw strings (manual parsing inside the function).
"""

from __future__ import annotations

import logging

from gpexp.core.template import EchoMessage, GetVersionMessage

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no auto-conversion).
_raw_commands: set[str] = {"echo"}

# Parameter names always parsed as hex.
_hex_params: set[str] = set()


def cmd_get_version(runner) -> bool:
    """Read the card's version."""
    result = runner._terminal.send(GetVersionMessage())
    if (result.sw >> 8) != 0x90:
        lg.error("GET VERSION failed: SW=%04X", result.sw)
        return False
    runner._info.version = result.version
    lg.info("version: %s", result.version.hex(" ").upper() if result.version else "(empty)")
    return True


def cmd_echo(runner, *, data: str = "") -> bool:
    """Send data to the card and receive it back."""
    payload = bytes.fromhex(data)
    result = runner._terminal.send(EchoMessage(data=payload))
    if (result.sw >> 8) != 0x90:
        lg.error("ECHO failed: SW=%04X", result.sw)
        return False
    lg.info("echo: %s", result.data.hex(" ").upper() if result.data else "(empty)")
    return True
