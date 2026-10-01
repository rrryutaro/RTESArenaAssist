from __future__ import annotations
from collections.abc import Iterable, Mapping
from typing import Optional
import assist_settings as settings
import dungeon_msg_lookup as dml
import i18n_helper as i18n
from inventory_reader import INV_SLOTS
SETTING_KEY = 'charsheet_magic_items'
MAGIC_ITEM_SLOT_COUNT = INV_SLOTS
DEFAULT_SELECTED: tuple[str, ...] = ()
MAGIC_ITEM_VALUE_KEYS: tuple[str, ...] = tuple((key for index in range(1, MAGIC_ITEM_SLOT_COUNT + 1) for key in (f'magic_item_{index}_name', f'magic_item_{index}_effect', f'magic_item_{index}_uses')))

def _normalise(names) -> tuple[str, ...]:
    if not isinstance(names, (list, tuple)):
        names = DEFAULT_SELECTED
    out: list[str] = []
    for value in names:
        name = value.strip() if isinstance(value, str) else ''
        if name and name not in out:
            out.append(name)
    return tuple(out)

def selected_names() -> tuple[str, ...]:
    return _normalise(settings.get(SETTING_KEY, DEFAULT_SELECTED))

def set_selected(name: str, enabled: bool) -> bool:
    name = (name or '').strip()
    if not name:
        return False
    names = list(selected_names())
    if enabled and name not in names:
        names.append(name)
    elif not enabled and name in names:
        names.remove(name)
    settings.set_val(SETTING_KEY, names)
    return True

def is_selectable(item: Mapping) -> bool:
    if item.get('is_unidentified') or not str(item.get('en') or '').strip():
        return False
    uses = item.get('uses')
    try:
        int(uses)
    except (TypeError, ValueError):
        return False
    return uses is not None

def effect_name(item_name: str) -> str:
    marker = ' of '
    pos = item_name.rfind(marker)
    if pos < 0:
        return item_name
    effect = item_name[pos + len(marker):].strip()
    if not effect:
        return item_name
    translated = dml.lookup_spell(effect)
    if translated:
        return translated
    translated = i18n.value('item_enchantments', f'of {effect}')
    if translated:
        return translated.removesuffix('の').strip() or translated
    return effect

def _selected_items(inventory: Iterable[Mapping]) -> list[Mapping]:
    selected = set(selected_names())
    return [item for item in inventory if str(item.get('en') or '').strip() in selected and is_selectable(item)]

def sheet_values(inventory: Optional[Iterable[Mapping]]) -> dict[str, str]:
    if inventory is None:
        return {}
    out: dict[str, str] = {}
    for index, item in enumerate(_selected_items(inventory), 1):
        if index > MAGIC_ITEM_SLOT_COUNT:
            break
        name = str(item.get('en') or '').strip()
        out[f'magic_item_{index}_name'] = dml.lookup_item(name) or name
        out[f'magic_item_{index}_effect'] = effect_name(name)
        out[f'magic_item_{index}_uses'] = str(int(item.get('uses')))
    return out

def state(inventory: Optional[Iterable[Mapping]]) -> tuple:
    names = selected_names()
    if inventory is None:
        return (names, None)
    return (names, tuple(((str(item.get('en') or ''), int(item.get('uses'))) for item in _selected_items(inventory))))
__all__ = ['SETTING_KEY', 'MAGIC_ITEM_SLOT_COUNT', 'DEFAULT_SELECTED', 'MAGIC_ITEM_VALUE_KEYS', 'selected_names', 'set_selected', 'is_selectable', 'effect_name', 'sheet_values', 'state']
