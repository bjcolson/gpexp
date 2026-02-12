"""GlobalPlatform commands."""

from __future__ import annotations

import logging

from gpexp.app.gp.cardinfo import (
    parse_card_recognition,
    parse_cplc,
    parse_key_info,
    parse_status,
)
from gpexp.app.gp.display import (
    format_card_data,
    format_contents,
    format_cplc,
    format_key_info,
)
from gpexp.core.gp import (
    C_MAC,
    AuthenticateMessage,
    DeleteKeyMessage,
    GetCardDataMessage,
    GetCPLCMessage,
    ListContentsMessage,
    PutKeyMessage,
    StaticKeys,
)

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = set()

# Parameter names always parsed as hex.
_hex_params: set[str] = {"kvn", "new_kvn", "key_type", "key_length", "level"}


# --- Helpers ---


def _key_length_for_kvn(runner, kvn: int) -> int:
    """Look up the key length for a KVN from card key info, default 16."""
    for ki in runner._info.key_info:
        if ki.key_version == kvn and ki.components:
            return ki.components[0][1]
    return 16


def _derive_key(runner, kvn: int) -> StaticKeys:
    """Derive a StaticKeys triple from runner._key sized for *kvn*."""
    key_len = _key_length_for_kvn(runner, kvn) if kvn else len(runner._key)
    key = (runner._key * 2)[:key_len]
    return StaticKeys(enc=key, mac=key, dek=key)


# --- Commands ---


def cmd_info_cplc(runner, *, display: bool = False) -> bool:
    """Read CPLC data."""
    result = runner._terminal.send(GetCPLCMessage())
    if result.cplc is not None:
        runner._info.cplc = parse_cplc(result.cplc)
        if display:
            lg.info("--- CPLC ---\n%s", format_cplc(runner._info.cplc))
    return True


def cmd_info_card_data(runner, *, display: bool = False) -> bool:
    """Read GP data objects: key info, card recognition, IIN, CIN, seq counter."""
    result = runner._terminal.send(GetCardDataMessage())
    if result.key_info is not None:
        runner._info.key_info = parse_key_info(result.key_info)
    if result.card_recognition is not None:
        runner._info.card_recognition = parse_card_recognition(result.card_recognition)
    if result.iin is not None:
        runner._info.iin = result.iin
    if result.cin is not None:
        runner._info.cin = result.cin
    if result.seq_counter is not None:
        runner._info.seq_counter = result.seq_counter
    if display:
        lg.info("\n%s", format_card_data(runner._info))
    return True


def cmd_auth(runner, *, kvn: int = 0x00, level: int = C_MAC) -> bool:
    """Authenticate with default keys (kvn=KVN, level=SECURITY_LEVEL)."""
    keys = _derive_key(runner, kvn)
    result = runner._terminal.send(
        AuthenticateMessage(keys=keys, security_level=level, key_version=kvn)
    )
    if not result.authenticated:
        lg.error(
            "authentication failed: %s",
            result.error or f"SW={result.sw or 0:04X}",
        )
        return False
    scp_id = (
        result.key_info[1] if result.key_info and len(result.key_info) >= 2 else 0
    )
    lg.info("SCP%02d session open (i=%02X)", scp_id, result.scp_i)
    return True


def cmd_info_contents(runner, *, display: bool = False) -> bool:
    """GET STATUS for ISD, applications, and packages."""
    result = runner._terminal.send(ListContentsMessage())
    runner._info.isd = parse_status(result.isd)
    runner._info.applications = parse_status(result.applications)
    runner._info.packages = parse_status(result.packages)
    if display:
        lg.info("\n%s", format_contents(runner._info))
    return True


def cmd_info_keys(runner, *, display: bool = False) -> bool:
    """Read the key information template."""
    result = runner._terminal.send(GetCardDataMessage())
    if result.key_info is not None:
        runner._info.key_info = parse_key_info(result.key_info)
        if display:
            lg.info("--- Keys ---\n%s", format_key_info(runner._info.key_info))
    return True


def cmd_put_keys(
    runner, *, new_kvn: int = 0x30, key_type: int = 0x88, key_length: int = 16
) -> bool:
    """PUT KEY to load a new key set."""
    new_key = (runner._key * 2)[:key_length]
    new_keys = StaticKeys(enc=new_key, mac=new_key, dek=new_key)
    result = runner._terminal.send(
        PutKeyMessage(
            new_keys=new_keys,
            new_kvn=new_kvn,
            old_kvn=0x00,
            key_id=0x01,
            key_type=key_type,
        )
    )
    if result.success:
        lg.info("PUT KEY success: loaded KVN %02X", new_kvn)
        return True
    lg.error("PUT KEY failed: SW=%04X", result.sw)
    return False


def cmd_delete_keys(runner, *, kvn: int) -> bool:
    """Delete a key set by version number."""
    result = runner._terminal.send(DeleteKeyMessage(key_version=kvn))
    if result.success:
        lg.info("DELETE KEY success: removed KVN %02X", kvn)
        return True
    lg.error("DELETE KEY failed: SW=%04X", result.sw)
    return False
