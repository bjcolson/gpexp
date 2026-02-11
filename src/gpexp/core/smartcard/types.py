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
        extended = len(self.data) > 255 or (self.le is not None and self.le > 256)
        if extended:
            if self.data:
                buf.append(0x00)
                buf.extend(len(self.data).to_bytes(2, "big"))
                buf.extend(self.data)
            elif self.le is not None:
                buf.append(0x00)
            if self.le is not None:
                le = 0x0000 if self.le == 65536 else self.le
                buf.extend(le.to_bytes(2, "big"))
        else:
            if self.data:
                buf.append(len(self.data))
                buf.extend(self.data)
            if self.le is not None:
                buf.append(0x00 if self.le == 256 else self.le)
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
