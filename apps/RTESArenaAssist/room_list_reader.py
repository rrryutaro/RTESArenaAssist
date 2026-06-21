from __future__ import annotations

import i18n_helper as i18n

from arena_bridge import ArenaMemoryAnalyzer


ROOM_NAMES_OFFSET = 0x2892
ROOM_PRICES_OFFSET = 0x28C3
ROOM_COUNT = 5

_EXPECTED_NAMES = (
    "Single", "Double", "Suite", "King's Suite", "Emperor's Suite",
)

_NAME_MIN = 0x20
_NAME_MAX = 0x7E


def parse_room_names(raw_names: bytes) -> list[str]:
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
        if not all(_NAME_MIN <= b <= _NAME_MAX for b in chunk):
            break
        names.append(chunk.decode("ascii", errors="replace"))
        pos = end + 1
    return names


def parse_room_prices(raw_prices: bytes) -> list[int]:
    prices: list[int] = []
    for i in range(ROOM_COUNT):
        off = i * 2
        if off + 2 > len(raw_prices):
            break
        prices.append(raw_prices[off] | (raw_prices[off + 1] << 8))
    return prices


def read_room_list(analyzer: "ArenaMemoryAnalyzer",
                    anchor: int) -> list[dict]:
    try:
        raw_names = analyzer.read_bytes(anchor + ROOM_NAMES_OFFSET, 64)
        raw_prices = analyzer.read_bytes(anchor + ROOM_PRICES_OFFSET,
                                          ROOM_COUNT * 2)
    except (OSError, AttributeError):
        return []
    names = parse_room_names(raw_names)
    if len(names) != ROOM_COUNT:
        return []
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
