"""ISO 9797-1 Method 2 padding (shared by SCP02 and SCP03)."""

from __future__ import annotations


def pad80(data: bytes, block_size: int) -> bytes:
    """Apply ISO 9797-1 Method 2 padding to *block_size* boundary."""
    return data + b"\x80" + b"\x00" * ((-len(data) - 1) % block_size)


def unpad80(data: bytes) -> bytes:
    """Remove ISO 9797-1 Method 2 padding."""
    i = len(data) - 1
    while i >= 0 and data[i] == 0x00:
        i -= 1
    if i < 0 or data[i] != 0x80:
        raise ValueError("invalid padding")
    return data[:i]
