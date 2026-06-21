"""
arena_bridge.py — メモリ読み取りモジュールへのブリッジ

Assist 所有の memory_core / arena_logic / mif_trigger / viewer_constants を
集約 import して Assist 内の各所へ再公開する。これらは Assist 配下に取り込み済み
（旧来は他アプリの実装を sys.path 経由で借用していたが、完全自己完結化した）。
"""

from memory_core import ArenaMemoryAnalyzer
from arena_logic import (find_anchor, read_game_state, interpret_location,
                         check_trigger_flag, read_live_buffer)
from mif_trigger import (MifTriggerMatcher, get_trigger_text_by_index,
                         extract_trigger_texts)
from viewer_constants import (
    TRIGGER_FLAG_OFFSET, TRIGGER_INDEX_OFFSET,
    TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ,
    RT_COORD_X_OFFSET, RT_COORD_Z_OFFSET,
    RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK,
    RT_ANGLE_RANGE, RT_ANGLE_NORTH_RAW,
    NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN,
    CHARGEN_STATE_OFFSET,
    CHARGEN_Q_SEQ_OFFSET, CHARGEN_Q_ARRAY_OFFSET,
    CHARGEN_DONE_OFFSET,
    SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN,
    NPC_PHASE_OFFSET,
    NPC_PHASE_IDLE, NPC_PHASE_ASKING, NPC_PHASE_RESPONDING,
    NPC_PHASE_BUILDING_ENTRY,
    INTERIOR_FLAG_OFFSET,
    JOURNAL_BUFFER_OFFSET, JOURNAL_BUFFER_MAXLEN,
)

ASK_ABOUT_MENU_OFFSET = 0x8525
ASK_ABOUT_MENU_LEN = 768


def read_ask_about_menu(analyzer: "ArenaMemoryAnalyzer", anchor: int) -> bytes:
    """ASK ABOUT? メニューバッファ生バイト列を取得する。"""
    return analyzer.read_bytes(anchor + ASK_ABOUT_MENU_OFFSET, ASK_ABOUT_MENU_LEN)


def read_npc_phase(analyzer: "ArenaMemoryAnalyzer", anchor: int) -> int | None:
    """NPC 会話状態フェーズバイト (anchor+0x0000A845) を読み取る。

    Returns:
        int: NPC_PHASE_IDLE (0x00) / NPC_PHASE_ASKING (0x85) /
             NPC_PHASE_RESPONDING (0x10) / その他 (未知値)
        None: 読み取り失敗時
    """
    try:
        return analyzer.read_bytes(anchor + NPC_PHASE_OFFSET, 1)[0]
    except OSError:
        return None


def read_interior_flag(analyzer: "ArenaMemoryAnalyzer", anchor: int) -> int | None:
    """Interior 在室判定バイト (anchor+0x0000BC8E) を読み取る。

    仮説扱い (強い仮説、IN/OUT のみ有効):
        0      → OUT (街路)
        非0    → IN  (Interior 在室)

    値そのものの意味 (menuType?) は未確定。
    """
    try:
        return analyzer.read_bytes(anchor + INTERIOR_FLAG_OFFSET, 1)[0]
    except OSError:
        return None


def is_in_interior(value: int | None) -> bool:
    """read_interior_flag の値から Interior 在室判定。"""
    return value is not None and value != 0


__all__ = [
    # 既存
    "ArenaMemoryAnalyzer",
    "find_anchor",
    "read_game_state",
    "interpret_location",
    # トリガー検出
    "check_trigger_flag",
    # MIF TRIG 座標照合
    "MifTriggerMatcher",
    "get_trigger_text_by_index",
    "extract_trigger_texts",
    # ライブバッファ読み取り
    "read_live_buffer",
    # オフセット定数
    "TRIGGER_FLAG_OFFSET",
    "TRIGGER_INDEX_OFFSET",
    "TRIGGER_BLOCK_OFFSET",
    "TRIGGER_BLOCK_READ",
    "RT_COORD_X_OFFSET",
    "RT_COORD_Z_OFFSET",
    "RT_ANGLE_OFFSET",
    "RT_ANGLE_BYTE_SIZE",
    "RT_ANGLE_MASK",
    "RT_ANGLE_RANGE",
    "RT_ANGLE_NORTH_RAW",
    "NPC_DIALOG_OFFSET",
    "NPC_DIALOG_MAXLEN",
    "CHARGEN_STATE_OFFSET",
    "CHARGEN_Q_SEQ_OFFSET",
    "CHARGEN_Q_ARRAY_OFFSET",
    "CHARGEN_DONE_OFFSET",
    "SCREEN_IMG_OFFSET",
    "SCREEN_IMG_MAXLEN",
    # NPC 会話状態フェーズバイト
    "NPC_PHASE_OFFSET",
    "NPC_PHASE_IDLE",
    "NPC_PHASE_ASKING",
    "NPC_PHASE_RESPONDING",
    "NPC_PHASE_BUILDING_ENTRY",
    "read_npc_phase",
    # Interior 在室判定 (強い仮説)
    "INTERIOR_FLAG_OFFSET",
    "read_interior_flag",
    "is_in_interior",
    # ASK ABOUT? メニュー
    "ASK_ABOUT_MENU_OFFSET",
    "ASK_ABOUT_MENU_LEN",
    "read_ask_about_menu",
    # ジャーナル render buffer (anchor 相対固定オフセット)
    "JOURNAL_BUFFER_OFFSET",
    "JOURNAL_BUFFER_MAXLEN",
]
