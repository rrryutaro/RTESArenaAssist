from __future__ import annotations

import logging
from types import SimpleNamespace

from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.npc_conversation_module import poll_npc_conversation
from normal_play.npc_message_module import (
    NPC_MESSAGE_OWNER,
    _poll_route3_dungeon_msg,
    _poll_route4a_arrival,
)
from normal_play.instore_dialog_module import (
    _poll_route1_instore_response,
)

_log = logging.getLogger("RTESArenaAssist")

def _build_dialog_context(w, *, in_interior, facility_active_now):
    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0x00
    _dialog_active_now = (_dialog_byte != 0x00)
    _dialog_active_prev = getattr(w, "_b30_dialog_active_prev", False)
    _dialog_just_opened = (_dialog_active_now and not _dialog_active_prev)
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
        _fg_ptr = _fg_raw[0] | (_fg_raw[1] << 8)
        try:
            from active_template_reader import (
                is_response_text_buffer_pointer,
            )
            _response_text_on_screen = (
                _dialog_active_now
                and is_response_text_buffer_pointer(_fg_ptr)
            )
        except Exception:  # noqa: BLE001
            _response_text_on_screen = (
                _dialog_active_now
                and any(start <= _fg_ptr < start + length
                        for start, length in (
                            (0x1044, 512),
                            (0x929E, 512),
                            (0x9A9E, 512),
                        ))
            )
    except (OSError, AttributeError):
        _response_text_on_screen = False

    _panel_only_interior_message = (
        in_interior
        and not facility_active_now
        and not bool(getattr(w, "_npc_conversation_active", False))
    )

    return SimpleNamespace(
        dialog_just_opened=_dialog_just_opened,
        response_text_on_screen=_response_text_on_screen,
        panel_only_interior_message=_panel_only_interior_message,
    )


def _show_npc_dialog_text(w, en: str, ja: str, *, panel_only: bool) -> None:
    if panel_only:
        w._ui_router.update_panel_translation(
            en, ja, speech_role="conversation")
    else:
        w._ui_router.update_translation(
            "npc_dialog", en, ja, speech_role="conversation")


def poll_npc_dialog(w, *, entry_handled: bool,
                    npc_overlay_active: bool, in_interior: bool,
                    npc_phase_raw,
                    shop_buy_active: bool,
                    shop_menu_visible: bool,
                    facility_active_now: bool,
                    npc_dialog: str,
                    npc_dialog_changed: bool = True,
                    c_area: str = "",
                    internalized_facility_active: bool = False,
                    shop_state_kind: str = "none",
                    negot_handled: bool = False,
                    active_tmpl_handled: bool = False) -> bool:
    ctx = _build_dialog_context(
        w, in_interior=in_interior,
        facility_active_now=facility_active_now)

    instore_resp_handled = False

    instore_resp_handled, entry_handled = _poll_route1_instore_response(
        w, ctx,
        entry_handled=entry_handled,
        npc_overlay_active=npc_overlay_active,
        in_interior=in_interior,
        npc_phase_raw=npc_phase_raw,
        facility_active_now=facility_active_now,
        instore_resp_handled=instore_resp_handled,
        internalized_facility_active=internalized_facility_active,
        shop_menu_visible=shop_menu_visible,
        shop_buy_active=shop_buy_active,
        shop_state_kind=shop_state_kind,
        negot_handled=negot_handled,
        active_tmpl_handled=active_tmpl_handled)

    if (not entry_handled
            and _current_top_level(w) == "normal-play"
            and not shop_buy_active
            and not shop_menu_visible):
        if _poll_route3_dungeon_msg(
                w, ctx,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                facility_active_now=facility_active_now,
                c_area=c_area):
            instore_resp_handled = True
        elif _poll_route4a_arrival(
                w,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                dialog_just_opened=ctx.dialog_just_opened,
                facility_active_now=facility_active_now):
            pass
        else:
            poll_npc_conversation(
                w, ctx,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                dialog_just_opened=ctx.dialog_just_opened,
                in_interior=in_interior,
                facility_active_now=facility_active_now,
                npc_translated=False)

    return instore_resp_handled


__all__ = ["poll_npc_dialog", "NPC_MESSAGE_OWNER"]
