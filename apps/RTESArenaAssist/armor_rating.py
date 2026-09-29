from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Optional
UNARMORED = 10
LOCATIONS: tuple[str, ...] = ('head', 'shoulder_right', 'shoulder_left', 'chest', 'hands', 'legs', 'feet')
_ARMOR_SLOT_LOCATION: dict[int, str] = {0: 'chest', 1: 'hands', 2: 'legs', 3: 'shoulder_left', 4: 'shoulder_right', 5: 'head', 6: 'feet'}
_SHIELDS: dict[int, tuple[tuple[str, ...], int]] = {7: (('hands', 'shoulder_left'), 1), 8: (('hands', 'shoulder_left', 'chest'), 2), 9: (('hands', 'shoulder_left', 'chest', 'legs'), 3), 10: (('hands', 'head', 'shoulder_left', 'chest', 'legs'), 4)}
_ARMOR_TYPE_VALUE = {0: 3, 1: 6, 2: 9}
_METAL_BONUS = {0: -1, 1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

def piece_value(item: dict) -> int:
    value = _number(item.get('armor_value'), 0)
    if value > 0:
        return value
    item_type = item.get('item_type')
    if item_type == 'armor':
        base = _ARMOR_TYPE_VALUE.get(_number(item.get('armor_material_id'), -1))
        if base is None:
            return 0
        if base == _ARMOR_TYPE_VALUE[2]:
            base += _METAL_BONUS.get(_number(item.get('metal'), -1), 0)
        return base
    if item_type == 'shield':
        return _SHIELDS.get(_number(item.get('slot_id'), -1), ((), 0))[1]
    return 0

@dataclass
class ArmorBreakdown:
    ratings: dict[str, int]
    pieces: dict[str, int] = field(default_factory=dict)
    shield: Optional[tuple[int, int, tuple[str, ...]]] = None
    jewelry: tuple[int, ...] = ()
    agility: int = 0
    unknown: tuple[str, ...] = ()

def compute(items: Optional[Iterable[dict]], to_defend: Optional[int]) -> Optional[ArmorBreakdown]:
    if items is None:
        return None
    agility = to_defend or 0
    pieces: dict[str, int] = {}
    jewelry: list[int] = []
    shield = None
    unknown: list[str] = []
    for item in items:
        if not item.get('equipped'):
            continue
        item_type = item.get('item_type')
        slot = _number(item.get('slot_id'), -1)
        if item_type == 'armor':
            location = _ARMOR_SLOT_LOCATION.get(slot)
            if location is None:
                unknown.append(f'armor slot {slot}')
                continue
            pieces[location] = piece_value(item)
        elif item_type == 'shield':
            known = _SHIELDS.get(slot)
            if known is None:
                unknown.append(f'shield slot {slot}')
                continue
            shield = (slot, piece_value(item), known[0])
        elif item_type == 'accessory':
            value = piece_value(item)
            if value:
                jewelry.append(value)
    jewelry_total = sum(jewelry)
    ratings = {}
    for location in LOCATIONS:
        value = UNARMORED - pieces.get(location, 0) - jewelry_total - agility
        if shield is not None and location in shield[2]:
            value -= shield[1]
        ratings[location] = value
    return ArmorBreakdown(ratings=ratings, pieces=pieces, shield=shield, jewelry=tuple(jewelry), agility=agility, unknown=tuple(unknown))

def materials_key(items: Optional[Iterable[dict]]) -> tuple:
    if not items:
        return ()
    return tuple(sorted(((str(item.get('item_type')), _number(item.get('slot_id'), -1), _number(item.get('armor_value'), 0), _number(item.get('armor_material_id'), -1), _number(item.get('metal'), -1)) for item in items if item.get('equipped') and item.get('item_type') in ('armor', 'shield', 'accessory'))))

def format_rating(value: int) -> str:
    return f'{value:+d}' if value else '0'

def sheet_values(breakdown: Optional[ArmorBreakdown]) -> dict[str, str]:
    if breakdown is None:
        return {}
    return {f'ar_{location}': format_rating(value) for location, value in breakdown.ratings.items()}

def describe(breakdown: ArmorBreakdown) -> str:
    ratings = ' '.join((f'{location}={format_rating(value)}' for location, value in breakdown.ratings.items()))
    return '%s 材料: 防具=%s 盾=%s 装身具=%s 敏捷の防御=%+d%s' % (ratings, breakdown.pieces, breakdown.shield, list(breakdown.jewelry), breakdown.agility, f' 計算に入れていない={list(breakdown.unknown)}' if breakdown.unknown else '')

def parse_signed(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        return int(str(text).replace('+', '').strip())
    except ValueError:
        return None

def _number(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
__all__ = ['UNARMORED', 'LOCATIONS', 'ArmorBreakdown', 'piece_value', 'compute', 'materials_key', 'format_rating', 'sheet_values', 'describe', 'parse_signed']
