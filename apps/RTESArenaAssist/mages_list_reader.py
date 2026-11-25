from __future__ import annotations
import logging
import re
import i18n_helper as i18n
_log = logging.getLogger('RTESArenaAssist')
POTION_LIST_OFFSET = 38532
SPELL_LIST_OFFSET = 39408
INVENTORY_LIST_OFFSET = 39534
SPELLMAKER_TARGET_OFFSET = 22161
SPELLMAKER_EFFECT_OFFSET = 38534
SPELLMAKER_SUBLIST_OFFSET = 21857
EFFECT_PICK_OFFSET = 4164
ACTIVE_LIST_PTR_OFFSET = 20520
_READ_LEN = 1024
_MAX_ITEMS = 64
LIST_KIND_POTION = 'potion'
LIST_KIND_SPELL = 'spell'
_MAGIC_NAME_SIG = b'\t031'
_MAGIC_SCAN_RANGES = ((2097152, 3145728), (0, 8388608))
_MAGIC_RE = re.compile('\\d{3}([^\\n]+)\\n\\D*?(\\d+)\\s*gp', re.DOTALL)
_magic_offset_cache: int | None = None
_PRICE_RE = re.compile('(\\d+)\\s*gp\\s*\\n?(.*)', re.DOTALL)
_KEEP_RE = re.compile('[^\\x20-\\x7E]')

def _read_raw(analyzer, anchor: int, offset: int, length: int=_READ_LEN) -> bytes:
    try:
        return analyzer.read_bytes(anchor + offset, length)
    except (OSError, AttributeError):
        return b''

def _clean(text: str) -> str:
    return _KEEP_RE.sub('', text).strip()

def _is_name(s: str) -> bool:
    if not s or len(s) < 2:
        return False
    return any((c.isalpha() for c in s))

def _strip_coord(price_digits: str) -> str:
    return price_digits[3:] if len(price_digits) > 3 else price_digits

def _segments(raw: bytes) -> list[str]:
    out: list[str] = []
    for seg in raw.split(b'\x00'):
        out.append(seg.decode('ascii', errors='replace'))
    return out

def read_priced_list(analyzer, anchor: int, offset: int, *, potion_names=None) -> list[dict]:
    if potion_names is None:
        from inventory_reader import read_potion_names
        potion_names = read_potion_names(analyzer, anchor)
    potion_set = {n for n in potion_names if n}
    if not potion_set:
        return []
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    list_kind = ''
    blanks = 0
    for seg in _segments(raw):
        m = _PRICE_RE.search(seg)
        if not m:
            if items:
                blanks += 1
                if blanks >= 3:
                    break
            continue
        blanks = 0
        name = _clean(m.group(2))
        if not _is_name(name):
            if items:
                break
            continue
        kind = LIST_KIND_POTION if name in potion_set else LIST_KIND_SPELL
        if not items:
            list_kind = kind
        elif kind != list_kind:
            break
        price = _strip_coord(m.group(1))
        items.append({'en': name, 'ja': translate_name(name), 'price_display': f'{price} gp', 'kind': kind})
        if len(items) >= _MAX_ITEMS:
            break
    return items

def read_active_list_offset(analyzer, anchor: int) -> int | None:
    try:
        off = analyzer.read_u16(anchor + ACTIVE_LIST_PTR_OFFSET)
    except (OSError, AttributeError):
        return None
    if isinstance(off, int) and 4096 <= off <= 65024:
        return off
    return None

def read_active_priced_list(analyzer, anchor: int) -> list[dict]:
    off = read_active_list_offset(analyzer, anchor)
    if off is None:
        return []
    return read_priced_list(analyzer, anchor, off)

def looks_like_potion_list(items: list[dict]) -> bool:
    return bool(items) and items[0].get('kind') == LIST_KIND_POTION

def _parse_magic_entries(raw: bytes) -> list[dict]:
    items: list[dict] = []
    for seg in _segments(raw):
        m = _MAGIC_RE.search(seg)
        if not m:
            if items:
                break
            continue
        name = _clean(m.group(1))
        if not _is_name(name):
            if items:
                break
            continue
        price = _strip_coord(m.group(2))
        items.append({'en': name, 'ja': translate_name(name), 'price_display': f'{price} gp'})
        if len(items) >= _MAX_ITEMS:
            break
    return items

def read_magic_item_list(analyzer, anchor: int) -> list[dict]:
    global _magic_offset_cache
    if _magic_offset_cache is not None:
        raw = _read_raw(analyzer, anchor, _magic_offset_cache, 2048)
        items = _parse_magic_entries(raw)
        if items:
            return items
        _magic_offset_cache = None
    try:
        for rel_start, rel_end in _MAGIC_SCAN_RANGES:
            hits = analyzer.scan_bytes(_MAGIC_NAME_SIG, anchor + rel_start, anchor + rel_end)
            for h in hits:
                off = h.address - anchor
                raw = _read_raw(analyzer, anchor, off, 2048)
                items = _parse_magic_entries(raw)
                if items:
                    _magic_offset_cache = off
                    return items
    except (OSError, AttributeError):
        pass
    return []

def read_name_list(analyzer, anchor: int, offset: int, *, stop_at_empty: bool=False) -> list[dict]:
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    blanks = 0
    for seg in _segments(raw):
        if stop_at_empty and items and (seg == ''):
            break
        if items and _PRICE_RE.search(seg):
            break
        name = _clean(seg)
        if not _is_name(name) or '\n' in name:
            if items:
                blanks += 1
                if blanks >= 3:
                    break
            continue
        blanks = 0
        items.append({'en': name, 'ja': translate_name(name)})
        if len(items) >= _MAX_ITEMS:
            break
    return items

def filter_known_items(items: list[dict], allowed: set[str] | frozenset[str]) -> list[dict]:
    allowed_set = set(allowed)
    out: list[dict] = []
    for item in items:
        name = (item.get('en') or '').strip()
        if name not in allowed_set:
            break
        copied = dict(item)
        copied['ja'] = translate_name(name)
        out.append(copied)
    return out

def spellmaker_static_list(tables, offset: int) -> tuple[str, str, list[dict]] | None:
    if tables is None:
        return None
    from spellmaker_tables import ELEMENT_NAMES_OFFSET, SAVE_VS_SHOWN, TARGET_NAMES_OFFSET
    if offset in tables.sublist_offsets.values():
        effect_id = next((e for e, off in tables.sublist_offsets.items() if off == offset))
        names, title, title_id = (tables.sublists[effect_id], 'Effect Options', 'mages_list.title_effect_options')
    elif offset == ELEMENT_NAMES_OFFSET:
        names, title, title_id = (tables.elements[:SAVE_VS_SHOWN], 'Effect Options', 'mages_list.title_effect_options')
    elif offset == TARGET_NAMES_OFFSET:
        names, title, title_id = (tables.targets, 'Targets', 'mages_list.title_targets')
    else:
        return None
    return (title, i18n.text(title_id), [{'en': name, 'ja': translate_name(name)} for name in names])

def classify_spellmaker_name_items(items: list[dict], tables) -> tuple[str, str, list[dict]] | None:
    if not items or tables is None:
        return None
    first = (items[0].get('en') or '').strip()
    effects = frozenset(tables.effects)
    options = frozenset((name for names in tables.sublists.values() for name in names))
    groups = ((frozenset(tables.targets), 'Targets', 'mages_list.title_targets'), (effects, 'Effects', 'mages_list.title_effects'), (options, 'Effect Options', 'mages_list.title_effect_options'), (frozenset(tables.full_names()), 'Effects', 'mages_list.title_effects'))
    for names, title, title_id in groups:
        if first in names:
            filtered = filter_known_items(items, names)
            if filtered:
                return (title, i18n.text(title_id), filtered)
    return None

def enrich_unidentified_by_index(analyzer, anchor: int, items: list[dict]) -> list[dict]:
    if not items:
        return items
    try:
        import inventory_reader as inv
        structs = inv.read_equipment_items(analyzer, anchor)
    except Exception:
        return items
    out: list[dict] = []
    for i, it in enumerate(items):
        copied = dict(it)
        if i < len(structs):
            s = structs[i]
            if s.get('en', '').strip() == (it.get('en', '') or '').strip():
                copied['is_unidentified'] = bool(s.get('is_unidentified'))
        out.append(copied)
    return out

def _translate_name_opt(en: str) -> str | None:
    key = (en or '').strip()
    direct = i18n.value('mages', key)
    if direct:
        return direct
    from item_name_lookup import translate_item_name_opt
    return translate_item_name_opt(key)

def translate_name(en: str) -> str:
    key = (en or '').strip()
    translated = _translate_name_opt(key)
    return translated if translated is not None else key
__all__ = ['POTION_LIST_OFFSET', 'SPELL_LIST_OFFSET', 'INVENTORY_LIST_OFFSET', 'SPELLMAKER_TARGET_OFFSET', 'SPELLMAKER_EFFECT_OFFSET', 'SPELLMAKER_SUBLIST_OFFSET', 'EFFECT_PICK_OFFSET', 'read_priced_list', 'read_name_list', 'read_magic_item_list', 'read_active_priced_list', 'read_active_list_offset', 'looks_like_potion_list', 'LIST_KIND_POTION', 'LIST_KIND_SPELL', 'ACTIVE_LIST_PTR_OFFSET', 'translate_name', 'enrich_unidentified_by_index', 'filter_known_items', 'classify_spellmaker_name_items', 'spellmaker_static_list']
