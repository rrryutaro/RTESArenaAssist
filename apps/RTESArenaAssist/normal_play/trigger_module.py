from __future__ import annotations
import logging
from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN, TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ, get_trigger_text_by_index
import inf_text_lookup as itl
import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.c1_cinematic_module import _current_hp_is_zero
_log = logging.getLogger('RTESArenaAssist')
_DEATH_RED_TEXTS = frozenset({'You are dead', 'You have been slain'})

def _entry_to_payload(entry: dict) -> tuple[str, str, str, str]:
    if entry.get('type') == 'riddle':
        en = entry.get('question', '') or ''
        trans = itl.get_translation(entry)
        ja = trans.get('question', '') if isinstance(trans, dict) else ''
        return (en, ja, en, ja)
    en = itl.get_text_display(entry) or ''
    ja_disp = itl.get_translation_display(entry)
    ja = ja_disp if isinstance(ja_disp, str) else ''
    panel_en = itl.get_text_panel(entry) or ''
    panel_ja_raw = itl.get_translation(entry)
    panel_ja = panel_ja_raw if isinstance(panel_ja_raw, str) else ''
    return (en, ja, panel_en, panel_ja)

def _render_trigger_entry(w, entry: dict) -> None:
    try:
        w._set_chargen_ui_state(False)
    except (AttributeError, RuntimeError):
        pass
    en, ja, panel_en, panel_ja = _entry_to_payload(entry)
    _store_last_trigger_display(w, en, ja, panel_en, panel_ja)
    w._ui_router.update_translation('trigger', en, ja, panel_en=panel_en, panel_ja=panel_ja, speech_role='situation')

def _store_last_trigger_display(w, en: str, ja: str, panel_en: str | None=None, panel_ja: str | None=None) -> None:
    w._last_trigger_display = (en, ja, panel_en, panel_ja)
    w._last_trigger_active = True

def restore_last_trigger_display(w) -> bool:
    if not getattr(w, '_last_trigger_active', False):
        return False
    payload = getattr(w, '_last_trigger_display', None)
    if not payload:
        return False
    en, ja, panel_en, panel_ja = payload
    w._ui_router.update_translation('trigger', en, ja, panel_en=panel_en, panel_ja=panel_ja, speech_role='situation')
    return True

def _is_death_red_text(text: str) -> bool:
    return (text or '').strip() in _DEATH_RED_TEXTS
_C1_DIALOG_A845_TO_SLOT = {121: 'runtime_msg', 146: 'corpse_gold', 16: 'dungeon_msg'}
_C1_DIALOG_BUFFER_RANGES = {'runtime_msg': ((31097, 68),), 'corpse_gold': ((37534, 512),), 'dungeon_msg': ((4164, 512), (39582, 512))}

def classify_c1_dialog_substate(w, b30, *, npc_dialog_changed: bool=False) -> str:
    axis = b30.get('c1_dialog_axis') if isinstance(b30, dict) else None
    a845 = getattr(axis, 'a845', 0) if axis is not None else 0
    ptr = getattr(axis, 'current_ptr', None) if axis is not None else None
    slot = _C1_DIALOG_A845_TO_SLOT.get(a845, '')
    if not slot and ptr is not None:
        for name, ranges in _C1_DIALOG_BUFFER_RANGES.items():
            if any((start <= ptr < start + length for start, length in ranges)):
                slot = name
                break
    if npc_dialog_changed and slot != 'corpse_gold':
        return 'c1_runtime_dialog'
    if slot == 'runtime_msg':
        dialog_active = bool(b30.get('dialog_active')) if isinstance(b30, dict) else False
        return 'red_text_dialog' if dialog_active else 'red_text'
    if slot == 'corpse_gold':
        return 'gold_drop'
    if slot == 'dungeon_msg':
        return 'c1_runtime_dialog'
    return ''

def poll_trigger(w, *, new_trigger: bool, trig_fell: bool, trigger_flag: int, trigger_idx: int, trigger_slot: int, body: str, inf_name: str) -> None:
    if trigger_flag != 0:
        w._sb.showMessage(f"Trigger: flag=0x{trigger_flag:02X}  INF={inf_name or '(none)'}  idx={trigger_idx}  slot={trigger_slot}  body={body[:30]}", 4000)
    if new_trigger:
        text_index = None
        correct_body = body
        if w._mif_matcher and w._cached_rt_x is not None and (w._cached_rt_z is not None):
            text_index = w._mif_matcher.find_text_index(w._cached_rt_x, w._cached_rt_z)
            if text_index is not None:
                try:
                    raw_b = w._analyzer.read_bytes(w._anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
                    correct_body = get_trigger_text_by_index(raw_b, text_index)
                except OSError:
                    pass
        if text_index is None and trigger_slot > 0:
            text_index = trigger_slot
        if text_index is not None:
            entry = itl.lookup(inf_name, text_index)
            if entry is not None and entry.get('type') == 'key':
                entry = None
            if entry is None and correct_body:
                entry = itl.lookup_by_text(inf_name, correct_body)
            if entry is None and correct_body and inf_name:
                entry = itl.lookup_by_substring(inf_name, correct_body)
            if entry is not None:
                _render_trigger_entry(w, entry)
            elif correct_body:
                _store_last_trigger_display(w, correct_body, '')
                w._ui_router.update_translation('trigger', correct_body, '', speech_role='situation')
        elif correct_body:
            entry = itl.lookup_by_text(inf_name, correct_body)
            if entry is None and inf_name:
                entry = itl.lookup_by_substring(inf_name, correct_body)
            if entry is not None:
                _render_trigger_entry(w, entry)
            else:
                _store_last_trigger_display(w, correct_body, '')
                w._ui_router.update_translation('trigger', correct_body, '', speech_role='situation')
    if trig_fell and (not settings.get('keep_trigger_on_panel', False)):
        w._last_trigger_active = False
        w._ui_router.clear_if_owner('trigger')
    elif trig_fell:
        w._last_trigger_active = False

def compute_b30_state(w, *, screen_id: str | None=None, c_area: str | None=None, c1_axis=None) -> dict:
    _screen_id = screen_id if screen_id is not None else getattr(w, '_screen_id_prev', None)
    try:
        _dialog_flag_raw = w._analyzer.read_bytes(w._anchor + 4732, 2)
        _dialog_flag = int.from_bytes(_dialog_flag_raw, 'little')
    except (OSError, AttributeError):
        _dialog_flag = getattr(w, '_b30_dialog_flag_prev', 41729)
    _dialog_flag_prev = getattr(w, '_b30_dialog_flag_prev', 41729)
    if _dialog_flag != _dialog_flag_prev:
        _log.debug('b30 0x127C %#06x → %#06x (idle pulse or dialog event)', _dialog_flag_prev, _dialog_flag)
    w._b30_dialog_flag_prev = _dialog_flag
    try:
        _red_raw = w._analyzer.read_bytes(w._anchor + 31097, 68)
        _red_str = _red_raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
    except (OSError, AttributeError):
        _red_str = ''
    _red_prev = getattr(w, '_b30_red_str_prev', '')
    _red_changed = _red_str != _red_prev
    if _red_changed:
        _log.debug('b30 0x7979 changed: %r → %r', _red_prev, _red_str)
    w._b30_red_str_prev = _red_str
    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 43077, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0
    _dialog_active = _dialog_byte != 0
    _dialog_active_prev = getattr(w, '_b30_dialog_active_prev', False)
    try:
        _img_raw = w._analyzer.read_bytes(w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        _img_name = _img_raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
    except (OSError, AttributeError, ImportError):
        _img_name = ''
    _in_gameplay = _screen_id in (None, 'game_screen', 'combat', 'npc_dialog', 'shop', 'loading') and _img_name not in ('MRSHIRT.IMG', 'PAGE2.IMG', 'CHARSTAT.IMG')
    _was_in_gameplay = getattr(w, '_b30_in_gameplay_prev', False)
    if _in_gameplay and (not _was_in_gameplay):
        _log.info('b30 gameplay entry: seeding prev state red=%r dialog_active=%s', _red_str, _dialog_active)
        w._b30_red_str_prev = _red_str
        w._b30_dialog_flag_prev = _dialog_flag
        _red_changed = False
        _dialog_active_prev = _dialog_active
    _c1_axis = c1_axis
    if c_area == 'dungeon':
        try:
            if _c1_axis is None:
                from normal_play.c1_dialog_axis import read_c1_dialog_axis
                _c1_axis = read_c1_dialog_axis(w, c_area=c_area, in_gameplay=_in_gameplay, update_prev=True)
            _dialog_active = _c1_axis.active
            _dialog_active_prev = _c1_axis.prev_active
        except Exception as exc:
            _log.debug('C1 dialog axis read failed: %s', exc)
    w._b30_in_gameplay_prev = _in_gameplay
    w._b30_dialog_active_prev = _dialog_active
    return {'dialog_flag': _dialog_flag, 'dialog_flag_prev': _dialog_flag_prev, 'red_str': _red_str, 'red_changed': _red_changed, 'dialog_byte': _dialog_byte, 'dialog_active': _dialog_active, 'dialog_active_prev': _dialog_active_prev, 'c1_dialog_axis': _c1_axis, 'c1_dialog_axis_active': bool(_c1_axis and _c1_axis.active), 'img_name': _img_name, 'in_gameplay': _in_gameplay}

def poll_red_text(w, *, b30: dict, npc_dialog_changed: bool, c1_fg: str='') -> None:
    _c1_fg_blocks_render = bool(c1_fg and c1_fg not in ('red_text', 'red_text_dialog'))
    _death_red_allowed = _is_death_red_text(b30['red_str']) and _current_hp_is_zero(w)
    if not _death_red_allowed:
        w._death_red_text_prev = ''
    _death_red_new = _death_red_allowed and b30['red_str'] != getattr(w, '_death_red_text_prev', '')
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
        _fg_ptr = _fg_raw[0] | _fg_raw[1] << 8
        try:
            from active_template_reader import is_runtime_message_buffer_pointer
            _dlg_on_screen = is_runtime_message_buffer_pointer(_fg_ptr)
        except Exception:
            _dlg_on_screen = 31097 <= _fg_ptr < 31097 + 68
    except (OSError, AttributeError):
        _dlg_on_screen = False
    _axis = b30.get('c1_dialog_axis')
    _c1_red_axis_active = bool(_axis and _axis.active and (_axis.a845 == 121 or (_axis.current_ptr is not None and 31097 <= _axis.current_ptr < 31097 + 68)))
    if not _c1_fg_blocks_render and _current_top_level(w) == 'normal-play' and (not w._npc_conversation_active) and b30['in_gameplay'] and (b30['red_changed'] or _death_red_new or _dlg_on_screen or _c1_red_axis_active) and b30['red_str']:
        import dungeon_msg_lookup as _dml
        _b30_red_jpn = _dml.lookup(b30['red_str'])
        if not _b30_red_jpn:
            try:
                import npc_dialog_lookup as _ndl
                _ndl_result = _ndl.lookup(b30['red_str'])
                if _ndl_result is not None:
                    _ja_tmpl, _ph = _ndl_result
                    _b30_red_jpn = _ndl.format_japanese(_ja_tmpl, _ph)
            except Exception as exc:
                _log.debug('npc_dialog fallback failed: %s', exc)
        _red_owner = 'red_text_dialog' if b30['dialog_active'] else 'red_text'
        if b30['red_changed'] or _death_red_new:
            w._ui_router.update_translation(_red_owner, b30['red_str'], _b30_red_jpn or '', speech_role='situation')
            w._dlg_keep_key = (b30['red_str'], _b30_red_jpn or '')
            _log.info('b30 red text accepted: %r → %r', b30['red_str'], _b30_red_jpn)
        elif _b30_red_jpn:
            _keep = (b30['red_str'], _b30_red_jpn)
            if not (getattr(w, '_dlg_keep_key', None) == _keep and w._ui_router.is_owner(_red_owner)):
                w._dlg_keep_key = _keep
                w._ui_router.update_translation(_red_owner, b30['red_str'], _b30_red_jpn, speech_role='situation')
        if _death_red_allowed:
            w._death_red_text_prev = b30['red_str']
    elif b30['red_changed'] and b30['red_str']:
        _reason = []
        if w._npc_conversation_active:
            _reason.append('npc-conversation-active')
        if not b30['in_gameplay']:
            _reason.append('not-in-gameplay')
        if npc_dialog_changed:
            _reason.append('npc-dialog-changed')
        _log.info('b30 red text skipped (%s): %r', ','.join(_reason) or 'unknown', b30['red_str'])

def poll_dialog_close(w, *, b30: dict, npc_dialog_changed: bool, instore_resp_handled: bool, c1_fg: str='') -> None:

    def _owner_text_still_on_screen(owner: str) -> bool:
        try:
            _fg_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
            _fg_ptr = _fg_raw[0] | _fg_raw[1] << 8
        except (OSError, AttributeError):
            return False
        try:
            from active_template_reader import is_response_text_buffer_pointer, is_runtime_message_buffer_pointer
            if owner in ('c1_runtime_dialog', 'gold_drop'):
                return is_response_text_buffer_pointer(_fg_ptr)
            if owner == 'red_text_dialog':
                return is_runtime_message_buffer_pointer(_fg_ptr)
        except Exception:
            if owner in ('c1_runtime_dialog', 'gold_drop'):
                return any((start <= _fg_ptr < start + length for start, length in ((4164, 512), (37534, 512), (39582, 512))))
            if owner == 'red_text_dialog':
                return 31097 <= _fg_ptr < 31097 + 68
        return False
    if b30['in_gameplay'] and (not w._npc_conversation_active) and b30['dialog_active_prev'] and (not b30['dialog_active']):
        if c1_fg != '' or instore_resp_handled:
            _log.info('b30 dialog close detected but C1 surface is foreground / instore resp this poll - skip clear (c1_fg=%r, instore_resp=%s, owner=%r)', c1_fg, instore_resp_handled, w._panel_owner)
        elif w._ui_router.current_owner() in ('c1_runtime_dialog', 'gold_drop', 'red_text_dialog'):
            _cur_owner = w._ui_router.current_owner()
            if _owner_text_still_on_screen(_cur_owner):
                _log.info('b30 dialog close detected but owner text still on screen (owner=%s) - preserve display', _cur_owner)
                return
            _log.info('b30 dialog closed (0xA845 → 0x00, owner=%s) - clearing', _cur_owner)
            w._ui_router.clear_if_owner(_cur_owner)
        else:
            _log.info('b30 dialog closed but owner=%r - preserve display', w._panel_owner)
__all__ = ['poll_trigger', 'compute_b30_state', 'poll_red_text', 'poll_dialog_close', 'restore_last_trigger_display', 'classify_c1_dialog_substate']
