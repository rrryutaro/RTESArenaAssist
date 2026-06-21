"""experience_calc.py — レベルアップに必要な累計経験値の算出

データソース:
  - L1〜L10: Arena 公式マニュアル page 37 "Experience Tables" の値を直接採用
  - L11 以降: OpenTESArena 由来の公式（floor(prev * 1.5)）で延長

クラスは 6 カテゴリに分類される（マニュアル準拠）:
  - Thieves base / Thief Subclasses
  - Warriors base / Warrior Subclasses
  - Mages base / Mage Subclasses
"""
from __future__ import annotations
import math
from typing import Optional

# Arena 公式マニュアル page 37 Experience Tables（L2〜L10、L1=0）
# index: level - 2
_EXP_TABLE_THIEVES     = [800,  1500,  2812,  5273,  9887,  18539,  34761,  65177,  122208]
_EXP_TABLE_THIEF_SUB   = [1000, 1875,  3515,  6591,  12359, 23174,  43451,  81472,  152760]
_EXP_TABLE_WARRIORS    = [900,  1687,  3164,  5932,  11123, 20856,  39106,  73324,  137484]
_EXP_TABLE_WARRIOR_SUB = [1100, 2062,  3867,  7250,  13595, 25491,  47796,  89617,  168032]
_EXP_TABLE_MAGES       = [1000, 1875,  3515,  6591,  12359, 23174,  43451,  81472,  152760]
_EXP_TABLE_MAGE_SUB    = [1200, 2250,  4218,  7910,  14831, 27809,  52142,  97766,  183312]

# クラス id（classes.json）→ 経験値テーブル
_CLASS_TABLE: dict[int, list[int]] = {
    0:  _EXP_TABLE_MAGES,        # Mage
    1:  _EXP_TABLE_MAGE_SUB,     # Spellsword
    2:  _EXP_TABLE_MAGE_SUB,     # Battlemage
    3:  _EXP_TABLE_MAGE_SUB,     # Sorceror
    4:  _EXP_TABLE_MAGE_SUB,     # Healer
    5:  _EXP_TABLE_THIEF_SUB,    # Nightblade
    6:  _EXP_TABLE_THIEF_SUB,    # Bard
    7:  _EXP_TABLE_THIEF_SUB,    # Burglar
    8:  _EXP_TABLE_THIEF_SUB,    # Rogue
    9:  _EXP_TABLE_THIEF_SUB,    # Acrobat
    10: _EXP_TABLE_THIEVES,      # Thief
    11: _EXP_TABLE_THIEF_SUB,    # Assassin
    12: _EXP_TABLE_WARRIOR_SUB,  # Monk
    13: _EXP_TABLE_WARRIOR_SUB,  # Archer
    14: _EXP_TABLE_WARRIOR_SUB,  # Ranger
    15: _EXP_TABLE_WARRIOR_SUB,  # Barbarian
    16: _EXP_TABLE_WARRIORS,     # Warrior
    17: _EXP_TABLE_WARRIOR_SUB,  # Knight
}

# L11+ で使うマルチプライヤ（OpenTESArena の getExperienceCap より）
_HIGH_LEVEL_MULTIPLIER = 1.5


def exp_threshold_for_level(class_id: int, level: int) -> Optional[int]:
    """指定クラスが指定レベルに到達するのに必要な累計経験値を返す。

    Args:
        class_id: classes.json の id（0〜17）
        level:    到達したいレベル（1 以上）

    Returns:
        累計経験値。class_id 未登録 / level 不正なら None。
        L1=0、L2〜L10 はマニュアル表値、L11+ は floor(prev * 1.5) で延長。
    """
    if class_id not in _CLASS_TABLE or level <= 0:
        return None
    if level == 1:
        return 0
    table = _CLASS_TABLE[class_id]
    if 2 <= level <= 10:
        return table[level - 2]
    # L11+: L10 値から floor(prev * 1.5) で延長
    cap = table[10 - 2]
    for _ in range(11, level + 1):
        cap = math.floor(cap * _HIGH_LEVEL_MULTIPLIER)
    return cap


def exp_threshold_for_next_level(class_id: int, current_level: int) -> Optional[int]:
    """現在レベルから次レベルに到達するのに必要な累計経験値を返す。"""
    return exp_threshold_for_level(class_id, current_level + 1)
