from __future__ import annotations
import logging
from dataclasses import dataclass
from active_template_reader import TEMPLATE_RANGE_HIGH, TEMPLATE_RANGE_LOW, is_dialog_text_pointer
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
CURRENT_TEXT_PTR_OFFSET = 43076
A84D_OFFSET = 43085
DLGFLG_VALUE = 64
AREA_NPC_DIALOG = 'npc_dialog'
AREA_RUNTIME_MSG = 'runtime_msg'
AREA_GOLD = 'gold'
AREA_MSG_BUF = 'msg_buf'
AREA_STATIC = 'static'

@dataclass(frozen=True)
class DialogTextArea:
    name: str
    start: int
    length: int
    close_confirmed: bool

    def contains(self, ptr: int | None) -> bool:
        return ptr is not None and self.start <= ptr < self.start + self.length
C1_DIALOG_TEXT_AREAS: tuple[DialogTextArea, ...] = (DialogTextArea(AREA_NPC_DIALOG, 4164, 512, close_confirmed=True), DialogTextArea(AREA_RUNTIME_MSG, 31097, 68, close_confirmed=True), DialogTextArea(AREA_GOLD, 37534, 512, close_confirmed=False), DialogTextArea(AREA_MSG_BUF, 39582, 512, close_confirmed=True), DialogTextArea(AREA_STATIC, TEMPLATE_RANGE_LOW, TEMPLATE_RANGE_HIGH - TEMPLATE_RANGE_LOW, close_confirmed=False))
_AREAS_BY_NAME = {a.name: a for a in C1_DIALOG_TEXT_AREAS}

def area_of(ptr: int | None) -> str:
    for area in C1_DIALOG_TEXT_AREAS:
        if area.contains(ptr):
            return area.name
    return ''

def close_confirmed(area: str) -> bool:
    found = _AREAS_BY_NAME.get(area)
    return bool(found is not None and found.close_confirmed)

@dataclass(frozen=True)
class C1DialogAxis:
    active: bool
    prev_active: bool
    opened: bool
    closed: bool
    current_ptr: int | None
    area: str
    a84d: int

    @property
    def a845(self) -> int:
        return (self.current_ptr or 0) >> 8 & 255

    @property
    def dlgflg(self) -> bool:
        return self.a84d == DLGFLG_VALUE

def _read_u8(w, offset: int) -> int:
    try:
        return w._analyzer.read_bytes(w._anchor + offset, 1)[0]
    except (OSError, AttributeError, TypeError, IndexError):
        return 0

def read_c1_dialog_axis(w, *, ptr: int | None, c_area: str | None, in_gameplay: bool=True, update_prev: bool=False) -> C1DialogAxis:
    a84d = _read_u8(w, A84D_OFFSET)
    area = area_of(ptr)
    in_c1 = c_area == 'dungeon'
    active = in_c1 and in_gameplay and is_dialog_text_pointer(ptr)
    prev_active = bool(getattr(w, '_c1_dialog_axis_active_prev', False))
    opened = active and (not prev_active)
    closed = prev_active and (not active)
    if update_prev:
        w._c1_dialog_axis_active_prev = active
        if opened or closed:
            _recog(_log, 'c1 dialog axis %s: ptr=%s area=%s a84d=0x%02X', 'opened' if opened else 'closed', '0x%04X' % ptr if ptr is not None else 'n/a', area or '-', a84d)
    return C1DialogAxis(active=active, prev_active=prev_active, opened=opened, closed=closed, current_ptr=ptr, area=area, a84d=a84d)

def release_c1_dialog_axis(w) -> None:
    w._c1_dialog_axis_active_prev = False
__all__ = ['A84D_OFFSET', 'AREA_GOLD', 'AREA_MSG_BUF', 'AREA_NPC_DIALOG', 'AREA_RUNTIME_MSG', 'AREA_STATIC', 'C1DialogAxis', 'C1_DIALOG_TEXT_AREAS', 'CURRENT_TEXT_PTR_OFFSET', 'DLGFLG_VALUE', 'DialogTextArea', 'area_of', 'close_confirmed', 'read_c1_dialog_axis', 'release_c1_dialog_axis']
