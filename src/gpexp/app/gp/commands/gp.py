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
    parse_privileges,
)
from gpexp.core.gp import (
    C_MAC,
    UPGRADE_ABORT,
    UPGRADE_RECOVERY,
    UPGRADE_RESUME,
    UPGRADE_START,
    UPGRADE_STATUS,
    UPS_COMPLETED,
    UPS_NO_SESSION,
    UPS_WAITING_ELF,
    UPS_WAITING_RESTORE,
    UPS_WAITING_RESTORE_FAILED,
    AuthenticateMessage,
    DeleteKeyMessage,
    DeleteMessage,
    GetCardDataMessage,
    GetCPLCMessage,
    InstallMessage,
    ListContentsMessage,
    LoadMessage,
    ManageUpgradeMessage,
    PutKeyMessage,
    SetStatusMessage,
    StaticKeys,
)
from gpexp.core.gp.capfile import read_load_file

lg = logging.getLogger(__name__)

# Commands that receive raw string kwargs (no conversion).
_raw_commands: set[str] = {"load", "install", "delete", "set_status", "upgrade", "upgrade_resume"}

# Parameter names always parsed as hex.
_hex_params: set[str] = {"kvn", "new_kvn", "key_type", "key_length", "level"}


# --- Helpers ---


_UPGRADE_STATUS_NAMES = {
    0x00: "NO_SESSION",
    0x01: "COMPLETED",
    0x02: "WAITING_ELF",
    0x03: "WAITING_RESTORE",
    0x04: "WAITING_RESTORE_FAILED",
    0x10: "INTERRUPTED_SAVING",
    0x20: "INTERRUPTED_CLEANUP",
    0x30: "INTERRUPTED_DELETE",
    0x40: "INTERRUPTED_INSTALL",
    0x50: "INTERRUPTED_RESTORE",
    0x60: "INTERRUPTED_CONSOLIDATE",
}


def _upgrade_status_name(status: int | None) -> str:
    if status is None:
        return "unknown"
    return _UPGRADE_STATUS_NAMES.get(status, f"UNKNOWN({status:#04x})")


def _key_length_for_kvn(runner, kvn: int) -> int:
    """Look up the key length for a KVN from card key info, default 16."""
    for ki in runner._info.key_info:
        if ki.key_version == kvn and ki.components:
            return ki.components[0][1]
    return 16


def _sized_key(key: bytes, key_len: int) -> bytes:
    """Pad or trim *key* to *key_len* bytes."""
    return (key * 2)[:key_len]


def _derive_key(runner, kvn: int) -> StaticKeys:
    """Derive a StaticKeys triple from runner key settings sized for *kvn*.

    Explicitly set per-key overrides (enc/mac/dek) are used at their
    original length.  The base key is padded/trimmed to match the card's
    expected key length for the given KVN.
    """
    key_len = _key_length_for_kvn(runner, kvn) if kvn else len(runner._key)
    enc = runner._enc if runner._enc is not None else _sized_key(runner._key, key_len)
    mac = runner._mac if runner._mac is not None else _sized_key(runner._key, key_len)
    dek = runner._dek if runner._dek is not None else _sized_key(runner._key, key_len)
    return StaticKeys(enc=enc, mac=mac, dek=dek)


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


def cmd_set_status(runner, *, scope: str = "80", state: str = "0F", aid: str = "") -> bool:
    """SET STATUS — change lifecycle state (scope=80 ISD/40 app/SD, state=lifecycle)."""
    scope_int = int(scope, 16)
    state_int = int(state, 16)
    aid_bytes = bytes.fromhex(aid) if aid else b""
    result = runner._terminal.send(
        SetStatusMessage(scope=scope_int, status=state_int, aid=aid_bytes)
    )
    if result.success:
        lg.info("SET STATUS success: scope=%02X state=%02X", scope_int, state_int)
        return True
    lg.error("SET STATUS failed: SW=%04X", result.sw)
    return False


def cmd_delete(runner, *, aid: str, related: str = "false") -> bool:
    """Delete a package or applet instance by AID."""
    aid_bytes = bytes.fromhex(aid)
    cascade = related.lower() in ("true", "yes", "1")
    result = runner._terminal.send(DeleteMessage(aid=aid_bytes, related=cascade))
    if result.success:
        lg.info("DELETE success: %s", aid_bytes.hex().upper())
        return True
    lg.error("DELETE failed: SW=%04X", result.sw)
    return False


def cmd_load(
    runner, *, file: str, aid: str = "", sd: str = "", block_size: str = "239"
) -> bool:
    """Load a CAP/IJC file onto the card (INSTALL for load + LOAD)."""
    load_info = read_load_file(file)
    load_file_aid = bytes.fromhex(aid) if aid else load_info.package_aid
    if not load_file_aid:
        lg.error("no package AID found in file and none provided via aid=")
        return False
    sd_aid = bytes.fromhex(sd) if sd else b""
    bs = int(block_size)

    lg.info(
        "loading %s (AID=%s, %d bytes, block_size=%d)",
        file, load_file_aid.hex().upper(), len(load_info.data), bs,
    )
    result = runner._terminal.send(
        LoadMessage(
            load_file_data=load_info.data,
            load_file_aid=load_file_aid,
            sd_aid=sd_aid,
            block_size=bs,
        )
    )
    if result.success:
        lg.info("LOAD success: %d blocks sent", result.blocks_sent)
        return True
    lg.error("LOAD failed: %s (SW=%04X)", result.error, result.sw)
    return False


def cmd_install(
    runner,
    *,
    package: str,
    module: str = "",
    instance: str = "",
    privileges: str = "00",
    params: str = "C900",
    selectable: str = "true",
) -> bool:
    """Install an applet from a loaded package (INSTALL for install).

    Privileges can be hex bytes (e.g. ``80C040``) or comma-separated
    mnemonics (e.g. ``SD,TP,AM,CLFDB``).  Run ``help install`` for the
    full list.
    """
    package_aid = bytes.fromhex(package)
    module_aid = bytes.fromhex(module) if module else package_aid
    instance_aid = bytes.fromhex(instance) if instance else b""
    priv = parse_privileges(privileges)
    params_bytes = bytes.fromhex(params)
    make_sel = selectable.lower() in ("true", "yes", "1")

    lg.info(
        "installing module=%s instance=%s from package=%s",
        module_aid.hex().upper(),
        (instance_aid or module_aid).hex().upper(),
        package_aid.hex().upper(),
    )
    result = runner._terminal.send(
        InstallMessage(
            package_aid=package_aid,
            module_aid=module_aid,
            instance_aid=instance_aid,
            privileges=priv,
            params=params_bytes,
            make_selectable=make_sel,
        )
    )
    if result.success:
        lg.info("INSTALL success")
        return True
    lg.error("INSTALL failed: SW=%04X", result.sw)
    return False


def cmd_upgrade(
    runner, *, file: str, aid: str = "", sd: str = "", block_size: str = "239"
) -> bool:
    """Start ELF upgrade: MANAGE ELF UPGRADE [start] + LOAD new package."""
    load_info = read_load_file(file)
    elf_aid = bytes.fromhex(aid) if aid else load_info.package_aid
    if not elf_aid:
        lg.error("no package AID found in file and none provided via aid=")
        return False
    sd_aid = bytes.fromhex(sd) if sd else b""
    bs = int(block_size)

    lg.info("starting ELF upgrade for AID=%s", elf_aid.hex().upper())
    result = runner._terminal.send(
        ManageUpgradeMessage(action=UPGRADE_START, elf_aid=elf_aid)
    )
    if not result.success:
        if result.sw == 0x6985:
            lg.error("upgrade session already active — run upgrade_status to check")
        else:
            lg.error("MANAGE ELF UPGRADE [start] failed: %s", result.error)
        return False

    status_name = _upgrade_status_name(result.session_status)
    if result.session_status != UPS_WAITING_ELF:
        lg.error("unexpected session status after start: %s", status_name)
        return False

    lg.info("session status: %s — loading new ELF", status_name)
    load_result = runner._terminal.send(
        LoadMessage(
            load_file_data=load_info.data,
            load_file_aid=elf_aid,
            sd_aid=sd_aid,
            block_size=bs,
        )
    )
    if not load_result.success:
        lg.error("LOAD failed: %s (SW=%04X)", load_result.error, load_result.sw)
        return False

    lg.info(
        "ELF loaded (%d blocks) — run upgrade_resume to trigger restore",
        load_result.blocks_sent,
    )
    return True


def cmd_upgrade_status(runner) -> bool:
    """Query the current ELF upgrade session status."""
    result = runner._terminal.send(ManageUpgradeMessage(action=UPGRADE_STATUS))
    if not result.success:
        lg.error("MANAGE ELF UPGRADE [status] failed: %s", result.error)
        return False

    status_name = _upgrade_status_name(result.session_status)
    msg = f"upgrade session: {status_name}"
    if result.elf_aid:
        msg += f" (ELF AID={result.elf_aid.hex().upper()})"
    lg.info("%s", msg)

    match result.session_status:
        case s if s == UPS_WAITING_ELF:
            lg.info("  → load the new ELF with upgrade_resume")
        case s if s == UPS_WAITING_RESTORE:
            lg.info("  → run install to trigger restore")
        case s if s == UPS_WAITING_RESTORE_FAILED:
            lg.info("  → run upgrade_recover to attempt recovery")
        case s if s is not None and s >= 0x10:
            lg.info("  → run upgrade_resume or upgrade_recover")
    return True


def cmd_upgrade_resume(
    runner, *, file: str = "", aid: str = "", sd: str = "", block_size: str = "239"
) -> bool:
    """Resume an interrupted ELF upgrade session."""
    result = runner._terminal.send(ManageUpgradeMessage(action=UPGRADE_RESUME))
    if not result.success:
        lg.error("MANAGE ELF UPGRADE [resume] failed: %s", result.error)
        return False

    status_name = _upgrade_status_name(result.session_status)
    lg.info("resume session status: %s", status_name)

    match result.session_status:
        case s if s == UPS_WAITING_ELF:
            if not file:
                lg.error("session needs ELF — provide file= parameter")
                return False
            load_info = read_load_file(file)
            elf_aid = bytes.fromhex(aid) if aid else load_info.package_aid
            if not elf_aid:
                lg.error("no package AID found in file and none provided via aid=")
                return False
            sd_aid = bytes.fromhex(sd) if sd else b""
            bs = int(block_size)
            lg.info("loading new ELF (AID=%s)", elf_aid.hex().upper())
            load_result = runner._terminal.send(
                LoadMessage(
                    load_file_data=load_info.data,
                    load_file_aid=elf_aid,
                    sd_aid=sd_aid,
                    block_size=bs,
                )
            )
            if not load_result.success:
                lg.error("LOAD failed: %s (SW=%04X)", load_result.error, load_result.sw)
                return False
            lg.info("ELF loaded — run upgrade_resume again to trigger restore")
        case s if s == UPS_WAITING_RESTORE:
            lg.info("  → run upgrade_resume again to trigger restore")
        case s if s == UPS_WAITING_RESTORE_FAILED:
            lg.info("  → run upgrade_recover to attempt recovery")
        case s if s in (UPS_NO_SESSION, UPS_COMPLETED):
            lg.info("nothing to resume")
        case s if s is not None and s >= 0x10:
            lg.info("  → interrupted state, retry or run upgrade_recover")
    return True


def cmd_upgrade_recover(runner) -> bool:
    """Force recovery of a failed ELF upgrade session."""
    result = runner._terminal.send(ManageUpgradeMessage(action=UPGRADE_RECOVERY))
    if not result.success:
        lg.error("MANAGE ELF UPGRADE [recovery] failed: %s", result.error)
        return False

    status_name = _upgrade_status_name(result.session_status)
    lg.info("recovery session status: %s", status_name)
    if result.session_status == UPS_WAITING_ELF:
        lg.info("  → load the original ELF to complete rollback")
    return True


def cmd_upgrade_abort(runner) -> bool:
    """Abort the current ELF upgrade session."""
    result = runner._terminal.send(ManageUpgradeMessage(action=UPGRADE_ABORT))
    if not result.success:
        lg.error("MANAGE ELF UPGRADE [abort] failed: %s", result.error)
        return False
    lg.info("upgrade session aborted")
    return True
