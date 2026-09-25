from __future__ import annotations
import logging
from arena_bridge import TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ, get_trigger_text_by_index
import inf_text_lookup as itl
import mif_trigger
from viewer_constants import CURRENT_TRIGGER_TEXT_PTR_OFFSET
import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.cinematic_module import _current_hp_is_zero
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
_DEATH_RED_TEXTS = frozenset({'You are dead', 'You have been slain'})

def _entry_to_payload(entry: dict) -> tuple[str, str, str, str]:
    if entry.get('type') == 'riddle':
        fld = entry.get('_riddle_field', 'question')
        en = entry.get(fld, '') or ''
        trans = itl.get_translation(entry)
        ja = trans.get(fld, '') if isinstance(trans, dict) else ''
        return (en, ja, en, ja)
    en = itl.get_text_display(entry) or ''
    ja_disp = itl.get_translation_display(entry)
    ja = ja_disp if isinstance(ja_disp, str) else ''
    panel_en = itl.get_text_panel(entry) or ''
    panel_ja_raw = itl.get_translation(entry)
    panel_ja = panel_ja_raw if isinstance(panel_ja_raw, str) else ''
    return (en, ja, panel_en, panel_ja)

def _riddle_display_begin(w, entry: dict) -> None:
    w._riddle_display = None
    try:
        raw = w._analyzer.read_bytes(w._anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
        ptr = int.from_bytes(w._analyzer.read_bytes(w._anchor + CURRENT_TRIGGER_TEXT_PTR_OFFSET, 2), 'little')
    except (OSError, AttributeError):
        return
    ranges = mif_trigger.find_riddle_group(raw, entry.get('question', ''))
    question = next((r for r in ranges if r['kind'] == 'question'), None)
    if question is None:
        return
    w._riddle_display = {'entry': entry, 'ranges': ranges, 'base': ptr - question['start'], 'kind': 'question'}

def poll_riddle_display(w) -> None:
    st = getattr(w, '_riddle_display', None)
    if not st:
        return
    try:
        ptr = int.from_bytes(w._analyzer.read_bytes(w._anchor + CURRENT_TRIGGER_TEXT_PTR_OFFSET, 2), 'little')
    except (OSError, AttributeError):
        return
    hit = mif_trigger.classify_riddle_part(ptr, st['base'], st['ranges'])
    if hit is None or hit['kind'] == st['kind']:
        return
    st['kind'] = hit['kind']
    entry = dict(st['entry'])
    entry['_riddle_field'] = hit['kind']
    _render_trigger_entry(w, entry, begin_riddle=False)

def riddle_group_holds_ptr(w, ptr) -> bool:
    st = getattr(w, '_riddle_display', None)
    if not st or ptr is None:
        return False
    return mif_trigger.classify_riddle_part(ptr, st['base'], st['ranges']) is not None

def _render_trigger_entry(w, entry: dict, *, begin_riddle: bool=True) -> None:
    try:
        w._set_chargen_ui_state(False)
    except (AttributeError, RuntimeError):
        pass
    if begin_riddle and entry.get('type') == 'riddle':
        _riddle_display_begin(w, entry)
        try:
            from services import riddle_store
            from viewer_constants import MAP_NAME_OFFSET, MAP_NAME_MAXLEN
            place = w._analyzer.read_bytes(w._anchor + MAP_NAME_OFFSET, MAP_NAME_MAXLEN).split(b'\x00')[0].decode('ascii', errors='replace').strip()
            answers = list(entry.get('answers') or [])
            if not answers:
                raw = w._analyzer.read_bytes(w._anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
                answers = mif_trigger.riddle_answers(raw, entry.get('question', ''))
            riddle_store.get_store().note_seen(entry.get('inf', ''), entry.get('idx'), place, answers)
        except Exception:
            pass
    en, ja, panel_en, panel_ja = _entry_to_payload(entry)
    tab_off = _riddle_tab_suppressed(w, entry)
    if _is_same_trigger_displaying(w, en, ja, panel_en, panel_ja, tab_off=tab_off):
        return
    _store_last_trigger_display(w, en, ja, panel_en, panel_ja, tab_off=tab_off)
    w._ui_router.update_translation('trigger', en, ja, panel_en=panel_en, panel_ja=panel_ja, update_tab=not tab_off, speech_role='situation')

def _riddle_tab_suppressed(w, entry: dict) -> bool:
    return entry.get('type') == 'riddle' and bool(getattr(w, '_is_layout_active', False))

def _reset_trigger_display(w) -> None:
    w._last_trigger_active = False
    w._riddle_display = None
    w._ui_router.clear_if_owner('trigger')

def _store_last_trigger_display(w, en: str, ja: str, panel_en: str | None=None, panel_ja: str | None=None, *, tab_off: bool=False) -> None:
    w._last_trigger_display = (en, ja, panel_en, panel_ja)
    w._last_trigger_active = True
    w._last_trigger_tab_off = tab_off

def _is_same_trigger_displaying(w, en: str, ja: str, panel_en: str | None=None, panel_ja: str | None=None, *, tab_off: bool=False) -> bool:
    return bool(getattr(w, '_last_trigger_active', False) and getattr(w, '_last_trigger_display', None) == (en, ja, panel_en, panel_ja) and (bool(getattr(w, '_last_trigger_tab_off', False)) == tab_off) and w._ui_router.is_displaying('trigger', en, ja))

def _push_raw_trigger_body(w, body: str) -> None:
    if not (body or '').strip():
        _reset_trigger_display(w)
        return
    if _is_same_trigger_displaying(w, body, ''):
        return
    _store_last_trigger_display(w, body, '')
    w._ui_router.update_translation('trigger', body, '', speech_role='situation')

def _static_text_index_state(inf_name: str, text_index: int) -> str:
    entries = itl.all_entries_for_inf(inf_name)
    if not entries:
        return 'unknown'
    if any((e.get('idx') == text_index for e in entries)):
        return 'present'
    return 'not_text'

def restore_last_trigger_display(w) -> bool:
    if not getattr(w, '_last_trigger_active', False):
        return False
    payload = getattr(w, '_last_trigger_display', None)
    if not payload:
        return False
    en, ja, panel_en, panel_ja = payload
    w._ui_router.update_translation('trigger', en, ja, panel_en=panel_en, panel_ja=panel_ja, update_tab=not getattr(w, '_last_trigger_tab_off', False), speech_role=None)
    return True

def _is_death_red_text(text: str) -> bool:
    return (text or '').strip() in _DEATH_RED_TEXTS

def _map_context(w):
    matcher = getattr(w, '_mif_matcher', None)
    if matcher is None:
        return None
    return (matcher.loaded_mif, matcher.active_level)

def reset_trigger_identification(w) -> None:
    w._trigger_unresolved = None

def _identify_fired_text(w, rt_x, rt_z, inf_name: str, *, retry: bool) -> bool:
    text_index = None
    correct_body = ''
    if w._mif_matcher and rt_x is not None and (rt_z is not None):
        text_index = w._mif_matcher.find_text_index(rt_x, rt_z)
        if text_index is not None:
            try:
                raw_b = w._analyzer.read_bytes(w._anchor + TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ)
                correct_body = get_trigger_text_by_index(raw_b, text_index)
            except OSError:
                correct_body = ''
    if text_index is None and retry:
        return False
    declared_inf = ''
    if w._mif_matcher is not None:
        declared_inf = w._mif_matcher.declared_inf_name() or ''
    lookup_inf = declared_inf or inf_name
    try:
        _disp_ptr = int.from_bytes(w._analyzer.read_bytes(w._anchor + CURRENT_TRIGGER_TEXT_PTR_OFFSET, 2), 'little')
    except (OSError, AttributeError):
        _disp_ptr = None
    _recog(_log, 'trigger %s: inf_live=%r inf_mif=%r coord=%r text_index=%s match=%s disp_ptr=%s correct_body=%r', 're-identified' if retry else 'fired', inf_name, declared_inf, (rt_x, rt_z), text_index, w._mif_matcher.last_status if w._mif_matcher else 'no-matcher', f'0x{_disp_ptr:04X}' if _disp_ptr is not None else 'n/a', (correct_body or '')[:60])
    if text_index is None:
        _reset_trigger_display(w)
        return False
    _render_identified_text(w, lookup_inf, text_index, correct_body)
    return True

def poll_trigger(w, *, new_trigger: bool, trig_fell: bool, trigger_flag: int, inf_name: str, position: tuple | None=None) -> None:
    if trigger_flag != 0:
        w._sb.showMessage(f"Trigger: flag=0x{trigger_flag:02X}  INF={inf_name or '(none)'}", 4000)
    poll_riddle_display(w)
    if new_trigger:
        w._trigger_unresolved = None
        at = (w._cached_rt_x, w._cached_rt_z)
        if not _identify_fired_text(w, at[0], at[1], inf_name, retry=False):
            w._trigger_unresolved = {'at': at, 'map': _map_context(w)}
    else:
        pending = getattr(w, '_trigger_unresolved', None)
        if pending and trigger_flag != 0 and (not trig_fell) and (position is not None) and (position != pending['at']) and (_map_context(w) == pending['map']):
            pending['at'] = position
            if _identify_fired_text(w, position[0], position[1], inf_name, retry=True):
                w._trigger_unresolved = None
    if trig_fell and getattr(w, '_trigger_unresolved', None):
        _recog(_log, 'trigger unresolved: 同定できないまま表示が終わった 座標=%r', w._trigger_unresolved['at'])
        w._trigger_unresolved = None
    if trig_fell and (not settings.get('keep_trigger_on_panel', False)):
        w._last_trigger_active = False
        w._riddle_display = None
        w._ui_router.clear_if_owner('trigger')
    elif trig_fell:
        w._last_trigger_active = False
        w._riddle_display = None

def _render_identified_text(w, lookup_inf: str, text_index: int, correct_body: str) -> None:
    entry = itl.lookup(lookup_inf, text_index)
    index_state = 'present' if entry is not None else _static_text_index_state(lookup_inf, text_index)
    if entry is not None and entry.get('type') == 'key':
        entry = None
    if entry is None and index_state == 'not_text':
        _recog(_log, 'trigger is not a text trigger: inf=%r text_index=%s (index not defined as text; display held)', lookup_inf, text_index)
        return
    if entry is None and correct_body:
        entry = itl.lookup_riddle_by_text(correct_body)
    if entry is None and correct_body:
        entry = itl.lookup_by_text(lookup_inf, correct_body)
    if entry is None and correct_body and lookup_inf:
        entry = itl.lookup_by_substring(lookup_inf, correct_body)
    if entry is not None:
        _render_trigger_entry(w, entry)
    elif index_state == 'present' and correct_body:
        _push_raw_trigger_body(w, correct_body)
    else:
        _reset_trigger_display(w)

def idle_b30_state(w) -> dict:
    w._b30_in_gameplay_prev = False
    w._b30_dialog_active_prev = False
    return {'dialog_flag': getattr(w, '_b30_dialog_flag_prev', 41729), 'dialog_flag_prev': getattr(w, '_b30_dialog_flag_prev', 41729), 'red_str': getattr(w, '_b30_red_str_prev', ''), 'red_changed': False, 'dialog_active': False, 'dialog_active_prev': False, 'c1_dialog_axis': None, 'c1_dialog_axis_active': False, 'img_name': '', 'in_gameplay': False, 'fg_ptr': None, 'dialog_text_fg': False, 'dialog_text_fg_prev': False}
GAMEPLAY_SCREEN_IDS = frozenset({'game_screen', 'combat', 'npc_dialog', 'shop', 'loading'})

def gameplay_screen(screen_id: str | None) -> bool:
    return screen_id is None or screen_id in GAMEPLAY_SCREEN_IDS
_FG_PTR_UNREAD = object()

def compute_b30_state(w, *, in_gameplay: bool, c_area: str | None=None, c1_axis=None, img_name: str | None=None, fg_ptr=_FG_PTR_UNREAD) -> dict:
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
        _recog(_log, 'b30 0x7979 changed: %r → %r', _red_prev, _red_str)
    w._b30_red_str_prev = _red_str
    _c1_axis = c1_axis if c_area == 'dungeon' else None
    if _c1_axis is not None:
        _fg_ptr = getattr(_c1_axis, 'current_ptr', None)
    elif fg_ptr is not _FG_PTR_UNREAD:
        _fg_ptr = fg_ptr
    else:
        try:
            _fg_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
            _fg_ptr = _fg_raw[0] | _fg_raw[1] << 8
        except (OSError, AttributeError):
            _fg_ptr = None
    try:
        from active_template_reader import is_dialog_text_pointer
        _dialog_text_fg = is_dialog_text_pointer(_fg_ptr)
    except Exception:
        _dialog_text_fg = _fg_ptr is not None and (4164 <= _fg_ptr < 4164 + 512 or 16384 <= _fg_ptr < 49152)
    _dialog_active = _dialog_text_fg
    _dialog_active_prev = getattr(w, '_b30_dialog_active_prev', False)
    _dialog_text_fg_prev = bool(_dialog_active_prev)
    _img_name = (img_name or '').upper()
    _in_gameplay = bool(in_gameplay)
    _was_in_gameplay = getattr(w, '_b30_in_gameplay_prev', False)
    if _in_gameplay and (not _was_in_gameplay):
        _log.info('b30 gameplay entry: seeding prev state red=%r dialog_active=%s', _red_str, _dialog_active)
        w._b30_red_str_prev = _red_str
        w._b30_dialog_flag_prev = _dialog_flag
        _red_changed = False
        _dialog_active_prev = _dialog_active
    if _c1_axis is not None:
        try:
            _dialog_active = _c1_axis.active
            _dialog_active_prev = _c1_axis.prev_active
        except AttributeError as exc:
            _log.debug('C1 dialog axis unusable: %s', exc)
    w._b30_in_gameplay_prev = _in_gameplay
    w._b30_dialog_active_prev = _dialog_text_fg
    return {'dialog_flag': _dialog_flag, 'dialog_flag_prev': _dialog_flag_prev, 'red_str': _red_str, 'red_changed': _red_changed, 'dialog_active': _dialog_active, 'dialog_active_prev': _dialog_active_prev, 'c1_dialog_axis': _c1_axis, 'c1_dialog_axis_active': bool(_c1_axis and _c1_axis.active), 'img_name': _img_name, 'in_gameplay': _in_gameplay, 'fg_ptr': _fg_ptr, 'dialog_text_fg': bool(_dialog_text_fg), 'dialog_text_fg_prev': _dialog_text_fg_prev}
_RED_TEXT_REPLACEABLE_OWNERS = frozenset({'', 'red_text', 'red_text_dialog', 'trigger', 'gold_drop', 'c1_runtime_dialog'})

def _red_text_is_framed(b30: dict) -> bool:
    from normal_play.c1_dialog_axis import AREA_RUNTIME_MSG, area_of
    axis = b30.get('c1_dialog_axis')
    if axis is not None:
        return bool(axis.active) and axis.area == AREA_RUNTIME_MSG
    return area_of(b30.get('fg_ptr')) == AREA_RUNTIME_MSG

def poll_red_text(w, *, b30: dict, message_taken: bool=False) -> None:
    _death_red_allowed = _is_death_red_text(b30['red_str']) and _current_hp_is_zero(w)
    if not _death_red_allowed:
        w._death_red_text_prev = ''
    _death_red_new = _death_red_allowed and b30['red_str'] != getattr(w, '_death_red_text_prev', '')
    try:
        _owner_now = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        _owner_now = getattr(w, '_panel_owner', '') or ''
    _panel_free = _owner_now in _RED_TEXT_REPLACEABLE_OWNERS
    _block_reasons = []
    if not _panel_free:
        _block_reasons.append('panel-owner=%s' % (_owner_now or '-'))
    if message_taken:
        _block_reasons.append('message-taken')
    if _current_top_level(w) != 'normal-play':
        _block_reasons.append('not-normal-play')
    if not b30['in_gameplay']:
        _block_reasons.append('not-in-gameplay')
    _dialog_reopened = bool(b30.get('dialog_active') and (not b30.get('dialog_active_prev')) and _red_text_is_framed(b30))
    if not _block_reasons and (b30['red_changed'] or _death_red_new or _dialog_reopened) and b30['red_str']:
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
        _red_owner = 'red_text_dialog' if _red_text_is_framed(b30) else 'red_text'
        w._ui_router.update_translation(_red_owner, b30['red_str'], _b30_red_jpn or '', speech_role='situation')
        _open_red_text_display(w, _red_owner, b30['red_str'])
        _recog(_log, 'red text accepted: %r → %r', b30['red_str'], _b30_red_jpn)
        if _death_red_allowed:
            w._death_red_text_prev = b30['red_str']
    elif b30['red_changed'] and b30['red_str']:
        _recog(_log, 'red text skipped (%s): %r', ','.join(_block_reasons) or 'no-trigger', b30['red_str'])
_RED_ABSENT_POLLS_TO_END = 10

def _open_red_text_display(w, red_owner: str, text: str='') -> None:
    w._red_text_open = red_owner
    w._red_text_close_seen = False
    w._red_text_band_seen = False
    w._red_text_polls_open = 0

def _close_red_text_display(w) -> None:
    w._red_text_open = ''
    w._red_text_close_seen = False
    w._red_text_band_seen = False
    w._red_text_polls_open = 0

def band_wanted(w) -> bool:
    return bool(getattr(w, '_red_text_open', ''))

def red_text_display_open(w) -> bool:
    return bool(getattr(w, '_red_text_open', ''))

def release_red_text(w) -> None:
    _close_red_text_display(w)

def poll_red_text_lifetime(w, *, b30: dict, band=None) -> None:
    try:
        owner = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return
    open_owner = getattr(w, '_red_text_open', '') or ''
    if not open_owner:
        w._red_text_close_seen = False
        return
    if b30.get('dialog_active_prev') and (not b30.get('dialog_active')):
        w._red_text_close_seen = True
    if band is None:
        from normal_play.action_text_band import current_band
        band = current_band(w)
    polls_open = int(getattr(w, '_red_text_polls_open', 0)) + 1
    w._red_text_polls_open = polls_open
    if band.live:
        w._red_text_band_seen = True
    band_seen = bool(getattr(w, '_red_text_band_seen', False))
    band_gone = band_seen and (not band.live) or (not band_seen and polls_open >= _RED_ABSENT_POLLS_TO_END)
    close_seen = bool(getattr(w, '_red_text_close_seen', False))
    if open_owner == 'red_text_dialog':
        game_end = close_seen
    else:
        game_end = close_seen or band_gone
    if owner not in ('', 'red_text', 'red_text_dialog'):
        return
    if not game_end:
        return
    feed = getattr(w, '_translation_feed', None)
    try:
        speaking_owner = feed.speaking_owner() if feed is not None else None
    except AttributeError:
        speaking_owner = None
    if speaking_owner == open_owner:
        try:
            if w._tts.is_speaking():
                return
        except AttributeError:
            pass
    _recog(_log, 'red text display end: owner=%s (表示終了・読み上げ終了)', open_owner)
    _close_red_text_display(w)
    if owner in ('red_text', 'red_text_dialog'):
        w._ui_router.notify_display_unit_closed(owner)
        w._ui_router.clear_if_owner(owner, notify_close=False)
        restore_last_trigger_display(w)
    else:
        w._ui_router.clear_display('', allowed_current_owners=('',))
__all__ = ['poll_trigger', 'riddle_group_holds_ptr', 'GAMEPLAY_SCREEN_IDS', 'gameplay_screen', 'compute_b30_state', 'poll_red_text', 'poll_red_text_lifetime', 'band_wanted', 'red_text_display_open', 'release_red_text', 'restore_last_trigger_display']
