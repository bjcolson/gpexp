from __future__ import annotations

from dataclasses import dataclass

from gpexp.core.base import Message, Result
from gpexp.core.gp.security import C_MAC, StaticKeys
from gpexp.core.smartcard.tlv import TLV


@dataclass
class ListContentsMessage(Message):
    """Request to list all card contents (ISD, applications, packages)."""


@dataclass
class ListContentsResult(Result):
    isd: list[TLV]
    applications: list[TLV]
    packages: list[TLV]


@dataclass
class GetCPLCMessage(Message):
    """Request CPLC data (GET DATA 9F7F)."""


@dataclass
class GetCPLCResult(Result):
    cplc: bytes | None
    sw: int


@dataclass
class GetCardDataMessage(Message):
    """Fetch GP data objects."""


@dataclass
class GetCardDataResult(Result):
    key_info: bytes | None
    card_recognition: bytes | None
    iin: bytes | None
    cin: bytes | None
    seq_counter: int | None


@dataclass
class AuthenticateMessage(Message):
    """Request to open an SCP03 secure channel."""

    keys: StaticKeys
    security_level: int = C_MAC
    key_version: int = 0x00
    key_id: int = 0x00


@dataclass
class AuthenticateResult(Result):
    authenticated: bool
    sw: int | None = None
    error: str | None = None
    key_diversification_data: bytes | None = None
    key_info: bytes | None = None
    scp_i: int | None = None


@dataclass
class DeleteKeyMessage(Message):
    """Request to DELETE a key set by version number."""

    key_version: int


@dataclass
class DeleteKeyResult(Result):
    success: bool
    sw: int


@dataclass
class PutKeyMessage(Message):
    """Request to PUT KEY — load a new key set onto the card."""

    new_keys: StaticKeys
    new_kvn: int
    old_kvn: int = 0x00
    key_id: int = 0x01
    key_type: int = 0x88


@dataclass
class PutKeyResult(Result):
    success: bool
    sw: int
