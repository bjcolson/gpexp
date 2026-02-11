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
class SelectMessage(Message):
    """SELECT by AID (04), DF name (04 0C), or EF file identifier (02 0C)."""

    aid: bytes
    p1: int = 0x04
    p2: int = 0x00


@dataclass
class SelectResult(Result):
    fci: list[TLV]
    sw: int


@dataclass
class PutDataMessage(Message):
    """PUT DATA — store a data object by tag (simple TLV)."""

    tag: int
    data: bytes


@dataclass
class PutDataResult(Result):
    success: bool
    sw: int


@dataclass
class UpdateBinaryMessage(Message):
    """UPDATE BINARY — write to a transparent EF."""

    offset: int
    data: bytes
    sfi: int | None = None


@dataclass
class UpdateBinaryResult(Result):
    success: bool
    sw: int


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
