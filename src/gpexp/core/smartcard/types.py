from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class APDU:
    """ISO 7816 command APDU."""

    cla: int
    ins: int
    p1: int
    p2: int
    data: bytes = b""
    le: int | None = None

    def to_bytes(self) -> bytes:
        buf = bytearray([self.cla, self.ins, self.p1, self.p2])
        if self.data:
            buf.append(len(self.data))
            buf.extend(self.data)
        if self.le is not None:
            buf.append(self.le)
        return bytes(buf)

    def __repr__(self) -> str:
        return self.to_bytes().hex(" ").upper()


@dataclass
class Response:
    """ISO 7816 response APDU."""

    data: bytes
    sw1: int
    sw2: int

    @property
    def sw(self) -> int:
        return (self.sw1 << 8) | self.sw2

    @property
    def success(self) -> bool:
        return self.sw1 == 0x90 and self.sw2 == 0x00

    def __repr__(self) -> str:
        sw = f"SW={self.sw:04X}"
        if self.data:
            return f"{self.data.hex(' ').upper()} {sw}"
        return sw
