from __future__ import annotations
import struct
from inventory_reader import SHIELD_SLOT_MIN, SHIELD_SLOT_MAX, is_broken_item
CLASS_COUNT = 18
WEAPON_COUNT = 18
PLAYER_CLASS_NUMBER_OFFSET = 425
CLASS_INDEX_MASK = 31
ALLOWED_ARMORS_OFFSET = -22012
ALLOWED_SHIELDS_OFFSET = -22063
ALLOWED_WEAPONS_OFFSET = -22139
ANCHOR_DS_OFFSET = 37536
_LIST_TERMINATOR = 255
_LIST_READ_MAX = 32
_ARMOR_MATERIALS_BY_LEVEL = {0: frozenset({0, 1, 2}), 1: frozenset({0, 1}), 2: frozenset({0}), 3: frozenset()}

def _read_allowed_list(analyzer, anchor: int, table_offset: int, class_index: int, all_values: range) -> frozenset | None:
    raw = analyzer.read_bytes(anchor + table_offset + class_index * 2, 2)
    ptr = struct.unpack('<H', raw)[0]
    if ptr == 0:
        return frozenset(all_values)
    data = analyzer.read_bytes(anchor + ptr - ANCHOR_DS_OFFSET, _LIST_READ_MAX)
    values: set[int] = set()
    for b in data:
        if b == _LIST_TERMINATOR:
            return frozenset(values)
        if b not in all_values:
            return None
        values.add(b)
    return None

def read_class_equip_rules(analyzer, anchor: int) -> dict | None:
    try:
        cls_num = analyzer.read_bytes(anchor + PLAYER_CLASS_NUMBER_OFFSET, 1)[0]
        class_index = cls_num & CLASS_INDEX_MASK
        if class_index >= CLASS_COUNT:
            return None
        armor_level = analyzer.read_bytes(anchor + ALLOWED_ARMORS_OFFSET + class_index, 1)[0]
        armor_materials = _ARMOR_MATERIALS_BY_LEVEL.get(armor_level)
        if armor_materials is None:
            return None
        shield_slots = _read_allowed_list(analyzer, anchor, ALLOWED_SHIELDS_OFFSET, class_index, range(SHIELD_SLOT_MIN, SHIELD_SLOT_MAX + 1))
        weapon_ids = _read_allowed_list(analyzer, anchor, ALLOWED_WEAPONS_OFFSET, class_index, range(WEAPON_COUNT))
        if shield_slots is None or weapon_ids is None:
            return None
        return {'class_index': class_index, 'armor_materials': armor_materials, 'shield_slots': shield_slots, 'weapon_ids': weapon_ids}
    except OSError:
        return None

def can_equip_item(item_summary: dict, rules: dict | None) -> bool | None:
    item_type = item_summary['item_type']
    if item_type == 'potion':
        return False
    if item_type in ('weapon', 'armor', 'shield'):
        if is_broken_item(item_summary.get('health', 0), item_summary.get('max_hp', 0), item_summary.get('hands', 0)):
            return False
    if item_type == 'weapon':
        if rules is None:
            return None
        return item_summary['slot_id'] in rules['weapon_ids']
    if item_type == 'armor':
        if rules is None:
            return None
        return item_summary['armor_material_id'] in rules['armor_materials']
    if item_type == 'shield':
        if rules is None:
            return None
        return item_summary['slot_id'] in rules['shield_slots']
    return True
