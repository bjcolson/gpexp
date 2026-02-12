"""GP card information data model and parsing."""

from __future__ import annotations

from dataclasses import dataclass, field

from gpexp.app.generic.cardinfo import CardInfo
from gpexp.core.smartcard.tlv import TLV, parse as parse_tlv


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CPLC:
    """Card Production Life Cycle data (42 bytes)."""

    ic_fabricator: bytes
    ic_type: bytes
    os_id: bytes
    os_release_date: bytes
    os_release_level: bytes
    ic_fabrication_date: bytes
    ic_serial: bytes
    ic_batch: bytes
    ic_module_fabricator: bytes
    ic_module_packaging_date: bytes
    icc_manufacturer: bytes
    ic_embedding_date: bytes
    ic_pre_personalizer: bytes
    ic_pre_personalization_date: bytes
    ic_pre_personalization_equipment: bytes
    ic_personalizer: bytes
    ic_personalization_date: bytes
    ic_personalization_equipment: bytes


@dataclass
class KeyInfo:
    """A key set entry from the Key Information Template (E0)."""

    key_id: int
    key_version: int
    components: list[tuple[int, int]]  # (key_type, key_length) pairs


@dataclass
class AppEntry:
    """Parsed GET STATUS entry (application, package, or ISD)."""

    aid: bytes
    lifecycle: int
    privileges: bytes = b""
    executable_load_file: bytes = b""
    executable_module: bytes = b""
    version: bytes = b""
    associated_sd: bytes = b""


@dataclass
class GPCardInfo(CardInfo):
    """GP-specific card information extending base CardInfo."""

    cplc: CPLC | None = None
    key_info: list[KeyInfo] = field(default_factory=list)
    card_recognition: list[str] = field(default_factory=list)
    iin: bytes | None = None
    cin: bytes | None = None
    seq_counter: int | None = None
    isd: list[AppEntry] = field(default_factory=list)
    applications: list[AppEntry] = field(default_factory=list)
    packages: list[AppEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_cplc(data: bytes) -> CPLC:
    """Parse 42 bytes of raw CPLC data."""
    if len(data) < 42:
        raise ValueError(f"CPLC too short: {len(data)} bytes")
    return CPLC(
        ic_fabricator=data[0:2],
        ic_type=data[2:4],
        os_id=data[4:6],
        os_release_date=data[6:8],
        os_release_level=data[8:10],
        ic_fabrication_date=data[10:12],
        ic_serial=data[12:16],
        ic_batch=data[16:18],
        ic_module_fabricator=data[18:20],
        ic_module_packaging_date=data[20:22],
        icc_manufacturer=data[22:24],
        ic_embedding_date=data[24:26],
        ic_pre_personalizer=data[26:28],
        ic_pre_personalization_date=data[28:30],
        ic_pre_personalization_equipment=data[30:34],
        ic_personalizer=data[34:36],
        ic_personalization_date=data[36:38],
        ic_personalization_equipment=data[38:42],
    )


def parse_key_info(data: bytes) -> list[KeyInfo]:
    """Parse Key Information Template response into KeyInfo entries."""
    nodes = parse_tlv(data)
    # Handle both wrapped (E0 > C0...) and bare (C0...) forms
    c0_nodes: list[TLV] = []
    for node in nodes:
        if node.tag == 0xE0:
            c0_nodes.extend(child for child in node.children if child.tag == 0xC0)
        elif node.tag == 0xC0:
            c0_nodes.append(node)

    entries = []
    for node in c0_nodes:
        val = node.value
        if len(val) < 4:
            continue
        key_id = val[0]
        key_version = val[1]
        components = []
        i = 2
        while i + 1 < len(val):
            components.append((val[i], val[i + 1]))
            i += 2
        entries.append(KeyInfo(key_id=key_id, key_version=key_version, components=components))
    return entries


def decode_oid(data: bytes) -> str:
    """Decode an ASN.1 OID from DER bytes to dotted notation."""
    if not data:
        return ""
    components = [data[0] // 40, data[0] % 40]
    value = 0
    for byte in data[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not (byte & 0x80):
            components.append(value)
            value = 0
    return ".".join(str(c) for c in components)


def parse_card_recognition(data: bytes) -> list[str]:
    """Parse Card Recognition Data (66) and return decoded OID strings."""
    nodes = parse_tlv(data)
    oids: list[str] = []
    _collect_oids(nodes, oids)
    return oids


def _collect_oids(nodes: list[TLV], out: list[str]) -> None:
    """Recursively collect OID values (tag 06) from a TLV tree."""
    for node in nodes:
        if node.tag == 0x06:
            out.append(decode_oid(node.value))
        if node.children:
            _collect_oids(node.children, out)


def parse_status(nodes: list[TLV]) -> list[AppEntry]:
    """Parse GET STATUS TLV nodes (E3 templates) into AppEntry list."""
    entries = []
    for node in nodes:
        if node.tag != 0xE3:
            continue
        aid_tlv = node.find(0x4F)
        lc_tlv = node.find(0x9F70)
        priv_tlv = node.find(0xC5)
        elf_tlv = node.find(0xC4)
        mod_tlv = node.find(0x84)
        ver_tlv = node.find(0xCE)
        sd_tlv = node.find(0xCC)
        entries.append(AppEntry(
            aid=aid_tlv.value if aid_tlv else b"",
            lifecycle=lc_tlv.value[0] if lc_tlv and lc_tlv.value else 0,
            privileges=priv_tlv.value if priv_tlv else b"",
            executable_load_file=elf_tlv.value if elf_tlv else b"",
            executable_module=mod_tlv.value if mod_tlv else b"",
            version=ver_tlv.value if ver_tlv else b"",
            associated_sd=sd_tlv.value if sd_tlv else b"",
        ))
    return entries
