from __future__ import annotations
from typing import Optional
import i18n_helper as i18n
_items_data: dict | None = None
_classes_data: dict | None = None
_races_data: dict | None = None
_ITEM_SECTIONS = ['weapons', 'armor_slots', 'shields', 'armor_materials', 'armors_by_material', 'accessories', 'accessory_attributes', 'magical_materials', 'potions', 'conditions']

def _num_id(entry_id: str) -> int:
    return int(entry_id.split('.')[-2])

def _section_entries(category: str, prefix: str) -> list[tuple[str, dict]]:
    out = [(k, e) for k, e in i18n.originals(category).items() if isinstance(e, dict) and k.startswith(prefix)]
    out.sort(key=lambda ke: _num_id(ke[0]))
    return out

def _item_flat(entry_id: str, e: dict) -> dict:
    flat = {'id': _num_id(entry_id), 'en': e.get('original', ''), 'ja': i18n.lang_value_in(entry_id, 'ja') or ''}
    flat.update(e.get('data', {}) or {})
    return flat

def _class_flat(entry_id: str, e: dict) -> dict:
    data = e.get('data', {}) or {}
    meta = e.get('_meta', {}) or {}
    flat = {'id': _num_id(entry_id), 'en': e.get('original', ''), 'ja': i18n.lang_value_in(entry_id, 'ja') or '', 'category': data.get('category', ''), 'category_ja': (data.get('category_translations', {}) or {}).get('ja', ''), 'health_die': data.get('health_die'), 'casts_magic': data.get('casts_magic'), 'allowed_armors': data.get('allowed_armors', []), 'allowed_shields': data.get('allowed_shields', []), 'allowed_weapons': data.get('allowed_weapons', [])}
    hyp = meta.get('hypothesis_note')
    if hyp:
        flat['_hypothesis_note'] = hyp
    return flat

def _race_flat(entry_id: str, e: dict) -> dict:
    data = e.get('data', {}) or {}
    return {'id': _num_id(entry_id), 'en_singular': e.get('original', ''), 'en_plural': i18n.lang_value_in(entry_id, 'en', 'plural') or '', 'ja_singular': i18n.lang_value_in(entry_id, 'ja') or '', 'ja_plural': i18n.lang_value_in(entry_id, 'ja', 'plural') or '', 'equipment_restrictions': data.get('equipment_restrictions')}

def _load() -> None:
    global _items_data, _classes_data, _races_data
    if _items_data is not None:
        return
    _items_data = {sect: [_item_flat(k, e) for k, e in _section_entries('items', f'items.{sect}.')] for sect in _ITEM_SECTIONS}
    _classes_data = {'classes': [_class_flat(k, e) for k, e in _section_entries('classes', 'classes.')]}
    _races_data = {'races': [_race_flat(k, e) for k, e in _section_entries('races', 'races.')]}

def reload() -> None:
    global _items_data, _classes_data, _races_data
    _items_data = _classes_data = _races_data = None

def get_weapon(weapon_id: int) -> Optional[dict]:
    _load()
    for w in _items_data.get('weapons', []):
        if w['id'] == weapon_id:
            return w
    return None

def get_shield(shield_id: int) -> Optional[dict]:
    _load()
    for s in _items_data.get('shields', []):
        if s['id'] == shield_id:
            return s
    return None

def get_armor_material(material_id: int) -> Optional[dict]:
    _load()
    for m in _items_data.get('armor_materials', []):
        if m['id'] == material_id:
            return m
    return None

def get_potion(potion_id: int) -> Optional[dict]:
    _load()
    for p in _items_data.get('potions', []):
        if p['id'] == potion_id:
            return p
    return None

def get_class_by_id(class_id: int) -> Optional[dict]:
    _load()
    for c in _classes_data.get('classes', []):
        if c['id'] == class_id:
            return c
    return None

def get_class_by_name(name: str) -> Optional[dict]:
    _load()
    for c in _classes_data.get('classes', []):
        if c['en'] == name or c['ja'] == name:
            return c
    return None

def all_classes() -> list[dict]:
    _load()
    return list(_classes_data.get('classes', []))

def get_race_by_id(race_id: int) -> Optional[dict]:
    _load()
    for r in _races_data.get('races', []):
        if r['id'] == race_id:
            return r
    return None

def all_races() -> list[dict]:
    _load()
    return list(_races_data.get('races', []))

def can_class_use_armor(class_id: int, material_id: int) -> bool | None:
    cls = get_class_by_id(class_id)
    if cls is None:
        return None
    return material_id in cls.get('allowed_armors', [])

def can_class_use_weapon(class_id: int, weapon_id: int) -> bool | None:
    cls = get_class_by_id(class_id)
    if cls is None:
        return None
    return weapon_id in cls.get('allowed_weapons', [])

def can_class_use_shield(class_id: int, shield_id: int) -> bool | None:
    cls = get_class_by_id(class_id)
    if cls is None:
        return None
    return shield_id in cls.get('allowed_shields', [])

def is_class_data_hypothesis(class_id: int) -> bool:
    cls = get_class_by_id(class_id)
    return bool(cls and cls.get('_hypothesis_note'))
