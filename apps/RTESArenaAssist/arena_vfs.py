r"""arena_vfs.py — Arena 資産の VFS（GLOBAL.BSA リーダ＋loose 優先解決）。

公開版はユーザーの Arena ディレクトリ（`A.EXE`/`GLOBAL.BSA` の
ある所）を指定させ、その場で復号/抽出/生成する。本モジュールはその土台＝
`GLOBAL.BSA`（非圧縮 BSA）を読むリーダと、loose file 優先→BSA fallback の VFS。

BSA フォーマット（OpenTESArena `components/archives/bsaarchive.cpp` 忠実）:
  - 先頭 uint16 LE = ファイル数 count。
  - 続いてファイルデータが連結（base = 2 から）。
  - 末尾 count×18 バイトがフッタ。各レコード 18 バイト:
      name[12]（NUL 終端・`\` → `/`）+ compressed(uint16 LE) + size(uint32 LE)。
    データ範囲は フッタ順に start=前の end（先頭は base=2）で累積。
  - 圧縮エントリ（compressed != 0）は非対応（OTA も非対応・Arena GLOBAL.BSA は非圧縮）。

本モジュール自体に Arena 原文/資産は含まれない（リーダのみ）。公開物に同梱してよい。
"""
from __future__ import annotations

import os
import struct

_FILENAME_LEN = 12          # DOSUtils::FilenameBufferSize(13) - 1
_RECORD_SIZE = 18           # name(12) + compressed(2) + size(4)
_BASE_OFFSET = 2            # 先頭 uint16 count の直後


class BsaError(Exception):
    pass


class BsaArchive:
    """非圧縮 GLOBAL.BSA のディレクトリを読み、名前→バイト列で取り出す。

    ファイル全体はメモリに載せず、フッタ（ディレクトリ）だけ読んでオフセットを保持し、
    read() の都度 必要範囲のみ seek して読む。Arena は DOS=大文字小文字無視のため
    名前は大文字正規化して索引する。
    """

    def __init__(self, path: str):
        self.path = path
        # upper_name -> (start, size)。元名も保持（列挙用）。
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
        """格納ファイル名の一覧（元の大小文字・フッタ順）。"""
        return list(self._names)

    def exists(self, name: str) -> bool:
        return name.upper() in self._entries

    def read(self, name: str) -> bytes | None:
        """名前のファイル内容を返す（大小文字無視）。無ければ None。"""
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
    """テスト用: name→bytes から非圧縮 BSA バイト列を構築する（リーダと対）。

    本番では使わない（公開物に Arena 資産を作らない）。合成 BSA で読取を検証する用途。
    """
    names = list(files.keys())
    count = len(names)
    body = b"".join(files[n] for n in names)
    footer = bytearray()
    for n in names:
        nb = n.encode("latin-1")[:_FILENAME_LEN]
        nb = nb + b"\x00" * (_FILENAME_LEN - len(nb))
        footer += nb + struct.pack("<HI", 0, len(files[n]))
    return struct.pack("<H", count) + body + bytes(footer)


# INF ファイル復号（OpenTESArena `INFFile.cpp` 忠実）。
# GLOBAL.BSA 内の INF は XOR 暗号化されている。loose（個別ファイル）の INF は平文。
# byte ^= (count + key[keyIndex])。key は 8 バイト周期、count は 256 バイト周期で増加。
_INF_ENCRYPTION_KEYS = (0xEA, 0x7B, 0x4E, 0xBD, 0x19, 0xC9, 0x38, 0x99)


def decrypt_inf(data: bytes) -> bytes:
    """GLOBAL.BSA 由来 INF の復号（OTA INFFile.cpp 準拠の鍵は固定データ・推測でない）。

    loose（個別ファイル）の INF は暗号化されていないため復号してはならない。
    呼び出し側は BSA 由来のときだけ本関数を通す（`Vfs.read_inf` が provenance を判定）。
    """
    out = bytearray(data)
    key_index = 0
    count = 0
    for i in range(len(out)):
        out[i] ^= (count + _INF_ENCRYPTION_KEYS[key_index]) & 0xFF
        key_index = (key_index + 1) & 7
        count = (count + 1) & 0xFF
    return bytes(out)


class Vfs:
    """Arena ディレクトリの VFS。loose file 優先 → GLOBAL.BSA fallback（OTA 同方針）。

    DOS の大小文字無視・`8.3` を吸収。読み取りは bytes を返す（復号/正規化は上位層）。
    Arena ディレクトリの妥当性は `A.EXE`/`GLOBAL.BSA` 等の存在で上位が検証する前提。
    """

    def __init__(self, arena_dir: str, bsa_name: str = "GLOBAL.BSA"):
        self.arena_dir = arena_dir
        self._bsa_name = bsa_name
        self._bsa: BsaArchive | None = None
        self._bsa_failed = False          # BSA が壊れていれば loose のみで動く
        self._loose_index: dict[str, str] | None = None  # upper -> 実パス

    # --- loose file（大小文字無視索引） ---
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
                # 壊れた/未対応の BSA は loose のみで動作継続（起動を妨げない）。
                self._bsa_failed = True
                return None
        return self._bsa

    def read(self, name: str) -> bytes | None:
        """loose 優先→BSA で name を読む。無ければ None。"""
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
        """INF を平文バイト列で読む。

        loose（個別ファイル）はそのまま、GLOBAL.BSA 由来は復号して返す（OTA
        `INFFile.cpp` の `isEncrypted = inGlobalBSA` と同じ provenance 規則）。無ければ None。
        """
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
        """loose と BSA を合わせた利用可能ファイル名一覧（大文字・重複除去・昇順）。

        複数ファイルを列挙して読む生成器（INF @TEXT 群など）が使う。loose と BSA で
        同名があっても 1 回だけ返す（read は loose 優先）。GLOBAL.BSA 自体は除外。
        """
        names: set[str] = set()
        for upper in self._loose():
            if upper != self._bsa_name.upper():
                names.add(upper)
        bsa = self._bsa_archive()
        if bsa is not None:
            names.update(n.upper() for n in bsa.names())
        return sorted(names)


__all__ = ["BsaArchive", "Vfs", "BsaError", "pack_bsa", "decrypt_inf"]
