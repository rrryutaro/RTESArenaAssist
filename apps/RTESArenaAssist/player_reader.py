from __future__ import annotations

LEVEL_OFFSET      = 0x01AA
EXPERIENCE_OFFSET = 0x05AD
BONUS_PTS_OFFSET  = 0x129C


def read_level(analyzer, anchor: int) -> int | None:
    try:
        b = analyzer.read_bytes(anchor + LEVEL_OFFSET, 1)[0]
        return b + 1
    except (OSError, AttributeError):
        return None


def read_experience(analyzer, anchor: int) -> int | None:
    try:
        raw = analyzer.read_bytes(anchor + EXPERIENCE_OFFSET, 4)
        return int.from_bytes(raw, "little")
    except (OSError, AttributeError):
        return None


def read_bonus_pts(analyzer, anchor: int) -> int | None:
    try:
        return analyzer.read_bytes(anchor + BONUS_PTS_OFFSET, 1)[0]
    except (OSError, AttributeError):
        return None


def read_all(analyzer, anchor: int) -> dict:
    return {
        "level":      read_level(analyzer, anchor),
        "experience": read_experience(analyzer, anchor),
        "bonus_pts":  read_bonus_pts(analyzer, anchor),
    }
