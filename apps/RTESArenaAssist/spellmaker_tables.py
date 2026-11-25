from __future__ import annotations
import logging
import struct
from dataclasses import dataclass, field
_log = logging.getLogger('RTESArenaAssist')
REGION_START = 21184
REGION_END = 22272
EFFECT_NAMES_OFFSET = 21185
SUBLIST_PTR_OFFSET = 21542
TEMPLATE_PTR_OFFSET = 21617
ELEMENT_NAMES_OFFSET = 22127
ELEMENT_COUNT = 6
TARGET_NAMES_OFFSET = 22161
SAVE_VS_SHOWN = 5
TRANSFER_EFFECT = 13
TRANSFER_SECOND_LEVEL = {0: (128, 9), 1: (48, 4)}

@dataclass(frozen=True)
class SpellmakerTables:
    effects: tuple[str, ...]
    sublists: dict[int, tuple[str, ...]] = field(default_factory=dict)
    sublist_offsets: dict[int, int] = field(default_factory=dict)
    templates: dict[int, tuple[int, ...]] = field(default_factory=dict)
    template_direct: dict[int, bool] = field(default_factory=dict)
    elements: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()

    def effect_name(self, effect_id: int) -> str | None:
        return self.effects[effect_id] if 0 <= effect_id < len(self.effects) else None

    def option_name(self, effect_id: int, sub_id: int) -> str | None:
        names = self.sublists.get(effect_id)
        if not names or not 0 <= sub_id < len(names):
            return None
        return names[sub_id]

    def transfer_value_name(self, sub_id: int, attr_id: int) -> str | None:
        rule = TRANSFER_SECOND_LEVEL.get(sub_id)
        if rule is None:
            return None
        base, source_effect = rule
        return self.option_name(source_effect, attr_id - base)

    def name_words(self, effect_id: int, sub_id: int, attr_id: int) -> list[str]:
        effect = self.effect_name(effect_id)
        if effect is None:
            return []
        words = [effect]
        option = self.option_name(effect_id, sub_id)
        if option is not None:
            words.append(option)
            if effect_id == TRANSFER_EFFECT:
                value = self.transfer_value_name(sub_id, attr_id)
                if value is not None:
                    words.append(value)
        return words

    def template_id(self, effect_id: int, sub_id: int) -> int | None:
        ids = self.templates.get(effect_id)
        if not ids:
            return None
        if self.template_direct.get(effect_id):
            return ids[0]
        return ids[sub_id] if 0 <= sub_id < len(ids) else None

    def full_names(self) -> dict[str, tuple[int, int]]:
        out: dict[str, tuple[int, int]] = {}
        for e, effect in enumerate(self.effects):
            names = self.sublists.get(e)
            if not names:
                out.setdefault(effect, (e, 0))
                continue
            for s, option in enumerate(names):
                if e == TRANSFER_EFFECT:
                    rule = TRANSFER_SECOND_LEVEL.get(s)
                    values = self.sublists.get(rule[1], ()) if rule else ()
                    for v in values:
                        out.setdefault(f'{effect} {option} {v}', (e, s))
                out.setdefault(f'{effect} {option}', (e, s))
        return out

def _names(region: bytes, offset: int, *, count: int | None=None) -> tuple[str, ...] | None:
    i = offset - REGION_START
    if not 0 <= i < len(region):
        return None
    out: list[str] = []
    while i < len(region):
        j = region.find(b'\x00', i)
        if j < 0:
            return None
        seg = region[i:j]
        if not seg:
            break
        if any((b < 32 or b > 126 for b in seg)):
            return None
        out.append(seg.decode('ascii'))
        i = j + 1
        if count is not None and len(out) >= count:
            break
    if count is not None and len(out) != count:
        return None
    return tuple(out) if out else None

def _u16(region: bytes, offset: int) -> int | None:
    i = offset - REGION_START
    if not 0 <= i <= len(region) - 2:
        return None
    return struct.unpack_from('<H', region, i)[0]

def parse(region: bytes) -> SpellmakerTables | None:
    if len(region) < REGION_END - REGION_START:
        return None
    effects = _names(region, EFFECT_NAMES_OFFSET)
    if not effects:
        return None
    n = len(effects)
    sublists: dict[int, tuple[str, ...]] = {}
    sublist_offsets: dict[int, int] = {}
    for e in range(n):
        ptr = _u16(region, SUBLIST_PTR_OFFSET + 2 * e)
        if ptr is None:
            return None
        if ptr == 0:
            continue
        names = _names(region, ptr)
        if not names:
            return None
        sublists[e] = names
        sublist_offsets[e] = ptr
    templates: dict[int, tuple[int, ...]] = {}
    direct: dict[int, bool] = {}
    for e in range(n):
        ptr = _u16(region, TEMPLATE_PTR_OFFSET + 2 * e)
        if ptr is None:
            return None
        if ptr < 256:
            templates[e] = (ptr,)
            direct[e] = True
            continue
        count = len(sublists.get(e, ()))
        i = ptr - REGION_START
        if not count or not 0 <= i <= len(region) - count:
            return None
        templates[e] = tuple(region[i:i + count])
        direct[e] = False
    elements = _names(region, ELEMENT_NAMES_OFFSET, count=ELEMENT_COUNT)
    targets = _names(region, TARGET_NAMES_OFFSET)
    if not elements or not targets:
        return None
    tables = SpellmakerTables(effects=effects, sublists=sublists, sublist_offsets=sublist_offsets, templates=templates, template_direct=direct, elements=elements, targets=targets)
    return tables
_cache: tuple[int, SpellmakerTables] | None = None
_last_state: bool | None = None

def ensure(analyzer, anchor: int) -> SpellmakerTables | None:
    global _cache
    if not anchor:
        return current()
    if _cache is not None and _cache[0] == anchor:
        return _cache[1]
    try:
        region = analyzer.read_bytes(anchor + REGION_START, REGION_END - REGION_START)
    except Exception:
        region = b''
    tables = parse(region or b'')
    _note_state(tables)
    if tables is None:
        return None
    _cache = (anchor, tables)
    return tables

def current() -> SpellmakerTables | None:
    return _cache[1] if _cache is not None else None

def set_for_test(tables: SpellmakerTables | None) -> None:
    global _cache
    _cache = (-1, tables) if tables is not None else None

def _note_state(tables: SpellmakerTables | None) -> None:
    global _last_state
    ok = tables is not None
    if ok == _last_state:
        return
    _last_state = ok
    from assist_log import recog
    if ok:
        recog(_log, 'spellmaker tables loaded: effects=%d sublists=%d targets=%d', len(tables.effects), len(tables.sublists), len(tables.targets))
    else:
        recog(_log, 'spellmaker tables unreadable')
__all__ = ['SpellmakerTables', 'parse', 'ensure', 'current', 'set_for_test', 'REGION_START', 'REGION_END', 'ELEMENT_NAMES_OFFSET', 'TARGET_NAMES_OFFSET', 'SAVE_VS_SHOWN']
