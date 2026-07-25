from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
NPC_MESSAGE_OWNER = 'npc_message'

def _poll_route3_dungeon_msg(w, ctx, *, npc_dialog: str, npc_dialog_changed: bool, facility_active_now: bool, c_area: str) -> bool:
    if npc_dialog and c_area != 'dungeon' and (npc_dialog_changed or ctx.dialog_just_opened or ctx.response_text_on_screen) and (not w._npc_conversation_active) and (not facility_active_now):
        try:
            import dungeon_msg_lookup as _dml
            _npc_ja = _dml.lookup(npc_dialog)
            if _npc_ja:
                _keep = (npc_dialog, _npc_ja)
                if npc_dialog_changed or ctx.dialog_just_opened or (not (getattr(w, '_npc_dialog_keep_key', None) == _keep and w._ui_router.is_owner(NPC_MESSAGE_OWNER))):
                    w._npc_dialog_keep_key = _keep
                    w._ui_router.update_translation(NPC_MESSAGE_OWNER, npc_dialog, _npc_ja, speech_role='situation')
                _log.info('panel_owner -> npc_message (route=dungeon_msg, text=%r)', npc_dialog)
                return True
        except (ImportError, AttributeError):
            pass
    return False

def _poll_route4a_arrival(w, *, npc_dialog: str, npc_dialog_changed: bool, dialog_just_opened: bool, facility_active_now: bool) -> bool:
    _arrival_text = ' '.join(npc_dialog.split()) if npc_dialog else ''
    if _arrival_text.startswith('You have arrived in') and (npc_dialog_changed or dialog_just_opened) and (not facility_active_now):
        try:
            import npc_dialog_lookup as _ndl_arr
            _arr_result = _ndl_arr.lookup(npc_dialog)
            if _arr_result:
                _arr_tmpl, _arr_ph = _arr_result
                _arr_ja = _ndl_arr.format_japanese(_arr_tmpl, _arr_ph)
                w._ui_router.update_translation(NPC_MESSAGE_OWNER, npc_dialog, _arr_ja, speech_role='conversation')
                _log.info('npc_message displayed (route=arrival text=%r)', npc_dialog[:80])
                return True
        except (ImportError, AttributeError):
            pass
    return False

def _clear_travel_event_residue(w) -> None:
    _keep = getattr(w, '_travel_event_keep_key', None)
    if not _keep:
        return
    w._travel_event_keep_key = None
    _en, _ja = _keep
    try:
        if not w._ui_router.is_displaying(NPC_MESSAGE_OWNER, _en, _ja):
            return
        w._ui_router.clear_if_owner(NPC_MESSAGE_OWNER, mode='translate')
    except (AttributeError, RuntimeError):
        pass

def poll_travel_event_lifecycle(w, *, npc_dialog: str, screen_img: str, facility_active_now: bool) -> bool:
    if screen_img != 'HORSE.DFA':
        _clear_travel_event_residue(w)
        return False
    if not npc_dialog or facility_active_now:
        return False
    try:
        import npc_dialog_lookup as _ndl_ev
        _res = _ndl_ev.lookup_travel_event(npc_dialog)
        if not _res:
            return False
        _tmpl, _ph = _res
        _ja = _ndl_ev.format_japanese(_tmpl, _ph)
        _keep = (npc_dialog, _ja)
        if getattr(w, '_travel_event_keep_key', None) != _keep:
            w._travel_event_keep_key = _keep
            w._ui_router.update_translation(NPC_MESSAGE_OWNER, npc_dialog, _ja, speech_role='situation')
            _log.info('npc_message displayed (route=travel_event text=%r)', npc_dialog[:80])
        return True
    except (ImportError, AttributeError):
        return False
__all__ = ['NPC_MESSAGE_OWNER', '_poll_route3_dungeon_msg', '_poll_route4a_arrival', 'poll_travel_event_lifecycle']
