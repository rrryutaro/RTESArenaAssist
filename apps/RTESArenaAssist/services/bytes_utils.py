"""bytes_utils.py — Arena 互換のビット演算ヘルパー。

OpenTESArena `components/utilities/Bytes` の rol/ror および Bytes::getLE32 を
Python に移植する。
"""
from __future__ import annotations


def rol32(value: int, count: int) -> int:
    """32-bit 左ローテーション。"""
    value &= 0xFFFFFFFF
    count &= 31
    return ((value << count) | (value >> (32 - count))) & 0xFFFFFFFF


def ror32(value: int, count: int) -> int:
    """32-bit 右ローテーション。"""
    value &= 0xFFFFFFFF
    count &= 31
    return ((value >> count) | (value << (32 - count))) & 0xFFFFFFFF


def rol16(value: int, count: int) -> int:
    """16-bit 左ローテーション。"""
    value &= 0xFFFF
    count &= 15
    return ((value << count) | (value >> (16 - count))) & 0xFFFF


def ror16(value: int, count: int) -> int:
    """16-bit 右ローテーション。"""
    value &= 0xFFFF
    count &= 15
    return ((value >> count) | (value << (16 - count))) & 0xFFFF


def get_le32(data: bytes, offset: int = 0) -> int:
    """little-endian 32-bit 整数を読み取る (Bytes::getLE32 相当)。"""
    return int.from_bytes(data[offset:offset + 4], "little")


def get_le16(data: bytes, offset: int = 0) -> int:
    """little-endian 16-bit 整数を読み取る。"""
    return int.from_bytes(data[offset:offset + 2], "little")
