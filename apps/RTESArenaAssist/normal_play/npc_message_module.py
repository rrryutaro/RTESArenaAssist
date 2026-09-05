from __future__ import annotations
import logging
_log = logging.getLogger('RTESArenaAssist')
NPC_MESSAGE_OWNER = 'npc_message'
_MSG_BUF_OFFSET = 39582
_MSG_BUF_READ = 512
_MSG_CONT_OFFSET = 37534
_MSG_CONT_READ = 512

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

def close_on_modal_overlay(w) -> None:
    try:
        w._ui_router.clear_if_owner(NPC_MESSAGE_OWNER, mode='translate', clear_place_list=True)
    except (AttributeError, RuntimeError):
        pass
__all__ = ['NPC_MESSAGE_OWNER', 'close_on_modal_overlay', '_poll_route_msg_foreground', '_poll_route3_dungeon_msg', '_poll_route4a_arrival', 'poll_travel_event_lifecycle']
