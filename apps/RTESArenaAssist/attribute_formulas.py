from __future__ import annotations


def _scale_100_to_256(v: int) -> int:
    return (v * 256) // 100


def _scale_256_to_100(v: int) -> int:
    return round(v * 100 / 256)


def calc_damage_bonus(strength: int) -> int:
    if strength <= 42:
        return (strength - 43) // 5
    if strength <= 54:
        return 0
    return (strength - 50) // 5


def calc_max_kilos(strength: int) -> int:
    return min(strength * 2, 199)


def calc_magic_defense(willpower: int) -> int:
    return int((willpower - 50) / 5)


def calc_bonus_to_hit(value: int) -> int:
    return int((value - 50) / 5)


def calc_bonus_to_health(endurance: int) -> int:
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
