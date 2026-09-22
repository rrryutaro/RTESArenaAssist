from __future__ import annotations
import logging
import re as _re
import inf_text_lookup as itl
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.c1_dialog_axis import close_confirmed as _close_confirmed
from normal_play.trigger_module import _render_trigger_entry, restore_last_trigger_display
from assist_log import recog as _recog
_log = logging.getLogger('RTESArenaAssist')
GOLD_DROP_OWNER = 'gold_drop'
_GOLD_DROP_RE = _re.compile('^You have found \\d+ gold pieces?!!?')
_INF_FRAG_EXCLUDE_RE = _re.compile('^(You have found |You open door |Bag of \\d+ gold pieces)', _re.IGNORECASE)
_GOLD_DROP_REPLACEABLE_OWNERS = frozenset({'', GOLD_DROP_OWNER, 'trigger', 'red_text', 'red_text_dialog', 'c1_runtime_dialog'})

def _poll_gold_inf_fragment(w, b131_str: str, inf_name: str, mif_name: str) -> None:
    _log.debug('b131 0x929E changed but not gold-drop format: %r', b131_str[:64])
    _inf_fragment_pushed = getattr(w, '_b131_inf_fragment_pushed', '')
    from normal_play.item_pickup_module import pickup_list_open
    _newpop_open_now = pickup_list_open(w)
    try:
        _inf_excluded = bool(_INF_FRAG_EXCLUDE_RE.match(b131_str))
    except Exception:
        _inf_excluded = False
    _inf_for_lookup = inf_name
    if not _inf_for_lookup and mif_name:
        _mif_base = mif_name.split('.')[0].upper()
        if _mif_base:
            _inf_for_lookup = f'{_mif_base}.INF'
    _skip_reason = ''
    if _inf_excluded:
        _skip_reason = 'excluded by special pattern'
    elif _newpop_open_now:
        _skip_reason = 'NEWPOP open'
    elif b131_str == _inf_fragment_pushed:
        _skip_reason = 'same as last pushed'
    elif len(b131_str.strip()) < 16:
        _skip_reason = 'fragment too short'
    elif _current_top_level(w) != 'normal-play':
        _skip_reason = 'not in normal-play'
    elif not _inf_for_lookup:
        _skip_reason = 'no inf_name nor mif_name to infer'
    if not _skip_reason:
        try:
            _inf_entry = itl.lookup_by_substring(_inf_for_lookup, b131_str)
        except Exception as exc:
            _inf_entry = None
            _log.debug('INF fragment lookup_by_substring error: %s', exc)
        if _inf_entry is not None:
            try:
                _render_trigger_entry(w, _inf_entry)
                w._b131_inf_fragment_pushed = b131_str
                _log.info('b131 INF fragment resolved (inf=%s, source=%s): %r', _inf_entry.get('inf'), _inf_for_lookup, b131_str[:48])
            except (AttributeError, RuntimeError) as exc:
                _log.debug('INF fragment update failed: %s', exc)
        else:
            _log.debug('b131 INF fragment lookup miss (inf=%s): %r', _inf_for_lookup, b131_str[:48])
    else:
        _log.debug('b131 INF fragment fallback skipped (%s): %r', _skip_reason, b131_str[:48])

def poll_gold_drop(w, *, b30: dict, inf_name: str, mif_name: str) -> None:
    try:
        _b131_raw = w._analyzer.read_bytes(w._anchor + 37534, 64)
        _b131_str = _b131_raw.split(b'\x00', 1)[0].decode('ascii', errors='replace')
    except (OSError, AttributeError):
        _b131_str = ''
    _b131_prev = getattr(w, '_b131_str_prev', '')
    _b131_changed = _b131_str != _b131_prev
    w._b131_str_prev = _b131_str
    _b131_match = bool(_b131_str and _GOLD_DROP_RE.match(_b131_str))
    if _b131_changed and _b131_match:
        try:
            _owner_now = w._ui_router.current_owner() or ''
        except (AttributeError, RuntimeError):
            _owner_now = getattr(w, '_panel_owner', '') or ''
        _block_reasons = []
        if _owner_now not in _GOLD_DROP_REPLACEABLE_OWNERS:
            _block_reasons.append('panel-owner=%s' % (_owner_now or '-'))
        if not b30['in_gameplay']:
            _block_reasons.append('not-in-gameplay')
        if _block_reasons:
            _recog(_log, 'gold drop skipped (%s): %r', ','.join(_block_reasons), _b131_str[:64])
            return
        import dungeon_msg_lookup as _dml131
        _b131_ja = _dml131.lookup(_b131_str)
        _log.info('b131 gold drop msg: %r -> %r', _b131_str, _b131_ja)
        if not _b131_ja:
            return
        w._ui_router.update_translation(GOLD_DROP_OWNER, _b131_str, _b131_ja, speech_role='situation')
        _axis = b30.get('c1_dialog_axis')
        _ptr = getattr(_axis, 'current_ptr', None)
        _open_gold_drop_display(w, area=getattr(_axis, 'area', '') or '')
        _recog(_log, 'gold drop accepted (ptr=%s area=%s): %r → %r', '0x%04X' % _ptr if _ptr is not None else 'n/a', getattr(_axis, 'area', '') or '-', _b131_str, _b131_ja)
    elif _b131_changed and _b131_str:
        _poll_gold_inf_fragment(w, _b131_str, inf_name, mif_name)

def _open_gold_drop_display(w, *, area: str='') -> None:
    w._gold_drop_open = True
    w._gold_drop_area = area
    w._gold_drop_closed = False
    w._gold_drop_left_noted = False

def _close_gold_drop_display(w) -> None:
    w._gold_drop_open = False
    w._gold_drop_area = ''
    w._gold_drop_closed = False
    w._gold_drop_left_noted = False

def release_gold_drop(w) -> None:
    _close_gold_drop_display(w)

def poll_gold_drop_lifetime(w, *, axis=None) -> None:
    if not getattr(w, '_gold_drop_open', False):
        return
    try:
        owner = w._ui_router.current_owner() or ''
    except (AttributeError, RuntimeError):
        return
    area_open = getattr(w, '_gold_drop_area', '') or ''
    if axis is not None and axis.area != area_open:
        ptr_text = '0x%04X' % axis.current_ptr if axis.current_ptr is not None else 'n/a'
        if _close_confirmed(area_open):
            if not getattr(w, '_gold_drop_closed', False):
                w._gold_drop_closed = True
                _recog(_log, 'gold drop: closed (pointer left %s, ptr=%s area=%s)', area_open, ptr_text, axis.area or '-')
        elif not getattr(w, '_gold_drop_left_noted', False):
            w._gold_drop_left_noted = True
            _recog(_log, 'gold drop: pointer left %s (ptr=%s area=%s) but the close signal for this kind is not confirmed; display end deferred to replacement', area_open or '-', ptr_text, axis.area or '-')
    if owner not in ('', GOLD_DROP_OWNER):
        return
    if not getattr(w, '_gold_drop_closed', False):
        return
    feed = getattr(w, '_translation_feed', None)
    try:
        speaking_owner = feed.speaking_owner() if feed is not None else None
    except AttributeError:
        speaking_owner = None
    if speaking_owner == GOLD_DROP_OWNER:
        try:
            if w._tts.is_speaking():
                return
        except AttributeError:
            pass
    _recog(_log, 'gold drop display end (表示終了・読み上げ終了)')
    _close_gold_drop_display(w)
    if owner == GOLD_DROP_OWNER:
        w._ui_router.notify_display_unit_closed(GOLD_DROP_OWNER)
        w._ui_router.clear_if_owner(GOLD_DROP_OWNER, notify_close=False)
        restore_last_trigger_display(w)
    else:
        w._ui_router.clear_display('', allowed_current_owners=('',))
__all__ = ['GOLD_DROP_OWNER', 'poll_gold_drop', 'poll_gold_drop_lifetime', 'release_gold_drop']
