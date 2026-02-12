"""Session management and raw APDU commands."""

from __future__ import annotations

import logging

from gpexp.core.generic import RawAPDUMessage

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = {"apdu"}

# Parameter names always parsed as hex.
_hex_params: set[str] = set()


def cmd_connect(runner) -> bool:
    """Connect to the card."""
    runner._terminal.connect()
    return True


def cmd_disconnect(runner) -> bool:
    """Disconnect from the card."""
    runner._terminal.disconnect()
    return True


def cmd_reconnect(runner) -> bool:
    """Disconnect and reconnect the card."""
    runner._terminal.disconnect()
    runner._terminal.connect()
    return True


def cmd_apdu(runner, *, apdu: str = "", cla: str = "", ins: str = "", p1: str = "", p2: str = "", data: str = "", le: str = "") -> bool:
    """Send a raw APDU (apdu=HEX or cla/ins/p1/p2/data/le, all hex)."""
    if apdu:
        raw = bytes.fromhex(apdu)
        if len(raw) < 4:
            lg.error("APDU too short: need at least 4 bytes (CLA INS P1 P2)")
            return False
        msg = RawAPDUMessage(
            cla=raw[0], ins=raw[1], p1=raw[2], p2=raw[3],
            data=raw[5:] if len(raw) > 5 else b"",
            le=raw[4] if len(raw) == 5 else None,
        )
    else:
        msg = RawAPDUMessage(
            cla=int(cla, 16), ins=int(ins, 16),
            p1=int(p1, 16), p2=int(p2, 16),
            data=bytes.fromhex(data) if data else b"",
            le=int(le, 16) if le else None,
        )
    result = runner._terminal.send(msg)
    lg.info("<< %s SW=%04X", result.data.hex(" ").upper() if result.data else "", result.sw)
    return (result.sw >> 8) == 0x90
