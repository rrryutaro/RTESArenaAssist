from __future__ import annotations
import re
import i18n_helper as i18n
from item_name_lookup import translate_item_name_opt
BUY_WEAPON_LIST_OFFSET = 2571124
BUY_ARMOR_LIST_OFFSET = 2577124
BUY_LIST_MAXLEN = 16384
SELL_REPAIR_ITEM_LIST_OFFSET = 39534
SELL_REPAIR_ITEM_LIST_MAXLEN = 4096
_COL_RE = re.compile('^\\t\\d{3}(.*)$')

def translate_equipment_shop_name(en: str) -> str | None:
    return translate_item_name_opt(en)

def _decode_cols(row: bytes) -> list[str]:
    text = row.decode('ascii', errors='replace')
    cols: list[str] = []
    for raw_col in text.split('\n'):
        if not raw_col:
            continue
        m = _COL_RE.match(raw_col)
        value = m.group(1) if m else raw_col.strip()
        cols.append(value.strip())
    return cols

def parse_buy_weapon_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for row in raw.split(b'\x00'):
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
        out.append({'en': en, 'ja': translate_equipment_shop_name(en), 'hands': _format_hands(hands), 'weight': _normalize_decimal(weight), 'price_raw': cost, 'price_display': cost})
    return out

def parse_buy_armor_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for row in raw.split(b'\x00'):
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
        out.append({'en': en, 'ja': translate_equipment_shop_name(en), 'protects': protects, 'protects_ja': i18n.value('protect_locations', protects) or protects, 'weight': _normalize_decimal(weight), 'price_raw': cost, 'price_display': cost})
    return out

def parse_sell_repair_item_list(raw: bytes) -> list[dict]:
    out: list[dict] = []
    for seg in raw.split(b'\x00'):
        if not seg:
            if out:
                break
            continue
        if not all((32 <= b <= 126 for b in seg)):
            if out:
                break
            continue
        en = seg.decode('ascii', errors='replace').strip()
        if not en:
            if out:
                break
            continue
        if len(en) < 2:
            if out:
                break
            continue
        if not any((c.isalnum() for c in en)):
            break
        out.append({'en': en, 'ja': translate_equipment_shop_name(en), 'price_raw': '', 'price_display': ''})
    return out

def read_buy_weapon_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(anchor + BUY_WEAPON_LIST_OFFSET, BUY_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_buy_weapon_list(raw)

def read_buy_armor_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(anchor + BUY_ARMOR_LIST_OFFSET, BUY_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_buy_armor_list(raw)

def read_sell_repair_item_list(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(anchor + SELL_REPAIR_ITEM_LIST_OFFSET, SELL_REPAIR_ITEM_LIST_MAXLEN)
    except (OSError, AttributeError):
        return []
    items = parse_sell_repair_item_list(raw)
    if items:
        try:
            from inventory_reader import read_equipment_items
            bound = len(read_equipment_items(analyzer, anchor))
            if bound > 0 and len(items) > bound:
                items = items[:bound]
        except Exception:
            pass
    return items

def _normalize_decimal(text: str) -> str:
    return f'0{text}' if text.startswith('.') else text

def _format_hands(text: str) -> str:
    if text == '1':
        return i18n.text('item.slot.one_handed')
    if text == '2':
        return i18n.text('item.slot.two_handed')
    return text
__all__ = ['BUY_WEAPON_LIST_OFFSET', 'BUY_ARMOR_LIST_OFFSET', 'BUY_LIST_MAXLEN', 'SELL_REPAIR_ITEM_LIST_OFFSET', 'SELL_REPAIR_ITEM_LIST_MAXLEN', 'parse_buy_armor_list', 'parse_buy_weapon_list', 'parse_sell_repair_item_list', 'read_buy_armor_list', 'read_buy_weapon_list', 'read_sell_repair_item_list', 'translate_equipment_shop_name']
