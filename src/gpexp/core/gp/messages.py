from __future__ import annotations

from dataclasses import dataclass

from gpexp.core.base import Message, Result
from gpexp.core.gp.security import C_MAC, StaticKeys
from gpexp.core.smartcard.tlv import TLV


# MANAGE ELF UPGRADE P1 values
UPGRADE_START = 0x01
UPGRADE_RESUME = 0x02
UPGRADE_RECOVERY = 0x03
UPGRADE_ABORT = 0x04
UPGRADE_STATUS = 0x08

# Upgrade session status values (tag 90 in response)
UPS_NO_SESSION = 0x00
UPS_COMPLETED = 0x01
UPS_WAITING_ELF = 0x02
UPS_WAITING_RESTORE = 0x03
UPS_WAITING_RESTORE_FAILED = 0x04
UPS_INTERRUPTED_SAVING = 0x10
UPS_INTERRUPTED_CLEANUP = 0x20
UPS_INTERRUPTED_DELETE = 0x30
UPS_INTERRUPTED_INSTALL = 0x40
UPS_INTERRUPTED_RESTORE = 0x50
UPS_INTERRUPTED_CONSOLIDATE = 0x60


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
class DeleteMessage(Message):
    """Request to DELETE card content (package or applet) by AID."""

    aid: bytes
    related: bool = False


@dataclass
class DeleteResult(Result):
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


@dataclass
class LoadMessage(Message):
    """Load a package onto the card (INSTALL [for load] + LOAD blocks)."""

    load_file_data: bytes
    load_file_aid: bytes
    sd_aid: bytes = b""
    block_size: int = 239


@dataclass
class LoadResult(Result):
    success: bool
    blocks_sent: int
    sw: int
    error: str | None = None


@dataclass
class InstallMessage(Message):
    """Install an applet (INSTALL [for install and make selectable])."""

    package_aid: bytes
    module_aid: bytes
    instance_aid: bytes = b""
    privileges: bytes = b"\x00"
    params: bytes = b"\xC9\x00"
    make_selectable: bool = True


@dataclass
class InstallResult(Result):
    success: bool
    sw: int


@dataclass
class ManageUpgradeMessage(Message):
    """MANAGE ELF UPGRADE (80 EA)."""

    action: int
    elf_aid: bytes = b""
    options: int = 0


@dataclass
class ManageUpgradeResult(Result):
    success: bool
    sw: int
    session_status: int | None = None
    elf_aid: bytes | None = None
    error: str | None = None
