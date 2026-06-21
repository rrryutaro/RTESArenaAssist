"""arena_pack.py — Arena 由来ローカル生成物の単一データパック。

ユーザー環境で再生成した Arena 由来データ（`_original`・en・復号済み MIF/INF/RMD/画像 等）を
**1 ファイル**へ集約する。ユーザー領域にファイルを散らかさず、再生成可能・削除可能にする。

実装方針:
  - 形式 = **SQLite + zlib**（stdlib のみ・追加依存なし。索引付き・単一ファイル・queryable）。
  - 各ファイルは zlib 圧縮 blob + sha256 で保持。読取時に sha 照合（破損検出）。
  - パック内に **実パスを保存しない**（名前は相対のみ。絶対/ドライブ/`..` は拒否）。
  - meta に Arena 版指紋・生成器バージョン・パック形式版を内蔵し、起動時に整合チェック。
  - **共有/export 不可**: 原文(_original)・en・復号物を含むためローカル限定。翻訳 overlay の
    共有パックとは別物（export は別経路で source_text 除外＋原文含有0件検査）。

公開物に Arena 資産を入れないため、このパック自体は**ユーザー環境でのみ生成**し、
公開 repo/exe には同梱しない。本モジュール（コンテナ実装）は Arena 原文を含まず公開可。
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import zlib

PACK_FORMAT_VERSION = "1"

# meta の予約キー（単一定義）。
META_FORMAT = "pack_format_version"
META_GENERATOR = "generator_version"
META_FINGERPRINT = "arena_fingerprint"


class PackError(Exception):
    pass


def _validate_name(name: str) -> str:
    """パック内ファイル名を検証・正規化する（相対のみ・実パス/traversal 拒否）。"""
    n = (name or "").replace("\\", "/")
    if not n:
        raise PackError("empty pack name")
    if n[0] == "/" or ":" in n:
        raise PackError(f"absolute path not allowed in pack: {name!r}")
    if any(part == ".." for part in n.split("/")):
        raise PackError(f"path traversal not allowed in pack: {name!r}")
    return n


class ArenaPack:
    """単一データパックの読み書き（SQLite+zlib）。

    使い方（書き込み）:
        with ArenaPack.create(path) as pack:
            pack.set_meta(ArenaPack-reserved keys...)
            pack.put_text("i18n/_original/foo.json", json_text)
    使い方（読み取り）:
        with ArenaPack.open(path) as pack:
            data = pack.get("i18n/_original/foo.json")
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # --- 生成/オープン ---
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

    # --- meta ---
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

    # --- files ---
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

    # --- 整合チェック ---
    def verify(self) -> list[str]:
        """全ファイルの sha/解凍を検証し、壊れているファイル名の一覧を返す（空=健全）。"""
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
        """内蔵 Arena 版指紋が expected と一致するか（起動時の版整合チェック用）。"""
        got = self.get_meta(META_FINGERPRINT)
        return got is not None and got == expected


def build_pack(path: str, files: dict[str, bytes], meta: dict[str, str]) -> None:
    """name→bytes と meta から単一データパックを構築する。

    meta は予約キー（generator_version/arena_fingerprint 等）を含む dict。
    実パスを meta に入れないこと（パックは redaction 済みのみ保持）。
    """
    with ArenaPack.create(path) as pack:
        for k, v in meta.items():
            pack.set_meta(k, v)
        for name, data in files.items():
            pack.put(name, data)


__all__ = ["ArenaPack", "PackError", "build_pack",
           "META_FORMAT", "META_GENERATOR", "META_FINGERPRINT",
           "PACK_FORMAT_VERSION"]
