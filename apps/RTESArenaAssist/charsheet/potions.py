from __future__ import annotations
from collections.abc import Iterable, Mapping
import re
from typing import Optional
import assist_settings as settings
import dungeon_msg_lookup as dml
from inventory_reader import POTION_COUNT
SETTING_KEY = 'charsheet_potions'
POTION_TYPE_COUNT = POTION_COUNT
DEFAULT_SELECTED: tuple[str, ...] = ('Potion of Healing', 'Potion of Stamina', 'Potion of Cure Disease')
POTION_VALUE_KEYS: tuple[str, ...] = tuple((key for index in range(1, POTION_TYPE_COUNT + 1) for key in (f'potion_{index}_name', f'potion_{index}_short', f'potion_{index}_count')))
_SHORT_NAME_PATTERNS: tuple[re.Pattern[str], ...] = tuple((re.compile(pattern, re.IGNORECASE) for pattern in ('\\s*のポーション\\s*$', '^\\s*Potion of\\s+', '^\\s*Poción de\\s+', '^\\s*Trank der\\s+', '^\\s*Potion de\\s+', "^\\s*Potion d['’]", '^\\s*Pozione di\\s+', '^\\s*Зелье\\s+')))

def short_name(localized_name: str) -> str:
    name = (localized_name or '').strip()
    for pattern in _SHORT_NAME_PATTERNS:
        shortened, replacements = pattern.subn('', name, count=1)
        if replacements and shortened.strip():
            return shortened.strip()
    return name

def _normalise(names) -> tuple[str, ...]:
    if not isinstance(names, (list, tuple)):
        names = DEFAULT_SELECTED
    out: list[str] = []
    for value in names:
        name = value.strip() if isinstance(value, str) else ''
        if name and name not in out:
            out.append(name)
        if len(out) >= POTION_TYPE_COUNT:
            break
    return tuple(out)

def selected_names() -> tuple[str, ...]:
    return _normalise(settings.get(SETTING_KEY, DEFAULT_SELECTED))

def set_selected(name: str, enabled: bool) -> bool:
    name = (name or '').strip()
    if not name:
        return False
    names = list(selected_names())
    if enabled:
        if name in names:
            return True
        if len(names) >= POTION_TYPE_COUNT:
            return False
        names.append(name)
    elif name in names:
        names.remove(name)
    settings.set_val(SETTING_KEY, names)
    return True

def _counts(inventory: Iterable[Mapping]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inventory:
        if item.get('item_type') != 'potion' or item.get('is_unidentified'):
            continue
        name = str(item.get('en') or '').strip()
        if not name:
            continue
        try:
            count = max(0, int(item.get('count') or 0))
        except (TypeError, ValueError):
            count = 0
        counts[name] = counts.get(name, 0) + count
    return counts

def sheet_values(inventory: Optional[Iterable[Mapping]]) -> dict[str, str]:
    if inventory is None:
        return {}
    counts = _counts(inventory)
    out: dict[str, str] = {}
    for index, name in enumerate(selected_names(), 1):
        localized_name = dml.lookup_item(name) or name
        out[f'potion_{index}_name'] = localized_name
        out[f'potion_{index}_short'] = short_name(localized_name)
        out[f'potion_{index}_count'] = str(counts.get(name, 0))
    return out

def state(inventory: Optional[Iterable[Mapping]]) -> tuple:
    names = selected_names()
    if inventory is None:
        return (names, None)
    counts = _counts(inventory)
    return (names, tuple((counts.get(name, 0) for name in names)))
__all__ = ['SETTING_KEY', 'POTION_TYPE_COUNT', 'DEFAULT_SELECTED', 'POTION_VALUE_KEYS', 'short_name', 'selected_names', 'set_selected', 'sheet_values', 'state']
