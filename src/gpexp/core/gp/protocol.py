from __future__ import annotations

import logging
from collections.abc import Callable

from gpexp.core.smartcard import APDU, Response
from gpexp.core.smartcard.logging import PROTOCOL

SCOPE_ISD = 0x80
SCOPE_APPS = 0x40
SCOPE_ELF = 0x20

_SCOPE_NAMES = {SCOPE_ISD: "ISD", SCOPE_APPS: "APPS", SCOPE_ELF: "ELF"}

lg = logging.getLogger(__name__)

_GREEN = "\033[32m"
_RED = "\033[31m"
_RESET = "\033[0m"


class GP:
    """GlobalPlatform protocol operations."""

    def __init__(self, transmit: Callable[[APDU], Response]) -> None:
        self._transmit = transmit

    def _send(self, label: str, apdu: APDU) -> Response:
        resp = self._transmit(apdu)
        color = _GREEN if resp.sw1 in (0x90, 0x61) else _RED
        lg.log(PROTOCOL, "%s %s%04X%s", label, color, resp.sw, _RESET)
        return resp

    # -- commands --

    def send_get_data(self, tag: int) -> Response:
        """GP GET DATA (80 CA)."""
        p1 = (tag >> 8) & 0xFF
        p2 = tag & 0xFF
        apdu = APDU(cla=0x80, ins=0xCA, p1=p1, p2=p2, le=0x00)
        return self._send(f"GP GET DATA {tag:04X}", apdu)

    def send_get_status(self, scope: int, next_occurrence: bool = False) -> Response:
        """GET STATUS (80 F2) — single command, one scope."""
        p2 = 0x03 if next_occurrence else 0x02
        apdu = APDU(cla=0x80, ins=0xF2, p1=scope, p2=p2, data=b"\x4F\x00", le=0x00)
        name = _SCOPE_NAMES.get(scope, f"{scope:02X}")
        return self._send(f"GET STATUS {name}", apdu)

    def send_initialize_update(
        self, key_version: int, key_id: int, host_challenge: bytes
    ) -> Response:
        """INITIALIZE UPDATE (80 50)."""
        apdu = APDU(
            cla=0x80, ins=0x50, p1=key_version, p2=key_id,
            data=host_challenge, le=0x00,
        )
        return self._send(f"INITIALIZE UPDATE ver={key_version:02X} id={key_id:02X}", apdu)

    def send_external_authenticate(
        self, security_level: int, host_cryptogram: bytes
    ) -> Response:
        """EXTERNAL AUTHENTICATE (84 82)."""
        apdu = APDU(
            cla=0x84, ins=0x82, p1=security_level, p2=0x00,
            data=host_cryptogram,
        )
        return self._send(f"EXTERNAL AUTHENTICATE level={security_level:02X}", apdu)

    def send_delete_key(self, key_version: int) -> Response:
        """DELETE (80 E4) — delete key set by version number."""
        data = bytes([0xD2, 0x01, key_version])
        apdu = APDU(cla=0x80, ins=0xE4, p1=0x00, p2=0x00, data=data)
        return self._send(f"DELETE KEY ver={key_version:02X}", apdu)

    def send_put_key(self, old_kvn: int, key_id: int, data: bytes) -> Response:
        """PUT KEY (80 D8)."""
        apdu = APDU(cla=0x80, ins=0xD8, p1=old_kvn, p2=key_id, data=data)
        return self._send(f"PUT KEY old_ver={old_kvn:02X} id={key_id:02X}", apdu)

    def send_install(self, p1: int, p2: int, data: bytes) -> Response:
        """INSTALL (80 E6)."""
        apdu = APDU(cla=0x80, ins=0xE6, p1=p1, p2=p2, data=data)
        return self._send(f"INSTALL P1={p1:02X}", apdu)

    def send_load(self, last_block: bool, block_number: int, data: bytes) -> Response:
        """LOAD (80 E8) — single block."""
        p1 = 0x80 if last_block else 0x00
        apdu = APDU(cla=0x80, ins=0xE8, p1=p1, p2=block_number, data=data)
        return self._send(f"LOAD block={block_number:02X} last={last_block}", apdu)

    # -- operations --

    def list_content(self, scope: int) -> bytes:
        """GET STATUS sequence — accumulates data across 0x6310 continuations."""
        buf = bytearray()
        resp = self.send_get_status(scope)
        while True:
            if resp.data:
                buf.extend(resp.data)
            if resp.sw != 0x6310:
                break
            resp = self.send_get_status(scope, next_occurrence=True)
        return bytes(buf)

    def load_file(self, data: bytes, block_size: int = 239) -> Response:
        """LOAD sequence — split data into blocks and send them all.

        Returns the Response from the last LOAD block.
        """
        blocks = [data[i : i + block_size] for i in range(0, len(data), block_size)]
        if not blocks:
            blocks = [b""]
        for i, block in enumerate(blocks):
            last = i == len(blocks) - 1
            resp = self.send_load(last, i, block)
            if not resp.success:
                return resp
        return resp

    def list_all_content(self) -> tuple[bytes, bytes, bytes]:
        """GET STATUS for all scopes (ISD, applications, packages)."""
        return (
            self.list_content(SCOPE_ISD),
            self.list_content(SCOPE_APPS),
            self.list_content(SCOPE_ELF),
        )
