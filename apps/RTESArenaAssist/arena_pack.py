from __future__ import annotations

import hashlib
import os
import sqlite3
import zlib

PACK_FORMAT_VERSION = "1"

META_FORMAT = "pack_format_version"
META_GENERATOR = "generator_version"
META_FINGERPRINT = "arena_fingerprint"


class PackError(Exception):
    pass


def _validate_name(name: str) -> str:
    n = (name or "").replace("\\", "/")
    if not n:
        raise PackError("empty pack name")
    if n[0] == "/" or ":" in n:
        raise PackError(f"absolute path not allowed in pack: {name!r}")
    if any(part == ".." for part in n.split("/")):
        raise PackError(f"path traversal not allowed in pack: {name!r}")
    return n


class ArenaPack:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    @classmethod
    def create(cls, path: str) -> "ArenaPack":
        if os.path.exists(path):
            os.remove(path)
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
        conn.execute(
            "CREATE TABLE files (name TEXT PRIMARY KEY, sha TEXT NOT NULL, "
            "raw_size INTEGER NOT NULL, data BLOB NOT NULL)")
        conn.execute("INSERT INTO meta(k, v) VALUES (?, ?)",
                     (META_FORMAT, PACK_FORMAT_VERSION))
        conn.commit()
        return cls(conn)

    @classmethod
    def open(cls, path: str) -> "ArenaPack":
        if not os.path.isfile(path):
            raise PackError(f"pack not found: {path}")
        conn = sqlite3.connect(path)
        return cls(conn)

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> "ArenaPack":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (key, str(value)))
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row[0] if row else None

    def all_meta(self) -> dict[str, str]:
        return {k: v for k, v in self._conn.execute("SELECT k, v FROM meta")}

    def put(self, name: str, data: bytes) -> None:
        n = _validate_name(name)
        sha = hashlib.sha256(data).hexdigest()
        comp = zlib.compress(data, 9)
        self._conn.execute(
            "INSERT INTO files(name, sha, raw_size, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET sha=excluded.sha, "
            "raw_size=excluded.raw_size, data=excluded.data",
            (n, sha, len(data), comp))
        self._conn.commit()

    def put_text(self, name: str, text: str) -> None:
        self.put(name, text.encode("utf-8"))

    def get(self, name: str) -> bytes | None:
        n = (name or "").replace("\\", "/")
        row = self._conn.execute(
            "SELECT sha, raw_size, data FROM files WHERE name=?", (n,)).fetchone()
        if row is None:
            return None
        sha, raw_size, comp = row
        try:
            data = zlib.decompress(comp)
        except zlib.error as exc:
            raise PackError(f"pack decompress failed for {name!r}: {exc}") from exc
        if len(data) != raw_size or hashlib.sha256(data).hexdigest() != sha:
            raise PackError(f"pack integrity check failed for {name!r}")
        return data

    def get_text(self, name: str) -> str | None:
        d = self.get(name)
        return None if d is None else d.decode("utf-8")

    def exists(self, name: str) -> bool:
        n = (name or "").replace("\\", "/")
        return self._conn.execute(
            "SELECT 1 FROM files WHERE name=?", (n,)).fetchone() is not None

    def names(self) -> list[str]:
        return [r[0] for r in self._conn.execute(
            "SELECT name FROM files ORDER BY name")]

    def verify(self) -> list[str]:
        bad: list[str] = []
        for name, sha, raw_size in self._conn.execute(
                "SELECT name, sha, raw_size FROM files"):
            try:
                data = self.get(name)
            except (PackError, zlib.error):
                bad.append(name)
                continue
            if data is None or len(data) != raw_size or \
                    hashlib.sha256(data).hexdigest() != sha:
                bad.append(name)
        return bad

    def fingerprint_matches(self, expected: str) -> bool:
        got = self.get_meta(META_FINGERPRINT)
        return got is not None and got == expected


def build_pack(path: str, files: dict[str, bytes], meta: dict[str, str]) -> None:
    with ArenaPack.create(path) as pack:
        for k, v in meta.items():
            pack.set_meta(k, v)
        for name, data in files.items():
            pack.put(name, data)


__all__ = ["ArenaPack", "PackError", "build_pack",
           "META_FORMAT", "META_GENERATOR", "META_FINGERPRINT",
           "PACK_FORMAT_VERSION"]
