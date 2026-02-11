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

    def send_select(
        self, data: bytes, p1: int = 0x04, p2: int = 0x00,
    ) -> Response:
        """SELECT (00 A4). P1=selection method, P2=response control."""
        le: int | None = None if (p2 & 0x0C) == 0x0C else 0x00
        apdu = APDU(cla=0x00, ins=0xA4, p1=p1, p2=p2, data=data, le=le)
        return self._send(f"SELECT {data.hex().upper()}", apdu)

    def send_read_binary(
        self, offset: int, length: int, *, sfi: int | None = None,
    ) -> Response:
        """Read binary data (00 B0). SFI in P1 bit 8 if given."""
        if sfi is not None:
            p1 = 0x80 | (sfi & 0x1F)
            p2 = offset & 0xFF
            label = f"READ BINARY SFI={sfi:02X} offset={offset:02X} le={length:02X}"
        else:
            p1 = (offset >> 8) & 0x7F
            p2 = offset & 0xFF
            label = f"READ BINARY offset={offset:04X} le={length:02X}"
        apdu = APDU(cla=0x00, ins=0xB0, p1=p1, p2=p2, le=length)
        return self._send(label, apdu)

    def send_get_data(self, tag: int) -> Response:
        """Retrieve a data object by tag (00 CA)."""
        p1 = (tag >> 8) & 0xFF
        p2 = tag & 0xFF
        apdu = APDU(cla=0x00, ins=0xCA, p1=p1, p2=p2, le=0x00)
        return self._send(f"GET DATA {tag:04X}", apdu)

    def send_put_data(self, tag: int, data: bytes) -> Response:
        """Store a data object by tag, simple TLV (00 DA)."""
        p1 = (tag >> 8) & 0xFF
        p2 = tag & 0xFF
        apdu = APDU(cla=0x00, ins=0xDA, p1=p1, p2=p2, data=data)
        return self._send(f"PUT DATA {tag:04X}", apdu)

    def send_update_binary(
        self, offset: int, data: bytes, *, sfi: int | None = None,
    ) -> Response:
        """Update binary data (00 D6). SFI in P1 bit 8 if given."""
        if sfi is not None:
            p1 = 0x80 | (sfi & 0x1F)
            p2 = offset & 0xFF
            label = f"UPDATE BINARY SFI={sfi:02X} offset={offset:02X} len={len(data):02X}"
        else:
            p1 = (offset >> 8) & 0x7F
            p2 = offset & 0xFF
            label = f"UPDATE BINARY offset={offset:04X} len={len(data):02X}"
        apdu = APDU(cla=0x00, ins=0xD6, p1=p1, p2=p2, data=data)
        return self._send(label, apdu)
