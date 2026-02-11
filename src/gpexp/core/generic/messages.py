from __future__ import annotations

from dataclasses import dataclass

from gpexp.core.base import Message, Result
from gpexp.core.smartcard.tlv import TLV


@dataclass
class ProbeMessage(Message):
    """Request to probe the card for UID, ATR, and default application."""


@dataclass
class ProbeResult(Result):
    uid: bytes | None
    atr: bytes
    fci: list[TLV]


@dataclass
class RawAPDUMessage(Message):
    """Send a raw APDU to the card."""

    cla: int
    ins: int
    p1: int
    p2: int
    data: bytes = b""
    le: int | None = None


@dataclass
class RawAPDUResult(Result):
    data: bytes
    sw: int
