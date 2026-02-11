"""Scenario registry — named Python scenarios for the CLI."""

from __future__ import annotations

import logging

from gpexp.app.gp.runner import Runner

lg = logging.getLogger(__name__)


_CLEANUP_KVNS = (0x40, 0x30, 0x31, 0x32)


# ---------------------------------------------------------------------------
# Simple scenarios (use Runner commands)
# ---------------------------------------------------------------------------


def scenario_read_card(runner: Runner, *, display: bool = True) -> None:
    """Authenticate with KVN 0x20 and read card contents."""
    runner.cmd_probe()
    runner.cmd_read_cplc()
    runner.cmd_read_card_data()
    if not runner.cmd_auth(kvn=0x20):
        if display:
            runner.cmd_display()
        return
    runner.cmd_list_contents()
    if display:
        runner.cmd_display()


def scenario_single_auth(runner: Runner, *, kvn: int = 0x00) -> None:
    """Authenticate once with default keys at a single KVN."""
    runner.cmd_read_card_data()
    runner.cmd_auth(kvn=kvn)


# ---------------------------------------------------------------------------
# Complex scenarios (use Runner for commands, direct terminal for loops)
# ---------------------------------------------------------------------------


def scenario_authenticate_all(runner: Runner) -> None:
    """Try authentication with each key set on the card (KVN 20/30/31/32)."""
    target_kvns = (0x20, 0x30, 0x31, 0x32)
    runner.cmd_read_card_data()
    present = {ki.key_version for ki in runner._info.key_info}

    for kvn in target_kvns:
        if kvn not in present:
            continue
        runner.cmd_reconnect()
        runner.cmd_auth(kvn=kvn)


def scenario_put_keys(
    runner: Runner, *, kvn: int = 0x30, key_type: int = 0x88, key_length: int = 16
) -> None:
    """Authenticate and load a key set."""
    runner.cmd_read_card_data()
    if not runner.cmd_auth(kvn=0x00):
        return
    runner.cmd_put_keys(new_kvn=kvn, key_type=key_type, key_length=key_length)
    runner.cmd_read_key_info()


_KEY_TYPES = [
    ("DES-128", 0x80, 16),
    ("AES-128", 0x88, 16),
    ("AES-192", 0x88, 24),
    ("AES-256", 0x88, 32),
]


def scenario_put_key_matrix(runner: Runner, *, test_kvn: int = 0x40) -> None:
    """Test PUT KEY for all key types under each auth KVN (SCP02 + SCP03)."""
    auth_kvns = (0x20, 0x30, 0x31, 0x32)
    runner.cmd_read_card_data()
    present = {ki.key_version for ki in runner._info.key_info}

    for auth_kvn in auth_kvns:
        if auth_kvn not in present:
            continue
        lg.info("authenticate KVN %02X", auth_kvn)
        runner.cmd_reconnect()
        if not runner.cmd_auth(kvn=auth_kvn):
            continue
        for name, key_type, key_length in _KEY_TYPES:
            lg.info("-- auth KVN %02X -> PUT %s into KVN %02X", auth_kvn, name, test_kvn)
            if not runner.cmd_put_keys(new_kvn=test_kvn, key_type=key_type, key_length=key_length):
                break
            if not runner.cmd_delete_keys(kvn=test_kvn):
                break


# ---------------------------------------------------------------------------
# Test fixture & rounds
# ---------------------------------------------------------------------------


def ensure_clean_state(runner: Runner) -> bool:
    """Ensure only KVN 20 remains on the card."""
    lg.info("fixture: cleaning up card state")
    runner.cmd_reconnect()
    if not runner.cmd_auth(kvn=0x20):
        lg.error("fixture: cannot authenticate with KVN 20")
        return False
    for kvn in _CLEANUP_KVNS:
        runner.cmd_delete_keys(kvn=kvn)
    runner.cmd_read_key_info()
    lg.info("fixture: card clean")
    return True


def _run_round(
    runner: Runner,
    label: str,
    key_type: int,
    key_length: int,
    kvn: int = 0x30,
) -> bool:
    lg.info("===== %s round =====", label)
    lg.info("loading %s into KVN %02X", label, kvn)
    runner.cmd_reconnect()
    if not runner.cmd_auth(kvn=0x20):
        return False
    if not runner.cmd_put_keys(new_kvn=kvn, key_type=key_type, key_length=key_length):
        return False
    lg.info("running PUT KEY matrix")
    runner.cmd_reconnect()
    scenario_put_key_matrix(runner)
    return ensure_clean_state(runner)


def round_base(runner: Runner) -> bool:
    lg.info("===== base (KVN 20 only) round =====")
    lg.info("running PUT KEY matrix")
    runner.cmd_reconnect()
    scenario_put_key_matrix(runner)
    return ensure_clean_state(runner)


def round_aes128(runner: Runner) -> bool:
    return _run_round(runner, "AES-128", key_type=0x88, key_length=16)


def round_aes192(runner: Runner) -> bool:
    return _run_round(runner, "AES-192", key_type=0x88, key_length=24)


def round_aes256(runner: Runner) -> bool:
    return _run_round(runner, "AES-256", key_type=0x88, key_length=32)


ALL_ROUNDS = [round_base, round_aes128, round_aes192, round_aes256]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# (name, description, callable(runner, **opts), {option: (type, default, desc)})
SCENARIOS = [
    ("read_card", "Authenticate and read card contents",
     lambda r, **o: scenario_read_card(r, display=o.get("display", True)),
     {"display": ("bool", True, "show card info")}),
    ("authenticate", "Single authentication with default keys",
     lambda r, **o: scenario_single_auth(r, kvn=o.get("kvn", 0x00)),
     {"kvn": ("hex", 0x00, "key version number")}),
    ("authenticate_all", "Try authentication with each key set (KVN 20/30/31/32)",
     lambda r, **_: scenario_authenticate_all(r),
     {}),
    ("put_key_matrix", "Test PUT KEY for all key types under each auth KVN",
     lambda r, **_: scenario_put_key_matrix(r),
     {}),
    ("put_keys", "Authenticate and load a key set",
     lambda r, **o: scenario_put_keys(r, kvn=o.get("kvn", 0x30)),
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


def run_scenario(
    runner: Runner,
    scenario: int | str | None = None,
    opts: dict | None = None,
) -> None:
    """Look up and run a scenario by number or name."""
    idx = _resolve_scenario(scenario)
    if idx is None:
        return

    name, _, fn, opt_defs = SCENARIOS[idx]

    # Merge CLI opts over defaults
    merged: dict = {k: dflt for k, (_, dflt, _) in opt_defs.items()}
    if opts:
        for k, v in opts.items():
            if k not in opt_defs:
                lg.warning("unknown option '%s' for scenario '%s'", k, name)
                continue
            merged[k] = _parse_opt(v, opt_defs[k][0]) if isinstance(v, str) else v

    if fn is not None:
        fn(runner, **merged)
    else:
        # "all_rounds"
        if not ensure_clean_state(runner):
            return
        for rnd in ALL_ROUNDS:
            if not rnd(runner):
                break


def _resolve_scenario(scenario: int | str | None) -> int | None:
    """Resolve a scenario number (1-based) or name to a 0-based index."""
    if scenario is None:
        return 0  # default: read_card

    # Try by number
    if isinstance(scenario, int):
        if not (1 <= scenario <= len(SCENARIOS)):
            lg.error("scenario %d out of range (1-%d)", scenario, len(SCENARIOS))
            return None
        return scenario - 1

    # Try by name
    for i, (name, *_) in enumerate(SCENARIOS):
        if name == scenario:
            return i
    lg.error("unknown scenario: %s", scenario)
    return None
