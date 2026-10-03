from __future__ import annotations
import logging
import i18n_helper as i18n
from assist_log import recog as _recog
from inventory_reader import read_artifact_names
from panel_mode_resolver import SCREEN_PANEL_PRIORITY
from screen_detector import SCREEN_BUFFER_OFFSET, SCREEN_ROW_BYTES
_log = logging.getLogger('equipment_detail_module')
OWNER = 'equipment_detail'
_HEADER_OFFSET = 4164
_RECT_X0, _RECT_X1 = (45, 275)
_RECT_Y0, _RECT_Y1 = (55, 145)
_MODAL_FLAT_MIN = 0.55

def _is_large_modal(frame_rows: bytes) -> bool:
    height = _RECT_Y1 - _RECT_Y0
    if len(frame_rows) != height * SCREEN_ROW_BYTES:
        return False
    counts = [0] * 256
    for row in range(height):
        begin = row * SCREEN_ROW_BYTES + _RECT_X0
        for color in frame_rows[begin:begin + (_RECT_X1 - _RECT_X0)]:
            counts[color] += 1
    return max(counts) / (height * (_RECT_X1 - _RECT_X0)) >= _MODAL_FLAT_MIN

def read_visible_artifact(w) -> tuple[str, int] | None:
    try:
        rows = w._analyzer.read_bytes(w._anchor + SCREEN_BUFFER_OFFSET + _RECT_Y0 * SCREEN_ROW_BYTES, (_RECT_Y1 - _RECT_Y0) * SCREEN_ROW_BYTES)
        if not _is_large_modal(rows):
            return None
        header = w._analyzer.read_bytes(w._anchor + _HEADER_OFFSET, 96)
        names = read_artifact_names(w._analyzer, w._anchor)
    except (OSError, AttributeError, TypeError):
        return None
    if not isinstance(header, bytes):
        return None
    name = header.split(b'\x00', 1)[0].split(b'\r', 1)[0].split(b'\n', 1)[0].decode('ascii', errors='replace').strip()
    if not name:
        return None
    try:
        return (name, names.index(name))
    except ValueError:
        return None

def poll_equipment_detail(w) -> bool:
    visible = read_visible_artifact(w)
    if visible is None:
        return False
    name, index = visible
    if getattr(w, '_equipment_detail_name', None) == name:
        return True
    key = f'npc_dialog.{505 + index:04d}.0'
    en_body = i18n.original_by_source_id(f'template:{505 + index:04d}:0', category='npc_dialog') or i18n.original(key)
    ja_body = i18n.text_opt(key)
    if not ja_body:
        if getattr(w, '_equipment_detail_missing_key', None) != key:
            _log.warning('artifact description unavailable: %s', key)
            w._equipment_detail_missing_key = key
        return True
    w._equipment_detail_missing_key = None
    from dungeon_msg_lookup import lookup_item
    local_name = lookup_item(name) or name
    w._equipment_detail_name = name
    _recog(_log, 'artifact detail open: name=%r key=%s', name, key)
    w._ui_router.propose_translation(OWNER, f'{name}\n\n{en_body}' if en_body else name, f'{local_name}\n\n{ja_body}', mode='translate', priority=SCREEN_PANEL_PRIORITY + 1, reason='equipment:artifact_detail', speech_role='situation', speech_text=ja_body)
    return True

def reset_equipment_detail(w) -> None:
    previous = getattr(w, '_equipment_detail_name', None)
    if previous is not None:
        _recog(_log, 'artifact detail closed: name=%r', previous)
    w._equipment_detail_name = None
    w._equipment_detail_missing_key = None
__all__ = ['OWNER', 'poll_equipment_detail', 'read_visible_artifact', 'reset_equipment_detail']
