"""GP card session — authenticate and enumerate card contents."""

from __future__ import annotations

import logging

from gpexp.app.gp.cardinfo import (
    CardInfo,
    parse_card_recognition,
    parse_cplc,
    parse_key_info,
    parse_status,
)
from gpexp.app.gp.display import format_card_info, format_key_info
from gpexp.core.base import Agent
from gpexp.core.generic import ProbeMessage
from gpexp.core.gp import (
    C_MAC,
    AuthenticateMessage,
    DeleteKeyMessage,
    DeleteKeyResult,
    GetCardDataMessage,
    GetCPLCMessage,
    GPTerminal,
    ListContentsMessage,
    PutKeyMessage,
    PutKeyResult,
    StaticKeys,
)
from gpexp.core.smartcard import Card
from gpexp.core.smartcard.tlv import parse as parse_tlv

lg = logging.getLogger(__name__)

GP_DEFAULT_KEY = bytes.fromhex("404142434445464748494A4B4C4D4E4F")


# ---------------------------------------------------------------------------
# Unit operations (each takes a terminal, returns data)
# ---------------------------------------------------------------------------


def probe(terminal: GPTerminal, info: CardInfo) -> None:
    """Probe card: UID, ATR, FCI."""
    result = terminal.send(ProbeMessage())
    info.uid = result.uid
    info.atr = result.atr
    info.fci = result.fci


def read_cplc(terminal: GPTerminal, info: CardInfo) -> None:
    """Read CPLC data (usually available before authentication)."""
    result = terminal.send(GetCPLCMessage())
    if result.cplc is not None:
        info.cplc = parse_cplc(result.cplc)


def read_card_data(terminal: GPTerminal, info: CardInfo) -> None:
    """Read GP data objects: key info, card recognition, IIN, CIN, seq counter."""
    result = terminal.send(GetCardDataMessage())
    if result.key_info is not None:
        info.key_info = parse_key_info(result.key_info)
    if result.card_recognition is not None:
        info.card_recognition = parse_card_recognition(result.card_recognition)
    if result.iin is not None:
        info.iin = result.iin
    if result.cin is not None:
        info.cin = result.cin
    if result.seq_counter is not None:
        raw = result.seq_counter
        # Strip C1 TLV wrapper if present
        nodes = parse_tlv(raw)
        if nodes and nodes[0].tag == 0xC1:
            raw = nodes[0].value
        info.seq_counter = int.from_bytes(raw, "big") if raw else None


def authenticate(
    terminal: GPTerminal,
    keys: StaticKeys,
    security_level: int = C_MAC,
    key_version: int = 0x00,
) -> tuple[int, int] | None:
    """Open a secure channel. Returns (scp_id, i_param) or None on failure."""
    result = terminal.send(
        AuthenticateMessage(keys=keys, security_level=security_level, key_version=key_version)
    )
    if not result.authenticated:
        lg.error(
            "authentication failed: %s",
            result.error or f"SW={result.sw or 0:04X}",
        )
        return None
    scp_id = (
        result.key_info[1] if result.key_info and len(result.key_info) >= 2 else 0
    )
    lg.info("SCP%02d session open (i=%02X)", scp_id, result.scp_i)
    return scp_id, result.scp_i


def list_contents(terminal: GPTerminal, info: CardInfo) -> None:
    """GET STATUS for ISD, applications, and packages."""
    result = terminal.send(ListContentsMessage())
    info.isd = parse_status(result.isd)
    info.applications = parse_status(result.applications)
    info.packages = parse_status(result.packages)


def read_key_info(terminal: GPTerminal) -> None:
    """Read and log the key information template."""
    result = terminal.send(GetCardDataMessage())
    if result.key_info is not None:
        lg.info(
            "--- Keys ---\n%s", format_key_info(parse_key_info(result.key_info))
        )


def put_keys(
    terminal: GPTerminal,
    new_keys: StaticKeys,
    new_kvn: int = 0x30,
    old_kvn: int = 0x00,
    key_id: int = 0x01,
    key_type: int = 0x88,
) -> PutKeyResult:
    """PUT KEY to load a new key set. Requires an open secure channel."""
    result = terminal.send(
        PutKeyMessage(
            new_keys=new_keys,
            new_kvn=new_kvn,
            old_kvn=old_kvn,
            key_id=key_id,
            key_type=key_type,
        )
    )
    if result.success:
        lg.info("PUT KEY success: loaded KVN %02X", new_kvn)
    else:
        lg.error("PUT KEY failed: SW=%04X", result.sw)
    return result


def delete_keys(terminal: GPTerminal, kvn: int) -> DeleteKeyResult:
    """Delete a key set by version number. Requires an open secure channel."""
    result = terminal.send(DeleteKeyMessage(key_version=kvn))
    if result.success:
        lg.info("DELETE KEY success: removed KVN %02X", kvn)
    else:
        lg.error("DELETE KEY failed: SW=%04X", result.sw)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _key_length_for_kvn(info: CardInfo, kvn: int) -> int:
    """Look up the key length for a KVN from card key info, default 16."""
    for ki in info.key_info:
        if ki.key_version == kvn and ki.components:
            return ki.components[0][1]
    return 16


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def scenario_authenticate(terminal: GPTerminal) -> None:
    """Try authentication with each key set on the card (KVN 20/30/31/32)."""
    target_kvns = (0x20, 0x30, 0x31, 0x32)

    info = CardInfo()
    read_card_data(terminal, info)
    present = {ki.key_version for ki in info.key_info}

    for kvn in target_kvns:
        if kvn not in present:
            continue
        terminal.disconnect()
        terminal.connect()
        key_len = _key_length_for_kvn(info, kvn)
        key = (GP_DEFAULT_KEY * 2)[:key_len]
        keys = StaticKeys(enc=key, mac=key, dek=key)
        authenticate(terminal, keys, key_version=kvn)


def scenario_put_keys(
    terminal: GPTerminal,
    *,
    auth_kvn: int = 0x00,
    new_kvn: int = 0x30,
    key_length: int = 16,
    key_type: int = 0x88,
) -> None:
    """Authenticate and load a key set."""
    info = CardInfo()
    read_card_data(terminal, info)
    auth_key_len = _key_length_for_kvn(info, auth_kvn)
    auth_key = (GP_DEFAULT_KEY * 2)[:auth_key_len]
    keys = StaticKeys(enc=auth_key, mac=auth_key, dek=auth_key)
    if authenticate(terminal, keys, key_version=auth_kvn) is None:
        return
    new_key = (GP_DEFAULT_KEY * 2)[:key_length]
    new_keys = StaticKeys(enc=new_key, mac=new_key, dek=new_key)
    put_keys(terminal, new_keys, new_kvn=new_kvn, key_type=key_type)
    read_key_info(terminal)


def scenario_delete_keys(
    terminal: GPTerminal,
    *,
    auth_kvn: int = 0x00,
    delete_kvn: int,
) -> None:
    """Authenticate and delete a key set."""
    info = CardInfo()
    read_card_data(terminal, info)
    auth_key_len = _key_length_for_kvn(info, auth_kvn)
    auth_key = (GP_DEFAULT_KEY * 2)[:auth_key_len]
    keys = StaticKeys(enc=auth_key, mac=auth_key, dek=auth_key)
    if authenticate(terminal, keys, key_version=auth_kvn) is None:
        return
    delete_keys(terminal, delete_kvn)
    read_key_info(terminal)


_KEY_TYPES = [
    ("DES-128", 0x80, 16),
    ("AES-128", 0x88, 16),
    ("AES-192", 0x88, 24),
    ("AES-256", 0x88, 32),
]


def scenario_put_key_matrix(terminal: GPTerminal, *, test_kvn: int = 0x40) -> None:
    """Test PUT KEY for all key types under each auth KVN (SCP02 + SCP03).

    For each auth KVN (20/30/31/32), opens a secure session and cycles
    through DES-128, AES-128, AES-192, AES-256: PUT KEY into test_kvn,
    then DELETE KEY.  16 combinations total.
    """
    auth_kvns = (0x20, 0x30, 0x31, 0x32)

    info = CardInfo()
    read_card_data(terminal, info)
    present = {ki.key_version for ki in info.key_info}

    for auth_kvn in auth_kvns:
        if auth_kvn not in present:
            continue
        auth_key_len = _key_length_for_kvn(info, auth_kvn)
        lg.info("authenticate KVN %02X (%d-bit)", auth_kvn, auth_key_len * 8)
        terminal.disconnect()
        terminal.connect()
        auth_key = (GP_DEFAULT_KEY * 2)[:auth_key_len]
        keys = StaticKeys(enc=auth_key, mac=auth_key, dek=auth_key)
        if authenticate(terminal, keys, key_version=auth_kvn) is None:
            continue
        for name, key_type, key_length in _KEY_TYPES:
            lg.info("-- auth KVN %02X -> PUT %s into KVN %02X", auth_kvn, name, test_kvn)
            new_key = (GP_DEFAULT_KEY * 2)[:key_length]
            new_keys = StaticKeys(enc=new_key, mac=new_key, dek=new_key)
            result = put_keys(terminal, new_keys, new_kvn=test_kvn, key_type=key_type)
            if not result.success:
                break
            dr = delete_keys(terminal, test_kvn)
            if not dr.success:
                break


def scenario_read_card(terminal: GPTerminal, *, display: bool = False) -> None:
    """Authenticate with KVN 0x20 and read card contents."""
    keys = StaticKeys(enc=GP_DEFAULT_KEY, mac=GP_DEFAULT_KEY, dek=GP_DEFAULT_KEY)
    info = CardInfo()

    probe(terminal, info)
    read_cplc(terminal, info)
    read_card_data(terminal, info)

    if authenticate(terminal, keys, key_version=0x20) is None:
        if display:
            lg.info("\n%s", format_card_info(info))
        return

    list_contents(terminal, info)

    if display:
        lg.info("\n%s", format_card_info(info))


# ---------------------------------------------------------------------------
# Test fixture
# ---------------------------------------------------------------------------

_DES_KEYS = StaticKeys(enc=GP_DEFAULT_KEY, mac=GP_DEFAULT_KEY, dek=GP_DEFAULT_KEY)
_CLEANUP_KVNS = (0x40, 0x30, 0x31, 0x32)


def ensure_clean_state(terminal: GPTerminal) -> bool:
    """Ensure only KVN 20 remains on the card.

    Authenticates with KVN 20 (SCP02/DES) and deletes any stale KVNs
    (30, 31, 32, 40).  Returns True if the card is in a clean state.
    """
    lg.info("fixture: cleaning up card state")
    terminal.disconnect()
    terminal.connect()
    if authenticate(terminal, _DES_KEYS, key_version=0x20) is None:
        lg.error("fixture: cannot authenticate with KVN 20")
        return False
    for kvn in _CLEANUP_KVNS:
        delete_keys(terminal, kvn)
    read_key_info(terminal)
    lg.info("fixture: card clean")
    return True


# ---------------------------------------------------------------------------
# PUT KEY matrix rounds
# ---------------------------------------------------------------------------


def _run_round(
    terminal: GPTerminal,
    label: str,
    key_type: int,
    key_length: int,
    kvn: int = 0x30,
) -> bool:
    """Load a key into *kvn*, run the PUT KEY matrix, then clean up.

    Returns True on success.  The card must be in clean state (only KVN 20)
    before calling this function.
    """
    lg.info("===== %s round =====", label)

    # 1. Auth KVN 20, load the round key into kvn
    lg.info("loading %s into KVN %02X", label, kvn)
    terminal.disconnect()
    terminal.connect()
    if authenticate(terminal, _DES_KEYS, key_version=0x20) is None:
        return False
    new_key = (GP_DEFAULT_KEY * 2)[:key_length]
    new_keys = StaticKeys(enc=new_key, mac=new_key, dek=new_key)
    result = put_keys(terminal, new_keys, new_kvn=kvn, key_type=key_type)
    if not result.success:
        return False

    # 2. Run the matrix (tests all 4 key types under each present auth KVN)
    lg.info("running PUT KEY matrix")
    terminal.disconnect()
    terminal.connect()
    scenario_put_key_matrix(terminal)

    # 3. Clean up
    return ensure_clean_state(terminal)


def round_base(terminal: GPTerminal) -> bool:
    """PUT KEY matrix with only KVN 20 (SCP02/DES) on the card."""
    lg.info("===== base (KVN 20 only) round =====")
    lg.info("running PUT KEY matrix")
    terminal.disconnect()
    terminal.connect()
    scenario_put_key_matrix(terminal)
    return ensure_clean_state(terminal)


def round_aes128(terminal: GPTerminal) -> bool:
    """Load AES-128 into KVN 30, run PUT KEY matrix, clean up."""
    return _run_round(terminal, "AES-128", key_type=0x88, key_length=16)


def round_aes192(terminal: GPTerminal) -> bool:
    """Load AES-192 into KVN 30, run PUT KEY matrix, clean up."""
    return _run_round(terminal, "AES-192", key_type=0x88, key_length=24)


def round_aes256(terminal: GPTerminal) -> bool:
    """Load AES-256 into KVN 30, run PUT KEY matrix, clean up."""
    return _run_round(terminal, "AES-256", key_type=0x88, key_length=32)


ALL_ROUNDS = [round_base, round_aes128, round_aes192, round_aes256]


# ---------------------------------------------------------------------------
# Session orchestrator
# ---------------------------------------------------------------------------


def _scenario_single_auth(terminal: GPTerminal, *, kvn: int = 0x00) -> None:
    """Authenticate once with default keys at a single KVN."""
    info = CardInfo()
    read_card_data(terminal, info)
    key_len = _key_length_for_kvn(info, kvn) if kvn else 16
    key = (GP_DEFAULT_KEY * 2)[:key_len]
    keys = StaticKeys(enc=key, mac=key, dek=key)
    authenticate(terminal, keys, key_version=kvn)


# Each entry: (name, description, callable(terminal, **opts), {option: (type, default, desc)})
# Types: "bool", "hex", "int"
SCENARIOS = [
    ("read_card", "Authenticate and read card contents",
     lambda t, **o: scenario_read_card(t, display=o.get("display", True)),
     {"display": ("bool", True, "show card info")}),
    ("authenticate", "Single authentication with default keys",
     lambda t, **o: _scenario_single_auth(t, kvn=o.get("kvn", 0x00)),
     {"kvn": ("hex", 0x00, "key version number")}),
    ("authenticate_all", "Try authentication with each key set (KVN 20/30/31/32)",
     lambda t, **_: scenario_authenticate(t),
     {}),
    ("put_key_matrix", "Test PUT KEY for all key types under each auth KVN",
     lambda t, **_: scenario_put_key_matrix(t),
     {}),
    ("put_keys", "Authenticate and load a key set",
     lambda t, **o: scenario_put_keys(t, new_kvn=o.get("kvn", 0x30)),
     {"kvn": ("hex", 0x30, "target key version number")}),
    ("all_rounds", "Run all PUT KEY matrix rounds (base/AES-128/192/256)",
     None,
     {}),
]


def _parse_opt(value: str, type_name: str) -> object:
    """Convert a CLI option string to the declared type."""
    if type_name == "bool":
        return value.lower() in ("true", "1", "yes")
    if type_name == "hex":
        return int(value, 16)
    if type_name == "int":
        return int(value)
    return value


def session(scenario: int | None = None, opts: dict | None = None) -> None:
    """Open a card session and run a scenario.

    When *scenario* is None the default scenario (read_card) runs.
    """
    if scenario is not None and not (1 <= scenario <= len(SCENARIOS)):
        lg.error("scenario %d out of range (1-%d)", scenario, len(SCENARIOS))
        return

    card = Card()
    agent = Agent(card)
    terminal = GPTerminal(agent)

    idx = (scenario or 1) - 1
    name, _, fn, opt_defs = SCENARIOS[idx]

    # Merge CLI opts over defaults
    merged: dict = {k: dflt for k, (_, dflt, _) in opt_defs.items()}
    if opts:
        for k, v in opts.items():
            if k not in opt_defs:
                lg.warning("unknown option '%s' for scenario '%s'", k, name)
                continue
            merged[k] = _parse_opt(v, opt_defs[k][0])

    try:
        terminal.connect()
        if fn is not None:
            fn(terminal, **merged)
        else:
            # "all_rounds" — run every round
            if not ensure_clean_state(terminal):
                return
            for rnd in ALL_ROUNDS:
                if not rnd(terminal):
                    break
    except Exception as exc:
        terminal.on_error(exc)
    finally:
        terminal.disconnect()
