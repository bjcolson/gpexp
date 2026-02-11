from __future__ import annotations

import logging

from smartcard.CardConnectionObserver import CardConnectionObserver

from gpexp.core.smartcard.logging import PROTOCOL, TRACE

lg = logging.getLogger(__name__)


LINE_BYTES = 16

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


def _color_sw(sw1: int) -> str:
    """Return ANSI color for a status word: green for success, red for error."""
    if sw1 == 0x90 or sw1 == 0x61:
        return _GREEN
    return _RED


class LoggingCardObserver(CardConnectionObserver):
    """CardConnectionObserver that logs APDU traffic via Python logging."""

    def _log_hex(self, prefix: str, data: bytes) -> None:
        """Log hex data, wrapping at LINE_BYTES bytes per line."""
        pad = " " * len(prefix)
        for i in range(0, len(data), LINE_BYTES):
            chunk = data[i : i + LINE_BYTES].hex(" ").upper()
            lg.log(TRACE, "%s%s", prefix if i == 0 else pad, chunk)

    def update(self, observable, event):
        if event.type == "connect":
            lg.log(PROTOCOL, "connect")

        elif event.type == "reconnect":
            lg.log(PROTOCOL, "reconnect")

        elif event.type == "disconnect":
            lg.log(PROTOCOL, "disconnect")

        elif event.type == "command":
            self._log_hex(">> ", bytes(event.args[0]))

        elif event.type == "response":
            data, sw1, sw2 = event.args[0], event.args[1], event.args[2]
            color = _color_sw(sw1)
            sw = f"{color}{sw1:02X} {sw2:02X}{_RESET}"
            if data:
                self._log_hex("<< ", bytes(data))
            lg.log(TRACE, "<< %s", sw)
