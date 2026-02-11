from __future__ import annotations

import logging
from collections.abc import Callable

from gpexp.core.smartcard import APDU, Response
from gpexp.core.smartcard.logging import PROTOCOL

lg = logging.getLogger(__name__)

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


class ISO7816:
    """ISO 7816-4 protocol operations."""

    def __init__(self, transmit: Callable[[APDU], Response]) -> None:
        self._transmit = transmit

    def _send(self, label: str, apdu: APDU) -> Response:
        resp = self._transmit(apdu)
        color = _GREEN if resp.sw1 in (0x90, 0x61) else _RED
        lg.log(PROTOCOL, "%s %s%04X%s", label, color, resp.sw, _RESET)
        return resp

    # -- commands --

    def send_select(self, aid: bytes) -> Response:
        """Select an application by AID (00 A4 04 00)."""
        apdu = APDU(cla=0x00, ins=0xA4, p1=0x04, p2=0x00, data=aid, le=0x00)
        return self._send(f"SELECT {aid.hex().upper()}", apdu)

    def send_read_binary(self, offset: int, length: int) -> Response:
        """Read binary data from the currently selected file (00 B0)."""
        p1 = (offset >> 8) & 0x7F
        p2 = offset & 0xFF
        apdu = APDU(cla=0x00, ins=0xB0, p1=p1, p2=p2, le=length)
        return self._send(f"READ BINARY offset={offset:04X} le={length:02X}", apdu)

    def send_get_data(self, tag: int) -> Response:
        """Retrieve a data object by tag (00 CA)."""
        p1 = (tag >> 8) & 0xFF
        p2 = tag & 0xFF
        apdu = APDU(cla=0x00, ins=0xCA, p1=p1, p2=p2, le=0x00)
        return self._send(f"GET DATA {tag:04X}", apdu)
