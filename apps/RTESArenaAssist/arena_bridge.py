
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
    return analyzer.read_bytes(anchor + ASK_ABOUT_MENU_OFFSET, ASK_ABOUT_MENU_LEN)


def read_npc_phase(analyzer: "ArenaMemoryAnalyzer", anchor: int) -> int | None:
    try:
        return analyzer.read_bytes(anchor + NPC_PHASE_OFFSET, 1)[0]
    except OSError:
        return None


def read_interior_flag(analyzer: "ArenaMemoryAnalyzer", anchor: int) -> int | None:
    try:
        return analyzer.read_bytes(anchor + INTERIOR_FLAG_OFFSET, 1)[0]
    except OSError:
        return None


def is_in_interior(value: int | None) -> bool:
    return value is not None and value != 0


__all__ = [
    "ArenaMemoryAnalyzer",
    "find_anchor",
    "read_game_state",
    "interpret_location",
    "check_trigger_flag",
    "MifTriggerMatcher",
    "get_trigger_text_by_index",
    "extract_trigger_texts",
    "read_live_buffer",
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
    "NPC_PHASE_OFFSET",
    "NPC_PHASE_IDLE",
    "NPC_PHASE_ASKING",
    "NPC_PHASE_RESPONDING",
    "NPC_PHASE_BUILDING_ENTRY",
    "read_npc_phase",
    "INTERIOR_FLAG_OFFSET",
    "read_interior_flag",
    "is_in_interior",
    "ASK_ABOUT_MENU_OFFSET",
    "ASK_ABOUT_MENU_LEN",
    "read_ask_about_menu",
    "JOURNAL_BUFFER_OFFSET",
    "JOURNAL_BUFFER_MAXLEN",
]
