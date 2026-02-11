"""Shared SCP types and constants (used by SCP02 and SCP03)."""

from __future__ import annotations

from dataclasses import dataclass

# Security level flags (GP 2.3 Table 11-18)
C_MAC = 0x01
C_DECRYPTION = 0x02
R_MAC = 0x10
R_ENCRYPTION = 0x20


@dataclass
class StaticKeys:
    """Static key set for secure channel establishment."""

    enc: bytes
    mac: bytes
    dek: bytes = b""


@dataclass
class SessionSetup:
    """Result of SCP session establishment (before EXTERNAL AUTHENTICATE)."""

    key_info: bytes
    i_param: int
    host_cryptogram: bytes
    channel: object  # SCP02Channel | SCP03Channel
