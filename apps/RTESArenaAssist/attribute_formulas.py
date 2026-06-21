"""attribute_formulas.py — プレイヤー派生値の純粋計算式（副作用なし）。

attributes_panel.py から分離した、Arena 派生値（Damage / Max Kilos / Magic Def /
to Hit / Bonus Health / Max Stamina 等）の計算式。すべて primary attribute から
派生値を求める純粋関数で、UI / メモリ / 設定に依存しない。

公式の根拠: Arena Manual p22 + OpenTESArena ArenaPlayerUtils.cpp、および実機
観測値での検証（各関数の docstring 参照）。
"""
from __future__ import annotations


def _scale_100_to_256(v: int) -> int:
    return (v * 256) // 100


def _scale_256_to_100(v: int) -> int:
    return round(v * 100 / 256)


def calc_damage_bonus(strength: int) -> int:
    """Damage modifier from STR.

    確定計算式 (実機観測値で検証):
      STR <= 42: floor((STR - 43) / 5)  [negative side]
      STR 43..54: 0
      STR >= 55: floor((STR - 50) / 5)  [positive side]

    検証データ:
      STR=33 → -2  (Python: -10//5 = -2)
      STR=36 → -2  (-7//5 = -2)
      STR=42 → -1  (-1//5 = -1)
      STR=43 →  0
      STR=90 → +8  (40//5 = 8)
      STR=100 → +10 (50//5 = 10)

    実プレイ中は memory +0x1DD (i16) を優先読み出し。本関数は fallback。
    """
    if strength <= 42:
        return (strength - 43) // 5
    if strength <= 54:
        return 0
    return (strength - 50) // 5


def calc_max_kilos(strength: int) -> int:
    """Max Kilos: STR * 2、ただし 199 で cap (STR=100→199 確認)。"""
    return min(strength * 2, 199)


def calc_magic_defense(willpower: int) -> int:
    """Magic Def (WIL) — 実機 Arena DOS の確認に基づく線形公式。

      formula: int((WIL - 50) / 5)  (C-style truncation toward zero)

      確認: WIL=0 → -10、WIL=41 → -1。
      OpenTESArena の "<=38: -2" 形式は実機に存在せず、線形であることが確定。
      負値は truncation（切り捨てではなく 0 方向への切り詰め）。
    """
    return int((willpower - 50) / 5)


def calc_bonus_to_hit(value: int) -> int:
    """to Hit / to Defend (AGI) / Charisma (PER) 共通 — 実機 Arena DOS 線形公式。

      formula: int((v - 50) / 5)  (C-style truncation toward zero)

      確認: v=0 → -10。OpenTESArena の "<=45: -1" 形式は
      実機に存在せず、線形であることが確定。
      負値は truncation（C-style int 除算と同等）。
    """
    return int((value - 50) / 5)


def calc_bonus_to_health(endurance: int) -> int:
    """Bonus Health / Heal Mod (END) — 256-base スケーリング + C-style truncation。

      formula:
        end_256 = (END * 256) // 100          # scale100To256（OpenTESArena 互換）
        result  = int((end_256 - 116) / 25)   # C-style truncation toward zero

      確認: END=0 → -4、END=50 → 0、END=56 → +1。
      旧式 (END-50)*2//25 は END=56 で 0 を返し誤りだった。

      段階表（実機確認値のみ):
        END=0   → -4
        END=50  →  0
        END=56  → +1
    """
    end_256 = (endurance * 256) // 100
    return int((end_256 - 116) / 25)


def calc_max_stamina(strength: int, endurance: int) -> int:
    return strength + endurance


__all__ = [
    "_scale_100_to_256",
    "_scale_256_to_100",
    "calc_damage_bonus",
    "calc_max_kilos",
    "calc_magic_defense",
    "calc_bonus_to_hit",
    "calc_bonus_to_health",
    "calc_max_stamina",
]
