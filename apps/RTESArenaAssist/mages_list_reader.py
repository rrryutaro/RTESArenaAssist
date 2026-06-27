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
_BOUNDARY_FFFD_MIN = 4
_MAGIC_NAME_SIG = b'\t031'
_MAGIC_SCAN_RANGES = ((2097152, 3145728), (0, 8388608))
_MAGIC_RE = re.compile('\\d{3}([^\\n]+)\\n\\D*?(\\d+)\\s*gp', re.DOTALL)
_magic_offset_cache: int | None = None
_PRICE_RE = re.compile('(\\d+)\\s*gp\\s*\\n?(.*)', re.DOTALL)
_KEEP_RE = re.compile('[^\\x20-\\x7E]')
SPELLMAKER_TARGET_NAMES = frozenset({'None', 'Caster only', '1 Target, Touch', '1 Target at Range', 'Area - Centered on Caster', 'Area - Centered On Caster', 'Area - at Range, Explosion'})
SPELLMAKER_EFFECT_CATEGORY_NAMES = frozenset({'Cause', 'Continuous Damage', 'Create', 'Cure', 'Damage', 'Designate as Non-Target', 'Destroy', 'Drain Attribute', 'Elemental Resistance', 'Fortify Attribute', 'Heal', 'Transfer', 'Invisibility', 'Levitate', 'Light', 'Lock', 'Open', 'Regenerate', 'Silence', 'Spell Absorption', 'Spell Reflection', 'Spell Resistance'})
SPELLMAKER_EFFECT_OPTION_NAMES = frozenset({'Disease', 'Poison', 'Paralyzation', 'Curse', 'Fear', 'Death', 'Health', 'Fatigue', 'Spell Points', 'Shield', 'Wall', 'Floor', 'Fire', 'Cold', 'Shock', 'Magic', 'Energy', 'Attribute', 'Figured Attribute', 'Strength', 'Intelligence', 'Willpower', 'Agility', 'Speed', 'Endurance', 'Personality', 'Luck', 'Follows caster', 'Projectile', 'Yes', 'No'})
_FULL_EFFECT_SUFFIXES = {'Cause': ('Disease', 'Poison', 'Paralyzation', 'Curse', 'Fear', 'Death'), 'Continuous Damage': ('Health', 'Fatigue', 'Spell Points'), 'Create': ('Shield', 'Wall', 'Floor'), 'Cure': ('Disease', 'Poison', 'Paralyzation', 'Curse', 'Fear'), 'Damage': ('Health', 'Fatigue', 'Spell Points'), 'Destroy': ('Wall', 'Floor'), 'Heal': ('Fatigue', 'Health', 'Spell Points'), 'Elemental Resistance': ('Fire', 'Cold', 'Shock', 'Magic', 'Poison')}
SPELLMAKER_EFFECT_FULL_NAMES = frozenset({f'{prefix} {suffix}' for prefix, suffixes in _FULL_EFFECT_SUFFIXES.items() for suffix in suffixes}) | frozenset({'Designate as Non-Target', 'Drain Attribute', 'Fortify Attribute', 'Transfer Attribute', 'Invisibility', 'Levitate', 'Light', 'Lock', 'Open', 'Regenerate', 'Silence', 'Spell Absorption', 'Spell Reflection', 'Spell Resistance'})

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

def read_priced_list(analyzer, anchor: int, offset: int) -> list[dict]:
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    blanks = 0
    for seg in _segments(raw):
        m = _PRICE_RE.search(seg)
        if not m:
            if items:
                blanks += 1
                if blanks >= 3:
                    break
            continue
        if items and seg[:m.start(1)].count('�') >= _BOUNDARY_FFFD_MIN:
            break
        blanks = 0
        name = _clean(m.group(2))
        if not _is_name(name):
            if items:
                break
            continue
        price = _strip_coord(m.group(1))
        items.append({'en': name, 'ja': translate_name(name), 'price_display': f'{price} gp'})
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
    return bool(items) and items[0].get('en', '').startswith('Potion of')

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

def read_name_list(analyzer, anchor: int, offset: int) -> list[dict]:
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    blanks = 0
    for seg in _segments(raw):
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

def classify_spellmaker_name_items(items: list[dict]) -> tuple[str, str, list[dict]] | None:
    if not items:
        return None
    first = (items[0].get('en') or '').strip()
    if first in SPELLMAKER_TARGET_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_TARGET_NAMES)
        if filtered:
            return ('Targets', '対象一覧', filtered)
    if first in SPELLMAKER_EFFECT_CATEGORY_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_CATEGORY_NAMES)
        if filtered:
            return ('Effects', '効果一覧', filtered)
    if first in SPELLMAKER_EFFECT_OPTION_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_OPTION_NAMES)
        if filtered:
            return ('Effect Options', '効果オプション', filtered)
    if first in SPELLMAKER_EFFECT_FULL_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_FULL_NAMES)
        if filtered:
            return ('Effects', '効果一覧', filtered)
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

def translate_name(en: str) -> str:
    key = (en or '').strip()
    direct = i18n.value('mages', key) or i18n.value('items', key)
    if direct:
        return direct
    m = re.match('^(.+?) (of .+)$', key)
    if m:
        ench_ja = i18n.value('item_enchantments', m.group(2))
        if ench_ja:
            base = m.group(1).strip()
            base_ja = translate_name(base)
            if base_ja and base_ja != base:
                return f'{ench_ja}の{base_ja}'
    parts = key.split()
    if len(parts) >= 2:
        base = parts[-1]
        base_ja = i18n.value('items', base) or i18n.value('mages', base)
        if base_ja:
            prefix_ja = ''.join((i18n.value('item_materials', p) or p for p in parts[:-1]))
            return f'{prefix_ja}{base_ja}'
    return key
__all__ = ['POTION_LIST_OFFSET', 'SPELL_LIST_OFFSET', 'INVENTORY_LIST_OFFSET', 'SPELLMAKER_TARGET_OFFSET', 'SPELLMAKER_EFFECT_OFFSET', 'SPELLMAKER_SUBLIST_OFFSET', 'EFFECT_PICK_OFFSET', 'read_priced_list', 'read_name_list', 'read_magic_item_list', 'read_active_priced_list', 'read_active_list_offset', 'looks_like_potion_list', 'ACTIVE_LIST_PTR_OFFSET', 'translate_name', 'enrich_unidentified_by_index', 'filter_known_items', 'classify_spellmaker_name_items', 'SPELLMAKER_TARGET_NAMES', 'SPELLMAKER_EFFECT_CATEGORY_NAMES', 'SPELLMAKER_EFFECT_OPTION_NAMES', 'SPELLMAKER_EFFECT_FULL_NAMES']
