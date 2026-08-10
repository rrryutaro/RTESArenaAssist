from __future__ import annotations
import logging
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('RTESArenaAssist')

def _container_display_count(w) -> int | None:
    try:
        import viewer_constants as vc
        import loot_records as lr
        container = int.from_bytes(w._analyzer.read_bytes(w._anchor + vc.CURRENT_CONTAINER_OFFSET, 2), 'little')
        if not container:
            return None
        raw = w._analyzer.read_bytes(w._anchor + vc.LOOT_ARRAY_OFFSET, vc.LOOT_RECORD_SIZE * vc.LOOT_RECORD_MAX)
    except (OSError, AttributeError, ImportError):
        return None
    return lr.container_item_count(lr.parse_records(raw), container)

def _corpse_list_state(w) -> bool | None:
    try:
        import viewer_constants as vc
        b = w._analyzer.read_bytes(w._anchor + vc.CORPSE_LIST_STATE_OFFSET, 1)[0]
    except (OSError, AttributeError, ImportError, IndexError):
        return None
    if b == vc.CORPSE_LIST_STATE_CLOSED:
        return True
    if b == vc.CORPSE_LIST_STATE_OPEN:
        return False
    return None

def _display_count(count: int) -> int:
    return max(count - 2, 0)

def _read_names(w, count: int) -> list[str]:
    if count <= 0:
        return []
    try:
        raw = w._analyzer.read_bytes(w._anchor + 37634, count * 48)
    except (OSError, AttributeError):
        return []
    names, pos = ([], 0)
    for _ in range(count):
        end = raw.find(b'\x00', pos)
        if end == -1:
            break
        seg = raw[pos:end]
        if not seg or not all((32 <= b <= 126 for b in seg)):
            break
        nm = seg.decode('ascii').strip()
        if not nm or not any((c.isalnum() for c in nm)):
            break
        names.append(nm)
        pos = end + 1
    return names

def _corpse_item_names(w, head: str) -> list[str]:
    if not head:
        return []
    try:
        import viewer_constants as vc
        import dungeon_msg_lookup as _dml
        raw = w._analyzer.read_bytes(w._anchor + vc.NPC_DIALOG_OFFSET, vc.NPC_DIALOG_MAXLEN)
        limit = vc.CORPSE_LIST_MAX
    except (OSError, AttributeError, ImportError):
        return []
    if not raw:
        return []
    names, pos = ([], 0)
    while len(names) < limit:
        end = raw.find(b'\x00', pos)
        if end == -1:
            break
        seg = raw[pos:end]
        if not seg or not all((32 <= b <= 126 for b in seg)):
            break
        nm = seg.decode('ascii').strip()
        if not nm or not any((c.isalnum() for c in nm)):
            break
        if not _dml.lookup_item(nm):
            break
        names.append(nm)
        pos = end + 1
    if not names or names[0] != head:
        return []
    return names

def _merge_corpse_items(w, names: list[str]) -> tuple[list[dict], int]:
    import dungeon_msg_lookup as _dml
    seen = list(getattr(w, '_b32_seen_items', []) or [])
    now = set(names)
    for it in seen:
        if not it['taken'] and it['en'] not in now:
            it['taken'] = True
    have = {it['en'] for it in seen}
    for n in names:
        if n not in have:
            seen.append({'en': n, 'ja': _dml.lookup_item(n) or '', 'taken': False})
    return (seen, len(names))

def _filter_suffix_fragments(names: list[str]) -> list[str]:
    if not names:
        return []
    filtered: list[str] = []
    for n in names:
        if not n:
            continue
        is_fragment = False
        for m in names:
            if m is n or m == n or len(m) <= len(n):
                continue
            if m.endswith(n):
                prefix_idx = len(m) - len(n)
                if prefix_idx > 0 and m[prefix_idx - 1] != ' ':
                    is_fragment = True
                    break
        if not is_fragment:
            filtered.append(n)
    return filtered

def corpse_item_message(npc_dialog: str) -> bool:
    if not npc_dialog:
        return False
    from controllers.chargen_helpers import _is_garbage_npc_buffer
    if _is_garbage_npc_buffer(npc_dialog):
        return False
    try:
        import dungeon_msg_lookup as _dml
        return bool(_dml.lookup_item(npc_dialog))
    except Exception:
        return False
_BLOCKED_SCREENS = ('equipment', 'spellbook', 'spell_detail', 'status_page', 'bonus_screen')
_CACHE_TTL = 10
_CLOSE_DEBOUNCE_POLLS = 2
_CLOSE_KEEP_OWNER_SCREENS = ('equipment', 'spellbook', 'spell_detail')

def _show_item_pickup(w, items: list[dict], remaining: int) -> None:
    w._ui_router.update_item_pickup_list('item_pickup', items, remaining)

def _clear_item_pickup_owner(w, *, restore_trigger: bool=False) -> None:
    w._ui_router.clear_if_owner('item_pickup', mode='translate')
    if restore_trigger:
        try:
            from normal_play.trigger_module import restore_last_trigger_display
            restore_last_trigger_display(w)
        except (ImportError, AttributeError, RuntimeError) as exc:
            _log.debug('NEWPOP trigger restore skipped: %s', exc)

def _claim_item_pickup_owner(w) -> None:
    w._ui_router.claim_owner('item_pickup', mode='item_pickup')

def _finalize_remaining_taken(w) -> None:
    _seen_final = getattr(w, '_b32_seen_items', []) or []
    _final_changed = False
    for _it in _seen_final:
        if not _it['taken']:
            _it['taken'] = True
            _final_changed = True
    if _final_changed and _seen_final:
        try:
            _show_item_pickup(w, _seen_final, 0)
        except AttributeError:
            pass

def _close_confirmed(w, *, reason: str, img_name: str, count: int, names_present: bool, corpse_item: bool, gate_open: bool, pending: int, screen_id) -> None:
    _log.info('NEWPOP popup CLOSE (img=%r count=%d names_present=%s corpse_item=%s gate_open=%s pending=%d panel_mode=%s panel_owner=%s reason=%s)', (img_name or '').upper(), count, names_present, corpse_item, gate_open, pending, getattr(w._tab_translate, 'panel_mode', lambda: '?')(), w._panel_owner, reason)
    if getattr(w, '_b32_was_corpse', False):
        w._b32_seen_items = []
    w._b32_newpop_open = False
    w._b32_was_corpse = False
    w._b32_pending_close_count = 0
    w._b32_seen_cache_age = 0
    if screen_id not in _CLOSE_KEEP_OWNER_SCREENS:
        _clear_item_pickup_owner(w, restore_trigger=True)

def _gate_close_step(w, *, count: int, names_present: bool, corpse_item: bool, img_name: str, screen_id) -> None:
    _pending = getattr(w, '_b32_pending_close_count', 0) + 1
    w._b32_pending_close_count = _pending
    if _pending < _CLOSE_DEBOUNCE_POLLS:
        _log.info('NEWPOP gate transient-close ignored (pending=%d/%d img=%r count=%d names_present=%s corpse_item=%s)', _pending, _CLOSE_DEBOUNCE_POLLS, (img_name or '').upper(), count, names_present, corpse_item)
        _claim_item_pickup_owner(w)
        return
    _no_content = count == 0 and (not names_present) and (not corpse_item)
    if _no_content:
        _finalize_remaining_taken(w)
    _close_confirmed(w, reason='no-content' if _no_content else 'gate-closed', img_name=img_name, count=count, names_present=names_present, corpse_item=corpse_item, gate_open=False, pending=_pending, screen_id=screen_id)

def _open_transition(w, *, display_n: int, names_present: bool, npc_dialog: str, chest_ready: bool, corpse_ready: bool) -> None:
    import dungeon_msg_lookup as _dml
    _is_corpse = corpse_ready and (not chest_ready)
    if chest_ready:
        _raw_names = _read_names(w, display_n)
        _filtered_names = _filter_suffix_fragments(_raw_names)
        _ignored_fragments = [n for n in _raw_names if n not in _filtered_names]
        _existing = getattr(w, '_b32_seen_items', []) or []
        _ex_untaken_set = {it['en'] for it in _existing if not it['taken']}
        _known_names = [n for n in _filtered_names if n in _ex_untaken_set]
        _unknown_names = [n for n in _filtered_names if n not in _ex_untaken_set]
        _cache_valid_chest = bool(_existing) and (not getattr(w, '_b32_was_corpse', False))
        if _cache_valid_chest and _known_names:
            _seen = list(_existing)
            _new_known_set = set(_known_names)
            for it in _seen:
                if not it['taken'] and it['en'] not in _new_known_set:
                    it['taken'] = True
            _remaining = sum((1 for it in _seen if not it['taken']))
            _log.info('NEWPOP re-OPEN (same chest): known=%s unknown=%s ignored_fragments=%s remaining=%d', _known_names, _unknown_names, _ignored_fragments, _remaining)
        else:
            _seen = [{'en': n, 'ja': _dml.lookup_item(n), 'taken': False} for n in _filtered_names]
            _remaining = len(_filtered_names)
            if _ignored_fragments or _existing:
                _log.info('NEWPOP new chest (raw=%s ignored_fragments=%s ex_untaken=%d known=%d remaining=%d)', _raw_names, _ignored_fragments, len(_ex_untaken_set), len(_known_names), _remaining)
    else:
        _corpse_names = _corpse_item_names(w, npc_dialog)
        if _corpse_names:
            _seen = [{'en': n, 'ja': _dml.lookup_item(n) or '', 'taken': False} for n in _corpse_names]
            _remaining = len(_corpse_names)
        else:
            _seen = [{'en': npc_dialog, 'ja': _dml.lookup_item(npc_dialog) or '', 'taken': False}]
            _remaining = 1
    w._b32_newpop_open = True
    w._b32_seen_items = _seen
    w._b32_was_corpse = _is_corpse
    w._b32_pending_close_count = 0
    w._b32_seen_cache_age = 0
    _show_item_pickup(w, _seen, _remaining)
    _log.info('NEWPOP popup OPEN (%s): %s', 'corpse' if _is_corpse else 'chest', [it['en'] for it in _seen])

def _poll_closed(w, *, gate_open: bool, display_n: int, names_present: bool, npc_dialog: str, corpse_item: bool, blocked: bool, screen_id) -> None:
    if getattr(w, '_b32_seen_items', []):
        _cache_age = getattr(w, '_b32_seen_cache_age', 0) + 1
        w._b32_seen_cache_age = _cache_age
        _cache_clear_reason = ''
        if _cache_age >= _CACHE_TTL:
            _cache_clear_reason = 'ttl'
        elif screen_id in _BLOCKED_SCREENS:
            _cache_clear_reason = 'blocked-screen'
        if _cache_clear_reason:
            _log.info('NEWPOP seen cache cleared (age=%d screen=%s reason=%s)', _cache_age, screen_id, _cache_clear_reason)
            w._b32_seen_items = []
            w._b32_seen_cache_age = 0
    _content_chest_ready = display_n > 0 and names_present
    _content_corpse_ready = corpse_item and _corpse_list_state(w) is not True
    if gate_open and (not blocked) and (_content_chest_ready or _content_corpse_ready):
        _open_transition(w, display_n=display_n, names_present=names_present, npc_dialog=npc_dialog, chest_ready=_content_chest_ready, corpse_ready=_content_corpse_ready)

def _poll_open_chest(w, *, gate_open: bool, container_n: int | None, display_n: int, names_present: bool, count: int, img_name: str, screen_id, corpse_item: bool) -> None:
    if container_n == 0:
        _finalize_remaining_taken(w)
        _close_confirmed(w, reason='all-taken', img_name=img_name, count=count, names_present=names_present, corpse_item=corpse_item, gate_open=gate_open, pending=getattr(w, '_b32_pending_close_count', 0), screen_id=screen_id)
        return
    if not gate_open:
        _gate_close_step(w, count=count, names_present=names_present, corpse_item=corpse_item, img_name=img_name, screen_id=screen_id)
        return
    w._b32_pending_close_count = 0
    _claim_item_pickup_owner(w)
    _disp_prev = getattr(w, '_b32_disp_n_prev', display_n)
    if display_n < _disp_prev and display_n > 0 and names_present:
        _seen = getattr(w, '_b32_seen_items', [])
        _names_now = set(_read_names(w, display_n))
        _changed = False
        for _it in _seen:
            if not _it['taken'] and _it['en'] not in _names_now:
                _it['taken'] = True
                _changed = True
        if _changed:
            _show_item_pickup(w, _seen, display_n)

def _poll_open_corpse(w, *, gate_open: bool, count: int, names_present: bool, npc_dialog: str, corpse_item: bool, img_name: str, screen_id) -> None:
    if _corpse_list_state(w) is True:
        _close_confirmed(w, reason='corpse-state-closed', img_name=img_name, count=count, names_present=names_present, corpse_item=corpse_item, gate_open=gate_open, pending=getattr(w, '_b32_pending_close_count', 0), screen_id=screen_id)
        return
    if not gate_open:
        _gate_close_step(w, count=count, names_present=names_present, corpse_item=corpse_item, img_name=img_name, screen_id=screen_id)
        return
    w._b32_pending_close_count = 0
    _claim_item_pickup_owner(w)
    if not corpse_item:
        return
    _names_now = _corpse_item_names(w, npc_dialog)
    if _names_now:
        _untaken_prev = [it['en'] for it in getattr(w, '_b32_seen_items', []) if not it['taken']]
        if _untaken_prev != _names_now:
            _seen, _remaining = _merge_corpse_items(w, _names_now)
            w._b32_seen_items = _seen
            _show_item_pickup(w, _seen, _remaining)
        return
    if npc_dialog != (w._b32_seen_items[0]['en'] if w._b32_seen_items else ''):
        import dungeon_msg_lookup as _dml2
        _seen = [{'en': npc_dialog, 'ja': _dml2.lookup_item(npc_dialog) or '', 'taken': False}]
        w._b32_seen_items = _seen
        _show_item_pickup(w, _seen, 1)

def poll_item_pickup(w, *, newpop_gate: bool, b30_img_name: str, npc_dialog: str, shop_buy_active: bool, shop_menu_visible: bool, screen_id: str | None=None, facility_active: bool=False, inventory_screen: bool=False) -> None:
    _screen_id = screen_id if screen_id is not None else getattr(w, '_screen_id_prev', None)
    if _current_top_level(w) != 'normal-play':
        if getattr(w, '_b32_newpop_open', False):
            _log.info('NEWPOP state force-closed due to top_level=%s', _current_top_level(w))
            w._b32_newpop_open = False
            w._b32_was_corpse = False
            w._b32_pending_close_count = 0
            _clear_item_pickup_owner(w)
        if getattr(w, '_b32_seen_items', []):
            _log.info('NEWPOP seen cache cleared (reason=top-level top_level=%s)', _current_top_level(w))
            w._b32_seen_items = []
            w._b32_seen_cache_age = 0
        return None
    try:
        _count = w._analyzer.read_bytes(w._anchor + 4082, 1)[0]
    except (OSError, AttributeError):
        _count = 0
    _was_open = getattr(w, '_b32_newpop_open', False)
    _container_n = _container_display_count(w)
    _display_n = _container_n if _container_n is not None else _display_count(_count)
    _names_present = bool(_read_names(w, 1))
    _corpse_item_name = corpse_item_message(npc_dialog)
    if not _was_open:
        _blocked = _screen_id in _BLOCKED_SCREENS or inventory_screen or shop_buy_active or shop_menu_visible or facility_active
        _poll_closed(w, gate_open=newpop_gate, display_n=_display_n, names_present=_names_present, npc_dialog=npc_dialog, corpse_item=_corpse_item_name, blocked=_blocked, screen_id=_screen_id)
    elif getattr(w, '_b32_was_corpse', False):
        _poll_open_corpse(w, gate_open=newpop_gate, count=_count, names_present=_names_present, npc_dialog=npc_dialog, corpse_item=_corpse_item_name, img_name=b30_img_name, screen_id=_screen_id)
    else:
        _poll_open_chest(w, gate_open=newpop_gate, container_n=_container_n, display_n=_display_n, names_present=_names_present, count=_count, img_name=b30_img_name, screen_id=_screen_id, corpse_item=_corpse_item_name)
    w._b32_disp_n_prev = _display_n
__all__ = ['poll_item_pickup', 'corpse_item_message']
