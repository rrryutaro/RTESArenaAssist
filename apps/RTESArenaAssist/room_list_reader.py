"""room_list_reader.py — タバーン部屋一覧 (Get a Room) 読取 + 翻訳。

memory layout (観測):
  anchor + 0x2890: u16 LE header (= 0x07D0 = 2000、drinks 価格 base 値と同じ)
  anchor + 0x2892: 5 部屋名が NUL 区切りで連続。
                   "Single\\0Double\\0Suite\\0King's Suite\\0Emperor's Suite\\0"
                   (合計 49 byte = 6+1+6+1+5+1+12+1+15+1)
  anchor + 0x28C3: 5 部屋価格 u16 LE 連続。
                   10 (Single) / 20 (Double) / 35 (Suite) /
                   50 (King's Suite) / 75 (Emperor's Suite)

これは **Arena の静的アセット** であり、タバーンによらず同じ値が並ぶ。
画面表示時に Arena は配列の先頭から順番にレンダリングするだけで、
タバーン毎の availability mask は本観測では確認できていない (= 全部屋を
表示するのが現状の実装方針)。

API:
  read_room_list(analyzer, anchor) -> list[dict]
  translate_room_list(items) -> list[dict]
"""
from __future__ import annotations

import i18n_helper as i18n

from arena_bridge import ArenaMemoryAnalyzer


# 静的部屋名 / 価格テーブル offset
ROOM_NAMES_OFFSET = 0x2892
ROOM_PRICES_OFFSET = 0x28C3
ROOM_COUNT = 5  # 全 5 部屋: Single/Double/Suite/King's Suite/Emperor's Suite

# 観測上の期待値 (sanity check 用)
_EXPECTED_NAMES = (
    "Single", "Double", "Suite", "King's Suite", "Emperor's Suite",
)

_NAME_MIN = 0x20
_NAME_MAX = 0x7E


def parse_room_names(raw_names: bytes) -> list[str]:
    """raw bytes から NUL 区切り部屋名を ROOM_COUNT 件抽出する。"""
    names: list[str] = []
    pos = 0
    n = len(raw_names)
    while len(names) < ROOM_COUNT and pos < n:
        end = raw_names.find(b"\x00", pos)
        if end < 0:
            break
        chunk = raw_names[pos:end]
        if not chunk:
            break
        # printable ASCII の検証
        if not all(_NAME_MIN <= b <= _NAME_MAX for b in chunk):
            break
        names.append(chunk.decode("ascii", errors="replace"))
        pos = end + 1
    return names


def parse_room_prices(raw_prices: bytes) -> list[int]:
    """raw bytes から u16 LE 価格を ROOM_COUNT 件抽出する。"""
    prices: list[int] = []
    for i in range(ROOM_COUNT):
        off = i * 2
        if off + 2 > len(raw_prices):
            break
        prices.append(raw_prices[off] | (raw_prices[off + 1] << 8))
    return prices


def read_room_list(analyzer: "ArenaMemoryAnalyzer",
                    anchor: int) -> list[dict]:
    """anchor + 0x2892 から 5 部屋名 + 価格を読み出す。

    観測した期待値と異なる場合 (= タバーン内ではない / 静的領域が
    変わった等) は空リストを返す。
    """
    try:
        raw_names = analyzer.read_bytes(anchor + ROOM_NAMES_OFFSET, 64)
        raw_prices = analyzer.read_bytes(anchor + ROOM_PRICES_OFFSET,
                                          ROOM_COUNT * 2)
    except (OSError, AttributeError):
        return []
    names = parse_room_names(raw_names)
    if len(names) != ROOM_COUNT:
        return []
    # sanity check: 期待値と一致するか (= 静的領域の妥当性確認)
    if tuple(names) != _EXPECTED_NAMES:
        return []
    prices = parse_room_prices(raw_prices)
    if len(prices) != ROOM_COUNT:
        return []
    items: list[dict] = []
    for name, price in zip(names, prices):
        items.append({
            "en": name,
            "price_raw": str(price),
            "price_display": str(price),
        })
    return items


def translate_room_list(items: list[dict], *,
                        section: str = "rooms") -> list[dict]:
    """items の各 en を翻訳切替コア (items カテゴリ) 経由で現在言語訳に変換。

    `section`（呼出元＝宿屋が知る公開安全 context・既定 rooms）を渡し、v2 有効時は
    section-scoped 解決を行う。v1 では従来通り。
    """
    out: list[dict] = []
    for it in items:
        en = it.get("en", "")
        ja = i18n.value_section("items", en, section) if en else None
        out.append({
            "en": en,
            "ja": ja,
            "price_raw": it.get("price_raw", ""),
            "price_display": it.get("price_display", ""),
        })
    return out


__all__ = [
    "ROOM_NAMES_OFFSET",
    "ROOM_PRICES_OFFSET",
    "ROOM_COUNT",
    "parse_room_names",
    "parse_room_prices",
    "read_room_list",
    "translate_room_list",
]
