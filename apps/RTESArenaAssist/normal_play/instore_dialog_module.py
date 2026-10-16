from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
_SHOP_SURFACE_KINDS = ('shop_menu', 'shop_buy', 'shop_rooms', 'shop_rumor_type')

def _hex_ptr(ptr) -> str:
    return f'0x{ptr:04X}' if ptr is not None else '?'

def _read_response_probe(w):
    try:
        from popup11_response_reader import candidate_contains_pointer, read_current_text_pointer, read_response_candidates_all
    except Exception:
        return ([], None, lambda _candidate, _ptr: False)
    try:
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:
        cands = []
    try:
        current_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        current_ptr = None
    return (cands, current_ptr, candidate_contains_pointer)

def _choose_instore_response(cands, current_ptr, prev_text_by_offset, contains_pointer, *, view_response: bool):
    hits = [c for c in cands if c.lookup_hit and c.text]
    changed_hits = [c for c in hits if prev_text_by_offset.get(c.source_offset) != c.text]
    ptr_cands = [c for c in cands if c.text and contains_pointer(c, current_ptr)]
    ptr_hits = [c for c in ptr_cands if c.lookup_hit]
    if ptr_hits:
        reason = 'ptr_surface_override' if view_response else 'ptr'
        return (ptr_hits[0], reason, changed_hits, ptr_cands)
    if changed_hits:
        return (changed_hits[0], 'source_changed', changed_hits, ptr_cands)
    return (None, '', changed_hits, ptr_cands)

def _log_ptr_misses(w, ptr_cands, current_ptr) -> None:
    for c in ptr_cands:
        if c.lookup_hit:
            continue
        try:
            raw_head = w._analyzer.read_bytes(w._anchor + c.source_offset, 128)
            _raw_hex = raw_head.hex()
        except (OSError, AttributeError):
            _raw_hex = '<read err>'
        _log.debug('in_store_resp ptr_match lookup miss (src=0x%X ptr=0x%04X text=%r raw=%s)', c.source_offset, current_ptr or 0, c.text[:120], _raw_hex)

def _log_no_display(cands, changed_hits, current_ptr, contains_pointer, npc_phase_raw, npc_overlay_active, in_interior) -> None:
    if not cands:
        _log.debug('in_store_resp no candidate (phase=0x%s overlay=%s in_interior=%s)', f'{npc_phase_raw:02X}' if npc_phase_raw is not None else '??', npc_overlay_active, in_interior)
        return
    _summary = ', '.join((f'0x{c.source_offset:X}:hit={c.lookup_hit} changed={c in changed_hits} ptr_match={contains_pointer(c, current_ptr)} text={c.text[:60]!r}' for c in cands))
    _log.debug('in_store_resp no display candidate (ptr=%s %s)', _hex_ptr(current_ptr), _summary)

def _show_instore_response(w, ctx, chosen, reason, current_ptr) -> bool:
    try:
        from normal_play.npc_dialog_module import _show_npc_dialog_text
        import npc_dialog_lookup as _ndl_msg
        _ndl_result = _ndl_msg.lookup(chosen.text)
        if not _ndl_result:
            return False
        _ndl_ja_tmpl, _ndl_ph = _ndl_result
        _ndl_ja = _ndl_msg.format_japanese(_ndl_ja_tmpl, _ndl_ph)
        _show_npc_dialog_text(w, chosen.text, _ndl_ja, panel_only=ctx.panel_only_interior_message)
        _log.info('npc_dialog message displayed (route=in_store_resp src=0x%X reason=%s panel_only=%s ptr=%s text=%r ph=%s)', chosen.source_offset, reason, ctx.panel_only_interior_message, _hex_ptr(current_ptr), chosen.text[:80], _ndl_ph)
        return True
    except (ImportError, AttributeError):
        return False

def _poll_route1_instore_response(w, ctx, *, entry_handled: bool, npc_overlay_active: bool, in_interior: bool, npc_phase_raw, facility_active_now: bool, instore_resp_handled: bool, internalized_facility_active: bool=False, shop_menu_visible: bool=False, shop_buy_active: bool=False, shop_state_kind: str='none', negot_handled: bool=False, active_tmpl_handled: bool=False, c_area: str=''):
    if c_area == 'dungeon':
        return (instore_resp_handled, entry_handled)
    _l4_surface_now = internalized_facility_active or shop_menu_visible or shop_buy_active or (shop_state_kind in _SHOP_SURFACE_KINDS) or negot_handled or active_tmpl_handled
    _probe = None

    def _read_probe():
        nonlocal _probe
        if _probe is None:
            _probe = _read_response_probe(w)
        return _probe

    def _has_visible_response_hit() -> bool:
        _cands_probe, _ptr_probe, _contains = _read_probe()
        return any((c.text and c.lookup_hit and _contains(c, _ptr_probe) for c in _cands_probe))
    _prev_poll_shop_kind = getattr(w, '_shop_kind_prev_poll', 'none')
    _facility_response_override = not entry_handled and in_interior and facility_active_now and (_prev_poll_shop_kind in _SHOP_SURFACE_KINDS) and _has_visible_response_hit()
    _route1_active = npc_overlay_active or _facility_response_override
    _route1_surface_allowed = not _l4_surface_now or _facility_response_override
    if not (not entry_handled and _route1_active and in_interior and _route1_surface_allowed):
        if in_interior and npc_overlay_active and entry_handled:
            _log.debug('in_store_resp skipped: _entry_handled=True (phase=0x%s)', f'{npc_phase_raw:02X}' if npc_phase_raw is not None else '??')
        return (instore_resp_handled, entry_handled)
    _cands, _current_ptr, _contains_pointer = _read_probe()
    _text_by_offset = dict(getattr(w, '_instore_resp_text_by_offset', {}))
    _chosen, _chosen_reason, _changed_hits, _ptr_cands = _choose_instore_response(_cands, _current_ptr, _text_by_offset, _contains_pointer, view_response=_facility_response_override and _l4_surface_now)
    for c in _cands:
        if c.text:
            _text_by_offset[c.source_offset] = c.text
    w._instore_resp_text_by_offset = _text_by_offset
    _log_ptr_misses(w, _ptr_cands, _current_ptr)
    if _chosen is None:
        _log_no_display(_cands, _changed_hits, _current_ptr, _contains_pointer, npc_phase_raw, npc_overlay_active, in_interior)
        return (instore_resp_handled, entry_handled)
    _chosen_key = (_chosen.source_offset, _chosen.text)
    if _chosen_key == getattr(w, '_instore_resp_current_key', None):
        _log.debug('in_store_resp held (src=0x%X reason=%s ptr=%s text=%r)', _chosen.source_offset, _chosen_reason, _hex_ptr(_current_ptr), _chosen.text[:60])
        return (instore_resp_handled, entry_handled)
    w._instore_resp_current_key = _chosen_key
    w._instore_resp_prev = _chosen.text
    if _show_instore_response(w, ctx, _chosen, _chosen_reason, _current_ptr):
        instore_resp_handled = True
        entry_handled = True
    return (instore_resp_handled, entry_handled)
INSTORE_DIALOG_OWNER = 'npc_dialog'

def close_on_modal_overlay(w) -> None:
    try:
        w._ui_router.clear_if_owner(INSTORE_DIALOG_OWNER, mode='translate', clear_place_list=True)
    except (AttributeError, RuntimeError):
        pass
__all__ = ['FACILITY_L4_OWNED', 'INSTORE_DIALOG_OWNER', 'close_on_modal_overlay', 'facility_l4_claim', '_poll_route1_instore_response']
