from __future__ import annotations

import math
from typing import Tuple


class WireType:
    VARINT = 0
    FIXED64 = 1
    BYTES = 2
    START_GROUP = 3
    END_GROUP = 4
    FIXED32 = 5


def put_uvarint(x: int) -> bytes:
    out = bytearray()
    while x >= 0x80:
        out.append((x & 0x7F) | 0x80)
        x >>= 7
    out.append(x & 0x7F)
    return bytes(out)


def uvarint(buf: bytes, pos: int = 0) -> Tuple[int, int]:
    x = 0
    s = 0
    i = pos
    for _ in range(10):
        if i >= len(buf):
            return 0, 0
        b = buf[i]
        i += 1
        if b < 0x80:
            if (i - pos) > 9 or ((i - pos) == 9 and b > 1):
                return 0, -(i - pos)
            return x | (b << s), i - pos
        x |= (b & 0x7F) << s
        s += 7
    return 0, 0


class ProtoEncoder:
    def __init__(self) -> None:
        self.buf = bytearray()

    def encode_field_number(self, field_number: int, wire_type: int) -> None:
        key = (field_number << 3) | (wire_type & 0x7)
        self.buf.extend(put_uvarint(key))

    def encode_varint(self, value: int) -> None:
        self.buf.extend(put_uvarint(value & ((1 << 64) - 1)))

    def encode_int64(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.VARINT)
        self.encode_varint(value & ((1 << 64) - 1))

    def encode_int32(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.VARINT)
        self.encode_varint(value & ((1 << 32) - 1))

    def encode_uint64(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.VARINT)
        self.encode_varint(value)

    def encode_uint32(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.VARINT)
        self.encode_varint(value)

    def encode_bool(self, field_number: int, value: bool) -> None:
        self.encode_field_number(field_number, WireType.VARINT)
        self.encode_varint(1 if value else 0)

    def encode_string(self, field_number: int, value: str) -> None:
        data = value.encode("utf-8")
        self.encode_field_number(field_number, WireType.BYTES)
        self.encode_varint(len(data))
        self.buf.extend(data)

    def encode_bytes(self, field_number: int, value: bytes) -> None:
        self.encode_field_number(field_number, WireType.BYTES)
        self.encode_varint(len(value))
        self.buf.extend(value)

    def encode_fixed64(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.FIXED64)
        self.buf.extend((value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little"))

    def encode_fixed32(self, field_number: int, value: int) -> None:
        self.encode_field_number(field_number, WireType.FIXED32)
        self.buf.extend((value & 0xFFFFFFFF).to_bytes(4, "little"))

    def encode_float(self, field_number: int, value: float) -> None:
        self.encode_fixed32(field_number, math.frexp(value)[0])  # not used

    def bytes(self) -> bytes:
        return bytes(self.buf)


class ProtoDecoder:
    def __init__(self, data: bytes) -> None:
        self.buf = data
        self.pos = 0

    def decode_field_number(self) -> Tuple[int, int]:
        if self.pos >= len(self.buf):
            raise EOFError("EOF")
        value, n = uvarint(self.buf, self.pos)
        if n <= 0:
            raise ValueError("invalid varint")
        self.pos += n
        field_number = value >> 3
        wire_type = value & 0x7
        return field_number, wire_type

    def decode_varint(self) -> int:
        if self.pos >= len(self.buf):
            raise EOFError("EOF")
        value, n = uvarint(self.buf, self.pos)
        if n <= 0:
            raise ValueError("invalid varint")
        self.pos += n
        return value

    def decode_int64(self) -> int:
        return int(self.decode_varint())

    def decode_int32(self) -> int:
        return int(self.decode_varint()) & 0xFFFFFFFF

    def decode_uint64(self) -> int:
        return self.decode_varint()

    def decode_bool(self) -> bool:
        return self.decode_varint() != 0

    def decode_string(self) -> str:
        length = self.decode_varint()
        end = self.pos + int(length)
        if end > len(self.buf):
            raise ValueError("invalid length")
        s = self.buf[self.pos:end].decode("utf-8", errors="replace")
        self.pos = end
        return s

    def decode_bytes(self) -> bytes:
        length = self.decode_varint()
        end = self.pos + int(length)
        if end > len(self.buf):
            raise ValueError("invalid length")
        b = self.buf[self.pos:end]
        self.pos = end
        return b

    def decode_fixed64(self) -> int:
        end = self.pos + 8
        if end > len(self.buf):
            raise EOFError("EOF")
        v = int.from_bytes(self.buf[self.pos:end], "little")
        self.pos = end
        return v

    def decode_fixed32(self) -> int:
        end = self.pos + 4
        if end > len(self.buf):
            raise EOFError("EOF")
        v = int.from_bytes(self.buf[self.pos:end], "little")
        self.pos = end
        return v

    def skip_field(self, wire_type: int) -> None:
        if wire_type == WireType.VARINT:
            _ = self.decode_varint()
            return
        if wire_type == WireType.FIXED64:
            self.pos += 8
            return
        if wire_type == WireType.BYTES:
            length = self.decode_varint()
            self.pos += int(length)
            return
        if wire_type == WireType.FIXED32:
            self.pos += 4
            return
        # Try to resync a bit if wire type is unexpected
        if not self._resync_to_next_key():
            raise ValueError(f"unsupported wire type: {wire_type}")

    def _resync_to_next_key(self) -> bool:
        start = self.pos
        limit = min(self.pos + 64, len(self.buf))
        for i in range(start, limit):
            key, n = uvarint(self.buf, i)
            if n > 0:
                wt = key & 0x7
                fn = key >> 3
                if wt <= 5 and fn != 0:
                    self.pos = i
                    return True
        return False

