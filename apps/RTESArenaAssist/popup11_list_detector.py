from __future__ import annotations
import logging
from typing import Optional
_log = logging.getLogger(__name__)
_LAST_STATE_LOG: dict = {}
POPUP11_ITEM_COUNT_OFFSET = 20779
POPUP11_LIST_PTR_OFFSET = 20775
POPUP11_DYN_COUNT_OFFSET = 43104
ASK_ABOUT_ACTIVE_OFFSET = 43079
ASK_ABOUT_CURRENT_PTR = 43076
ASK_ABOUT_STATE_OFFSET = 43088
ASK_ABOUT_MAIN_FLAG_OFFSET = 43096
NPC_RESPONSE_BUFFER_PTR = 4164
MENU_TEMPLATE_RANGE = (32768, 36864)
ASK_ABOUT_MAIN_STATE_VALUE = 159
ASK_ABOUT_MAIN_FLAG_VALUE = 175
_LIST_PTR_RANGE = (32768, 45056)
_MAX_LIST_ITEM_BYTES = 64

def _read_u8(analyzer, addr: int) -> Optional[int]:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return None

def _read_u16(analyzer, addr: int) -> Optional[int]:
    try:
        raw = analyzer.read_bytes(addr, 2)
        if len(raw) < 2:
            return None
        return raw[0] | raw[1] << 8
    except (OSError, AttributeError, IndexError):
        return None

def _read_first_nul_ascii(analyzer, addr: int) -> str:
    try:
        raw = analyzer.read_bytes(addr, _MAX_LIST_ITEM_BYTES)
    except (OSError, AttributeError):
        return ''
    nul = raw.find(b'\x00')
    if nul < 0:
        return ''
    text = raw[:nul].decode('ascii', errors='ignore').strip()
    if not text or any((ord(ch) < 32 or ord(ch) > 126 for ch in text)):
        return ''
    return text

def _has_popup11_list_payload(analyzer, anchor: int, item_count: int) -> bool:
    if item_count <= 0:
        return False
    ptr = _read_u16(analyzer, anchor + POPUP11_LIST_PTR_OFFSET)
    if ptr is None:
        return False
    lo, hi = _LIST_PTR_RANGE
    if not lo <= ptr < hi:
        return False
    return bool(_read_first_nul_ascii(analyzer, anchor + ptr))

def _is_ask_about_menu_box_drawn(frame) -> bool | None:
    from screen_detector import popup_frame_is_drawn
    return popup_frame_is_drawn(frame)

def _decode_arena_menu_item(raw: bytes) -> str:
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 192 and i + 1 < n:
            ch = raw[i + 1]
            if 32 <= ch <= 126:
                out.append(chr(ch))
            i += 2
            continue
        if b == 212 and i + 1 < n:
            j = i + 1
            while j < n and raw[j] != 0:
                cj = raw[j]
                if 32 <= cj <= 126:
                    out.append(chr(cj))
                else:
                    break
                j += 1
            return ''.join(out).strip()
        i += 1
    return ''.join(out).strip()

def read_active_menu_marker(analyzer, anchor: int) -> str:
    try:
        ptr_raw = analyzer.read_bytes(anchor + ASK_ABOUT_CURRENT_PTR, 2)
        if len(ptr_raw) < 2:
            _log_marker_once('ptr_raw_short', None, None, b'')
            return ''
        ptr = ptr_raw[0] | ptr_raw[1] << 8
        if ptr == NPC_RESPONSE_BUFFER_PTR:
            _log_marker_once('response_ptr', ptr, None, b'')
            return ''
        lo, hi = MENU_TEMPLATE_RANGE
        if not lo <= ptr < hi:
            _log_marker_once('ptr_out_of_range', ptr, None, b'')
            return ''
        raw = analyzer.read_bytes(anchor + ptr, 16)
    except (OSError, AttributeError, IndexError) as exc:
        _log_marker_once('read_error', None, None, b'')
        return ''
    decoded = _decode_arena_menu_item(raw)
    _log_marker_once('ok', ptr, decoded, raw)
    return decoded

def _log_marker_once(reason: str, ptr, decoded, raw: bytes) -> None:
    key = (reason, ptr, decoded, bytes(raw[:8]))
    if _LAST_STATE_LOG.get('marker') == key:
        return
    _LAST_STATE_LOG['marker'] = key
    if reason == 'ok':
        _log.info('read_active_menu_marker: ptr=0x%04X raw=%s decoded=%r', ptr or 0, raw.hex(' '), decoded)
    else:
        _log.info('read_active_menu_marker: %s ptr=%s', reason, f'0x{ptr:04X}' if ptr is not None else '?')

def is_ask_about_main_foreground(analyzer, anchor: int, marker: str | None=None) -> bool:
    if marker is not None and marker != 'Exit':
        return False
    state = _read_u8(analyzer, anchor + ASK_ABOUT_STATE_OFFSET)
    main_flag = _read_u8(analyzer, anchor + ASK_ABOUT_MAIN_FLAG_OFFSET)
    return state == ASK_ABOUT_MAIN_STATE_VALUE and main_flag == ASK_ABOUT_MAIN_FLAG_VALUE

def detect_popup11_list_state(analyzer, anchor: int) -> str:
    item_count = _read_u8(analyzer, anchor + POPUP11_ITEM_COUNT_OFFSET)
    dyn_count = _read_u8(analyzer, anchor + POPUP11_DYN_COUNT_OFFSET)
    if item_count is None or dyn_count is None:
        return 'undecided'
    from screen_detector import read_popup_frame
    sub_marker = read_active_menu_marker(analyzer, anchor)
    frame = read_popup_frame(analyzer, anchor)
    menu_box = _is_ask_about_menu_box_drawn(frame)
    if sub_marker == 'Work':
        result = 'rumor_type'
    elif sub_marker != 'Exit':
        result = 'npc_response'
    elif menu_box is None:
        result = 'undecided'
    elif menu_box:
        result = 'ask_about_main'
    elif dyn_count > 0 and dyn_count == item_count:
        result = 'dynamic_place_list'
    elif item_count > 0:
        result = 'where_is_list'
    else:
        result = 'npc_response'
    key = (item_count, dyn_count, sub_marker, frame, result)
    if _LAST_STATE_LOG.get('key') != key:
        _LAST_STATE_LOG['key'] = key
        _log.info('detect_popup11_list_state: item_count=%d dyn_count=%d sub_marker=%r frame=%s -> %s', item_count, dyn_count, sub_marker, frame, result)
    return result
