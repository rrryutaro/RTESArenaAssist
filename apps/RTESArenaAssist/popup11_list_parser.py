"""POPUP11.IMG リストパーサ。

場所一覧 / 詳細場所一覧 ともに同じアクセスパターンを使う:
  - anchor + 0x5127 (u16 LE) が、現在表示中リスト項目テキスト群の起点
    (anchor 相対オフセット) を保持
  - その起点から NUL 区切り ASCII 文字列が item_count 件続く

場所一覧: ptr → anchor + 0x85D3（静的テンプレ Inn\0 Temple\0 ...）
詳細場所一覧: ptr → message_buf 内の動的固有名群
"""

from __future__ import annotations

import logging
import struct

_log = logging.getLogger(__name__)

POPUP11_LIST_PTR_OFFSET = 0x5127


def _read_list_ptr(analyzer, anchor: int) -> int:
    raw = analyzer.read_bytes(anchor + POPUP11_LIST_PTR_OFFSET, 2)
    return struct.unpack("<H", raw)[0]


def _read_nul_strings(analyzer, addr: int, count: int) -> list[str]:
    if count <= 0:
        return []
    buf = analyzer.read_bytes(addr, count * 64 + 16)
    items: list[str] = []
    pos = 0
    while pos < len(buf) and len(items) < count:
        nul = buf.find(b"\x00", pos)
        if nul == -1:
            break
        chunk = buf[pos:nul]
        text = chunk.decode("ascii", errors="replace").strip()
        if not text:
            break
        items.append(text)
        pos = nul + 1
    return items


def parse_popup11_list(analyzer, anchor: int, item_count: int) -> list[str]:
    """POPUP11.IMG 場所一覧 / 詳細場所一覧 共通パーサ。

    anchor + 0x5127 が指す先から item_count 件の NUL 区切り文字列を取得する。
    取得失敗時は空リスト。
    """
    try:
        ptr = _read_list_ptr(analyzer, anchor)
        if ptr == 0:
            return []
        return _read_nul_strings(analyzer, anchor + ptr, item_count)
    except (OSError, struct.error):
        _log.exception("parse_popup11_list failed")
        return []


def parse_where_is_list(analyzer, anchor: int, item_count: int) -> list[str]:
    """場所一覧（Where is... クリック直後の固定 9 項目程度の画面）を抽出する。"""
    return parse_popup11_list(analyzer, anchor, item_count)


def parse_dynamic_place_list(analyzer, anchor: int, item_count: int) -> list[str]:
    """詳細場所一覧（場所一覧から Inn 等を選んだ後の動的固有名一覧）を抽出する。"""
    return parse_popup11_list(analyzer, anchor, item_count)
