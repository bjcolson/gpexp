"""Base card information data model."""

from __future__ import annotations

from dataclasses import dataclass, field

from gpexp.core.smartcard.tlv import TLV


@dataclass
class CardInfo:
    """Base card information: identity fields only."""

    uid: bytes | None = None
    atr: bytes = b""
    fci: list[TLV] = field(default_factory=list)
