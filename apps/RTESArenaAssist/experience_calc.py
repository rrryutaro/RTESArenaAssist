from __future__ import annotations
import math
from typing import Optional
_EXP_TABLE_THIEVES = [800, 1500, 2812, 5273, 9887, 18539, 34761, 65177, 122208]
_EXP_TABLE_THIEF_SUB = [1000, 1875, 3515, 6591, 12359, 23174, 43451, 81472, 152760]
_EXP_TABLE_WARRIORS = [900, 1687, 3164, 5932, 11123, 20856, 39106, 73324, 137484]
_EXP_TABLE_WARRIOR_SUB = [1100, 2062, 3867, 7250, 13595, 25491, 47796, 89617, 168032]
_EXP_TABLE_MAGES = [1000, 1875, 3515, 6591, 12359, 23174, 43451, 81472, 152760]
_EXP_TABLE_MAGE_SUB = [1200, 2250, 4218, 7910, 14831, 27809, 52142, 97766, 183312]
_CLASS_TABLE: dict[int, list[int]] = {0: _EXP_TABLE_MAGES, 1: _EXP_TABLE_MAGE_SUB, 2: _EXP_TABLE_MAGE_SUB, 3: _EXP_TABLE_MAGE_SUB, 4: _EXP_TABLE_MAGE_SUB, 5: _EXP_TABLE_THIEF_SUB, 6: _EXP_TABLE_THIEF_SUB, 7: _EXP_TABLE_THIEF_SUB, 8: _EXP_TABLE_THIEF_SUB, 9: _EXP_TABLE_THIEF_SUB, 10: _EXP_TABLE_THIEVES, 11: _EXP_TABLE_THIEF_SUB, 12: _EXP_TABLE_WARRIOR_SUB, 13: _EXP_TABLE_WARRIOR_SUB, 14: _EXP_TABLE_WARRIOR_SUB, 15: _EXP_TABLE_WARRIOR_SUB, 16: _EXP_TABLE_WARRIORS, 17: _EXP_TABLE_WARRIOR_SUB}
_HIGH_LEVEL_MULTIPLIER = 1.5

def exp_threshold_for_level(class_id: int, level: int) -> Optional[int]:
    if class_id not in _CLASS_TABLE or level <= 0:
        return None
    if level == 1:
        return 0
    table = _CLASS_TABLE[class_id]
    if 2 <= level <= 10:
        return table[level - 2]
    cap = table[10 - 2]
    for _ in range(11, level + 1):
        cap = math.floor(cap * _HIGH_LEVEL_MULTIPLIER)
    return cap

def exp_threshold_for_next_level(class_id: int, current_level: int) -> Optional[int]:
    return exp_threshold_for_level(class_id, current_level + 1)
