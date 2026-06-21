from __future__ import annotations

import logging

from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("RTESArenaAssist")

_RESPONSE_PTR_RANGES = (
    (0x1044, 512),
    (0x7979, 68),
    (0x929E, 512),
    (0x9A9E, 512),
)
_TAVERN_SHOP_L4_KINDS = frozenset({
    "menu", "rooms", "drinks", "rumor_type",
})


def should_poll_active_template(
    *,
    shop_menu_visible: bool,
    shop_buy_active: bool,
    active_facility: str,
    allow_during_shop_menu: bool,
    response_active: bool,
    in_negotiation: bool,
    top_level_state: str,
    tavern_l4_kind: str = "",
) -> bool:
    if (active_facility == "tavern"
            and (tavern_l4_kind or "") in _TAVERN_SHOP_L4_KINDS):
        return False
    return (
        not shop_buy_active
        and (not shop_menu_visible or allow_during_shop_menu)
        and not response_active
        and not in_negotiation
        and top_level_state == "normal-play"
    )


def poll_active_template(w, *, shop_img_name: str,
                         shop_menu_visible: bool,
                         shop_buy_active: bool,
                         active_facility: str,
                         allow_during_shop_menu: bool,
                         tavern_l4_kind: str = "",
                         c_area: str = "") -> bool:
    try:
        _ptr_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
        _ptr_val = _ptr_raw[0] | (_ptr_raw[1] << 8)
    except (OSError, AttributeError):
        _ptr_val = 0
    try:
        from active_template_reader import is_response_buffer_pointer
        _response_active = is_response_buffer_pointer(_ptr_val)
    except Exception:  # noqa: BLE001
        _response_active = any(
            start <= _ptr_val < start + length
            for start, length in _RESPONSE_PTR_RANGES)
    _c1_axis = getattr(w, "_c1_dialog_axis_now", None)
    if _c1_axis is not None and _c1_axis.active:
        _block_key = (
            _c1_axis.a845,
            _c1_axis.a84d,
            _c1_axis.a847,
            _c1_axis.current_ptr,
            _c1_axis.reason,
        )
        if _block_key != getattr(w, "_active_tmpl_c1_axis_block_key", None):
            w._active_tmpl_c1_axis_block_key = _block_key
            _log.info(
                "active_template blocked by C1 dialog axis "
                "(a845=0x%02X a84d=0x%02X a847=0x%02X ptr=%s reason=%s)",
                _c1_axis.a845, _c1_axis.a84d, _c1_axis.a847,
                f"0x{_c1_axis.current_ptr:04X}"
                if _c1_axis.current_ptr is not None else "None",
                _c1_axis.reason or "unknown")
        return False

    try:
        from negotiation_reader import NEGOTIATION_PROFILES as _NPF
        _in_negot = (
            shop_img_name in _NPF
            and (shop_img_name or "").upper() != "YESNO.IMG"
        )
    except Exception:  # noqa: BLE001
        _in_negot = False

    _top_level = _current_top_level(w)
    _gate_ok = should_poll_active_template(
        shop_menu_visible=shop_menu_visible,
        shop_buy_active=shop_buy_active,
        active_facility=active_facility,
        allow_during_shop_menu=allow_during_shop_menu,
        response_active=_response_active,
        in_negotiation=_in_negot,
        top_level_state=_top_level,
        tavern_l4_kind=tavern_l4_kind,
    )
    if not _gate_ok:
        if (active_facility == "tavern"
                and (tavern_l4_kind or "") in _TAVERN_SHOP_L4_KINDS):
            _block_key = (shop_img_name, tavern_l4_kind)
            if _block_key != getattr(w, "_active_tmpl_tavern_l4_block_key",
                                     None):
                w._active_tmpl_tavern_l4_block_key = _block_key
                _log.info(
                    "active_template blocked by tavern L4=%s img=%r",
                    tavern_l4_kind, shop_img_name)
        return False

    try:
        from active_template_reader import (
            read_active_template_candidates,
            read_current_text_pointer,
            candidate_signature,
            select_active_template_candidate,
            template_surface_kind,
        )
        _candidates = read_active_template_candidates(
            w._analyzer, w._anchor)
        _cur_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("active_template_reader failed")
        return False
    try:
        import npc_dialog_lookup as _ndl
    except Exception:  # noqa: BLE001
        _log.exception("npc_dialog_lookup import failed")
        _ndl = None

    _ctx_key = (shop_img_name, _cur_ptr, _top_level)
    _prev_ctx = getattr(w, "_active_tmpl_ctx_prev", None)
    _prev_sigs = getattr(w, "_active_tmpl_sig_prev", frozenset())
    _sigs_now = frozenset(
        candidate_signature(c) for c in _candidates
    )
    w._active_tmpl_ctx_prev = _ctx_key
    w._active_tmpl_sig_prev = _sigs_now

    _active_tmpl: str | None = None
    _ndl_result = None
    _active_tmpl_src: str = ""
    if _ndl is not None and _candidates:
        def _hit(text: str, _ndl=_ndl) -> bool:
            try:
                return _ndl.lookup(text) is not None
            except Exception:  # noqa: BLE001
                return False
        _selected = select_active_template_candidate(
            _candidates,
            ctx_key=_ctx_key,
            prev_ctx_key=_prev_ctx,
            prev_signatures=_prev_sigs,
            lookup_hit=_hit,
            active_facility=active_facility,
            img_name=shop_img_name,
        )
        if _selected is not None:
            try:
                _r = _ndl.lookup(_selected.text)
            except Exception:  # noqa: BLE001
                _r = None
            if _r:
                _active_tmpl = _selected.text
                _ndl_result = _r
                _active_tmpl_src = _selected.source

    if _active_tmpl is None and _candidates:
        try:
            from active_template_reader import (
                input_prompt_facility as _ipf,
            )
        except ImportError:
            _ipf = lambda _c: ""  # noqa: E731
        _log.debug(
            "active_template no-select: img=%r cur_ptr=%s "
            "ctx_changed=%s candidates=%d new_sigs=%d "
            "active_facility=%r",
            shop_img_name,
            f"0x{_cur_ptr:04X}" if _cur_ptr is not None else "None",
            _ctx_key != _prev_ctx,
            len(_candidates), len(_sigs_now - _prev_sigs),
            active_facility)
        for _c in _candidates:
            try:
                _hit_ok = _ndl.lookup(_c.text) is not None if _ndl else False
            except Exception:  # noqa: BLE001
                _hit_ok = False
            _ipf_name = _ipf(_c)
            _log.debug(
                "  candidate src=%s slot=%s ptr=0x%04X "
                "hit=%s input_prompt=%r text=%r",
                _c.source,
                (f"0x{_c.ptr_slot:04X}" if _c.ptr_slot is not None
                 else "None"),
                _c.ptr, _hit_ok, _ipf_name,
                _c.text.rstrip()[:60])

    if _active_tmpl is not None and _ndl_result is not None:
        _ja_tmpl, _ph = _ndl_result
        _ja = _ndl.format_japanese(_ja_tmpl, _ph)
        _tmpl_key = (_active_tmpl, _ja)
        _prev_key = getattr(w, "_active_tmpl_key_prev", None)
        _owner_taken = (w._panel_owner != "active_template")
        if _tmpl_key != _prev_key or _owner_taken:
            w._active_tmpl_key_prev = _tmpl_key
            try:
                w._active_tmpl_surface_kind_prev = (
                    template_surface_kind(_selected) if _selected else "")
            except Exception:  # noqa: BLE001
                w._active_tmpl_surface_kind_prev = ""
            _orig_clean = _active_tmpl.rstrip()
            w._ui_router.update_translation(
                "active_template", _orig_clean, _ja,
                speech_role="situation")
            _log.info(
                "active_template translated: src=%s en=%r ja=%r",
                _active_tmpl_src, _orig_clean[:80], _ja[:80])
        return True
    return False


def cleanup_if_owner(w) -> None:
    if w._ui_router.is_owner("active_template"):
        w._active_tmpl_key_prev = None
        w._active_tmpl_surface_kind_prev = ""
        w._ui_router.clear_if_owner("active_template")
        _log.info("active_template exit")


__all__ = [
    "poll_active_template",
    "cleanup_if_owner",
    "should_poll_active_template",
]
