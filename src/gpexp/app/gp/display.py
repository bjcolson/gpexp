"""Human-readable GP card information formatting."""

from __future__ import annotations

from gpexp.app.gp.cardinfo import AppEntry, GPCardInfo, CPLC, KeyInfo
from gpexp.core.base.tags import TAG_NAMES


def _hex(data: bytes) -> str:
    return data.hex(" ").upper() if data else ""


# --- Lookup tables ---

_FABRICATORS: dict[bytes, str] = {
    bytes.fromhex("4790"): "NXP",
    bytes.fromhex("4180"): "Atmel",
    bytes.fromhex("4090"): "Infineon",
    bytes.fromhex("3060"): "Renesas",
    bytes.fromhex("0003"): "Samsung",
}

_KEY_TYPES: dict[int, str] = {
    0x80: "DES",
    0x82: "3DES-CBC",
    0x83: "DES-ECB",
    0x84: "DES-CBC",
    0x88: "AES",
    0xFF: "Extended",
}

_ISD_STATES: dict[int, str] = {
    0x01: "OP_READY",
    0x07: "INITIALIZED",
    0x0F: "SECURED",
    0x7F: "CARD_LOCKED",
    0xFF: "TERMINATED",
}

_APP_STATES: dict[int, str] = {
    0x03: "INSTALLED",
    0x07: "SELECTABLE",
    0x83: "LOCKED",
}

_PKG_STATES: dict[int, str] = {
    0x01: "LOADED",
}

_PRIVILEGES: list[tuple[int, int, str]] = [
    # Byte 1
    (0, 0x80, "Security Domain"),
    (0, 0x40, "DAP Verification"),
    (0, 0x20, "Delegated Management"),
    (0, 0x10, "Card Lock"),
    (0, 0x08, "Card Terminate"),
    (0, 0x04, "Default Selected"),
    (0, 0x02, "CVM Management"),
    (0, 0x01, "Mandated DAP Verification"),
    # Byte 2
    (1, 0x80, "Trusted Path"),
    (1, 0x40, "Authorized Management"),
    (1, 0x20, "Token Verification"),
    (1, 0x10, "Global Delete"),
    (1, 0x08, "Global Lock"),
    (1, 0x04, "Global Registry"),
    (1, 0x02, "Final Application"),
    (1, 0x01, "Global Service"),
    # Byte 3
    (2, 0x80, "Receipt Generation"),
    (2, 0x40, "Ciphered Load File Data Block"),
    (2, 0x20, "Contactless Activation"),
    (2, 0x10, "Contactless Self-Activation"),
]

_GP_OID_BASE = "1.2.840.114283"

_GP_OID_NAMES: dict[str, str] = {
    f"{_GP_OID_BASE}.1": "GP Card Recognition Data",
    f"{_GP_OID_BASE}.2.2.1.1": "GP v2.1.1",
    f"{_GP_OID_BASE}.2.2.2": "GP v2.2",
    f"{_GP_OID_BASE}.2.2.2.1": "GP v2.2.1",
    f"{_GP_OID_BASE}.2.2.3": "GP v2.3",
    f"{_GP_OID_BASE}.2.2.3.1": "GP v2.3.1",
    f"{_GP_OID_BASE}.3.1": "Card ID Scheme 1",
    f"{_GP_OID_BASE}.3.2": "Card ID Scheme 2",
    f"{_GP_OID_BASE}.4.1": "SCP01",
    f"{_GP_OID_BASE}.4.2": "SCP02",
    f"{_GP_OID_BASE}.4.3": "SCP03",
}


# --- Helpers ---

def _fab(data: bytes) -> str:
    name = _FABRICATORS.get(data)
    return f" ({name})" if name else ""


def _state(value: int, names: dict[int, str]) -> str:
    name = names.get(value)
    return f"{name} ({value:02X})" if name else f"{value:02X}"


def _key_type_str(key_type: int, key_length: int) -> str:
    name = _KEY_TYPES.get(key_type, f"{key_type:02X}")
    bits = key_length * 8
    return f"{name}-{bits}"


def _decode_privileges(data: bytes) -> list[str]:
    names: list[str] = []
    for byte_idx, mask, label in _PRIVILEGES:
        if byte_idx < len(data) and data[byte_idx] & mask:
            names.append(label)
    return names


def _describe_oid(oid: str) -> str:
    if oid in _GP_OID_NAMES:
        return _GP_OID_NAMES[oid]
    # SCP with i parameter: e.g. 1.2.840.114283.4.3.112
    parts = oid.rsplit(".", 1)
    if len(parts) == 2 and parts[0] in _GP_OID_NAMES and parts[0].startswith(f"{_GP_OID_BASE}.4."):
        try:
            i_param = int(parts[1])
            return f"{_GP_OID_NAMES[parts[0]]} i={i_param:02X}"
        except ValueError:
            pass
    return ""


# --- Section formatters ---

def format_cplc(cplc: CPLC) -> str:
    fields = [
        ("IC Fabricator", f"{_hex(cplc.ic_fabricator)}{_fab(cplc.ic_fabricator)}"),
        ("IC Type", _hex(cplc.ic_type)),
        ("OS ID", _hex(cplc.os_id)),
        ("OS Release Date", _hex(cplc.os_release_date)),
        ("OS Release Level", _hex(cplc.os_release_level)),
        ("IC Fabrication Date", _hex(cplc.ic_fabrication_date)),
        ("IC Serial Number", _hex(cplc.ic_serial)),
        ("IC Batch ID", _hex(cplc.ic_batch)),
        ("Module Fabricator", f"{_hex(cplc.ic_module_fabricator)}{_fab(cplc.ic_module_fabricator)}"),
        ("Module Packaging Date", _hex(cplc.ic_module_packaging_date)),
        ("ICC Manufacturer", f"{_hex(cplc.icc_manufacturer)}{_fab(cplc.icc_manufacturer)}"),
        ("IC Embedding Date", _hex(cplc.ic_embedding_date)),
        ("Pre-Personalizer", _hex(cplc.ic_pre_personalizer)),
        ("Pre-Perso Date", _hex(cplc.ic_pre_personalization_date)),
        ("Pre-Perso Equipment", _hex(cplc.ic_pre_personalization_equipment)),
        ("Personalizer", _hex(cplc.ic_personalizer)),
        ("Perso Date", _hex(cplc.ic_personalization_date)),
        ("Perso Equipment", _hex(cplc.ic_personalization_equipment)),
    ]
    w = max(len(label) for label, _ in fields)
    return "\n".join(f"  {label:<{w}}  {value}" for label, value in fields)


def format_key_info(entries: list[KeyInfo]) -> str:
    lines = []
    for entry in entries:
        components = " / ".join(_key_type_str(t, l) for t, l in entry.components)
        lines.append(f"  Version {entry.key_version:02X}  ID {entry.key_id:02X}  {components}")
    return "\n".join(lines)


def format_card_recognition(oids: list[str]) -> str:
    lines = []
    for oid in oids:
        desc = _describe_oid(oid)
        if desc:
            lines.append(f"  {oid} ({desc})")
        else:
            lines.append(f"  {oid}")
    return "\n".join(lines)


def _format_entry(entry: AppEntry, states: dict[int, str]) -> str:
    aid = _hex(entry.aid)
    state = _state(entry.lifecycle, states)
    line = f"  {aid:<48s}{state}"
    privs = _decode_privileges(entry.privileges)
    if privs:
        line += f"\n    {', '.join(privs)}"
    for mod in entry.executable_modules:
        line += f"\n    {_hex(mod)}"
    return line


# --- Composite formatters ---

def format_card_data(info: GPCardInfo) -> str:
    """Format card data sections: keys, card recognition, IIN, CIN, seq counter."""
    sections: list[str] = []
    if info.key_info:
        sections.append(f"--- Keys ---\n{format_key_info(info.key_info)}")
    if info.card_recognition:
        sections.append(f"--- Card Recognition ---\n{format_card_recognition(info.card_recognition)}")
    if info.iin:
        sections.append(f"  IIN  {_hex(info.iin)}")
    if info.cin:
        sections.append(f"  CIN  {_hex(info.cin)}")
    if info.seq_counter is not None:
        sections.append(f"--- Sequence Counter ---\n  {info.seq_counter}")
    return "\n\n".join(sections)


def format_contents(info: GPCardInfo) -> str:
    """Format ISD, applications, and packages."""
    sections: list[str] = []
    if info.isd:
        entries = "\n".join(_format_entry(e, _ISD_STATES) for e in info.isd)
        sections.append(f"--- ISD ---\n{entries}")
    if info.applications:
        entries = "\n".join(_format_entry(e, _APP_STATES) for e in info.applications)
        sections.append(f"--- Applications ({len(info.applications)}) ---\n{entries}")
    if info.packages:
        entries = "\n".join(_format_entry(e, _PKG_STATES) for e in info.packages)
        sections.append(f"--- Packages ({len(info.packages)}) ---\n{entries}")
    return "\n\n".join(sections)
