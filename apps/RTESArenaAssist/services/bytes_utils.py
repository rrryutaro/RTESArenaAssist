from __future__ import annotations

def rol32(value: int, count: int) -> int:
    value &= 4294967295
    count &= 31
    return (value << count | value >> 32 - count) & 4294967295

def ror32(value: int, count: int) -> int:
    value &= 4294967295
    count &= 31
    return (value >> count | value << 32 - count) & 4294967295

def rol16(value: int, count: int) -> int:
    value &= 65535
    count &= 15
    return (value << count | value >> 16 - count) & 65535

def ror16(value: int, count: int) -> int:
    value &= 65535
    count &= 15
    return (value >> count | value << 16 - count) & 65535

def get_le32(data: bytes, offset: int=0) -> int:
    return int.from_bytes(data[offset:offset + 4], 'little')

def get_le16(data: bytes, offset: int=0) -> int:
    return int.from_bytes(data[offset:offset + 2], 'little')
