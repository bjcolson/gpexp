"""Runner — holds session state, dispatches commands."""

from __future__ import annotations

import logging
try:
    import readline  # noqa: F401 — enables line editing in input()
except ImportError:
    pass
import shlex

from gpexp.app.gp.cardinfo import (
    CardInfo,
    parse_card_recognition,
    parse_cplc,
    parse_key_info,
    parse_status,
)
from gpexp.app.gp.display import format_card_info, format_key_info
from gpexp.core.generic import (
    ProbeMessage,
    PutDataMessage,
    RawAPDUMessage,
    ReadBinaryMessage,
    SelectMessage,
    UpdateBinaryMessage,
)
from gpexp.core.gp import (
    C_MAC,
    AuthenticateMessage,
    DeleteKeyMessage,
    GetCardDataMessage,
    GetCPLCMessage,
    GPTerminal,
    ListContentsMessage,
    PutKeyMessage,
    StaticKeys,
)
lg = logging.getLogger(__name__)

GP_DEFAULT_KEY = bytes.fromhex("404142434445464748494A4B4C4D4E4F")


def _parse_value(s: str) -> int | str | bool:
    """Parse a command argument value.

    Returns int (hex detection: contains a-f/A-F or 0x prefix), bool
    for true/false literals, otherwise the raw string.
    """
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    # Hex: has 0x prefix or contains hex digit a-f
    if low.startswith("0x") or any(c in "abcdef" for c in low):
        try:
            return int(s, 16)
        except ValueError:
            pass
    # Plain int
    try:
        return int(s)
    except ValueError:
        pass
    return s


def parse_command(line: str) -> tuple[str, dict[str, str]] | None:
    """Parse a command line into (name, raw_kwargs).

    Returns None for blank/comment lines.  Values are kept as raw strings;
    the caller decides how to convert them.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    parts = shlex.split(stripped)
    name = parts[0]
    kwargs: dict[str, str] = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            kwargs[k] = v
        else:
            kwargs[part] = "true"
    return name, kwargs


class Runner:
    """Holds session state and dispatches commands."""

    def __init__(self, terminal: GPTerminal) -> None:
        self._terminal = terminal
        self._info = CardInfo()
        self._key = GP_DEFAULT_KEY
        self._stop_on_error = True

        # Build command table from cmd_* methods
        self._commands: dict[str, callable] = {}
        self._descriptions: dict[str, str] = {}
        for attr in dir(self):
            if attr.startswith("cmd_"):
                method = getattr(self, attr)
                name = attr[4:]
                self._commands[name] = method
                self._descriptions[name] = (method.__doc__ or "").split("\n")[0].strip()

    # --- Helpers ---

    def _key_length_for_kvn(self, kvn: int) -> int:
        """Look up the key length for a KVN from card key info, default 16."""
        for ki in self._info.key_info:
            if ki.key_version == kvn and ki.components:
                return ki.components[0][1]
        return 16

    def _derive_key(self, kvn: int) -> StaticKeys:
        """Derive a StaticKeys triple from self._key sized for *kvn*."""
        key_len = self._key_length_for_kvn(kvn) if kvn else len(self._key)
        key = (self._key * 2)[:key_len]
        return StaticKeys(enc=key, mac=key, dek=key)

    # --- Commands (each returns True on success, False on error) ---

    def cmd_probe(self) -> bool:
        """Probe card: UID, ATR, FCI."""
        result = self._terminal.send(ProbeMessage())
        self._info.uid = result.uid
        self._info.atr = result.atr
        self._info.fci = result.fci
        return True

    def cmd_select(self, *, aid: str = "", fid: str = "", p1: str = "", p2: str = "") -> bool:
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
        result = self._terminal.send(SelectMessage(aid=data, p1=sel_p1, p2=sel_p2))
        if result.fci:
            self._info.fci = result.fci
        if (result.sw >> 8) != 0x90:
            lg.error("SELECT %s failed: SW=%04X", label, result.sw)
            return False
        lg.info("SELECT %s SW=%04X", label, result.sw)
        return True

    def cmd_put_data(self, *, tag: str, data: str = "") -> bool:
        """PUT DATA — store a data object by tag (simple TLV)."""
        tag_int = int(tag, 16)
        result = self._terminal.send(
            PutDataMessage(tag=tag_int, data=bytes.fromhex(data))
        )
        if result.success:
            lg.info("PUT DATA %04X success", tag_int)
            return True
        lg.error("PUT DATA %04X failed: SW=%04X", tag_int, result.sw)
        return False

    def cmd_read_binary(self, *, offset: str = "0", le: str = "0", sfi: str = "") -> bool:
        """READ BINARY — read from a transparent EF (by offset or SFI)."""
        offset_int = int(offset, 16)
        le_int = int(le, 16)
        sfi_int = int(sfi, 16) if sfi else None
        result = self._terminal.send(
            ReadBinaryMessage(offset=offset_int, length=le_int, sfi=sfi_int)
        )
        label = f"SFI={sfi_int:02X}" if sfi_int is not None else f"offset={offset_int:04X}"
        if (result.sw >> 8) == 0x90:
            lg.info("READ BINARY %s: %s", label, result.data.hex(" ").upper() if result.data else "")
            return True
        lg.error("READ BINARY %s failed: SW=%04X", label, result.sw)
        return False

    def cmd_update_binary(self, *, offset: str = "0", data: str = "", sfi: str = "") -> bool:
        """UPDATE BINARY — write to a transparent EF (by offset or SFI)."""
        offset_int = int(offset, 16)
        sfi_int = int(sfi, 16) if sfi else None
        result = self._terminal.send(
            UpdateBinaryMessage(offset=offset_int, data=bytes.fromhex(data), sfi=sfi_int)
        )
        label = f"SFI={sfi_int:02X}" if sfi_int is not None else f"offset={offset_int:04X}"
        if result.success:
            lg.info("UPDATE BINARY %s success", label)
            return True
        lg.error("UPDATE BINARY %s failed: SW=%04X", label, result.sw)
        return False

    def cmd_read_cplc(self) -> bool:
        """Read CPLC data."""
        result = self._terminal.send(GetCPLCMessage())
        if result.cplc is not None:
            self._info.cplc = parse_cplc(result.cplc)
        return True

    def cmd_read_card_data(self) -> bool:
        """Read GP data objects: key info, card recognition, IIN, CIN, seq counter."""
        result = self._terminal.send(GetCardDataMessage())
        if result.key_info is not None:
            self._info.key_info = parse_key_info(result.key_info)
        if result.card_recognition is not None:
            self._info.card_recognition = parse_card_recognition(result.card_recognition)
        if result.iin is not None:
            self._info.iin = result.iin
        if result.cin is not None:
            self._info.cin = result.cin
        if result.seq_counter is not None:
            self._info.seq_counter = result.seq_counter
        return True

    def cmd_auth(self, *, kvn: int = 0x00, level: int = C_MAC) -> bool:
        """Authenticate with default keys (kvn=KVN, level=SECURITY_LEVEL)."""
        keys = self._derive_key(kvn)
        result = self._terminal.send(
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

    def cmd_list_contents(self) -> bool:
        """GET STATUS for ISD, applications, and packages."""
        result = self._terminal.send(ListContentsMessage())
        self._info.isd = parse_status(result.isd)
        self._info.applications = parse_status(result.applications)
        self._info.packages = parse_status(result.packages)
        return True

    def cmd_read_key_info(self) -> bool:
        """Read and log the key information template."""
        result = self._terminal.send(GetCardDataMessage())
        if result.key_info is not None:
            lg.info(
                "--- Keys ---\n%s", format_key_info(parse_key_info(result.key_info))
            )
        return True

    def cmd_put_keys(
        self, *, new_kvn: int = 0x30, key_type: int = 0x88, key_length: int = 16
    ) -> bool:
        """PUT KEY to load a new key set."""
        new_key = (self._key * 2)[:key_length]
        new_keys = StaticKeys(enc=new_key, mac=new_key, dek=new_key)
        result = self._terminal.send(
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

    def cmd_delete_keys(self, *, kvn: int) -> bool:
        """Delete a key set by version number."""
        result = self._terminal.send(DeleteKeyMessage(key_version=kvn))
        if result.success:
            lg.info("DELETE KEY success: removed KVN %02X", kvn)
            return True
        lg.error("DELETE KEY failed: SW=%04X", result.sw)
        return False

    def cmd_connect(self) -> bool:
        """Connect to the card."""
        self._terminal.connect()
        return True

    def cmd_disconnect(self) -> bool:
        """Disconnect from the card."""
        self._terminal.disconnect()
        return True

    def cmd_reconnect(self) -> bool:
        """Disconnect and reconnect the card."""
        self._terminal.disconnect()
        self._terminal.connect()
        return True

    def cmd_display(self) -> bool:
        """Display collected card information."""
        lg.info("\n%s", format_card_info(self._info))
        return True

    def cmd_set(self, **kwargs: int | str | bool) -> bool:
        """Set runner configuration (key=HEX, stop_on_error=BOOL)."""
        for k, v in kwargs.items():
            if k == "key":
                if isinstance(v, str):
                    self._key = bytes.fromhex(v)
                elif isinstance(v, int):
                    # Interpret as hex string without prefix
                    self._key = bytes.fromhex(f"{v:X}")
                lg.info("key set to %s", self._key.hex().upper())
            elif k == "stop_on_error":
                self._stop_on_error = bool(v)
                lg.info("stop_on_error = %s", self._stop_on_error)
            else:
                lg.warning("unknown setting: %s", k)
        return True

    def cmd_apdu(self, *, apdu: str = "", cla: str = "", ins: str = "", p1: str = "", p2: str = "", data: str = "", le: str = "") -> bool:
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
        result = self._terminal.send(msg)
        lg.info("<< %s SW=%04X", result.data.hex(" ").upper() if result.data else "", result.sw)
        return (result.sw >> 8) == 0x90

    def cmd_help(self) -> bool:
        """List available commands."""
        lines = []
        for name in sorted(self._descriptions):
            lines.append(f"  {name:20s} {self._descriptions[name]}")
        lg.info("Commands:\n%s", "\n".join(lines))
        return True

    # Commands that receive raw string kwargs (no conversion at all).
    _raw_commands: set[str] = {"apdu", "put_data", "read_binary", "select", "update_binary"}

    # Parameter names that map to APDU fields or tags — always parsed as hex.
    _hex_params: set[str] = {
        "kvn", "new_kvn", "key_type", "key_length", "level",
    }

    # --- Execution ---

    def execute(self, line: str) -> bool:
        """Parse and execute one command line. Returns True on success."""
        parsed = parse_command(line)
        if parsed is None:
            return True  # blank/comment — not an error
        name, raw_kwargs = parsed
        if name in ("quit", "exit"):
            raise StopIteration
        cmd = self._commands.get(name)
        if cmd is None:
            lg.error("unknown command: %s", name)
            return False
        if name in self._raw_commands:
            kwargs = raw_kwargs
        else:
            kwargs = {
                k: int(v, 16) if k in self._hex_params else _parse_value(v)
                for k, v in raw_kwargs.items()
            }
        try:
            return cmd(**kwargs)
        except TypeError as exc:
            lg.error("bad arguments for '%s': %s", name, exc)
            return False
        except Exception as exc:
            lg.error("command '%s' failed: %s", name, exc)
            return False

    def run_file(self, path: str) -> bool:
        """Read and execute commands from a file. Returns True if all succeed."""
        with open(path) as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            ok = self.execute(line)
            if not ok and self._stop_on_error:
                lg.error("stopped at line %d: %s", i, line.strip())
                return False
        return True

    def run_interactive(self) -> None:
        """Interactive REPL with readline support."""
        lg.info("interactive mode — type 'help' for commands, 'quit' to exit")
        while True:
            try:
                line = input("gpexp> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                self.execute(line)
            except StopIteration:
                break
