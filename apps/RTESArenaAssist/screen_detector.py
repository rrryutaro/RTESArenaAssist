from __future__ import annotations
from typing import Optional, Tuple
import threading
import time
import i18n_helper as _i18n
FLAG_STATUS_POPUP_OFFSET = 4794
FLAG_EQUIPMENT_OPEN_OFFSET = 4762
FLAG_SPELL_DETAIL_OFFSET = 6890
SPELL_INDEX_OFFSET = 4758
SPELL_DETAIL_ACTIVE_OFFSET = 37790
SCREEN_BUFFER_OFFSET = 84288
SCREEN_ROW_BYTES = 320
SCREEN_ROWS = 200
PALETTE_OFFSET = 3089872
PALETTE_BYTES = 256 * 3
PALETTE_IS_VGA_6BIT = True
ACTION_TEXT_ROW_FIRST = 20
ACTION_TEXT_ROW_LAST = 28
ACTION_TEXT_RGB = (195, 0, 0)
SPELL_VIEW_OFFSET = 36718
MENU_ACTIVE_OFFSET = 4732
POPUP_OPEN_OFFSET = 31012
CITY_NPC_ACTIVE_OFFSET = 43077
ACTION_ACTIVE_OFFSET = 31145
SCREEN_IDS: frozenset = frozenset({'quote', 'scroll01', 'scroll02', 'menu', 'loadsave', 'newgame_intro', 'race_select', 'race_confirm', 'race_description', 'status_proclamation', 'class_select', 'class_list', 'class_accept', 'ten_questions', 'province_confirm', 'class_advice', 'goyenow', 'distribute', 'choose_attrs', 'name_input', 'sex_select', 'appearance', 'chargen_complete', 'opening_cinematic', 'game_screen', 'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail', 'system_menu', 'loadsave_in_play', 'automap', 'logbook', 'npc_dialog', 'combat', 'shop', 'travel_map', 'message_box', 'loading', 'unknown'})

def _tr(sid: str, **kwargs) -> str:
    return _i18n.tr(f'screen.{sid}', **kwargs)

def _read_u8(analyzer, addr: int) -> int:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return 0

def read_screen_row(analyzer, anchor: int, row: int=0) -> bytes | None:
    try:
        return analyzer.read_bytes(anchor + SCREEN_BUFFER_OFFSET + row * SCREEN_ROW_BYTES, SCREEN_ROW_BYTES)
    except (OSError, AttributeError):
        return None

def is_spell_detail_drawn(analyzer, anchor: int) -> bool | None:
    row = read_screen_row(analyzer, anchor, 0)
    if row is None or len(row) < SCREEN_ROW_BYTES:
        return None
    return 0 in row
POPUP_FRAME_OFFSET = 36724
POPUP_FRAME_FULLSCREEN = (0, 308, 0, 199)
POPUP_FRAME_ABSENT_POLLS_TO_END = 3

def read_popup_frame(analyzer, anchor: int) -> tuple[int, int, int, int] | None:
    try:
        raw = analyzer.read_bytes(anchor + POPUP_FRAME_OFFSET, 8)
    except (OSError, AttributeError):
        return None
    if raw is None or len(raw) < 8:
        return None
    return (raw[0] | raw[1] << 8, raw[2] | raw[3] << 8, raw[4] | raw[5] << 8, raw[6] | raw[7] << 8)

def popup_frame_is_drawn(frame: tuple[int, int, int, int] | None) -> bool | None:
    if frame is None:
        return None
    if frame == POPUP_FRAME_FULLSCREEN:
        return False
    left, right, top, bottom = frame
    _, full_right, _, full_bottom = POPUP_FRAME_FULLSCREEN
    if not 0 < left < right <= full_right:
        return None
    if not 0 < top < bottom <= full_bottom:
        return None
    return right < full_right or bottom < full_bottom

def is_popup_frame_drawn(analyzer, anchor: int) -> bool | None:
    return popup_frame_is_drawn(read_popup_frame(analyzer, anchor))

def read_palette(analyzer, anchor: int) -> bytes | None:
    try:
        raw = analyzer.read_bytes(anchor + PALETTE_OFFSET, PALETTE_BYTES)
    except (OSError, AttributeError, RuntimeError):
        return None
    if len(raw) < PALETTE_BYTES:
        return None
    if not PALETTE_IS_VGA_6BIT:
        return bytes(raw)
    return bytes(((v << 2 | v >> 4) & 255 for v in raw))

def resolve_action_text_color_index(analyzer, anchor: int) -> int | None:
    pal = read_palette(analyzer, anchor)
    if pal is None:
        return None
    want = bytes(ACTION_TEXT_RGB)
    for index in range(256):
        if pal[index * 3:index * 3 + 3] == want:
            return index
    return None
_DISPLAY_KEY_ROW_FIRST = 170
_DISPLAY_KEY_ROWS = 10
_DISPLAY_SCAN_RANGE = (65536, 2147418112)

def _read_display_key(analyzer, comp_base: int) -> bytes | None:
    key_len = _DISPLAY_KEY_ROWS * SCREEN_ROW_BYTES
    try:
        key = analyzer.read_bytes(comp_base + _DISPLAY_KEY_ROW_FIRST * SCREEN_ROW_BYTES, key_len)
    except (OSError, AttributeError, RuntimeError):
        return None
    if not key or len(key) < key_len or len(set(key)) < 8:
        return None
    return bytes(key)

def resolve_display_buffer(analyzer, anchor: int) -> int | None:
    if analyzer is None or not anchor:
        return None
    comp_base = anchor + SCREEN_BUFFER_OFFSET
    key = _read_display_key(analyzer, comp_base)
    if key is None:
        return None
    key_off = _DISPLAY_KEY_ROW_FIRST * SCREEN_ROW_BYTES
    frame_len = SCREEN_ROWS * SCREEN_ROW_BYTES
    try:
        regions = analyzer._enum_readable_regions(*_DISPLAY_SCAN_RANGE)
    except (OSError, AttributeError, RuntimeError):
        return None
    for base, size in regions:
        if size < frame_len:
            continue
        try:
            buf = analyzer.read_bytes(base, size)
        except (OSError, AttributeError, RuntimeError):
            continue
        if not buf:
            continue
        pos = buf.find(key)
        while pos >= 0:
            start = pos - key_off
            if start >= 0 and start + frame_len <= len(buf) and (base + start != comp_base):
                return base + start
            pos = buf.find(key, pos + 1)
    return None

def display_buffer_matches(analyzer, anchor: int, base: int) -> bool | None:
    if analyzer is None or not anchor:
        return None
    key = _read_display_key(analyzer, anchor + SCREEN_BUFFER_OFFSET)
    if key is None:
        return None
    try:
        got = analyzer.read_bytes(base + _DISPLAY_KEY_ROW_FIRST * SCREEN_ROW_BYTES, len(key))
    except (OSError, AttributeError, RuntimeError):
        return False
    return bool(got) and bytes(got) == key

def action_text_full_band_addr(screen_base: int) -> tuple[int, int]:
    rows = ACTION_TEXT_ROW_LAST - ACTION_TEXT_ROW_FIRST + 1
    return (screen_base + ACTION_TEXT_ROW_FIRST * SCREEN_ROW_BYTES, rows * SCREEN_ROW_BYTES)

def action_text_ink_rows(block: bytes, color: int) -> tuple[tuple[int, ...], ...]:
    rows = ACTION_TEXT_ROW_LAST - ACTION_TEXT_ROW_FIRST + 1
    out = []
    for r in range(rows):
        seg = block[r * SCREEN_ROW_BYTES:(r + 1) * SCREEN_ROW_BYTES]
        out.append(tuple((c for c, v in enumerate(seg) if v == color)))
    return tuple(out)

def _read_u16_le(analyzer, addr: int) -> int:
    try:
        b = analyzer.read_bytes(addr, 2)
        return b[0] | b[1] << 8
    except (OSError, AttributeError):
        return 65535
_CITY_NPC_PHASE_ASKING = 133
_CITY_NPC_PHASE_RESPONDING = 16

def is_city_npc_dialog_active(raw_value: int) -> bool:
    return int(raw_value) & 255 in (_CITY_NPC_PHASE_ASKING, _CITY_NPC_PHASE_RESPONDING)

def _detect_pregame_screen(img_name: str) -> Optional[Tuple[str, str]]:
    img_upper = (img_name or '').upper()
    if img_upper.endswith('.XMI'):
        return ('loading', _tr('loading'))
    if img_upper == 'QUOTE.IMG':
        return ('quote', _tr('quote'))
    if img_upper == 'SCROLL01.IMG':
        return ('scroll01', _tr('scroll01'))
    if img_upper == 'SCROLL02.IMG':
        return ('scroll02', _tr('scroll02'))
    if img_upper == 'MENU.IMG':
        return ('menu', _tr('menu'))
    if img_upper == 'LOADSAVE.IMG':
        return ('loadsave', _tr('loadsave'))
    return None

def detect_screen(analyzer, anchor: Optional[int], img_name: str, chargen_hint: Optional[str]=None, menu_active_was_zero: bool=False, top_level_state: str='pregame', last_chargen_subscreen: Optional[str]=None, mif_name: str='', area: Optional[str]=None, foreground_ptr: Optional[int]=None, trigger_display_active: bool=False) -> Tuple[str, str]:
    from screen_detector_chargen import detect_chargen_screen
    from screen_detector_play import detect_play_screen
    if analyzer is None or anchor is None:
        return ('loading', _tr('loading'))
    if top_level_state == 'pregame':
        result = _detect_pregame_screen(img_name)
        return result if result is not None else ('loading', _tr('loading'))
    elif top_level_state == 'chargen':
        result = detect_chargen_screen(chargen_hint, img_name, last_subscreen=last_chargen_subscreen)
        if result is not None:
            return result
        fallback = last_chargen_subscreen or 'loading'
        return (fallback, _tr(fallback))
    else:
        return detect_play_screen(analyzer, anchor, img_name, mif_name=mif_name, menu_active_was_zero=menu_active_was_zero, area=area, foreground_ptr=foreground_ptr, trigger_display_active=trigger_display_active)

def get_chargen_subscreen(window) -> Optional[str]:
    if getattr(window, '_chargen_opening_displayed', False):
        return 'opening_cinematic'
    if getattr(window, '_chargen_sex_select_displayed', False):
        return 'sex_select'
    if getattr(window, '_in_chargen_name', False):
        return 'name_input'
    if getattr(window, '_chargen_appearance_displayed', False):
        return 'appearance'
    if getattr(window, '_chargen_choose_attrs_displayed', False):
        return 'choose_attrs'
    if getattr(window, '_chargen_distribute_displayed', False):
        return 'distribute'
    if getattr(window, '_chargen_goyenow_displayed', False):
        return 'goyenow'
    if getattr(window, '_chargen_in_advice', False):
        return 'class_advice'
    if getattr(window, '_chargen_race_desc_displayed', False):
        return 'race_description'
    if getattr(window, '_chargen_complete_displayed', False):
        return 'status_proclamation'
    if getattr(window, '_chargen_race_select_displayed', False):
        return 'race_select'
    if getattr(window, '_chargen_class_accept_displayed', False):
        return 'class_accept'
    if getattr(window, '_chargen_10q_displayed', False):
        return 'ten_questions'
    if getattr(window, '_chargen_class_list_active', False):
        return 'class_list'
    if getattr(window, '_chargen_method_window', False):
        return 'class_select'
    return None
