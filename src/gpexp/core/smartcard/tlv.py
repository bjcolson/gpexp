from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TLV:
    """A single BER-TLV node."""

    tag: int
    value: bytes = b""
    children: list[TLV] = field(default_factory=list)

    @property
    def constructed(self) -> bool:
        """Whether this TLV has a constructed (non-primitive) tag."""
        if self.tag <= 0xFF:
            return bool(self.tag & 0x20)
        return bool((self.tag >> 8) & 0x20)

    def find(self, tag: int) -> TLV | None:
        """Find the first child with the given tag (non-recursive)."""
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def find_recursive(self, tag: int) -> TLV | None:
        """Find the first descendant with the given tag (depth-first)."""
        for child in self.children:
            if child.tag == tag:
                return child
            result = child.find_recursive(tag)
            if result is not None:
                return result
        return None

    def format(self, tag_names: dict[int, str] | None = None, indent: int = 0) -> str:
        """Format this TLV node as a human-readable tree."""
        names = tag_names or {}
        tag_hex = f"{self.tag:02X}" if self.tag <= 0xFF else f"{self.tag:04X}"
        name = names.get(self.tag, "")
        prefix = "  " * indent
        if self.children:
            label = f"{prefix}{tag_hex} {name}".rstrip()
            lines = [label]
            for child in self.children:
                lines.append(child.format(names, indent + 1))
            return "\n".join(lines)
        return f"{prefix}{tag_hex} {name}: {self.value.hex(' ').upper()}".rstrip()

    def __repr__(self) -> str:
        tag_hex = f"{self.tag:02X}" if self.tag <= 0xFF else f"{self.tag:04X}"
        if self.children:
            kids = ", ".join(repr(c) for c in self.children)
            return f"TLV({tag_hex}, [{kids}])"
        return f"TLV({tag_hex}, {self.value.hex().upper()})"


def parse(data: bytes) -> list[TLV]:
    """Parse a byte sequence into a list of BER-TLV nodes."""
    nodes: list[TLV] = []
    offset = 0
    while offset < len(data):
        if data[offset] in (0x00, 0xFF):
            offset += 1
            continue
        tag, offset = _read_tag(data, offset)
        length, offset = _read_length(data, offset)
        value = data[offset : offset + length]
        offset += length

        node = TLV(tag=tag, value=value)
        if node.constructed:
            node.children = parse(value)
        nodes.append(node)
    return nodes


def _read_tag(data: bytes, offset: int) -> tuple[int, int]:
    """Read a BER-TLV tag and return (tag, new_offset)."""
    b = data[offset]
    offset += 1
    if (b & 0x1F) == 0x1F:
        tag = b
        while True:
            b = data[offset]
            tag = (tag << 8) | b
            offset += 1
            if not (b & 0x80):
                break
    else:
        tag = b
    return tag, offset


def _read_length(data: bytes, offset: int) -> tuple[int, int]:
    """Read a BER-TLV length and return (length, new_offset)."""
    b = data[offset]
    offset += 1
    if b < 0x80:
        return b, offset
    num_bytes = b & 0x7F
    length = 0
    for _ in range(num_bytes):
        length = (length << 8) | data[offset]
        offset += 1
    return length, offset
