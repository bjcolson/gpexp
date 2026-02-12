"""ISO 7816 generic file and data commands."""

from __future__ import annotations

import logging

from gpexp.core.generic import (
    ProbeMessage,
    PutDataMessage,
    ReadBinaryMessage,
    SelectMessage,
    UpdateBinaryMessage,
)

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = {"put_data", "read_binary", "select", "update_binary"}

# Parameter names always parsed as hex.
_hex_params: set[str] = set()


def cmd_probe(runner) -> bool:
    """Probe card: UID, ATR, FCI."""
    result = runner._terminal.send(ProbeMessage())
    runner._info.uid = result.uid
    runner._info.atr = result.atr
    runner._info.fci = result.fci
    return True


def cmd_select(runner, *, aid: str = "", fid: str = "", p1: str = "", p2: str = "") -> bool:
    """SELECT by AID, DF name, or EF file identifier."""
    if fid:
        data = bytes.fromhex(fid)
        sel_p1 = int(p1, 16) if p1 else 0x02
        sel_p2 = int(p2, 16) if p2 else 0x0C
        label = f"FID {fid.upper()}"
    else:
        data = bytes.fromhex(aid)
        sel_p1 = int(p1, 16) if p1 else 0x04
        sel_p2 = int(p2, 16) if p2 else 0x00
        label = aid.upper() or "(default)"
    result = runner._terminal.send(SelectMessage(aid=data, p1=sel_p1, p2=sel_p2))
    if result.fci:
        runner._info.fci = result.fci
    if (result.sw >> 8) != 0x90:
        lg.error("SELECT %s failed: SW=%04X", label, result.sw)
        return False
    lg.info("SELECT %s SW=%04X", label, result.sw)
    return True


def cmd_put_data(runner, *, tag: str, data: str = "") -> bool:
    """PUT DATA — store a data object by tag (simple TLV)."""
    tag_int = int(tag, 16)
    result = runner._terminal.send(
        PutDataMessage(tag=tag_int, data=bytes.fromhex(data))
    )
    if result.success:
        lg.info("PUT DATA %04X success", tag_int)
        return True
    lg.error("PUT DATA %04X failed: SW=%04X", tag_int, result.sw)
    return False


def cmd_read_binary(runner, *, offset: str = "0", le: str = "0", sfi: str = "") -> bool:
    """READ BINARY — read from a transparent EF (by offset or SFI)."""
    offset_int = int(offset, 16)
    le_int = int(le, 16)
    sfi_int = int(sfi, 16) if sfi else None
    result = runner._terminal.send(
        ReadBinaryMessage(offset=offset_int, length=le_int, sfi=sfi_int)
    )
    label = f"SFI={sfi_int:02X}" if sfi_int is not None else f"offset={offset_int:04X}"
    if (result.sw >> 8) == 0x90:
        lg.info("READ BINARY %s: %s", label, result.data.hex(" ").upper() if result.data else "")
        return True
    lg.error("READ BINARY %s failed: SW=%04X", label, result.sw)
    return False


def cmd_update_binary(runner, *, offset: str = "0", data: str = "", sfi: str = "") -> bool:
    """UPDATE BINARY — write to a transparent EF (by offset or SFI)."""
    offset_int = int(offset, 16)
    sfi_int = int(sfi, 16) if sfi else None
    result = runner._terminal.send(
        UpdateBinaryMessage(offset=offset_int, data=bytes.fromhex(data), sfi=sfi_int)
    )
    label = f"SFI={sfi_int:02X}" if sfi_int is not None else f"offset={offset_int:04X}"
    if result.success:
        lg.info("UPDATE BINARY %s success", label)
        return True
    lg.error("UPDATE BINARY %s failed: SW=%04X", label, result.sw)
    return False
