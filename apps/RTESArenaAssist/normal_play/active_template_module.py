from __future__ import annotations
import logging
from display_intent import PASSIVE_PANEL_OWNERS
from screen_img_signals import YESNO_IMG
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('RTESArenaAssist')
_RESPONSE_PTR_RANGES = ((4164, 512), (31097, 68), (37534, 512), (39582, 512))

def replaceable_owners(handoff_owners: frozenset=frozenset()) -> frozenset:
    return frozenset({'', 'active_template'}) | PASSIVE_PANEL_OWNERS | frozenset(handoff_owners)

def should_poll_active_template(*, shop_menu_visible: bool, shop_buy_active: bool, allow_during_shop_menu: bool, response_active: bool, in_negotiation: bool, top_level_state: str, facility_l4_surface: bool=False, c_area: str='') -> bool:
    if c_area == 'dungeon':
        return False
    if facility_l4_surface:
        return False
    return not shop_buy_active and (not shop_menu_visible or allow_during_shop_menu) and (not response_active) and (not in_negotiation) and (top_level_state == 'normal-play')

def note_unclaimed_dialog_template(w, *, reason: str) -> None:
    _key = None
    if reason:
        try:
            from active_template_reader import _read_template_from_ptr, is_response_buffer_pointer, read_current_text_pointer
            import npc_dialog_lookup as _ndl
            _ptr = read_current_text_pointer(w._analyzer, w._anchor)
            _text = _read_template_from_ptr(w._analyzer, w._anchor, _ptr) if _ptr is not None and (not is_response_buffer_pointer(_ptr)) else None
            if _text and _ndl.lookup(_text) is not None:
                _key = (_ptr, reason, _text)
        except Exception:
            _key = None
    if _key == getattr(w, '_active_tmpl_unclaimed_prev', None):
        return
    w._active_tmpl_unclaimed_prev = _key
    if _key is not None:
        from assist_log import recog as _recog
        _recog(_log, 'active_template not evaluated: ptr=0x%04X reason=%s text=%r', _key[0], _key[1], _key[2][:60])

def poll_active_template(w, *, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, allow_during_shop_menu: bool, c_area: str='', select_candidate=None, handoff_owners: frozenset=frozenset(), diag_label: str='', input_prompt_label=None, choice_buttons=None) -> bool:
    try:
        _ptr_raw = w._analyzer.read_bytes(w._anchor + 43076, 2)
        _ptr_val = _ptr_raw[0] | _ptr_raw[1] << 8
    except (OSError, AttributeError):
        _ptr_val = 0
    try:
        from active_template_reader import is_response_buffer_pointer
        _response_active = is_response_buffer_pointer(_ptr_val)
    except Exception:
        _response_active = any((start <= _ptr_val < start + length for start, length in _RESPONSE_PTR_RANGES))
    try:
        from negotiation_reader import NEGOTIATION_PROFILES as _NPF
        _in_negot = shop_img_name in _NPF and (shop_img_name or '').upper() != YESNO_IMG
    except Exception:
        _in_negot = False
    _top_level = _current_top_level(w)
    from store_surface import l4_surface_claimed as _l4_surface_claimed
    _facility_l4_surface = _l4_surface_claimed(w)
    _gate_ok = should_poll_active_template(shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, allow_during_shop_menu=allow_during_shop_menu, response_active=_response_active, in_negotiation=_in_negot, top_level_state=_top_level, facility_l4_surface=_facility_l4_surface, c_area=c_area)
    if not _gate_ok:
        if c_area != 'dungeon' and select_candidate is None:
            note_unclaimed_dialog_template(w, reason=f'gate(menu={shop_menu_visible} buy={shop_buy_active} response={_response_active} negot={_in_negot} top={_top_level} img={shop_img_name!r})')
        if _facility_l4_surface:
            _block_key = (shop_img_name, diag_label)
            if _block_key != getattr(w, '_active_tmpl_l4_block_key', None):
                w._active_tmpl_l4_block_key = _block_key
                _log.info('active_template blocked by facility L4 surface facility=%s img=%r', diag_label, shop_img_name)
        return False
    try:
        from active_template_reader import read_active_template_candidates, read_current_text_pointer, candidate_signature, select_foreground_candidate
        _candidates = read_active_template_candidates(w._analyzer, w._anchor)
        _cur_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        _log.exception('active_template_reader failed')
        return False
    note_unclaimed_dialog_template(w, reason='')
    try:
        import npc_dialog_lookup as _ndl
    except Exception:
        _log.exception('npc_dialog_lookup import failed')
        _ndl = None
    _ctx_key = (shop_img_name, _cur_ptr, _top_level)
    _prev_ctx = getattr(w, '_active_tmpl_ctx_prev', None)
    _prev_sigs = getattr(w, '_active_tmpl_sig_prev', frozenset())
    _sigs_now = frozenset((candidate_signature(c) for c in _candidates))
    w._active_tmpl_ctx_prev = _ctx_key
    w._active_tmpl_sig_prev = _sigs_now
    _active_tmpl: str | None = None
    _ndl_result = None
    _active_tmpl_src: str = ''
    if _ndl is not None and _candidates:

        def _hit(text: str, _ndl=_ndl) -> bool:
            try:
                return _ndl.lookup(text) is not None
            except Exception:
                return False
        if select_candidate is None:
            _selected = select_foreground_candidate(_candidates, _hit)
        else:
            _selected = select_candidate(_candidates, img_name=shop_img_name, lookup_hit=_hit)
        if _selected is not None:
            try:
                _r = _ndl.lookup(_selected.text)
            except Exception:
                _r = None
            if _r:
                _active_tmpl = _selected.text
                _ndl_result = _r
                _active_tmpl_src = _selected.source
    if _active_tmpl is None and _candidates:
        _ipf = input_prompt_label or (lambda _c: '')
        _log.debug('active_template no-select: img=%r cur_ptr=%s ctx_changed=%s candidates=%d new_sigs=%d active_facility=%r', shop_img_name, f'0x{_cur_ptr:04X}' if _cur_ptr is not None else 'None', _ctx_key != _prev_ctx, len(_candidates), len(_sigs_now - _prev_sigs), diag_label)
        for _c in _candidates:
            try:
                _hit_ok = _ndl.lookup(_c.text) is not None if _ndl else False
            except Exception:
                _hit_ok = False
            _ipf_name = _ipf(_c)
            _log.debug('  candidate src=%s slot=%s ptr=0x%04X hit=%s input_prompt=%r text=%r', _c.source, f'0x{_c.ptr_slot:04X}' if _c.ptr_slot is not None else 'None', _c.ptr, _hit_ok, _ipf_name, _c.text.rstrip()[:60])
    if _active_tmpl is not None and _ndl_result is not None:
        from normal_play.level_up_module import is_level_up_message
        if is_level_up_message(_active_tmpl):
            return True
        _ja_tmpl, _ph = _ndl_result
        _ja = _ndl.format_japanese(_ja_tmpl, _ph)
        _tmpl_key = (_active_tmpl, _ja)
        _prev_key = getattr(w, '_active_tmpl_key_prev', None)
        if _tmpl_key != _prev_key:
            w._active_tmpl_key_prev = _tmpl_key
            w._active_tmpl_selected_ptr_prev = _selected.ptr if _selected else None
            _orig_clean = _active_tmpl.rstrip()
            try:
                _owner_now = w._ui_router.current_owner() or ''
            except (AttributeError, RuntimeError):
                _owner_now = getattr(w, '_panel_owner', '') or ''
            if _owner_now not in replaceable_owners(handoff_owners):
                _log.info('active_template withheld (panel-owner=%s): en=%r', _owner_now, _orig_clean[:80])
                return True
            _buttons = choice_buttons(_selected) if choice_buttons is not None and _selected is not None else None
            if _buttons:
                w._ui_router.update_translation('active_template', f'{_buttons[0]}\n{_orig_clean}', f'{_buttons[1]}\n{_ja}', speech_role='situation', speech_text=_ja)
            else:
                w._ui_router.update_translation('active_template', _orig_clean, _ja, speech_role='situation')
            _log.info('active_template translated: src=%s en=%r ja=%r', _active_tmpl_src, _orig_clean[:80], _ja[:80])
        return True
    return False

def poll_template_outside_conversation(w, *, shop_img_name: str, shop_menu_visible: bool, shop_buy_active: bool, area: str) -> bool:
    from controllers.poll_diag import _phase_record, _phase_start
    _t_active_tmpl = _phase_start()
    handled = poll_active_template(w, shop_img_name=shop_img_name, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, allow_during_shop_menu=False, c_area=area)
    _phase_record(w, 'active_template', _t_active_tmpl)
    if not handled:
        cleanup_if_owner(w)
    return handled

def cleanup_if_owner(w) -> None:
    if getattr(w, '_active_tmpl_key_prev', None) is not None:
        w._ui_router.notify_display_unit_closed('active_template')
    w._active_tmpl_key_prev = None
    w._active_tmpl_selected_ptr_prev = None
    if w._ui_router.is_owner('active_template'):
        w._ui_router.clear_if_owner('active_template', notify_close=False)
        _log.info('active_template exit')
__all__ = ['poll_active_template', 'poll_template_outside_conversation', 'replaceable_owners', 'cleanup_if_owner', 'should_poll_active_template', 'note_unclaimed_dialog_template']
