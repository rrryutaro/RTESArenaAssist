from __future__ import annotations
from typing import NamedTuple, Optional
CAMP_BLOCK_OFFSET = 18740
CAMP_BLOCK_LEN = 128
CURRENT_TEXT_PTR_OFFSET = 43076
CAMP_HOURS_ECHO_OFFSET = 18816
CAMP_HOURS_TEMPLATE_OFFSET = 18820
CAMP_INPUT_SLOT_OFFSET = 64184
CAMP_RESPONSE_OFFSET = 37534
CAMP_RESPONSE_READ_LEN = 64
POPUP_FRAME_LEFT_OFFSET = 36724
POPUP_FRAME_RIGHT_OFFSET = 36726
POPUP_FRAME_TOP_OFFSET = 36728
POPUP_FRAME_BOTTOM_OFFSET = 36730
SCREEN_FRAME_RIGHT = 308
SCREEN_FRAME_BOTTOM = 199
MENU_RELEASE_FULLSCREEN_POLLS = 3
CAMP_CONFIRM_OFFSET = 4164
CAMP_CONFIRM_READ_LEN = 96
CAMP_CONFIRM_MARKER = 'remaining hours'
CAMP_BLOCK_SPAN = (CAMP_BLOCK_OFFSET, CAMP_BLOCK_OFFSET + CAMP_BLOCK_LEN)
CAMP_TITLE_TEXT = 'CAMP OPTIONS'
CAMP_MENU_ITEM_TEXTS = ('Camp for a while...', 'Until fully  healed')
CAMP_MENU_ITEM_HOTKEYS = ('C', 'U')
CAMP_HOURS_PROMPT_TEXT = 'How many hours do you wish to rest?'

class CampMenuItem(NamedTuple):
    text: str
    start: int
    end: int
    hotkey: str

class CampView(NamedTuple):
    kind: str
    title: str = ''
    items: tuple = ()
    prompt_text: str = ''
    reason: str = ''
    menu_release_streak: int = 0

def _norm(text: str) -> str:
    return ' '.join((text or '').split())

def _parse_camp_records(raw: bytes, base_offset: int) -> list[CampMenuItem]:
    records: list[CampMenuItem] = []
    n = len(raw)
    i = 0
    while i + 3 < n:
        if not (raw[i] == 9 and raw[i + 1] == 192):
            i += 1
            continue
        start = i
        first_b = raw[i + 2]
        first_char = chr(first_b) if 32 <= first_b <= 126 else ''
        j = i + 3
        if j + 1 < n and raw[j] == 9 and (raw[j + 1] == 212):
            j += 2
        chars: list[str] = []
        while j < n and raw[j] not in (0, 13):
            if 32 <= raw[j] <= 126:
                chars.append(chr(raw[j]))
            j += 1
        while j < n and raw[j] in (0, 13):
            j += 1
        text = (first_char + ''.join(chars)).strip()
        if text:
            records.append(CampMenuItem(text=text, start=base_offset + start, end=base_offset + j, hotkey=first_char.strip()))
        i = j
    return records

def _read_u16(analyzer, anchor: int, off: int) -> Optional[int]:
    try:
        b = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if not b or len(b) < 2:
        return None
    return b[0] | b[1] << 8

def _read_text(analyzer, anchor: int, off: int, length: int) -> str:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError):
        return ''
    if not raw:
        return ''
    nul = raw.find(b'\x00')
    end = nul if nul != -1 else len(raw)
    return raw[:end].decode('ascii', errors='replace')

def _read_u8(analyzer, anchor: int, off: int) -> Optional[int]:
    try:
        b = analyzer.read_bytes(anchor + off, 1)
    except (OSError, AttributeError):
        return None
    return b[0] if b else None

def _read_confirm_text(analyzer, anchor: int) -> str:
    try:
        raw = analyzer.read_bytes(anchor + CAMP_CONFIRM_OFFSET, CAMP_CONFIRM_READ_LEN)
    except (OSError, AttributeError):
        return ''
    if not raw:
        return ''
    nul = raw.find(b'\x00')
    if nul != -1:
        raw = raw[:nul]
    lines: list[str] = []
    for part in raw.split(b'\r'):
        cleaned = ''.join((chr(c) for c in part if 32 <= c <= 126 and c != 96)).strip()
        if cleaned:
            lines.append(cleaned)
    return ' '.join(lines)

def ptr_in_camp_block(ptr: Optional[int]) -> bool:
    if ptr is None:
        return False
    lo, hi = CAMP_BLOCK_SPAN
    return lo <= ptr < hi

def _popup_frame_shown(analyzer, anchor: int) -> bool:
    left = _read_u16(analyzer, anchor, POPUP_FRAME_LEFT_OFFSET)
    right = _read_u16(analyzer, anchor, POPUP_FRAME_RIGHT_OFFSET)
    top = _read_u16(analyzer, anchor, POPUP_FRAME_TOP_OFFSET)
    bottom = _read_u16(analyzer, anchor, POPUP_FRAME_BOTTOM_OFFSET)
    if None in (left, right, top, bottom):
        return False
    if not 0 < left < right <= SCREEN_FRAME_RIGHT:
        return False
    if not 0 < top < bottom <= SCREEN_FRAME_BOTTOM:
        return False
    return right < SCREEN_FRAME_RIGHT or bottom < SCREEN_FRAME_BOTTOM

def _popup_frame_fullscreen(analyzer, anchor: int) -> bool:
    left = _read_u16(analyzer, anchor, POPUP_FRAME_LEFT_OFFSET)
    right = _read_u16(analyzer, anchor, POPUP_FRAME_RIGHT_OFFSET)
    top = _read_u16(analyzer, anchor, POPUP_FRAME_TOP_OFFSET)
    bottom = _read_u16(analyzer, anchor, POPUP_FRAME_BOTTOM_OFFSET)
    return left == 0 and right == SCREEN_FRAME_RIGHT and (top == 0) and (bottom == SCREEN_FRAME_BOTTOM)

def _confirm_record_live(analyzer, anchor: int) -> bool:
    try:
        head = analyzer.read_bytes(anchor + CAMP_CONFIRM_OFFSET, 2)
    except (OSError, AttributeError):
        return False
    return bool(head) and len(head) >= 2 and (head[0] == 9) and (head[1] == 96)

def classify_camp_view(analyzer, anchor: int, *, menu_release_streak: int=0) -> CampView:
    try:
        raw = analyzer.read_bytes(anchor + CAMP_BLOCK_OFFSET, CAMP_BLOCK_LEN)
    except (OSError, AttributeError):
        return CampView(kind='none', reason='block read failed')
    if not raw or len(raw) < 80:
        return CampView(kind='none', reason='block too short')
    records = _parse_camp_records(raw, CAMP_BLOCK_OFFSET)
    if not records or records[0].text != CAMP_TITLE_TEXT:
        return CampView(kind='none', reason='title mismatch')
    items = tuple((r for r in records[1:3]))
    if len(items) < 2 or tuple((r.text for r in items)) != CAMP_MENU_ITEM_TEXTS or tuple((r.hotkey for r in items)) != CAMP_MENU_ITEM_HOTKEYS:
        return CampView(kind='none', reason='items mismatch')
    tmpl = _norm(_read_text(analyzer, anchor, CAMP_HOURS_TEMPLATE_OFFSET, CAMP_RESPONSE_READ_LEN))
    if tmpl != CAMP_HOURS_PROMPT_TEXT:
        return CampView(kind='none', reason='hours template mismatch')
    ptr = _read_u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET)
    _released_streak = 0
    if ptr is not None and any((it.start <= ptr < it.end for it in items)):
        if not _popup_frame_fullscreen(analyzer, anchor):
            return CampView(kind='menu', title=CAMP_TITLE_TEXT, items=items, reason=f'ptr=0x{ptr:04X} in camp item span')
        streak = min(max(int(menu_release_streak), 0) + 1, MENU_RELEASE_FULLSCREEN_POLLS)
        if streak < MENU_RELEASE_FULLSCREEN_POLLS:
            return CampView(kind='menu', title=CAMP_TITLE_TEXT, items=items, menu_release_streak=streak, reason=f'ptr=0x{ptr:04X} in span, fullscreen frame x{streak} (grace)')
        _released_streak = streak
    resp = _norm(_read_text(analyzer, anchor, CAMP_RESPONSE_OFFSET, CAMP_RESPONSE_READ_LEN))
    slot = _read_u16(analyzer, anchor, CAMP_INPUT_SLOT_OFFSET)
    if resp == CAMP_HOURS_PROMPT_TEXT and slot == CAMP_HOURS_ECHO_OFFSET:
        return CampView(kind='hours_prompt', title=CAMP_TITLE_TEXT, items=items, prompt_text=resp, reason='response matches hours prompt + input slot on echo')
    if _popup_frame_shown(analyzer, anchor) and _confirm_record_live(analyzer, anchor):
        confirm = _read_confirm_text(analyzer, anchor)
        if CAMP_CONFIRM_MARKER in confirm:
            left = _read_u16(analyzer, anchor, POPUP_FRAME_LEFT_OFFSET)
            return CampView(kind='rest_confirm', title=CAMP_TITLE_TEXT, items=items, prompt_text=confirm, reason=f'popup frame (left={left}) + confirm text')
    if _released_streak:
        return CampView(kind='none', menu_release_streak=_released_streak, reason=f'menu released: stale ptr=0x{ptr:04X} + fullscreen frame x{_released_streak}')
    return CampView(kind='none', reason='no camp foreground signal')
__all__ = ['CAMP_BLOCK_OFFSET', 'CAMP_BLOCK_LEN', 'CAMP_BLOCK_SPAN', 'CAMP_HOURS_ECHO_OFFSET', 'CAMP_HOURS_TEMPLATE_OFFSET', 'CAMP_INPUT_SLOT_OFFSET', 'CAMP_RESPONSE_OFFSET', 'CAMP_TITLE_TEXT', 'CAMP_MENU_ITEM_TEXTS', 'CAMP_MENU_ITEM_HOTKEYS', 'CAMP_HOURS_PROMPT_TEXT', 'MENU_RELEASE_FULLSCREEN_POLLS', 'CampMenuItem', 'CampView', 'classify_camp_view', 'ptr_in_camp_block']
