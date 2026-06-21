"""arena_random.py — Arena 本体互換の擬似乱数生成器 (LCG)。

OpenTESArena `Math/Random.cpp` の `ArenaRandom` クラスを Python 移植。
multiplier = 7143469、戻り値は (value >> 16) & 0xFFFF (上位 16-bit)。
"""
from __future__ import annotations


class ArenaRandom:
    """Arena 互換の決定論的 LCG。"""

    DEFAULT_SEED = 12345
    MAX = 0xFFFF
    MULTIPLIER = 7143469

    def __init__(self, seed: int | None = None):
        if seed is None:
            seed = self.DEFAULT_SEED
        self.value = seed & 0xFFFFFFFF

    def srand(self, seed: int) -> None:
        """seed で内部状態をリセット。"""
        self.value = seed & 0xFFFFFFFF

    def next(self) -> int:
        """次の 16-bit 乱数を返す (0 〜 0xFFFF)。"""
        self.value = (self.value * self.MULTIPLIER) & 0xFFFFFFFF
        return (self.value >> 16) & 0xFFFF

    def get_seed(self) -> int:
        """現在の内部状態を返す。"""
        return self.value
