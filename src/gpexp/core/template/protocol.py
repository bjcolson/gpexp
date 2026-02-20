"""Template protocol operations.

This is the protocol class for your card. It translates high-level
operations into APDUs. Each method that maps to a single APDU command
uses the ``send_`` prefix.

The protocol class is standalone: it receives ``agent.transmit`` as a
callable and has no other dependencies on the framework.

Replace the example commands below with your card's actual commands.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from gpexp.core.smartcard import APDU, Response
from gpexp.core.smartcard.logging import PROTOCOL

lg = logging.getLogger(__name__)

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


class TemplateProtocol:
    """Protocol operations for the template card."""

    def __init__(self, transmit: Callable[[APDU], Response]) -> None:
        self._transmit = transmit

    def _send(self, label: str, apdu: APDU) -> Response:
        resp = self._transmit(apdu)
        color = _GREEN if resp.sw1 in (0x90, 0x61) else _RED
        lg.log(PROTOCOL, "%s %s%04X%s", label, color, resp.sw, _RESET)
        return resp

    # -- commands (replace with your card's actual APDUs) --

    def send_get_version(self) -> Response:
        """Example: GET VERSION (80 01 00 00, Le=00).

        Replace CLA/INS/P1/P2 with your card's actual command.
        """
        apdu = APDU(cla=0x80, ins=0x01, p1=0x00, p2=0x00, le=0x00)
        return self._send("GET VERSION", apdu)

    def send_echo(self, data: bytes) -> Response:
        """Example: ECHO (80 02 00 00, data).

        Sends data and expects the card to echo it back.
        Replace with your card's actual command.
        """
        apdu = APDU(cla=0x80, ins=0x02, p1=0x00, p2=0x00, data=data, le=0x00)
        return self._send("ECHO", apdu)
