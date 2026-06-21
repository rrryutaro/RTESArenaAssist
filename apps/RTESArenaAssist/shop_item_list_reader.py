from __future__ import annotations

import re
from typing import Optional

import i18n_helper as i18n
from arena_bridge import ArenaMemoryAnalyzer


SHOP_ITEM_LIST_OFFSET = 0x1040
SHOP_ITEM_LIST_MAXLEN = 1024

_NAME_MIN = 0x20
_NAME_MAX = 0x7E

_PRICE_RE = re.compile(rb"^([0-9]+)\s+gp$")

_BREAK_MAX_NONTEXT = 4


def _extract_display_price(price_digits: bytes) -> str:
    try:
        n = int(price_digits.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return price_digits.decode("ascii", errors="replace")
    return str(n % 10)


def parse_shop_item_list(raw: bytes) -> list[dict]:
    items: list[dict] = []
    n = len(raw)
    if n < 6:
        return items
    if raw[4] != 0x00 or raw[5] != 0x09:
        return items
    i = 4
    while i + 1 < n:
        if raw[i] != 0x00 or raw[i + 1] != 0x09:
            break
        i += 2
        lf_idx = raw.find(b"\x0A", i, min(n, i + 64))
        if lf_idx < 0:
            break
        price_str = raw[i:lf_idx]
        m = _PRICE_RE.match(price_str)
        if not m:
            break
        price_digits = m.group(1)
        price_display = _extract_display_price(price_digits)
        i = lf_idx + 1
        nul_idx = raw.find(b"\x00", i, min(n, i + 64))
        if nul_idx < 0:
            break
        name_bytes = raw[i:nul_idx]
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
        i = nul_idx
    return items


def read_shop_item_list(analyzer: "ArenaMemoryAnalyzer",
                         anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(
            anchor + SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_shop_item_list(raw)


def translate_shop_item_list(items: list[dict], *,
                             section: str = "drinks") -> list[dict]:
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
