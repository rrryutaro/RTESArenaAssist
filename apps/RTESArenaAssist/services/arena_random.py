from __future__ import annotations

class ArenaRandom:
    DEFAULT_SEED = 12345
    MAX = 65535
    MULTIPLIER = 7143469

    def __init__(self, seed: int | None=None):
        if seed is None:
            seed = self.DEFAULT_SEED
        self.value = seed & 4294967295

    def srand(self, seed: int) -> None:
        self.value = seed & 4294967295

    def next(self) -> int:
        self.value = self.value * self.MULTIPLIER & 4294967295
        return self.value >> 16 & 65535

    def get_seed(self) -> int:
        return self.value
