from __future__ import annotations

import logging
from types import SimpleNamespace

from controllers.poll_diag import (
    _checkpoint,
    _phase_record,
    _phase_start,
)
from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("normal_play_render")


def poll_c1_surface_dispatch(
        w, b30, *, npc_dialog_changed, inf_name, mif_name,
        instore_resp_handled):
    from normal_play.trigger_module import (
        poll_red_text as _poll_red_text,
        poll_dialog_close as _poll_dialog_close,
        classify_c1_dialog_substate as _classify_c1_dialog_substate,
    )
    from normal_play.c1_cinematic_module import (
        poll_vision_cinematic as _poll_vision_cinematic,
        poll_death_cinematic as _poll_death_cinematic,
    )
    from normal_play.c1_gold_drop_module import (
        poll_gold_drop as _poll_gold_drop,
    )
    _c1_fg = _classify_c1_dialog_substate(
        w, b30, npc_dialog_changed=npc_dialog_changed)
    w._c1_dialog_foreground = _c1_fg
    _poll_vision_cinematic(w, b30=b30)
    _poll_death_cinematic(w)
    _poll_red_text(w, b30=b30, npc_dialog_changed=npc_dialog_changed,
                   c1_fg=_c1_fg)
    _poll_gold_drop(w, b30=b30, inf_name=inf_name, mif_name=mif_name,
                    c1_fg=_c1_fg)
    _poll_dialog_close(w, b30=b30, npc_dialog_changed=npc_dialog_changed,
                       instore_resp_handled=instore_resp_handled,
                       c1_fg=_c1_fg)


_ASK_ABOUT_MAIN_BLOCKING_LIST_STATES = frozenset({
    "where_is_list",
    "dynamic_place_list",
    "npc_response",
})

_ASK_ABOUT_MENU_PTR_MIN = 0x8000
_ASK_ABOUT_MENU_PTR_MAX = 0x9000
_ASK_ABOUT_MAIN_RECOVERY_STATE = "ask_about_main_recovery"


def blocks_ask_about_main(list_state: str) -> bool:
    return list_state in _ASK_ABOUT_MAIN_BLOCKING_LIST_STATES


def ask_about_main_display_allowed(
        list_state: str, img_name: str, current_ptr: int) -> bool:
    if not blocks_ask_about_main(list_state):
        return True
    if (img_name or "").upper() == "POPUP11.IMG":
        return False
    try:
        ptr = int(current_ptr)
    except (TypeError, ValueError):
        return False
    return _ASK_ABOUT_MENU_PTR_MIN <= ptr < _ASK_ABOUT_MENU_PTR_MAX


def _render_ask_about_main_recovery(w, prev_list_state: str) -> None:
    if prev_list_state != _ASK_ABOUT_MAIN_RECOVERY_STATE:
        w._img_screen._show_ask_about_menu()
    w._popup11_list_state_prev = _ASK_ABOUT_MAIN_RECOVERY_STATE
    w._popup11_exit_pending_ask_about = False


def _classify_popup11_substate(w, _img_name, _list_state_eligible):
    if _list_state_eligible:
        try:
            from popup11_list_detector import (
                detect_popup11_list_state,
                POPUP11_ITEM_COUNT_OFFSET,
                POPUP11_DYN_COUNT_OFFSET,
            )
            _list_state = detect_popup11_list_state(w._analyzer, w._anchor)
            try:
                _ic_raw = w._analyzer.read_bytes(
                    w._anchor + POPUP11_ITEM_COUNT_OFFSET, 1)
                _dc_raw = w._analyzer.read_bytes(
                    w._anchor + POPUP11_DYN_COUNT_OFFSET, 1)
                _item_dyn_now = (_ic_raw[0], _dc_raw[0])
            except (OSError, AttributeError, IndexError):
                _item_dyn_now = (-1, -1)
        except Exception:
            _list_state = "npc_response"
            _item_dyn_now = (-1, -1)
    else:
        _list_state = "npc_response"
        _item_dyn_now = (-1, -1)

    _prev_list_state_for_recovery = getattr(w, "_popup11_list_state_prev", "")
    _prev_item_dyn_for_recovery = getattr(
        w, "_popup11_item_dyn_prev", (-1, -1))
    _item_dyn_changed = (
        _prev_item_dyn_for_recovery != (-1, -1)
        and _prev_item_dyn_for_recovery != _item_dyn_now
    )
    if (_prev_list_state_for_recovery == "npc_response"
            and _list_state == "dynamic_place_list"
            and not _item_dyn_changed):
        w._popup11_ask_recovery = True
    elif _list_state in ("where_is_list", "rumor_type", "npc_response"):
        w._popup11_ask_recovery = False
    elif (_list_state == "dynamic_place_list"
            and _item_dyn_changed):
        w._popup11_ask_recovery = False
    w._popup11_item_dyn_prev = _item_dyn_now

    if w._popup11_ask_recovery and _list_state == "dynamic_place_list":
        _list_state = _ASK_ABOUT_MAIN_RECOVERY_STATE

    try:
        from popup11_response_reader import read_response_candidate
        _resp_cand = read_response_candidate(w._analyzer, w._anchor)
    except Exception:
        _resp_cand = None

    _fresh_response_text = _resp_cand.text if _resp_cand else ""
    _response_lookup_hit = bool(_resp_cand and _resp_cand.lookup_hit)

    _prev_list_state = getattr(w, "_popup11_list_state_prev", "")
    _response_is_new = (
        _fresh_response_text
        and _fresh_response_text != w._npc_dialog_text_prev
    )
    _state_transition_to_response = (
        _list_state == "npc_response"
        and _prev_list_state in ("where_is_list", "dynamic_place_list")
    )

    _diag_resp_off = _resp_cand.source_offset if _resp_cand else -1
    _diag_resp_text = (_resp_cand.text[:48] if _resp_cand else "")
    _diag_key = (
        _img_name, _list_state, _response_lookup_hit,
        _prev_list_state, _diag_resp_off, _diag_resp_text,
    )
    _diag_prev_key = getattr(w, "_cap159_diag_prev", None)
    _diag_changed = (_diag_prev_key != _diag_key)
    if _diag_changed:
        w._cap159_diag_prev = _diag_key

    _stale_list_override = False
    if (_response_lookup_hit
            and _list_state in (
                "where_is_list", "dynamic_place_list")):
        _dyn_count = _item_dyn_now[1] if _item_dyn_now else -1
        _unnatural_dyn = (_dyn_count > 32 or _dyn_count < 0)
        _response_text_changed = (
            _fresh_response_text
            != getattr(w, "_npc_dialog_text_prev", "")
        )
        _fresh_at_npcd = (
            _diag_resp_off == 0x1044
            and bool(_fresh_response_text)
            and _response_text_changed
        )
        if _unnatural_dyn or _fresh_at_npcd:
            _stale_list_override = True
    if _stale_list_override:
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RESPONSE_OVERRIDE_STALE_LIST "
                "img=%r prev_list=%r stale=%r dyn_count=%d "
                "resp_off=0x%X resp_text=%r",
                _img_name, _prev_list_state, _list_state,
                _item_dyn_now[1] if _item_dyn_now else -1,
                _diag_resp_off if _diag_resp_off >= 0 else 0,
                _diag_resp_text)
        _list_state = "npc_response"
    return SimpleNamespace(
        list_state=_list_state,
        prev_list_state=_prev_list_state,
        item_dyn_now=_item_dyn_now,
        diag_resp_off=_diag_resp_off,
        diag_resp_text=_diag_resp_text,
        diag_changed=_diag_changed,
        fresh_response_text=_fresh_response_text,
        response_lookup_hit=_response_lookup_hit,
        response_is_new=_response_is_new,
        state_transition_to_response=_state_transition_to_response,
    )


def _render_popup11_substate(w, _img_name, sub):
    _list_state = sub.list_state
    _prev_list_state = sub.prev_list_state
    _item_dyn_now = sub.item_dyn_now
    _diag_resp_off = sub.diag_resp_off
    _diag_resp_text = sub.diag_resp_text
    _diag_changed = sub.diag_changed
    _fresh_response_text = sub.fresh_response_text
    _response_lookup_hit = sub.response_lookup_hit
    _response_is_new = sub.response_is_new
    _state_transition_to_response = sub.state_transition_to_response

    if _list_state == _ASK_ABOUT_MAIN_RECOVERY_STATE:
        if _diag_changed:
            _log.info(
                "cap162 diag: branch=ASK_MAIN_RECOVERY "
                "img=%r prev_list=%r item_dyn=%r resp_off=0x%X resp_text=%r",
                _img_name, _prev_list_state, _item_dyn_now,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        _render_ask_about_main_recovery(w, _prev_list_state)
    elif _list_state == "rumor_type":
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RUMOR_TYPE "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "rumor_type":
            w._img_screen._show_ask_about_menu()
        w._popup11_list_state_prev = "rumor_type"
    elif _list_state == "where_is_list":
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=WHERE_IS_LIST "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "where_is_list":
            w._img_screen._show_where_is_list()
        w._popup11_list_state_prev = "where_is_list"
    elif _list_state == "dynamic_place_list":
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=DYNAMIC_PLACE_LIST "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "dynamic_place_list":
            w._img_screen._show_dynamic_place_list()
        w._popup11_list_state_prev = "dynamic_place_list"
    elif _response_lookup_hit:
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RESPONSE_LOOKUP_HIT "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        _needs_redraw = (
            _fresh_response_text != w._npc_dialog_text_prev
            or _prev_list_state != "npc_response"
        )
        if _needs_redraw:
            w._npc_dialog_text_prev = _fresh_response_text
            w._img_screen._show_npc_dialog(text_override=_fresh_response_text)
        w._popup11_list_state_prev = "npc_response"
    elif _response_is_new or _state_transition_to_response:
        _confirmed_npc_context = (
            _img_name == "POPUP11.IMG"
            or _prev_list_state in (
                "npc_response", "rumor_type",
                "where_is_list", "dynamic_place_list",
            )
        )
        if _confirmed_npc_context:
            if _diag_changed:
                _log.info(
                    "cap159 diag: branch=RESPONSE_NEW_CONFIRMED "
                    "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                    _img_name, _list_state, _prev_list_state,
                    _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
            if _fresh_response_text:
                w._npc_dialog_text_prev = _fresh_response_text
            w._popup11_list_state_prev = "npc_response"
            w._img_screen._show_npc_dialog(text_override=_fresh_response_text)
        else:
            if _diag_changed:
                _log.info(
                    "cap159 diag: branch=RESPONSE_NEW_UNCONFIRMED "
                    "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                    _img_name, _list_state, _prev_list_state,
                    _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
            _log.debug(
                "NPC response lookup miss in unconfirmed context "
                "(img=%r prev=%r) - skip display: %r",
                _img_name, _prev_list_state, _fresh_response_text[:48])
    else:
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=FALLBACK_NPC_RESPONSE "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        w._popup11_list_state_prev = "npc_response"


def _poll_npc_conversation_foreground(
        w, _img_name, _shop_menu_visible, _shop_buy_active,
        _npc_popup_active, _list_state_eligible, _npc_detection_allowed):
    _sub = (_classify_popup11_substate(w, _img_name, _list_state_eligible)
            if _npc_popup_active else None)
    _predicted_lsp = (
        _sub.list_state if _sub is not None
        else getattr(w, "_popup11_list_state_prev", ""))

    _ok = True
    _city_npc = -1
    try:
        from screen_detector import CITY_NPC_ACTIVE_OFFSET, _read_u16_le
        _city_npc = _read_u16_le(
            w._analyzer, w._anchor + CITY_NPC_ACTIVE_OFFSET)
    except Exception:  # noqa: BLE001
        _ok = False

    _ask_about_active = False
    _cur_ptr = -1
    _ptr_changed = False
    _blocking = False
    _fire = False
    _skip = False
    if _ok:
        _ask_about_active = (
            _city_npc == 0x4385
            and _npc_detection_allowed
            and not _shop_menu_visible
            and not _shop_buy_active
        )
        if _ask_about_active:
            try:
                _ptr_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
                _cur_ptr = _ptr_raw[0] | (_ptr_raw[1] << 8)
            except (OSError, AttributeError, IndexError):
                _cur_ptr = -1
        _ptr_changed = (
            _ask_about_active
            and _cur_ptr != getattr(w, "_ask_about_current_ptr_prev", -1))
        _refire = (
            not w._ask_about_menu_active_prev
            or getattr(w, "_popup11_exit_pending_ask_about", False)
            or _ptr_changed)
        _blocking = blocks_ask_about_main(_predicted_lsp)
        _allowed = ask_about_main_display_allowed(
            _predicted_lsp, _img_name, _cur_ptr)
        _fire = _ask_about_active and _refire and _allowed
        _skip = _ask_about_active and _refire and not _allowed

    if _fire:
        if _blocking:
            w._popup11_list_state_prev = ""
        elif _sub is not None:
            w._popup11_list_state_prev = _predicted_lsp
        w._img_screen._show_ask_about_menu()
        w._popup11_exit_pending_ask_about = False
    elif _npc_popup_active:
        _render_popup11_substate(w, _img_name, _sub)
    if _skip:
        _log.info(
            "cap160 diag: ASK_ABOUT_SKIP "
            "(list_state=%r img=%r ptr=0x%04X ptr_changed=%s)",
            _predicted_lsp, _img_name,
            _cur_ptr if _cur_ptr >= 0 else 0, _ptr_changed)

    if _ok:
        if _ask_about_active:
            w._ask_about_current_ptr_prev = _cur_ptr
        else:
            w._ask_about_current_ptr_prev = -1
        w._ask_about_menu_active_prev = _ask_about_active

        _city_npc_was_nonzero = getattr(
            w, "_city_npc_active_was_nonzero_prev", False)
        if (_current_top_level(w) == "normal-play"
                and _city_npc_was_nonzero and _city_npc == 0):
            w._img_screen._reset_npc_dialog_display()
        w._city_npc_active_was_nonzero_prev = (_city_npc != 0)


def _poll_npc_popup_display(w, _img_name, _shop_menu_visible, _shop_buy_active):
    _NPC_DIALOG_INCOMPATIBLE_SCREENS = frozenset({
        "system_menu", "equipment", "spellbook", "spell_detail",
        "automap", "logbook", "status_page", "bonus_screen", "loading",
    })
    _prev_sid = getattr(w, "_screen_id_prev", None)
    _npc_detection_allowed = (
        _current_top_level(w) == "normal-play"
        and _prev_sid not in _NPC_DIALOG_INCOMPATIBLE_SCREENS
        and w._npc_conversation_active
    )
    _cif_continuation = (
        _img_name.endswith(".CIF")
        and _current_top_level(w) == "normal-play"
        and bool(getattr(w, "_popup11_list_state_prev", ""))
    )
    _npc_popup_active = _npc_detection_allowed and (
        _img_name == "POPUP11.IMG" or _cif_continuation
    )
    try:
        if w._npc_conversation_active and not _npc_popup_active:
            _diag_b263_key = (
                _img_name,
                _npc_detection_allowed,
                _cif_continuation,
                getattr(w, "_popup11_list_state_prev", ""),
            )
            _diag_b263_prev = getattr(
                w, "_b263_npc_popup_active_diag_prev", None)
            if _diag_b263_key != _diag_b263_prev:
                w._b263_npc_popup_active_diag_prev = _diag_b263_key
                _log.info(
                    "npc_popup_active=False during npc_conv "
                    "(img=%r detect_allowed=%s cif_cont=%s "
                    "list_state_prev=%r)",
                    _img_name, _npc_detection_allowed,
                    _cif_continuation,
                    getattr(w, "_popup11_list_state_prev", ""))
    except (AttributeError, OSError):
        pass
    _list_state_eligible = _npc_popup_active and _img_name == "POPUP11.IMG"

    if (not _npc_popup_active and w._npc_conversation_active
            and _current_top_level(w) == "normal-play"):
        try:
            from popup11_response_reader import (
                read_response_candidate as _read_resp_cand_diag,
            )
            _diag_cand = _read_resp_cand_diag(w._analyzer, w._anchor)
            _diag_text = _diag_cand.text if _diag_cand else ""
            _diag_off = _diag_cand.source_offset if _diag_cand else -1
            _diag_hit = bool(
                _diag_cand and _diag_cand.lookup_hit)
            if _diag_text:
                _diag_b263_resp_key = (
                    _diag_off, _diag_hit, _diag_text[:80])
                _diag_b263_resp_prev = getattr(
                    w, "_b263_unpicked_resp_prev", None)
                if _diag_b263_resp_key != _diag_b263_resp_prev:
                    w._b263_unpicked_resp_prev = _diag_b263_resp_key
                    _log.info(
                        "unpicked response candidate "
                        "(img=%r src_off=0x%X lookup_hit=%s "
                        "text=%r)",
                        _img_name,
                        _diag_off if _diag_off >= 0 else 0,
                        _diag_hit, _diag_text[:120])
        except Exception:  # noqa: BLE001
            pass

    _poll_npc_conversation_foreground(
        w, _img_name, _shop_menu_visible, _shop_buy_active,
        _npc_popup_active, _list_state_eligible, _npc_detection_allowed)


_UNIFIED_DISPATCH_FACILITIES = ("equipment", "mages_guild", "temple")


def _unified_facility_node(w):
    try:
        active = w._session_manager.active_session()
    except AttributeError:
        return None
    name = getattr(active, "name", "") if active is not None else ""
    if name not in _UNIFIED_DISPATCH_FACILITIES:
        return None
    from session import facility_nodes  # noqa: F401
    from session.facility_node import get_facility_node
    return get_facility_node(name)


def _poll_compute_temple_gate(w, *, _temple_active_now):
    if _temple_active_now:
        try:
            from temple_dialog_reader import temple_gate_foreground
            (w._temple_menu_fg, w._temple_popup_fg,
             _temple_gate_now) = temple_gate_foreground(
                w, w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            w._temple_menu_fg = False
            w._temple_popup_fg = False
    else:
        w._temple_menu_fg = False
        w._temple_popup_fg = False
        w._temple_gate_stable_value = None
        w._temple_gate_stable_count = 0


def _poll_shared_negotiation_and_template(
        w, *,
        _shop_menu_visible, _shop_buy_active, _shop_img_name,
        _temple_active_now, _tavern_active_now, _tavern_l4_kind,
        _poll_hierarchy_area, _negot_handled, _active_tmpl_handled):
    from normal_play.negotiation_module import (
        poll_negotiation as _poll_negotiation,
        cleanup_if_owner as _cleanup_negotiation,
    )
    if _shop_menu_visible:
        _negot_handled = False
        _cleanup_negotiation(w)
    else:
        _negot_handled = _poll_negotiation(
            w,
            img_name=_shop_img_name,
            top_level_state=_current_top_level(w),
        )
        if not _negot_handled:
            _cleanup_negotiation(w)

    from normal_play.active_template_module import (
        poll_active_template as _poll_active_template,
        cleanup_if_owner as _cleanup_active_template,
    )
    _at_active_facility = (
        "temple" if _temple_active_now
        else "tavern" if _tavern_active_now
        else ""
    )
    if _negot_handled:
        _active_tmpl_handled = False
    else:
        _t_active_tmpl = _phase_start()
        _active_tmpl_handled = _poll_active_template(
            w,
            shop_img_name=_shop_img_name,
            shop_menu_visible=_shop_menu_visible,
            shop_buy_active=_shop_buy_active,
            active_facility=_at_active_facility,
            allow_during_shop_menu=(
                _temple_active_now or _tavern_active_now),
            tavern_l4_kind=_tavern_l4_kind,
            c_area=_poll_hierarchy_area,
        )
        _phase_record(w, "active_template", _t_active_tmpl)
    if not _active_tmpl_handled and not _negot_handled:
        _cleanup_active_template(w)
    return (_negot_handled, _active_tmpl_handled)


def _poll_facility_render_dispatch(
        w, *, _shop_state, _shop_img_name, _facility_tavern, _tview,
        _temple_active_now, _tavern_active_now, _tavern_l4_kind,
        _poll_hierarchy_area, _shop_menu_visible, _shop_buy_active):
    _unified_node = _unified_facility_node(w)
    _closed_facility_active = (_unified_node is not None)
    _poll_compute_temple_gate(w, _temple_active_now=_temple_active_now)
    w._equipment_reply_polled_in_render = False
    w._equipment_reply_handled_in_render = False
    w._mages_reply_polled_in_render = False
    w._mages_reply_handled_in_render = False
    _t_facility_render = _phase_start()
    _negot_handled = False
    _active_tmpl_handled = False
    if _unified_node is not None:
        _uview = _unified_node.classify_view(
            w, shop_state=_shop_state, shop_img_name=_shop_img_name)
        (_negot_handled, _active_tmpl_handled,
         _shop_menu_visible, _shop_buy_active) = _unified_node.render(
            w, view=_uview, shop_state=_shop_state,
            shop_img_name=_shop_img_name,
            top_level_state=_current_top_level(w))
    elif _facility_tavern:
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
        (_negot_handled, _active_tmpl_handled,
         _shop_menu_visible, _shop_buy_active) = _TAVERN_NODE.render(
            w,
            view=_tview,
            shop_state=_shop_state,
            shop_img_name=_shop_img_name,
            top_level_state=_current_top_level(w),
        )
    _phase_record(w, "facility_render", _t_facility_render)
    _checkpoint(w, "facility_render")

    if _unified_node is None and not _facility_tavern:
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE_NS
        (_shop_buy_active, _shop_menu_visible) = (
            _TAVERN_NODE_NS.render_no_session_shop(
                w,
                shop_state=_shop_state,
                shop_img_name=_shop_img_name,
                shop_buy_active=_shop_buy_active,
                shop_menu_visible=_shop_menu_visible,
            ))

        (_negot_handled, _active_tmpl_handled) = (
            _poll_shared_negotiation_and_template(
                w,
                _shop_menu_visible=_shop_menu_visible,
                _shop_buy_active=_shop_buy_active,
                _shop_img_name=_shop_img_name,
                _temple_active_now=_temple_active_now,
                _tavern_active_now=_tavern_active_now,
                _tavern_l4_kind=_tavern_l4_kind,
                _poll_hierarchy_area=_poll_hierarchy_area,
                _negot_handled=_negot_handled,
                _active_tmpl_handled=_active_tmpl_handled,
            ))
    return (_negot_handled, _active_tmpl_handled,
            _shop_menu_visible, _shop_buy_active)


def _poll_l4_dialog_dispatch(
        w, *, in_interior, msg_buf, npc_dialog, _npc_dialog_changed,
        _npc_phase_raw, _img_name_now, _building_entry_active,
        _entry_phase_prev, _shop_state, _shop_img_name,
        _shop_menu_visible, _shop_buy_active,
        _facility_active_now, _poll_hierarchy_area,
        _temple_active_now, _temple_just_started,
        _equipment_active_now, _equipment_just_started,
        _mages_active_now, _mages_just_started,
        _negot_handled, _active_tmpl_handled):
    from arena_bridge import (
        NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING,
        NPC_PHASE_IDLE, NPC_PHASE_ASKING,
    )
    from normal_play.building_entry_module import (
        poll_building_entry as _poll_building_entry,
    )
    _phase_overlay = _npc_phase_raw in (
        NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING)
    _menu_overlay = (
        in_interior
        and _img_name_now == "MENU_RT.IMG"
        and _npc_phase_raw not in (NPC_PHASE_IDLE, NPC_PHASE_ASKING)
    )
    _npc_overlay_active = (
        (_phase_overlay or _menu_overlay)
        and not _building_entry_active
        and not _shop_buy_active
        and not _shop_menu_visible
    )
    _npc_overlay_active_prev = getattr(
        w, "_npc_overlay_active_prev", False)
    w._npc_overlay_active_prev = _npc_overlay_active
    if _npc_overlay_active and not _npc_overlay_active_prev:
        w._instore_resp_prev = ""
        w._instore_resp_current_key = None

    _entry_handled = _poll_building_entry(
        w,
        building_entry_active=_building_entry_active,
        entry_phase_prev=_entry_phase_prev,
        msg_buf=msg_buf,
        npc_dialog=npc_dialog,
    )

    if not _entry_handled:
        from normal_play.palace_dialog_module import (
            poll_palace_dialog as _poll_palace_dialog,
            is_palace_interior_mif as _is_palace_interior_mif,
        )
        _palace_active = (
            in_interior
            and _is_palace_interior_mif(
                getattr(w, "_interior_mif_name", None))
        )
        _poll_palace_dialog(w, palace_active=_palace_active)

    from normal_play.temple_dialog_module import (
        poll_temple_dialog as _poll_temple_dialog,
        reset_temple_reply_on_stop as _reset_temple_reply_on_stop,
    )
    from normal_play.equipment_reply_module import (
        poll_equipment_reply as _poll_equipment_reply,
    )
    from normal_play.mages_reply_module import (
        poll_mages_reply as _poll_mages_reply,
    )
    _temple_shop_owner_now = (
        _shop_state is not None
        and getattr(_shop_state, "owner_kind", "") == "temple"
    )
    _temple_dialog_context = (_temple_active_now or _temple_shop_owner_now)
    _temple_context_prev = getattr(w, "_temple_dialog_context_prev", False)
    if _temple_context_prev and not _temple_dialog_context:
        _reset_temple_reply_on_stop(w)

    _facility_reply_handled = False
    if not _entry_handled and _temple_dialog_context:
        _t_temple_dialog = _phase_start()
        _facility_reply_handled = _poll_temple_dialog(
            w,
            temple_active=True,
            temple_just_started=(
                _temple_just_started
                or (_temple_shop_owner_now and not _temple_context_prev)),
            img_name=_shop_img_name,
            shop_menu_visible=_shop_menu_visible,
            menu_foreground=bool(getattr(w, "_temple_menu_fg", False)),
            popup_foreground=bool(getattr(w, "_temple_popup_fg", False)),
        )
        _phase_record(w, "temple_dialog", _t_temple_dialog)
    elif not _entry_handled and _equipment_active_now:
        if getattr(w, "_equipment_reply_polled_in_render", False):
            _facility_reply_handled = bool(getattr(
                w, "_equipment_reply_handled_in_render", False))
        else:
            _facility_reply_handled = _poll_equipment_reply(
                w,
                equipment_active=True,
                equipment_just_started=_equipment_just_started,
                img_name=_shop_img_name,
                shop_menu_visible=_shop_menu_visible,
            )
    elif not _entry_handled and _mages_active_now:
        if getattr(w, "_mages_reply_polled_in_render", False):
            _facility_reply_handled = bool(getattr(
                w, "_mages_reply_handled_in_render", False))
        else:
            _facility_reply_handled = _poll_mages_reply(
                w,
                mages_active=True,
                mages_just_started=_mages_just_started,
                img_name=_shop_img_name,
                shop_menu_visible=_shop_menu_visible,
            )
    w._temple_dialog_context_prev = _temple_dialog_context
    if _facility_reply_handled:
        _entry_handled = True

    from normal_play.npc_dialog_module import (
        poll_npc_dialog as _poll_npc_dialog,
    )
    _instore_resp_handled = False
    if not _entry_handled:
        _instore_resp_handled = _poll_npc_dialog(
            w,
            entry_handled=False,
            npc_overlay_active=_npc_overlay_active,
            in_interior=in_interior,
            npc_phase_raw=_npc_phase_raw,
            shop_buy_active=_shop_buy_active,
            shop_menu_visible=_shop_menu_visible,
            facility_active_now=_facility_active_now,
            npc_dialog=npc_dialog,
            npc_dialog_changed=_npc_dialog_changed,
            c_area=_poll_hierarchy_area,
            internalized_facility_active=(
                _temple_active_now or _equipment_active_now
                or _mages_active_now),
            shop_state_kind=(
                _shop_state.kind if _shop_state is not None else "none"),
            negot_handled=_negot_handled,
            active_tmpl_handled=_active_tmpl_handled,
        )
        if _instore_resp_handled:
            _entry_handled = True

    if _poll_hierarchy_area == "dungeon" and not _entry_handled:
        from normal_play.c1_runtime_dialog_module import (
            poll_c1_runtime_dialog as _poll_c1_runtime_dialog,
        )
        if _poll_c1_runtime_dialog(
                w,
                npc_dialog=npc_dialog,
                npc_dialog_changed=_npc_dialog_changed,
                facility_active_now=_facility_active_now):
            _instore_resp_handled = True
            _entry_handled = True
    return _entry_handled, _instore_resp_handled


__all__ = [
    "poll_c1_surface_dispatch",
    "blocks_ask_about_main",
    "ask_about_main_display_allowed",
]
