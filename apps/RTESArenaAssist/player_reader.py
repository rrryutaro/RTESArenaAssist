"""player_reader.py — Player struct メモリ読み取り。

確定オフセット (anchor 相対):
    +0x1AA  (u8)      : Level - 1（実 Level = 値 + 1）
    +0x5AD  (u32 LE)  : Experience
    +0x129C (u8)      : BONUS PTS（ステータス画面表示中のみ有意・他はゴミ値）
    +0xA845 (u8)      : ダイアログ表示中フラグ（別ハンドラ）

レベルアップ全工程の検出材料を提供する。
"""
from __future__ import annotations

LEVEL_OFFSET      = 0x01AA
EXPERIENCE_OFFSET = 0x05AD
BONUS_PTS_OFFSET  = 0x129C


def read_level(analyzer, anchor: int) -> int | None:
    """表示 Level (1-based) を返す。読み取り失敗時は None。

    内部値は Level - 1 で格納されているため +1 して返す。
    """
    try:
        b = analyzer.read_bytes(anchor + LEVEL_OFFSET, 1)[0]
        return b + 1
    except (OSError, AttributeError):
        return None


def read_experience(analyzer, anchor: int) -> int | None:
    """Experience (u32 LE) を返す。"""
    try:
        raw = analyzer.read_bytes(anchor + EXPERIENCE_OFFSET, 4)
        return int.from_bytes(raw, "little")
    except (OSError, AttributeError):
        return None


def read_bonus_pts(analyzer, anchor: int) -> int | None:
    """BONUS PTS (u8) を返す。

    ステータス系画面（PAGE2.IMG / CHARSTAT.IMG）表示中以外はゴミ値
    （戦闘カウンタ等として使い回される）。呼び出し側で
    screen_id ∈ {'status_page', 'bonus_screen'} を必ず確認すること。

    + flag_status (+0x12BA) == 1 の間のみ真値。
    """
    try:
        return analyzer.read_bytes(anchor + BONUS_PTS_OFFSET, 1)[0]
    except (OSError, AttributeError):
        return None


def read_all(analyzer, anchor: int) -> dict:
    """Level / Experience / BONUS PTS を一度に読む。"""
    return {
        "level":      read_level(analyzer, anchor),
        "experience": read_experience(analyzer, anchor),
        "bonus_pts":  read_bonus_pts(analyzer, anchor),
    }
