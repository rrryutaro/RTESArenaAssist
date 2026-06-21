from __future__ import annotations


class ArenaRandom:

    DEFAULT_SEED = 12345
    MAX = 0xFFFF
    MULTIPLIER = 7143469

    def __init__(self, seed: int | None = None):
        if seed is None:
            seed = self.DEFAULT_SEED
        self.value = seed & 0xFFFFFFFF

    def srand(self, seed: int) -> None:
        self.value = seed & 0xFFFFFFFF

    def next(self) -> int:
        self.value = (self.value * self.MULTIPLIER) & 0xFFFFFFFF
        return (self.value >> 16) & 0xFFFF

    def get_seed(self) -> int:
        return self.value
