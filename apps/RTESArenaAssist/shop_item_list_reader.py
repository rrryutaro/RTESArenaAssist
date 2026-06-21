"""shop_item_list_reader.py — 店主メニュー「Buy Drinks」選択後等の
アイテム一覧 (酒一覧 / 部屋一覧 / 武具一覧 等) の読取・翻訳。

memory layout (観測):
  anchor + 0x104E 付近に 4 byte の header (例: 06 0c af 68) があり、
  続いてエントリが連続:

    \\0 \\t <price_str> \\n <name> \\0 \\t <price_str> \\n <name> ...

  - `\\0 \\t` (= 00 09) がエントリ区切り (前エントリ name 終端 NUL を兼ねる)
  - `<price_str>` は ASCII (例: "2003 gp")
  - `<name>` は ASCII printable

  価格表示エンコード (観測):
    memory "2003 gp" が画面では "3 gp" と表示 — 6 件すべて
    ASCII 数値 % 10 (= 末尾 1 桁) が画面表示と一致。
    先頭 3 桁 "200" は drink type / 種別バンドリングと推定 (詳細未解明)。
    現状の実装は最終 1 桁を表示価格として扱う。

API:
  read_shop_item_list(analyzer, anchor)
    -> list[dict]: [{"en": str, "price_raw": str, "price_display": str}, ...]
  translate_shop_item_list(items)
    -> list[dict]: [{"en": str, "ja": str | None, "price_raw": str,
                     "price_display": str}, ...]
"""
from __future__ import annotations

import re
from typing import Optional

import i18n_helper as i18n
from arena_bridge import ArenaMemoryAnalyzer


# Memory Analyzer 観測で anchor 相対固定。
# 構造: +0x1040 から 4 byte header (例: 06 0c af 68)、+0x1044 から最初の
# `\0\t` 区切り、+0x104E から最初の name ("Orcgut" 等) が始まる。
# offset は header 先頭 (+0x1040) に合わせ、最初の entry を取りこぼさない。
# 別店舗 (寺院 / 武具店 / 魔ギルド / 宮殿) でも同一 offset の想定だが要追加観測。
SHOP_ITEM_LIST_OFFSET = 0x1040
SHOP_ITEM_LIST_MAXLEN = 1024  # 12 entries 程度を余裕を持って読む

# アイテム名として許容する printable ASCII の範囲
_NAME_MIN = 0x20
_NAME_MAX = 0x7E

# 価格文字列マッチ (digits + " gp")
_PRICE_RE = re.compile(rb"^([0-9]+)\s+gp$")

# パース打ち切り判定: 連続する非テキスト byte 数
_BREAK_MAX_NONTEXT = 4


def _extract_display_price(price_digits: bytes) -> str:
    """ASCII 数値の末尾 1 桁を表示価格として返す。

    観測: memory "2003" → 画面 "3"、"2002" → "2" 等。
    """
    try:
        n = int(price_digits.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return price_digits.decode("ascii", errors="replace")
    return str(n % 10)


def parse_shop_item_list(raw: bytes) -> list[dict]:
    """raw から店アイテム一覧を抽出する。

    エントリ構造: `\\0 \\t <price_str> \\n <name>` 繰り返し。
    `<price_str>` が「digits gp」形式にマッチしない、または `<name>` が
    空 / 非 printable のときに打ち切る。

    `\\0\\t` は **4 byte header の直後 (offset 4)** になければ drinks data
    として認めない。stale / mixed buffer (Rooms popup 時の "Gold left :  XXX"
    等) を drinks と誤判定しないため。
    """
    items: list[dict] = []
    n = len(raw)
    if n < 6:
        return items
    # strict header check: bytes 4-5 が `\0\t` でなければ drinks 一覧ではない
    if raw[4] != 0x00 or raw[5] != 0x09:
        return items
    i = 4
    while i + 1 < n:
        # 区切り `\0 \t` を期待
        if raw[i] != 0x00 or raw[i + 1] != 0x09:
            break
        i += 2  # `\0 \t` を skip
        # `\n` までを price_str として読む
        lf_idx = raw.find(b"\x0A", i, min(n, i + 64))
        if lf_idx < 0:
            break
        price_str = raw[i:lf_idx]
        m = _PRICE_RE.match(price_str)
        if not m:
            break
        price_digits = m.group(1)
        price_display = _extract_display_price(price_digits)
        i = lf_idx + 1  # `\n` を skip
        # 次の `\0` までを name として読む
        nul_idx = raw.find(b"\x00", i, min(n, i + 64))
        if nul_idx < 0:
            break
        name_bytes = raw[i:nul_idx]
        # name は printable ASCII (空白を含む) のみ許容
        if not name_bytes or not all(
                _NAME_MIN <= b <= _NAME_MAX for b in name_bytes):
            break
        name = name_bytes.decode("ascii", errors="replace").strip()
        if not name:
            break
        items.append({
            "en": name,
            "price_raw": price_digits.decode("ascii"),
            "price_display": price_display,
        })
        i = nul_idx  # 次の `\0` 位置に進む (= 次エントリの `\0\t` 先頭)
    return items


def read_shop_item_list(analyzer: "ArenaMemoryAnalyzer",
                         anchor: int) -> list[dict]:
    """店アイテム一覧を anchor + 0x104E から読み出す。空ならゲーム側未表示。"""
    try:
        raw = analyzer.read_bytes(
            anchor + SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_shop_item_list(raw)


def translate_shop_item_list(items: list[dict], *,
                             section: str = "drinks") -> list[dict]:
    """items の各 en を i18n コア経由で翻訳。

    `section`（呼出元＝酒場が知る公開安全 context・既定 drinks）を渡し、v2 有効時は
    section-scoped 解決（conflict bare 誤訳を fail-closed）。v1 では従来通り。
    """
    out: list[dict] = []
    for it in items:
        en = it.get("en", "")
        ja = i18n.value_section("items", en, section)
        out.append({
            "en": en,
            "ja": ja,
            "price_raw": it.get("price_raw", ""),
            "price_display": it.get("price_display", ""),
        })
    return out


__all__ = [
    "SHOP_ITEM_LIST_OFFSET",
    "SHOP_ITEM_LIST_MAXLEN",
    "parse_shop_item_list",
    "read_shop_item_list",
    "translate_shop_item_list",
]
