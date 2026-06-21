from __future__ import annotations

import re

import i18n_helper as i18n


BUY_WEAPON_LIST_OFFSET = 0x273B74
BUY_ARMOR_LIST_OFFSET = 0x2752E4
BUY_LIST_MAXLEN = 0x4000
SELL_REPAIR_ITEM_LIST_OFFSET = 0x9A6E
SELL_REPAIR_ITEM_LIST_MAXLEN = 0x1000

_COL_RE = re.compile(r"^\t\d{3}(.*)$")

_ITEM_NAME_DICT: dict[str, str] | None = None
_MATERIALS: list[tuple[str, str]] | None = None
_SUFFIXES: list[tuple[str, str]] | None = None


def _item_name_dict() -> dict[str, str]:
    global _ITEM_NAME_DICT
    if _ITEM_NAME_DICT is None:
        out: dict[str, str] = {}
        for _id, e in i18n.originals("items").items():
            if not isinstance(e, dict):
                continue
            en = e.get("original", "")
            if not en:
                continue
            ja = i18n.text(_id)
            if ja and ja != _id:
                out[en] = ja
        for ent in i18n.v2_category_entries("items"):
            en, ja = ent.get("original"), ent.get("text")
            if en and ja:
                out.setdefault(en, ja)
        _ITEM_NAME_DICT = out
    return _ITEM_NAME_DICT


def _section_pairs(section_name: str) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for ent in i18n.v2_category_entries("items"):
        if (ent.get("context") or {}).get("section") != section_name:
            continue
        en, ja = ent.get("original"), ent.get("text")
        if en and ja:
            out.setdefault(en, ja)
    for _id, e in i18n.originals("items").items():
        parts = _id.split(".")
        if len(parts) < 2 or parts[1] != section_name or not isinstance(e, dict):
            continue
        en = e.get("original", "")
        ja = i18n.text(_id)
        if en and ja and ja != _id:
            out.setdefault(en, ja)
    return sorted(out.items(), key=lambda p: len(p[0]), reverse=True)


def _materials() -> list[tuple[str, str]]:
    global _MATERIALS
    if _MATERIALS is None:
        _MATERIALS = _section_pairs("magical_materials")
    return _MATERIALS


def _suffixes() -> list[tuple[str, str]]:
    global _SUFFIXES
    if _SUFFIXES is None:
        suffixes = _section_pairs("accessory_attributes")
        seen = {en for en, _ in suffixes}
        for ent in i18n.v2_category_entries("equipment_suffixes"):
            en, ja = ent.get("original"), ent.get("text")
            if en and ja and en not in seen:
                suffixes.append((en, ja))
                seen.add(en)
        for _id, e in i18n.originals("equipment_suffixes").items():
            en = e.get("original", "") if isinstance(e, dict) else ""
            if en and en not in seen:
                suffixes.append((en, i18n.value("equipment_suffixes", en) or ""))
                seen.add(en)
        suffixes.sort(key=lambda p: len(p[0]), reverse=True)
        _SUFFIXES = suffixes
    return _SUFFIXES


def translate_equipment_shop_name(en: str) -> str | None:
    name_dict = _item_name_dict()
    if en in name_dict:
        return name_dict[en]

    prefix_ja = ""
    base_en = en
    for mat_en, mat_ja in _materials():
        pfx = f"{mat_en} "
        if base_en.startswith(pfx):
            prefix_ja = mat_ja
            base_en = base_en[len(pfx):]
            break

    suffix_ja = ""
    for suffix_en, s_ja in _suffixes():
        if base_en.endswith(f" {suffix_en}"):
            suffix_ja = s_ja
            base_en = base_en[:-(len(suffix_en) + 1)]
            break

    base_ja = name_dict.get(base_en)
    if not base_ja:
        return None
    return f"{prefix_ja}{base_ja}{suffix_ja}"


def _decode_cols(row: bytes) -> list[str]:
    text = row.decode("ascii", errors="replace")
    cols: list[str] = []
    for raw_col in text.split("\n"):
        if not raw_col:
            continue
        m = _COL_RE.match(raw_col)
        value = m.group(1) if m else raw_col.strip()
        cols.append(value.strip())
    return cols


def parse_buy_weapon_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for row in raw.split(b"\x00"):
        if not row:
            if out:
                break
            continue
        cols = _decode_cols(row)
        if len(cols) < 4:
            continue
        en, hands, weight, cost = cols[:4]
        if not en:
            continue
        out.append({
            "en": en,
            "ja": translate_equipment_shop_name(en),
            "hands": _format_hands(hands),
            "weight": _normalize_decimal(weight),
            "price_raw": cost,
            "price_display": cost,
        })
    return out


def parse_buy_armor_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for row in raw.split(b"\x00"):
        if not row:
            if out:
                break
            continue
        cols = _decode_cols(row)
        if len(cols) < 4:
            continue
        en, protects, weight, cost = cols[:4]
        if not en:
            continue
        out.append({
            "en": en,
            "ja": translate_equipment_shop_name(en),
            "protects": protects,
            "protects_ja": i18n.value("protect_locations", protects) or protects,
            "weight": _normalize_decimal(weight),
            "price_raw": cost,
            "price_display": cost,
        })
    return out


def parse_sell_repair_item_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for seg in raw.split(b"\x00"):
        if not seg:
            if out:
                break
            continue
        if not all(0x20 <= b <= 0x7E for b in seg):
            if out:
                break
            continue
        en = seg.decode("ascii", errors="replace").strip()
        if not en:
            if out:
                break
            continue
        if len(en) < 2:
            if out:
                break
            continue
        out.append({
            "en": en,
            "ja": translate_equipment_shop_name(en),
            "price_raw": "",
            "price_display": "",
        })
    return out


def read_buy_weapon_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(
            anchor + BUY_WEAPON_LIST_OFFSET, BUY_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_buy_weapon_list(raw)


def read_buy_armor_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(
            anchor + BUY_ARMOR_LIST_OFFSET, BUY_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_buy_armor_list(raw)


def read_sell_repair_item_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(
            anchor + SELL_REPAIR_ITEM_LIST_OFFSET,
            SELL_REPAIR_ITEM_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_sell_repair_item_list(raw)


def _normalize_decimal(text: str) -> str:
    return f"0{text}" if text.startswith(".") else text


def _format_hands(text: str) -> str:
    if text == "1":
        return "片手"
    if text == "2":
        return "両手"
    return text


__all__ = [
    "BUY_WEAPON_LIST_OFFSET",
    "BUY_ARMOR_LIST_OFFSET",
    "BUY_LIST_MAXLEN",
    "SELL_REPAIR_ITEM_LIST_OFFSET",
    "SELL_REPAIR_ITEM_LIST_MAXLEN",
    "parse_buy_armor_list",
    "parse_buy_weapon_list",
    "parse_sell_repair_item_list",
    "read_buy_armor_list",
    "read_buy_weapon_list",
    "read_sell_repair_item_list",
    "translate_equipment_shop_name",
]
