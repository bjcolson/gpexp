"""CAP/IJC load file handling."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# GP 2.2 Table 6-2: component load order.
_CAP_COMPONENTS = [
    "Header",
    "Directory",
    "Applet",
    "Import",
    "ConstantPool",
    "Class",
    "Method",
    "StaticField",
    "RefLocation",
    "Descriptor",
    "Debug",
]


@dataclass
class LoadFileInfo:
    """Metadata and data extracted from a CAP or IJC file."""

    data: bytes
    package_aid: bytes = b""
    applet_aids: list[bytes] = field(default_factory=list)


def read_load_file(path: str) -> LoadFileInfo:
    """Read a CAP or IJC file and return load file data plus metadata.

    CAP files are ZIP archives; components are extracted and concatenated
    in the order defined by GP 2.2 Table 6-2.  IJC files are raw binary
    data already in load-file format.
    """
    p = Path(path)
    if p.suffix.lower() == ".ijc":
        return _read_ijc(p)
    return _read_cap(p)


def _read_ijc(path: Path) -> LoadFileInfo:
    data = path.read_bytes()
    package_aid, applet_aids = _parse_metadata(data)
    return LoadFileInfo(data=data, package_aid=package_aid, applet_aids=applet_aids)


def _read_cap(path: Path) -> LoadFileInfo:
    with zipfile.ZipFile(path, "r") as zf:
        cap_entries = [n for n in zf.namelist() if n.lower().endswith(".cap")]
        if not cap_entries:
            raise ValueError(f"no .cap components found in {path}")

        # Map component name to zip entry.
        entry_map: dict[str, str] = {}
        for entry in cap_entries:
            name = entry.split("/")[-1].rsplit(".", 1)[0]
            entry_map[name] = entry

        # Concatenate in defined order.
        buf = bytearray()
        for component in _CAP_COMPONENTS:
            if component in entry_map:
                buf.extend(zf.read(entry_map[component]))

    data = bytes(buf)
    package_aid, applet_aids = _parse_metadata(data)
    return LoadFileInfo(data=data, package_aid=package_aid, applet_aids=applet_aids)


def _parse_metadata(data: bytes) -> tuple[bytes, list[bytes]]:
    """Extract package AID and applet AIDs from concatenated component data.

    Header component (tag 0x01): minor(1) major(1) flags(1) package_info...
        package_info: minor(1) major(1) aid_length(1) aid(n)
    Applet component (tag 0x03): count(1) then for each:
        aid_length(1) aid(n) install_method_offset(2)
    """
    package_aid = b""
    applet_aids: list[bytes] = []

    offset = 0
    while offset + 3 <= len(data):
        tag = data[offset]
        size = int.from_bytes(data[offset + 1 : offset + 3], "big")
        comp_data = data[offset + 3 : offset + 3 + size]
        offset += 3 + size

        if tag == 0x01 and len(comp_data) >= 6:
            # Header: skip minor(1) major(1) flags(1) -> package info
            p = 3
            # package info: minor(1) major(1) aid_length(1) aid(n)
            p += 2  # skip pkg minor, major
            aid_len = comp_data[p]
            p += 1
            if p + aid_len <= len(comp_data):
                package_aid = bytes(comp_data[p : p + aid_len])

        elif tag == 0x03 and len(comp_data) >= 1:
            # Applet component
            count = comp_data[0]
            p = 1
            for _ in range(count):
                if p >= len(comp_data):
                    break
                aid_len = comp_data[p]
                p += 1
                if p + aid_len + 2 <= len(comp_data):
                    applet_aids.append(bytes(comp_data[p : p + aid_len]))
                    p += aid_len + 2  # aid + install_method_offset(2)

    return package_aid, applet_aids
