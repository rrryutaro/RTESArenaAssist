from __future__ import annotations
import logging
from types import SimpleNamespace
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.npc_conversation_module import poll_npc_conversation
from normal_play.npc_message_module import NPC_MESSAGE_OWNER, _poll_route_msg_foreground, _poll_route3_dungeon_msg, _poll_route4a_arrival, poll_npc_message_popup_lifetime
from normal_play.instore_dialog_module import _poll_route1_instore_response
_log = logging.getLogger('RTESArenaAssist')
_POPUP_FRAME_UNSET = object()

def _build_dialog_context(w, *, b30, in_interior, facility_active_now, screen_img: str='', popup_frame=_POPUP_FRAME_UNSET, popup_frame_drawn=_POPUP_FRAME_UNSET, npc_message_popup_closed: bool=False):
    if b30 is None:
        _fg_ptr = None
        _dialog_active_now = False
        _dialog_active_prev = False
    else:
        _fg_ptr = b30.get('fg_ptr')
        _dialog_active_now = bool(b30.get('dialog_text_fg'))
        _dialog_active_prev = bool(b30.get('dialog_text_fg_prev'))
    try:
        from active_template_reader import is_response_text_buffer_pointer, is_message_buffer_pointer
        _response_text_on_screen = is_response_text_buffer_pointer(_fg_ptr)
        _msg_text_on_screen = is_message_buffer_pointer(_fg_ptr)
    except Exception:
        _response_text_on_screen = _fg_ptr is not None and any((start <= _fg_ptr < start + length for start, length in ((4164, 512), (37534, 512), (39582, 512))))
        _msg_text_on_screen = _fg_ptr is not None and 39582 <= _fg_ptr < 39582 + 512
    _dialog_just_opened = _dialog_active_now and (not _dialog_active_prev)
    if popup_frame is _POPUP_FRAME_UNSET or popup_frame_drawn is _POPUP_FRAME_UNSET:
        try:
            from screen_detector import read_popup_frame, popup_frame_is_drawn
            popup_frame = read_popup_frame(w._analyzer, w._anchor)
            popup_frame_drawn = popup_frame_is_drawn(popup_frame)
        except (ImportError, AttributeError, OSError):
            popup_frame = None
            popup_frame_drawn = None
    _panel_only_interior_message = in_interior and (not facility_active_now) and (not bool(getattr(w, '_npc_conversation_active', False)))
    return SimpleNamespace(dialog_just_opened=_dialog_just_opened, response_text_on_screen=_response_text_on_screen, msg_text_on_screen=_msg_text_on_screen, screen_img=str(screen_img or '').upper(), popup_frame=popup_frame, popup_frame_drawn=popup_frame_drawn, npc_message_popup_closed=npc_message_popup_closed, panel_only_interior_message=_panel_only_interior_message)

def _show_npc_dialog_text(w, en: str, ja: str, *, panel_only: bool) -> None:
    if panel_only:
        w._ui_router.update_panel_translation(en, ja, speech_role='conversation')
    else:
        w._ui_router.update_translation('npc_dialog', en, ja, speech_role='conversation')

def _prepare_dialog_context(w, *, b30, in_interior, facility_active_now, popup_observation=_POPUP_FRAME_UNSET):
    if popup_observation is _POPUP_FRAME_UNSET:
        popup_frame = popup_frame_drawn = _POPUP_FRAME_UNSET
        screen_img = ''
        lifetime_polled = closed = False
    else:
        popup_frame, popup_frame_drawn, lifetime_polled, closed, screen_img = popup_observation
    ctx = _build_dialog_context(w, b30=b30, in_interior=in_interior, facility_active_now=facility_active_now, screen_img=screen_img, popup_frame=popup_frame, popup_frame_drawn=popup_frame_drawn, npc_message_popup_closed=closed)
    if not lifetime_polled:
        ctx.npc_message_popup_closed = poll_npc_message_popup_lifetime(w, popup_frame=ctx.popup_frame, popup_frame_drawn=ctx.popup_frame_drawn, screen_img=ctx.screen_img)
    return ctx

def poll_npc_dialog(w, *, b30, entry_handled: bool, npc_overlay_active: bool, in_interior: bool, npc_phase_raw, shop_buy_active: bool, shop_menu_visible: bool, facility_active_now: bool, npc_dialog: str, npc_dialog_changed: bool=True, c_area: str='', internalized_facility_active: bool=False, shop_state_kind: str='none', negot_handled: bool=False, active_tmpl_handled: bool=False, popup_observation=_POPUP_FRAME_UNSET) -> bool:
    ctx = _prepare_dialog_context(w, b30=b30, in_interior=in_interior, facility_active_now=facility_active_now, popup_observation=popup_observation)
    instore_resp_handled = False
    instore_resp_handled, entry_handled = _poll_route1_instore_response(w, ctx, entry_handled=entry_handled, npc_overlay_active=npc_overlay_active, in_interior=in_interior, npc_phase_raw=npc_phase_raw, facility_active_now=facility_active_now, instore_resp_handled=instore_resp_handled, internalized_facility_active=internalized_facility_active, shop_menu_visible=shop_menu_visible, shop_buy_active=shop_buy_active, shop_state_kind=shop_state_kind, negot_handled=negot_handled, active_tmpl_handled=active_tmpl_handled, c_area=c_area)
    if not entry_handled and _current_top_level(w) == 'normal-play' and (not shop_buy_active) and (not shop_menu_visible):
        if _poll_route_msg_foreground(w, ctx, in_interior=in_interior, facility_active_now=facility_active_now, c_area=c_area):
            pass
        elif _poll_route3_dungeon_msg(w, ctx, npc_dialog=npc_dialog, npc_dialog_changed=npc_dialog_changed, facility_active_now=facility_active_now, c_area=c_area):
            instore_resp_handled = True
        elif _poll_route4a_arrival(w, npc_dialog=npc_dialog, npc_dialog_changed=npc_dialog_changed, dialog_just_opened=ctx.dialog_just_opened, facility_active_now=facility_active_now, screen_img=ctx.screen_img, popup_frame=ctx.popup_frame, popup_frame_drawn=ctx.popup_frame_drawn):
            pass
        else:
            poll_npc_conversation(w, ctx, npc_dialog=npc_dialog, npc_dialog_changed=npc_dialog_changed, dialog_just_opened=ctx.dialog_just_opened, in_interior=in_interior, facility_active_now=facility_active_now, npc_translated=False, c_area=c_area)
    return instore_resp_handled
__all__ = ['poll_npc_dialog', 'NPC_MESSAGE_OWNER']
