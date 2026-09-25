from __future__ import annotations
import logging
from assist_log import recog as _recog
from screen_detector import POPUP_FRAME_ABSENT_POLLS_TO_END
_log = logging.getLogger('RTESArenaAssist')
NPC_MESSAGE_OWNER = 'npc_message'
_MSG_BUF_OFFSET = 39582
_MSG_BUF_READ = 512
_MSG_CONT_OFFSET = 37534
_MSG_CONT_READ = 512

def _reset_npc_message_popup_tracking(w) -> None:
    w._npc_message_popup_frame_seen = False
    w._npc_message_popup_frame_absent_polls = 0
    w._npc_message_popup_route = ''
    w._npc_message_popup_keep_key = None
    w._npc_message_popup_screen_img = ''

def poll_npc_message_popup_lifetime(w, *, popup_frame, popup_frame_drawn, screen_img: str='') -> bool:
    start_img = str(getattr(w, '_npc_message_popup_screen_img', '') or '')
    current_img = str(screen_img or '').upper()
    surface_ended = bool(start_img and current_img and (current_img != start_img))
    frame_ended = False
    if getattr(w, '_npc_message_popup_frame_seen', False):
        if popup_frame_drawn is True:
            w._npc_message_popup_frame_absent_polls = 0
        elif popup_frame_drawn is False:
            absent = getattr(w, '_npc_message_popup_frame_absent_polls', 0) + 1
            w._npc_message_popup_frame_absent_polls = absent
            frame_ended = absent >= POPUP_FRAME_ABSENT_POLLS_TO_END
    if not surface_ended and (not frame_ended):
        return False
    keep = getattr(w, '_npc_message_popup_keep_key', None)
    if keep:
        try:
            if not w._ui_router.is_displaying(NPC_MESSAGE_OWNER, *keep):
                _reset_npc_message_popup_tracking(w)
                return False
        except (AttributeError, RuntimeError):
            pass
    w._ui_router.notify_display_context_ended(NPC_MESSAGE_OWNER)
    w._ui_router.clear_if_owner(NPC_MESSAGE_OWNER, notify_close=False)
    route = getattr(w, '_npc_message_popup_route', '')
    _reset_npc_message_popup_tracking(w)
    reason = 'screen surface ended' if surface_ended else 'popup frame ended'
    _recog(_log, 'npc_message closed: route=%s reason=%s', route, reason)
    return True

def _remember_npc_message_popup(w, *, popup_frame, frame_drawn, screen_img: str, route: str, keep: tuple[str, str]) -> None:
    w._npc_message_popup_route = route
    w._npc_message_popup_keep_key = keep
    if not getattr(w, '_npc_message_popup_screen_img', '') and screen_img:
        w._npc_message_popup_screen_img = str(screen_img).upper()
    if frame_drawn is True:
        w._npc_message_popup_frame_seen = True
        w._npc_message_popup_frame_absent_polls = 0

def _normalize_msg_text(text: str) -> str:
    return ' '.join(text.split())

def _read_msg_chunks(w, offset: int, length: int, *, stop_after_gap: bool) -> list[str]:
    try:
        raw = w._analyzer.read_bytes(w._anchor + offset, length)
    except (OSError, AttributeError):
        return []
    chunks: list[str] = []
    for seg in raw.split(b'\x00'):
        frag = seg.decode('ascii', errors='replace').strip()
        printable = sum((1 for c in frag if 32 <= ord(c) <= 126))
        if frag and printable / max(len(frag), 1) >= 0.8 and (len(frag) >= 2):
            chunks.append(frag)
        elif chunks and stop_after_gap:
            break
    return chunks

def _build_msg_foreground_candidates(w) -> list[str]:
    chunks = [_normalize_msg_text(c) for c in _read_msg_chunks(w, _MSG_BUF_OFFSET, _MSG_BUF_READ, stop_after_gap=True)]
    chunks = [c for c in chunks if c]
    if not chunks:
        return []
    first = chunks[0]
    candidates = [first]
    if first.endswith(('.', '?', '!')):
        return candidates
    heads = [first]
    if len(chunks) > 1:
        joined = ' '.join(chunks)
        heads.append(joined)
        candidates.append(joined)
    cont_chunks = [_normalize_msg_text(c) for c in _read_msg_chunks(w, _MSG_CONT_OFFSET, _MSG_CONT_READ, stop_after_gap=False)]
    cont_chunks = [c for c in cont_chunks if c]
    if not cont_chunks:
        return candidates
    variants = [' '.join(cont_chunks)]
    if len(cont_chunks) > 1:
        variants.append(' '.join(reversed(cont_chunks)))
    for head in heads:
        for suffix in variants:
            if not suffix or suffix in head:
                continue
            for cand in (f'{head} {suffix}', f'{head}{suffix}'):
                if cand not in candidates:
                    candidates.append(cand)
    return candidates

def _poll_route_msg_foreground(w, ctx, *, in_interior: bool, facility_active_now: bool, c_area: str) -> bool:
    if getattr(ctx, 'npc_message_popup_closed', False):
        return False
    if not getattr(ctx, 'msg_text_on_screen', False):
        return False
    if in_interior or c_area == 'dungeon' or getattr(w, '_npc_conversation_active', False) or facility_active_now:
        return False
    candidates = _build_msg_foreground_candidates(w)
    if not candidates:
        return False
    head = candidates[0]
    try:
        import i18n_helper as _i18n
        _lang = _i18n.current_lang()
    except (ImportError, AttributeError):
        _lang = ''
    cache = getattr(w, '_msg_foreground_cache', None)
    if not (cache and cache[0] == head and (cache[1] == _lang)):
        en = ja = None
        try:
            import npc_dialog_lookup as _ndl
            for cand in candidates:
                res = _ndl.lookup(cand)
                if res:
                    en = cand
                    ja = _ndl.format_japanese(res[0], res[1])
                    break
        except (ImportError, AttributeError):
            return False
        cache = (head, _lang, en, ja)
        w._msg_foreground_cache = cache
    en, ja = (cache[2], cache[3])
    if not en or not ja:
        return False
    _remember_npc_message_popup(w, popup_frame=getattr(ctx, 'popup_frame', None), frame_drawn=getattr(ctx, 'popup_frame_drawn', None), screen_img=getattr(ctx, 'screen_img', ''), route='msg_foreground', keep=(en, ja))
    keep = (en, ja)
    if ctx.dialog_just_opened or getattr(w, '_msg_foreground_keep_key', None) != keep:
        w._msg_foreground_keep_key = keep
        w._ui_router.update_translation(NPC_MESSAGE_OWNER, en, ja, speech_role='situation')
        _log.info('npc_message displayed (route=msg_foreground, text=%r)', en[:80])
    return True

def _poll_route3_dungeon_msg(w, ctx, *, npc_dialog: str, npc_dialog_changed: bool, facility_active_now: bool, c_area: str) -> bool:
    if npc_dialog and c_area != 'dungeon' and (npc_dialog_changed or ctx.dialog_just_opened) and (not w._npc_conversation_active) and (not facility_active_now):
        try:
            import dungeon_msg_lookup as _dml
            _npc_ja = _dml.lookup(npc_dialog)
            if _npc_ja:
                w._ui_router.update_translation(NPC_MESSAGE_OWNER, npc_dialog, _npc_ja, speech_role='situation')
                _remember_npc_message_popup(w, popup_frame=getattr(ctx, 'popup_frame', None), frame_drawn=getattr(ctx, 'popup_frame_drawn', None), screen_img=getattr(ctx, 'screen_img', ''), route='dungeon_msg', keep=(npc_dialog, _npc_ja))
                _log.info('panel_owner -> npc_message (route=dungeon_msg, text=%r)', npc_dialog)
                return True
        except (ImportError, AttributeError):
            pass
    return False

def _poll_route4a_arrival(w, *, npc_dialog: str, npc_dialog_changed: bool, dialog_just_opened: bool, facility_active_now: bool, screen_img: str='', popup_frame=None, popup_frame_drawn=None) -> bool:
    try:
        import npc_dialog_lookup as _ndl_arr
    except ImportError:
        return False
    if _ndl_arr.is_arrival_text(npc_dialog) and (npc_dialog_changed or dialog_just_opened) and (not facility_active_now):
        try:
            _arr_result = _ndl_arr.lookup(npc_dialog)
            if _arr_result:
                _arr_tmpl, _arr_ph = _arr_result
                _arr_ja = _ndl_arr.format_japanese(_arr_tmpl, _arr_ph)
                w._ui_router.update_translation(NPC_MESSAGE_OWNER, npc_dialog, _arr_ja, speech_role='conversation')
                _remember_npc_message_popup(w, popup_frame=popup_frame, frame_drawn=popup_frame_drawn, screen_img=screen_img, route='arrival', keep=(npc_dialog, _arr_ja))
                _log.info('npc_message displayed (route=arrival text=%r)', npc_dialog[:80])
                return True
        except AttributeError:
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

def close_on_modal_overlay(w) -> None:
    try:
        _reset_npc_message_popup_tracking(w)
        w._ui_router.clear_if_owner(NPC_MESSAGE_OWNER, mode='translate', clear_place_list=True)
    except (AttributeError, RuntimeError):
        pass
__all__ = ['NPC_MESSAGE_OWNER', 'close_on_modal_overlay', '_poll_route_msg_foreground', '_poll_route3_dungeon_msg', '_poll_route4a_arrival', 'poll_npc_message_popup_lifetime', 'poll_travel_event_lifecycle']
