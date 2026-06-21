from __future__ import annotations

import os
import struct

_FILENAME_LEN = 12
_RECORD_SIZE = 18
_BASE_OFFSET = 2


class BsaError(Exception):
    pass


class BsaArchive:

    def __init__(self, path: str):
        self.path = path
        self._entries: dict[str, tuple[int, int]] = {}
        self._names: list[str] = []
        self._load()

    def _load(self) -> None:
        size = os.path.getsize(self.path)
        with open(self.path, "rb") as fh:
            head = fh.read(2)
            if len(head) < 2:
                raise BsaError(f"BSA too small: {self.path}")
            count = struct.unpack_from("<H", head)[0]
            footer_size = count * _RECORD_SIZE
            if footer_size > size - _BASE_OFFSET:
                raise BsaError(
                    f"BSA footer ({footer_size}) exceeds file size {size}")
            fh.seek(size - footer_size)
            footer = fh.read(footer_size)
        if len(footer) != footer_size:
            raise BsaError("Failed to read BSA footer")

        cursor = _BASE_OFFSET
        for i in range(count):
            off = i * _RECORD_SIZE
            raw_name = footer[off:off + _FILENAME_LEN]
            name = raw_name.split(b"\x00", 1)[0].decode("latin-1").replace("\\", "/")
            compressed = struct.unpack_from("<H", footer, off + _FILENAME_LEN)[0]
            fsize = struct.unpack_from("<I", footer, off + _FILENAME_LEN + 2)[0]
            if compressed != 0:
                raise BsaError(f"Compressed BSA entry not supported: {name}")
            start = cursor
            cursor += fsize
            self._entries[name.upper()] = (start, fsize)
            self._names.append(name)

    def names(self) -> list[str]:
        return list(self._names)

    def exists(self, name: str) -> bool:
        return name.upper() in self._entries

    def read(self, name: str) -> bytes | None:
        ent = self._entries.get(name.upper())
        if ent is None:
            return None
        start, fsize = ent
        with open(self.path, "rb") as fh:
            fh.seek(start)
            data = fh.read(fsize)
        if len(data) != fsize:
            raise BsaError(f"Short read for {name}: {len(data)}/{fsize}")
        return data


def pack_bsa(files: dict[str, bytes]) -> bytes:
    names = list(files.keys())
    count = len(names)
    body = b"".join(files[n] for n in names)
    footer = bytearray()
    for n in names:
        nb = n.encode("latin-1")[:_FILENAME_LEN]
        nb = nb + b"\x00" * (_FILENAME_LEN - len(nb))
        footer += nb + struct.pack("<HI", 0, len(files[n]))
    return struct.pack("<H", count) + body + bytes(footer)


_INF_ENCRYPTION_KEYS = (0xEA, 0x7B, 0x4E, 0xBD, 0x19, 0xC9, 0x38, 0x99)


def decrypt_inf(data: bytes) -> bytes:
    out = bytearray(data)
    key_index = 0
    count = 0
    for i in range(len(out)):
        out[i] ^= (count + _INF_ENCRYPTION_KEYS[key_index]) & 0xFF
        key_index = (key_index + 1) & 7
        count = (count + 1) & 0xFF
    return bytes(out)


class Vfs:

    def __init__(self, arena_dir: str, bsa_name: str = "GLOBAL.BSA"):
        self.arena_dir = arena_dir
        self._bsa_name = bsa_name
        self._bsa: BsaArchive | None = None
        self._bsa_failed = False
        self._loose_index: dict[str, str] | None = None

    def _loose(self) -> dict[str, str]:
        if self._loose_index is None:
            idx: dict[str, str] = {}
            try:
                for entry in os.listdir(self.arena_dir):
                    full = os.path.join(self.arena_dir, entry)
                    if os.path.isfile(full):
                        idx[entry.upper()] = full
            except OSError:
                pass
            self._loose_index = idx
        return self._loose_index

    def _bsa_archive(self) -> BsaArchive | None:
        if self._bsa is None and not self._bsa_failed:
            path = self._loose().get(self._bsa_name.upper())
            if path is None:
                self._bsa_failed = True
                return None
            try:
                self._bsa = BsaArchive(path)
            except (BsaError, OSError, struct.error):
                self._bsa_failed = True
                return None
        return self._bsa

    def read(self, name: str) -> bytes | None:
        loose = self._loose().get(name.upper())
        if loose is not None and name.upper() != self._bsa_name.upper():
            try:
                with open(loose, "rb") as fh:
                    return fh.read()
            except OSError:
                pass
        bsa = self._bsa_archive()
        if bsa is not None:
            return bsa.read(name)
        return None

    def read_inf(self, name: str) -> bytes | None:
        loose = self._loose().get(name.upper())
        if loose is not None and name.upper() != self._bsa_name.upper():
            try:
                with open(loose, "rb") as fh:
                    return fh.read()
            except OSError:
                pass
        bsa = self._bsa_archive()
        if bsa is not None:
            data = bsa.read(name)
            if data is not None:
                return decrypt_inf(data)
        return None

    def exists(self, name: str) -> bool:
        if name.upper() in self._loose() and name.upper() != self._bsa_name.upper():
            return True
        bsa = self._bsa_archive()
        return bool(bsa and bsa.exists(name))

    def names(self) -> list[str]:
        names: set[str] = set()
        for upper in self._loose():
            if upper != self._bsa_name.upper():
                names.add(upper)
        bsa = self._bsa_archive()
        if bsa is not None:
            names.update(n.upper() for n in bsa.names())
        return sorted(names)


__all__ = ["BsaArchive", "Vfs", "BsaError", "pack_bsa", "decrypt_inf"]
