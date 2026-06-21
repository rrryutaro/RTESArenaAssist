"""wild_block_lists.py — wilderness chunk ID lists (normal/village/dungeon/tavern/temple)。

Arena 本体 EXE (= A.EXE / ACD.EXE) の固定データ領域に
[size_byte, id_byte × size_byte] の 5 ブロックリストが連続配置されている
(= OpenTESArena `ExeData.cpp::ExeDataWilderness::init`)。

OpenTESArena 既知オフセット:
  - A.EXE   floppy:  Normal=0x3F02C, Village=0x3F045, Dungeon=0x3F052,
                     Tavern=0x3F05F, Temple=0x3F06A
  - ACD.EXE CD:      Normal=0x3F314, Village=0x3F32D, Dungeon=0x3F33A,
                     Tavern=0x3F347, Temple=0x3F352
  - 隣接オフセット差から判明する list size: Normal=24, Village=12,
    Dungeon=12, Tavern=10, Temple=?

ただし A.EXE / ACD.EXE はいずれも EXE-packed (= 圧縮) なので、
ファイル直読みでは取得できない。本モジュールは下記 2 経路で取得する:

  1. DOSBox ライブメモリ署名サーチ (= 起動中の Arena プロセスから
     decompressed 状態の EXE データを直接探す)
  2. 1 が失敗した場合は内蔵 fallback 値を返す
     (= 仕様調査用、再現性は memory 取得に劣る)

複数 poll で繰り返し失敗しないよう、成功した結果はモジュール global
変数にキャッシュする。

**仮説扱い (= 観測 0 回ベース)**: 内蔵 fallback 値は OpenTESArena 既知
オフセットとサイズ規則から「妥当な構造」として置いた仮値であり、実機との
照合 (= memory 経由取得との一致) ができていない。最初の wilderness 描画
動作確認時に必ず memory 取得側を試行して fallback との差異を観測する。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional


_log = logging.getLogger("wild_block_lists")


@dataclass(frozen=True)
class WildBlockLists:
    """5 種の wilderness chunk ID リスト。各要素は ≥1。"""
    normal: tuple[int, ...]
    village: tuple[int, ...]
    dungeon: tuple[int, ...]
    tavern: tuple[int, ...]
    temple: tuple[int, ...]


# 仮置き fallback (= 観測前)。
# 既知のリストサイズ (= Normal=24, Village=12, Dungeon=12, Tavern=10)
# は OpenTESArena offsets の隣接差から確定。Temple サイズは未確定 (= 10
# と仮定)。ID 値そのものは Arena 本体 EXE の固定データなので、wilderness
# 描画が動かない場合は memory 取得経由で上書きする必要あり。
# WILD005-070 の範囲 (5-70) 内で「それっぽい」値を仮置きするが、
# **これは実機未検証の仮説**。
_FALLBACK_LISTS = WildBlockLists(
    normal=tuple(),   # 仮: 空 (= 描画されず気付く)
    village=tuple(),
    dungeon=tuple(),
    tavern=tuple(),
    temple=tuple(),
)


# モジュール global キャッシュ
_CACHED: Optional[WildBlockLists] = None
_CACHE_SOURCE: Optional[str] = None  # "memory" / "fallback"


def _is_plausible_list(data: bytes, offset: int,
                       expected_size: int) -> bool:
    """data[offset] = size, data[offset+1..offset+1+size] = IDs の構造妥当性チェック。

    - size == expected_size
    - 全 ID が [1, 70] 範囲内
    - 全 ID が互いに異なる (= リスト内重複は通常無い前提、仮)
    """
    if offset + 1 + expected_size > len(data):
        return False
    if data[offset] != expected_size:
        return False
    ids = data[offset + 1:offset + 1 + expected_size]
    if not all(1 <= b <= 70 for b in ids):
        return False
    # 重複は許す (= OpenTESArena 観測で実際にあるかも、強い条件にしない)
    return True


def search_block_lists_in_buffer(buf: bytes) -> Optional[WildBlockLists]:
    """連続メモリバッファ内で 5 連続 block list 構造を探す。

    検出条件 (= 隣接 offsets 規則から):
      offset+0       == 24  (Normal size)
      offset+1..25   ∈ [1,70]
      offset+25      == 12  (Village size)
      offset+26..38  ∈ [1,70]
      offset+38      == 12  (Dungeon size)
      offset+39..51  ∈ [1,70]
      offset+51      == 10  (Tavern size)
      offset+52..62  ∈ [1,70]
      offset+62      ∈ [1,30]   (Temple size 仮 = 1〜30 の範囲)
      offset+63..63+t ∈ [1,70]

    最初に一致する offset を返す。複数候補がある場合は最初のみ採用。
    """
    NORMAL_SIZE = 24
    VILLAGE_SIZE = 12
    DUNGEON_SIZE = 12
    TAVERN_SIZE = 10
    # Temple サイズの妥当範囲 (仮)
    TEMPLE_MIN = 1
    TEMPLE_MAX = 30

    n = len(buf)
    if n < 64:
        return None

    # Normal=24 から始まる位置を線形探索
    end = n - (1 + NORMAL_SIZE + 1 + VILLAGE_SIZE + 1 + DUNGEON_SIZE
               + 1 + TAVERN_SIZE + 1 + TEMPLE_MIN)
    for off in range(end):
        if buf[off] != NORMAL_SIZE:
            continue
        # Normal
        if not _is_plausible_list(buf, off, NORMAL_SIZE):
            continue
        p = off + 1 + NORMAL_SIZE
        # Village
        if not _is_plausible_list(buf, p, VILLAGE_SIZE):
            continue
        p += 1 + VILLAGE_SIZE
        # Dungeon
        if not _is_plausible_list(buf, p, DUNGEON_SIZE):
            continue
        p += 1 + DUNGEON_SIZE
        # Tavern
        if not _is_plausible_list(buf, p, TAVERN_SIZE):
            continue
        p += 1 + TAVERN_SIZE
        # Temple (= サイズ未確定、妥当範囲で探索)
        if p >= n:
            continue
        temple_size = buf[p]
        if not (TEMPLE_MIN <= temple_size <= TEMPLE_MAX):
            continue
        if not _is_plausible_list(buf, p, temple_size):
            continue

        # 5 連続成功 → 確定
        normal = tuple(buf[off + 1:off + 1 + NORMAL_SIZE])
        vp = off + 1 + NORMAL_SIZE
        village = tuple(buf[vp + 1:vp + 1 + VILLAGE_SIZE])
        dp = vp + 1 + VILLAGE_SIZE
        dungeon = tuple(buf[dp + 1:dp + 1 + DUNGEON_SIZE])
        tp = dp + 1 + DUNGEON_SIZE
        tavern = tuple(buf[tp + 1:tp + 1 + TAVERN_SIZE])
        temple = tuple(buf[p + 1:p + 1 + temple_size])
        _log.info(
            "wild_block_lists: signature match at +0x%X "
            "(normal=%s village=%s dungeon=%s tavern=%s temple=%s)",
            off, list(normal), list(village), list(dungeon),
            list(tavern), list(temple))
        return WildBlockLists(
            normal=normal, village=village, dungeon=dungeon,
            tavern=tavern, temple=temple)
    return None


def load_block_lists_from_memory(
        analyzer,
        scan_start: int = 0x00000000,
        scan_end: int = 0x7FFFFFFF) -> Optional[WildBlockLists]:
    """DOSBox メモリから wild block lists を 1 度読み出す。

    `analyzer._enum_readable_regions(start, end)` で読み取り可能リージョン
    を列挙し、各リージョン内で署名 match を探す。成功すれば WildBlockLists
    を返す。失敗時 None。

    analyzer: RTESArenaProbe.core.memory_core.ArenaMemoryAnalyzer 互換。
    """
    if analyzer is None:
        return None
    enum_func = getattr(analyzer, "_enum_readable_regions", None)
    if enum_func is None:
        _log.warning("analyzer has no _enum_readable_regions; skip search")
        return None

    try:
        regions = enum_func(scan_start, scan_end)
    except Exception:  # noqa: BLE001
        _log.exception("_enum_readable_regions failed")
        return None

    for base, size in regions:
        if size <= 0 or size > 0x10000000:
            # 巨大領域はスキップ (= heap / stack 等で wild block list は
            # data segment にあるため数 MB 以下のはず、安全側で 256MB 上限)
            continue
        try:
            data = analyzer.read_bytes(base, size)
        except OSError:
            continue
        result = search_block_lists_in_buffer(data)
        if result is not None:
            _log.info(
                "wild_block_lists: signature match in region "
                "base=0x%08X size=0x%X", base, size)
            return result
    _log.info("wild_block_lists: no signature match in any region")
    return None


def get_block_lists(analyzer=None) -> WildBlockLists:
    """wild block lists を取得 (= キャッシュ済みなら即返却)。

    初回呼び出し時:
      1. analyzer 経由でメモリサーチ
      2. 失敗時 fallback (= 内蔵仮値、現状空)
    """
    global _CACHED, _CACHE_SOURCE
    if _CACHED is not None:
        return _CACHED

    if analyzer is not None:
        try:
            result = load_block_lists_from_memory(analyzer)
        except Exception:  # noqa: BLE001
            _log.exception("load_block_lists_from_memory failed")
            result = None
        if result is not None:
            _CACHED = result
            _CACHE_SOURCE = "memory"
            return result

    _CACHED = _FALLBACK_LISTS
    _CACHE_SOURCE = "fallback"
    _log.warning(
        "wild_block_lists: using empty fallback (= memory search failed). "
        "wilderness map outside city center will be mostly empty until "
        "block lists are obtained.")
    return _CACHED


def get_cache_source() -> Optional[str]:
    """キャッシュ確定後の source ("memory" / "fallback") を返す。未確定なら None。"""
    return _CACHE_SOURCE


def invalidate_cache() -> None:
    """キャッシュをクリア (= analyzer 再接続後の再取得用)。"""
    global _CACHED, _CACHE_SOURCE
    _CACHED = None
    _CACHE_SOURCE = None


__all__ = [
    "WildBlockLists",
    "search_block_lists_in_buffer",
    "load_block_lists_from_memory",
    "get_block_lists",
    "get_cache_source",
    "invalidate_cache",
]
