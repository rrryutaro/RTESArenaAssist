from __future__ import annotations
import os
import struct
import time
import logging
import assist_settings as settings
from assist_log import recog as _recog
import i18n_helper as i18n
import inf_text_lookup as itl
from display_intent import PollFrame
from hierarchy_state import facility_owners_for_session, HierarchyRecognitionInput, SeparationHierarchy
from normal_play.base_location.base_location_view import resolve_area_with_indoor_fallback as _resolve_area_with_indoor_fallback
from controllers.chargen_helpers import _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN, _CHARGEN_GOYENOW_PREFIX, _CHARGEN_GOYENOW_SCAN_START, _CHARGEN_GOYENOW_SCAN_END
from controllers.coord_transition_gate import resolve_coord_transition as _resolve_coord_transition
from controllers.map_fallback_suppression import arm_city_load_fallback_suppression as _arm_city_load_fallback_suppression, city_load_fallback_suppression as _city_load_fallback_suppression
from top_level.normal_play_state import poll_sessions as _poll_normal_play_sessions
from top_level.top_level_dispatcher import build_session_context as _build_session_context, current_state as _current_top_level
from controllers.poll_diag import _checkpoint, _phase_record, _phase_start
_log = logging.getLogger('poll_controller')
_wild_diag_log = logging.getLogger('wild_diag')

def _restore_chargen_cleared_maps(w, tab_map) -> None:
    try:
        tab_map.restore_map()
    except (AttributeError, RuntimeError):
        _log.exception('tab_map.restore_map failed')
    try:
        w._tab_translate.fallback_map_tab().restore_map()
    except (AttributeError, RuntimeError):
        _log.exception('fallback_map.restore_map failed')
_WILD_DIAG_CANDIDATES = [(43092, 'rt_x'), (43094, 'rt_z'), (43096, 'rt_a858'), (43098, 'rt_a85a'), (43084, 'rt_a84c'), (43086, 'rt_a84e'), (43088, 'rt_a850'), (43090, 'rt_a852')]
_wild_diag_prev: dict[int, tuple[int, int]] = {}
_wild_diag_hex_dumped: bool = False

def _dump_wild_diag_hex(analyzer, anchor: int) -> None:
    global _wild_diag_hex_dumped
    if _wild_diag_hex_dumped or anchor is None:
        return
    if analyzer is None:
        return
    _wild_diag_hex_dumped = True
    try:
        raw = analyzer.read_bytes(anchor + 43072, 48)
    except OSError:
        return
    for line_off in range(0, len(raw), 16):
        chunk = raw[line_off:line_off + 16]
        _wild_diag_log.info('wild_diag hex around_rt_xz +0x%04X: %s', 43072 + line_off, ' '.join((f'{b:02X}' for b in chunk)))

def _poll_wild_diagnostic(analyzer, anchor: int) -> None:
    if analyzer is None or anchor is None:
        return
    for off, label in _WILD_DIAG_CANDIDATES:
        try:
            raw = analyzer.read_bytes(anchor + off, 4)
        except OSError:
            continue
        if not raw or len(raw) < 4:
            continue
        u16 = int.from_bytes(raw[:2], 'little')
        u32 = int.from_bytes(raw, 'little')
        prev = _wild_diag_prev.get(off)
        cur = (u16, u32)
        if prev == cur:
            continue
        _wild_diag_prev[off] = cur
        delta_u16 = u16 - prev[0] if prev else None
        _wild_diag_log.info('wild_diag ax+0x%04X %-12s u16=%5d (Δ%s) u32=%d hex=%s', off, label, u16, f'{delta_u16:+d}' if delta_u16 is not None else '?', u32, raw.hex())
_SCREEN_PANEL_PRIORITY = 30

def _normal_play_idle_panel_mode() -> str:
    fallback = settings.get('translate_fallback_screen', 'map')
    if fallback == 'map':
        return 'fallback_map'
    if fallback == 'status':
        return 'fallback_status'
    return 'translate'

def _detect_save_file_write(w) -> bool:
    save_dir = str(settings.get('save_dir', ''))
    if not save_dir or not os.path.isdir(save_dir):
        return False
    sig: dict[str, int] = {}
    try:
        for f in os.listdir(save_dir):
            up = f.upper()
            if up.startswith('SAVEGAME.0') or up.startswith('SAVEENGN.0'):
                try:
                    sig[up] = os.stat(os.path.join(save_dir, f)).st_mtime_ns
                except OSError:
                    pass
    except OSError:
        return False
    prev = getattr(w, '_loadscreen_save_mtimes', None)
    w._loadscreen_save_mtimes = sig
    if prev is None:
        return False
    return sig != prev

def _release_completed_load_screen_owner(w, *, img_name: str, save_detected: bool, loading_active: bool, loading_post_settle: bool, screen_id: str='', npc_idle: bool=True) -> None:
    if _current_top_level(w) != 'normal-play':
        return
    if (getattr(w, '_panel_owner', '') or '') != 'load_screen':
        w._loadscreen_release_pending = False
        return
    if save_detected:
        w._loadscreen_release_pending = True
    pending = bool(getattr(w, '_loadscreen_release_pending', False))
    back_in_idle_gameplay = screen_id == 'game_screen' and npc_idle
    if (img_name or '').upper() == 'LOADSAVE.IMG' and (not (save_detected or pending)) and (not back_in_idle_gameplay):
        return
    if loading_active or loading_post_settle:
        return
    try:
        w._ui_router.claim_owner('', mode=_normal_play_idle_panel_mode(), priority=_SCREEN_PANEL_PRIORITY, reason='loadsave:release')
    except (AttributeError, RuntimeError) as exc:
        _log.debug('load_screen owner release skipped: %s', exc)

def _screen_state_display_active(w) -> bool:
    from panel_mode_resolver import is_screen_state_owner
    return is_screen_state_owner(getattr(w, '_panel_owner', '') or '')
_INTERIOR_KIND_LABEL_SOURCES: dict[str, tuple[str, str | None, str]] = {'TAVERN': ('Inn', 'ask_about_menu', 'ask_about_menu.place_inn.0'), 'TEMPLE': ('Temple', 'ask_about_menu', 'ask_about_menu.place_temple.0'), 'EQUIP': ('Equipment Store', 'ask_about_menu', 'ask_about_menu.place_equipment_store.0'), 'MAGES': ('Mages Guild', 'ask_about_menu', 'ask_about_menu.place_mages_guild.0'), 'PALACE': ('Palace', 'ask_about_menu', 'ask_about_menu.place_palace.0'), 'TOWNPAL': ('Palace', 'ask_about_menu', 'ask_about_menu.place_palace.0'), 'VILPAL': ('Palace', 'ask_about_menu', 'ask_about_menu.place_palace.0'), 'NOBLE': ('Noble House', None, 'place.facility.noble_house'), 'HOUSE': ('House', None, 'place.facility.house'), 'WCRYPT': ('Crypt', None, 'place.facility.crypt'), 'TOWER': ('tower', 'location', 'location.tower.0'), 'BS': ('House', None, 'place.facility.house')}

def _interior_kind_label(interior_mif_name: str | None) -> str:
    if not interior_mif_name:
        return ''
    u = interior_mif_name.upper()
    for prefix, (en, category, label_id) in _INTERIOR_KIND_LABEL_SOURCES.items():
        if u.startswith(prefix):
            label = i18n.value(category, en) if category else None
            if not label:
                label = i18n.lang_value_in(label_id, i18n.current_lang())
            if not label:
                label = i18n.text_opt(label_id)
            return label or en
    return ''

def _format_place_text(state: dict, in_interior: bool, interior_mif_name: str | None, area: str, player_floor: int, interior_facility_name: str | None=None, include_weather: bool=True) -> str:
    location = state.get('location') or ''
    weather = state.get('weather') or '' if include_weather else ''
    try:
        floor_n = int(player_floor) + 1
    except (TypeError, ValueError):
        floor_n = None
    floor_s = f'  {floor_n}F' if floor_n is not None and floor_n > 0 else ''
    if in_interior:
        kind = _interior_kind_label(interior_mif_name)
        name = (interior_facility_name or '').strip()
        if name and kind:
            return f'{location} - {name} ({kind}){floor_s}'.strip()
        if name:
            return f'{location} - {name}{floor_s}'.strip()
        if kind:
            return f'{location} - {kind}{floor_s}'.strip()
        return f'{location}{floor_s}'.strip()
    if area == 'dungeon':
        return f'{location}{floor_s}'.strip()
    if weather:
        return f'{location}  {weather}'.strip()
    return location
from play_area_classifier import detect_play_area as _detect_play_area
_WILDERNESS_FLAG_OFFSET = 19408
_TAVERN_VIEW_DESC_OFFSET = 36718
_TAVERN_VIEW_FLAG_OFFSET = 36724

def _fmt_hex_byte(value) -> str:
    if value is None:
        return 'None'
    try:
        return f'0x{int(value) & 255:02X}'
    except (TypeError, ValueError):
        return repr(value)

def _active_session_name_for_log(w) -> str:
    try:
        active = w._session_manager.active_session()
    except (AttributeError, RuntimeError):
        return ''
    return getattr(active, 'name', '') if active is not None else ''

def _clear_stopped_facility_display(w, session_name: str) -> None:
    try:
        owner = w._ui_router.current_owner()
    except (AttributeError, RuntimeError):
        owner = getattr(w, '_panel_owner', '') or ''
    if owner not in facility_owners_for_session(session_name):
        return
    key = (session_name, owner, getattr(w, '_screen_id_prev', None), getattr(w, '_img_name_prev', '') or '')
    if key != getattr(w, '_b351_facility_stop_clear_key', None):
        w._b351_facility_stop_clear_key = key
        _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r screen=%r img=%r)', session_name, owner, getattr(w, '_screen_id_prev', None), getattr(w, '_img_name_prev', '') or '')
    try:
        w._ui_router.clear_if_owner(owner, mode='translate', clear_place_list=owner in ('npc_dialog', 'npc_conversation', 'npc_message'))
    except (AttributeError, RuntimeError) as exc:
        _log.debug('facility stop display clear skipped: %s', exc)

def _poll_update_npc_conversation_latch(w, *, _facility_active_now, _facility_just_started, _npc_phase_early):
    from arena_bridge import NPC_PHASE_ASKING, NPC_PHASE_IDLE, NPC_PHASE_RESPONDING
    _npc_state_freeze = w._loading_state_active or _facility_active_now
    _npc_state_prev = w._npc_conversation_active
    if _facility_just_started and w._npc_conversation_active:
        _log.info('facility session started → NPC conversation latch forced to False')
        w._npc_conversation_active = False
        _npc_state_prev = False
    if not _npc_state_freeze and _npc_phase_early is not None:
        if _npc_phase_early == NPC_PHASE_ASKING:
            if not _npc_state_prev:
                _log.info('NPC conversation state: False → True (ASKING observed)')
            w._npc_conversation_active = True
        elif _npc_phase_early == NPC_PHASE_IDLE:
            if _npc_state_prev:
                _log.info('NPC conversation state: True → False (IDLE observed)')
            w._npc_conversation_active = False
        elif _npc_phase_early != NPC_PHASE_RESPONDING:
            if w._npc_phase_unknown_prev != _npc_phase_early:
                _log.warning('NPC_PHASE unknown value: 0x%02X', _npc_phase_early)
                w._npc_phase_unknown_prev = _npc_phase_early
    if _npc_state_prev and (not w._npc_conversation_active):
        try:
            w._img_screen._reset_npc_dialog_display()
        except (AttributeError, RuntimeError) as exc:
            _log.debug('NPC state transition reset failed: %s', exc)

def _poll_log_hierarchy_recognition_post_session(w, *, _resolved_area, in_interior, _npc_phase_early, mif_name, _img_name_early, interior_mif_name, interior_raw):
    _hierarchy_area_now = _resolved_area
    _hierarchy_session_name = _active_session_name_for_log(w)
    _hierarchy_npc_active = bool(getattr(w, '_npc_conversation_active', False)) or bool(_hierarchy_session_name)
    _hierarchy_now = SeparationHierarchy.from_parts(top_level_state=_current_top_level(w), c_area=_hierarchy_area_now, in_interior=in_interior, npc_active=_hierarchy_npc_active)
    _log_hierarchy_recognition(w, stage='post_session', hierarchy=_hierarchy_now, decision=HierarchyRecognitionInput(top_level_state=_current_top_level(w), c_area=_hierarchy_area_now, in_interior=in_interior, npc_active=_hierarchy_npc_active, npc_phase=_npc_phase_early, mif_name=mif_name, img_name=_img_name_early, screen_id=getattr(w, '_screen_id_prev', None), panel_owner=getattr(w, '_panel_owner', '') or '', active_session=_hierarchy_session_name, interior_mif_name=interior_mif_name or '', interior_raw=interior_raw))

def _poll_reset_temple_keys_on_img_transition(w, *, _img_name_early, _temple_active_now):
    _temple_img_now = (_img_name_early or '').upper()
    _temple_img_prev = (w._temple_last_img_prev or '').upper()
    _temple_img_transition_to_menu = _temple_active_now and _temple_img_prev == 'YESNO.IMG' and (_temple_img_now == 'MENU_RT.IMG')
    if _temple_img_transition_to_menu:
        w._negot_key_prev = None
        w._active_tmpl_key_prev = None
        w._active_tmpl_ctx_prev = None
        w._negot_prompts_ctx_prev = None
        w._temple_menu_key_prev = None
        w._temple_dialog_current_key = None
        w._temple_dialog_current_text = None
        w._temple_dialog_hold_polls = 0
        _log.info('temple IMG transition YESNO.IMG -> MENU_RT.IMG: owner keys reset for menu redraw')
    w._temple_last_img_prev = _temple_img_now

def _poll_track_facility_latch(w):
    _active_facility_sess = w._session_manager.active_session()
    _active_facility_name = _active_facility_sess.name if _active_facility_sess is not None else ''
    _tavern_active_now = _active_facility_name == 'tavern'
    _tavern_just_started = _tavern_active_now and (not w._tavern_active_prev)
    _tavern_just_stopped = w._tavern_active_prev and (not _tavern_active_now)
    w._tavern_active_prev = _tavern_active_now
    _temple_active_now = _active_facility_name == 'temple'
    _temple_just_started = _temple_active_now and (not w._temple_active_prev)
    _temple_just_stopped = w._temple_active_prev and (not _temple_active_now)
    w._temple_active_prev = _temple_active_now
    _equipment_active_now = _active_facility_name == 'equipment'
    _equipment_just_started = _equipment_active_now and (not w._equipment_active_prev)
    _equipment_just_stopped = w._equipment_active_prev and (not _equipment_active_now)
    w._equipment_active_prev = _equipment_active_now
    _mages_active_now = _active_facility_name == 'mages_guild'
    _mages_just_started = _mages_active_now and (not w._mages_guild_active_prev)
    _mages_just_stopped = w._mages_guild_active_prev and (not _mages_active_now)
    w._mages_guild_active_prev = _mages_active_now
    _facility_active_now = _tavern_active_now or _temple_active_now or _equipment_active_now or _mages_active_now
    _facility_just_started = _tavern_just_started or _temple_just_started or _equipment_just_started or _mages_just_started
    if _tavern_just_stopped:
        _clear_stopped_facility_display(w, 'tavern')
    if _temple_just_stopped:
        _clear_stopped_facility_display(w, 'temple')
    if _equipment_just_stopped:
        _clear_stopped_facility_display(w, 'equipment')
        try:
            from session.equipment_node import EQUIPMENT_NODE
            EQUIPMENT_NODE.on_exit(w)
        except Exception:
            _log.exception('equipment on_exit cleanup failed')
    if _mages_just_stopped:
        _clear_stopped_facility_display(w, 'mages_guild')
        if getattr(w, '_mages_reply_baselined', False):
            from normal_play.mages_reply_module import reset_mages_reply_state as _reset_mages_reply
            _reset_mages_reply(w)
    return (_active_facility_name, _tavern_active_now, _temple_active_now, _temple_just_started, _equipment_active_now, _equipment_just_started, _mages_active_now, _mages_just_started, _facility_active_now, _facility_just_started)

def _poll_resolve_yesno_menu_recovery(w, *, _shop_img_name, _temple_active_now):
    _allow_yesno_menu_recovery = False
    if _shop_img_name == 'YESNO.IMG':
        _popup_surface_active = False
        try:
            from active_template_reader import read_active_template_candidates as _ratc_rec, template_surface_kind as _tsk_rec, input_prompt_facility as _ipf_rec
            for _rc in _ratc_rec(w._analyzer, w._anchor):
                if (_tsk_rec(_rc) or '') or (_ipf_rec(_rc) or ''):
                    _popup_surface_active = True
                    break
        except Exception:
            _popup_surface_active = False
        if _popup_surface_active:
            w._yesno_recovery_empty_polls = 0
        else:
            w._yesno_recovery_empty_polls = getattr(w, '_yesno_recovery_empty_polls', 0) + 1
        _allow_yesno_menu_recovery = getattr(w, '_yesno_recovery_empty_polls', 0) >= 2
        if _temple_active_now:
            try:
                from temple_dialog_reader import classify_temple_phase
                _temple_phase_rec, _ = classify_temple_phase(w._analyzer, w._anchor)
            except Exception:
                _temple_phase_rec = ''
            if _temple_phase_rec == 'menu':
                _allow_yesno_menu_recovery = True
    else:
        w._yesno_recovery_empty_polls = 0
    w._yesno_menu_recovery_last = _allow_yesno_menu_recovery
    return _allow_yesno_menu_recovery

def _poll_detect_shop_state(w, *, _shop_img_name, in_interior, _active_facility_name, _allow_yesno_menu_recovery, area=None):
    try:
        from shop_popup_detector import detect_shop_popup_state
        _active_facility_for_shop = _active_facility_name if _active_facility_name in ('equipment', 'mages_guild', 'temple', 'tavern') else ''
        _shop_state = detect_shop_popup_state(w._analyzer, w._anchor, top_level_state=_current_top_level(w), img_name=_shop_img_name, in_interior=in_interior, screen_id=w._screen_id_prev, allow_yesno_menu_recovery=_allow_yesno_menu_recovery, interior_mif_name=getattr(w, '_interior_mif_name', '') or '', active_facility_name=_active_facility_for_shop, area=area)
    except Exception:
        _log.exception('shop_popup_detector failed')
        _shop_state = None
    return _shop_state

def _poll_classify_tavern_view_and_log(w, *, _shop_state, _shop_img_name, in_interior, _tavern_active_now):
    _shop_kind = _shop_state.kind if _shop_state else 'none'
    w._shop_kind_prev_poll = getattr(w, '_shop_kind_this_poll', 'none')
    w._shop_kind_this_poll = _shop_kind
    _shop_kind_prev = getattr(w, '_shop_kind_prev', None)
    _shop_img_prev = getattr(w, '_shop_img_prev', None)
    _kind_changed = _shop_kind != _shop_kind_prev
    _img_changed = _shop_img_name != _shop_img_prev
    _newpop_unexpected = _shop_img_name == 'NEWPOP.IMG' and _shop_kind in ('none', 'shop_menu')
    _shop_owner_now = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
    _interior_mif_u = (getattr(w, '_interior_mif_name', '') or '').upper()
    _facility_tavern = bool(_tavern_active_now)
    try:
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
        _tview = _TAVERN_NODE.classify_view(w, shop_kind=_shop_kind, shop_owner=_shop_owner_now, img=_shop_img_name, in_interior=in_interior, facility_tavern=_facility_tavern, npc_phase=getattr(w, '_npc_phase', None))
    except Exception:
        _log.exception('tavern view classify failed')
        from session.tavern_view import TavernView as _TVErr
        _tview = _TVErr(l4_kind='none', render_owner='', bar_key='', l4_visible=False, l3_start=False, reason='error')
    w._tavern_view = _tview
    w._tavern_view_l4_visible = _tview.l4_visible
    _tavern_l4_kind = _tview.l4_kind
    _tview_log_key = (_tview.l4_kind, _tview.render_owner, _shop_kind, _shop_owner_now, _shop_img_name, _facility_tavern)
    if _tview.l4_kind != 'none' and _tview_log_key != getattr(w, '_tview_log_key', None):
        w._tview_log_key = _tview_log_key
        _log.info('tavern view l4=%s owner=%s reason=%s (shop_kind=%s shop_owner=%r img=%r fac_tav=%s)', _tview.l4_kind, _tview.render_owner, _tview.reason, _shop_kind, _shop_owner_now, _shop_img_name, _facility_tavern)
    if _shop_state is not None and (_kind_changed or _img_changed or _newpop_unexpected):
        _log.info('shop_state kind=%s img=%r screen=%r interior=%s ptr=%s ptr_hi=%s b7c4=%s ff2=%s menu_span=%s buy_span=%s menu_items=%r buy_count=%d panel_owner=%r prev_kind=%r reason=%r', _shop_state.kind, _shop_state.img_name, _shop_state.screen_id, _shop_state.in_interior, f'0x{_shop_state.ptr:04X}' if _shop_state.ptr is not None else '?', f'0x{_shop_state.ptr_hi:02X}' if _shop_state.ptr_hi is not None else '?', f'0x{_shop_state.b7c4:02X}' if _shop_state.b7c4 is not None else '?', f'0x{_shop_state.ff2:02X}' if _shop_state.ff2 is not None else '?', f'[0x{_shop_state.menu_span[0]:X},0x{_shop_state.menu_span[1]:X})' if _shop_state.menu_span else 'None', f'[0x{_shop_state.buy_span[0]:X},0x{_shop_state.buy_span[1]:X})' if _shop_state.buy_span else 'None', _shop_state.menu_items[:8], len(_shop_state.buy_items), w._panel_owner, _shop_kind_prev, _shop_state.reason)
        w._shop_kind_prev = _shop_kind
        w._shop_img_prev = _shop_img_name
    return (_tview, _tavern_l4_kind, _facility_tavern)

def _poll_detect_dungeon_entry(w, *, mif_name):
    _post_chargen_reached = w._chargen_opening_displayed or bool(w._chargen_opening_text_prev)
    if mif_name and mif_name.lower() == 'start.mif' and (not w._dungeon_entry_cleared):
        if _current_top_level(w) == 'chargen' and _post_chargen_reached:
            w._transition_top_level('normal-play', 'start.mif in chargen (post-chargen)')
        if _post_chargen_reached:
            w._dungeon_entry_cleared = True
            w._chargen_opening_retry = 0
            w._chargen_opening_text_prev = ''
            w._set_chargen_ui_state(False)
            w._ui_router.clear_display('')
            try:
                w._chargen._reset_chargen_state_for_restart(reason='start.mif restart (dungeon entry, chargen end)')
            except (AttributeError, RuntimeError) as exc:
                _log.debug('chargen reset on start.mif skipped: %s', exc)
            _log.info('dungeon: start.mif entry detected, cinematic cleared')
    elif mif_name and mif_name.lower() != 'start.mif':
        w._dungeon_entry_cleared = False

def _poll_compute_newpop_gate(w, *, npc_dialog):
    try:
        _newpop_img_now = w._analyzer.read_bytes(w._anchor + 37238, 12).split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
        _newpop_gate_byte = w._analyzer.read_bytes(w._anchor + 47044, 1)[0]
        _newpop_gate = _newpop_img_now == 'NEWPOP.IMG' and _newpop_gate_byte == 0
    except (OSError, AttributeError):
        _newpop_gate = False
    from normal_play.item_pickup_module import corpse_item_message
    _is_corpse_loot = bool(_newpop_gate and corpse_item_message(npc_dialog))
    return (_newpop_gate, _is_corpse_loot)

def _resolve_dungeon_level(w, mif_name: str | None) -> int | None:
    if not mif_name:
        return None
    try:
        import dungeon_level as dl
        identity = dl.read_level_identity(w._analyzer, w._anchor)
        if identity is None:
            return None
        if identity.get('mif', '').strip().lower() != str(mif_name).strip().lower():
            return None
        cache = getattr(w, '_dungeon_level_names_cache', None)
        if not cache or cache.get('mif') != mif_name:
            from services.mif_loader import DEFAULT_MIF_DIR, load_mif
            from runtime_paths import resolve_arena_install_dir
            dirs = [d for d in (DEFAULT_MIF_DIR, resolve_arena_install_dir()) if d is not None]
            head = load_mif(mif_name, dirs)
            if head is None:
                return None
            names: list[str] = []
            infs: list[str] = []
            want = max(int(head.level_count or 1), 1)
            for i in range(want):
                lv = load_mif(mif_name, dirs, level_index_override=i)
                if lv is None:
                    break
                names.append(lv.mif_name or '')
                infs.append(lv.info_name or '')
            if len(names) < want:
                return None
            cache = {'mif': mif_name, 'names': names, 'infs': infs}
            w._dungeon_level_names_cache = cache
        if len(cache.get('names') or []) <= 1:
            return None
        return dl.match_level_index(identity, cache['names'], cache['infs'])
    except Exception:
        return None

def _dungeon_floor_with_hold(dungeon_level_hyp: int | None, display_mif_name: str | None, held: tuple[str, int] | None) -> tuple[int | None, tuple[str, int] | None]:
    if dungeon_level_hyp is not None:
        if display_mif_name:
            return (dungeon_level_hyp, (display_mif_name, dungeon_level_hyp))
        return (dungeon_level_hyp, held)
    if held is not None and display_mif_name and (held[0] == display_mif_name):
        return (held[1], held)
    return (None, None)

def reset_map_progress_on_load(w) -> None:
    for tab in (getattr(w, '_tab_map', None), _fallback_map_tab_or_none(w)):
        if tab is None:
            continue
        try:
            tab.reset_progress()
        except (AttributeError, RuntimeError):
            _log.exception('reset_progress failed on load')

def _fallback_map_tab_or_none(w):
    try:
        return w._tab_translate.fallback_map_tab()
    except (AttributeError, RuntimeError):
        return None

def reset_floor_holds_on_load(w) -> None:
    w._dungeon_level_held = None
    w._interior_floor_held = None

def _poll_handle_triggers(w, *, rt_x, rt_z, inf_name):
    try:
        from tts_prewarm import prewarm_dungeon_inf
        prewarm_dungeon_inf(w, inf_name)
    except Exception:
        pass
    from arena_bridge import check_trigger_flag
    body, trigger_flag, trigger_idx, _n, trigger_slot = check_trigger_flag(w._analyzer, w._anchor, w._trigger_flag_prev, w._trigger_indices, w._cached_trig_idx)
    old_flag = w._trigger_flag_prev
    _new_trigger = trigger_flag > old_flag and (not getattr(w, '_npc_conversation_active', False))
    _trig_fell = old_flag != 0 and trigger_flag == 0
    if _new_trigger:
        w._cached_rt_x = rt_x
        w._cached_rt_z = rt_z
        w._cached_trig_idx = trigger_idx
    w._trigger_flag_prev = trigger_flag
    from normal_play.trigger_module import poll_trigger as _poll_trigger
    _poll_trigger(w, new_trigger=_new_trigger, trig_fell=_trig_fell, trigger_flag=trigger_flag, trigger_idx=trigger_idx, trigger_slot=trigger_slot, body=body, inf_name=inf_name)

def _poll_status_template_parse(w, *, _entry_handled):
    try:
        from template_parser import parse_filled, render_status, status_popup_foreground
        _status_fg = status_popup_foreground(w._analyzer, w._anchor)
        _status_fg_was = getattr(w, '_b21_status_fg_was', False)
        try:
            _flag_popup = w._analyzer.read_bytes(w._anchor + 31012, 1)[0]
        except (OSError, AttributeError):
            _flag_popup = 0
        _popup_active = _flag_popup == 1
        _popup_was = getattr(w, '_b21_popup_was_open', False)
        if _status_fg_was and (not _status_fg) or (_popup_was and (not _popup_active)):
            if getattr(w, '_b21_owns_panel', False):
                w._ui_router.clear_if_owner('status')
                w._b21_owns_panel = False
                w._last_status_vkey = None
        w._b21_popup_was_open = _popup_active
        w._b21_status_fg_was = _status_fg
        _parsed = parse_filled(w._analyzer, w._anchor)
        if _parsed is not None:
            _vkey = (_parsed.get('location', ''), _parsed.get('time', ''), _parsed.get('date', ''), _parsed.get('weight', ''), _parsed.get('weight_max', ''), _parsed.get('states', ()))
            _full_en, _full_ja, _ = render_status(_parsed)
            if _status_fg and (not _entry_handled) and (_vkey != getattr(w, '_last_status_vkey', None)):
                w._last_status_vkey = _vkey
                w._ui_router.update_translation('status', _full_en, _full_ja)
                w._b21_owns_panel = w._ui_router.is_owner('status')
    except (ImportError, AttributeError, OSError):
        pass

def _propose_automap_screen_mode(w, *, screen_id_stable, top_level):
    try:
        if screen_id_stable == 'automap' and top_level == 'normal-play':
            w._ui_router.set_panel_mode('map_screen', priority=_SCREEN_PANEL_PRIORITY, reason='screen:automap')
            w._automap_mode_active = True
        elif getattr(w, '_automap_mode_active', False):
            w._ui_router.set_panel_mode('translate', reason='screen:automap_exit')
            w._automap_mode_active = False
    except (AttributeError, RuntimeError):
        pass

def _poll_detect_img_name(w):
    try:
        from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
        _raw_img = w._analyzer.read_bytes(w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        _img_name = _raw_img.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
    except (OSError, ImportError):
        _img_name = ''
    w._img_name_lbl.setText(_img_name)
    if _img_name != w._img_name_prev:
        w._img_name_prev = _img_name
        if _img_name:
            w._img_screen.on_img_name_changed(_img_name)
        if _img_name != 'POPUP11.IMG' and (not (_img_name.endswith('.CIF') and _current_top_level(w) == 'normal-play')):
            w._npc_dialog_text_prev = ''
            if getattr(w, '_popup11_list_state_prev', ''):
                w._popup11_exit_pending_ask_about = True
            w._popup11_list_state_prev = ''
            w._popup11_place_response_lock = None
    return _img_name

def _resolve_field_facility(w, interior_raw):
    try:
        from normal_play.base_location.base_location_view import resolve_field_facility_entry
    except ImportError:
        return (False, None, '', None)
    tab_map = getattr(w, '_tab_map', None)
    disp = getattr(tab_map, '_dispatcher', None) if tab_map is not None else None
    wild = getattr(disp, 'wilderness', None) if disp is not None else None
    if wild is None:
        return (False, None, '', None)
    try:
        hint = wild.field_entrance_hint()
    except (AttributeError, RuntimeError):
        hint = None
    if hint is None:
        return (False, None, '', None)
    try:
        from play_area_classifier import _WILDERNESS_FLAG_OFFSET
        wild_flag = w._analyzer.read_bytes(w._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
    except (OSError, AttributeError):
        wild_flag = 0
    active, mif, label = resolve_field_facility_entry(hint, interior_flag_nonzero=bool(interior_raw), wild_flag=wild_flag)
    facility_name = None
    if active:
        facility_name = getattr(hint, 'name_ja', None) or getattr(hint, 'name_en', '') or None
    return (active, mif, label, facility_name)

def _poll_resolve_interior_entry(w, *, in_interior, rt_x, rt_z, interior_raw, mif_name, gs):
    try:
        from arena_bridge import SCREEN_IMG_OFFSET as _SI_OFF_SAFE, SCREEN_IMG_MAXLEN as _SI_LEN_SAFE
        _img_raw_safe = w._analyzer.read_bytes(w._anchor + _SI_OFF_SAFE, _SI_LEN_SAFE)
        _img_safe = _img_raw_safe.split(b'\x00')[0].decode('ascii', errors='ignore').upper()
    except Exception:
        _img_safe = ''
    if not in_interior and rt_x is not None and (rt_z is not None):
        w._last_outside_rt = (rt_x, rt_z)
    prev_in_interior = getattr(w, '_in_interior_prev', False)
    _just_entered_interior = in_interior and (not prev_in_interior)
    if _just_entered_interior:
        w._entry_door_pos = getattr(w, '_last_outside_rt', None)
        w._building_entry_pending = True
        w._b288_entry_diag_count = 0
        _log.info('interior entered, door_pos=%s map=%s interior_raw=%s', getattr(w, '_entry_door_pos', None), gs.get('MapName'), interior_raw)
    if not in_interior and prev_in_interior:
        _log.info('interior left')
        w._entry_door_pos = None
        w._instore_resp_prev = ''
        w._instore_resp_current_key = None
        w._instore_resp_text_by_offset = {}
        w._building_entry_pending = False
    w._in_interior_prev = in_interior
    display_mif_name = mif_name
    interior_mif_name: str | None = None
    interior_facility_name: str | None = None
    if in_interior:
        door_pos = getattr(w, '_entry_door_pos', None)
        location_name = gs.get('MapName') or ''
        if door_pos is not None and location_name:
            try:
                from city_viewer_bridge import lookup_interior_facility
                facility_info = lookup_interior_facility(location_name, door_pos[0], door_pos[1])
            except Exception:
                _log.exception('city_viewer_bridge lookup failed')
                facility_info = None
            if facility_info is not None and facility_info.mif_name:
                interior_mif_name = facility_info.mif_name
                interior_facility_name = facility_info.name_ja or facility_info.name_en or None
                display_mif_name = interior_mif_name
            if getattr(w, '_entry_door_logged', None) != door_pos:
                w._entry_door_logged = door_pos
                try:
                    from city_viewer_bridge import describe_entered_door
                    _log.info('interior door: pos=%s %s -> mif=%r name=%r', door_pos, describe_entered_door(location_name, *door_pos), interior_mif_name, interior_facility_name)
                except Exception:
                    pass
        if interior_mif_name is None and location_name and (_img_safe == 'PALACE.XMI'):
            try:
                from services.city_lookup import get_palace_mif_for_location
                _palace_mif = get_palace_mif_for_location(location_name)
            except Exception:
                _log.exception('palace mif fallback failed')
                _palace_mif = None
            if _palace_mif:
                interior_mif_name = _palace_mif
                display_mif_name = _palace_mif
                _log.info('palace mif resolved door-free: %s (img=PALACE.XMI)', _palace_mif)
    effective_in_interior = in_interior
    field_active, field_mif, _field_label, field_name = _resolve_field_facility(w, interior_raw)
    if field_active and field_mif:
        interior_mif_name = field_mif
        display_mif_name = field_mif
        interior_facility_name = field_name
        effective_in_interior = True
    _cur_location = gs.get('MapName') or ''
    _prev_location = getattr(w, '_interior_location_name', '')
    if _cur_location and _prev_location and (_cur_location != _prev_location):
        if getattr(w, '_interior_mif_name', None):
            _log.info('interior facility memory dropped: location %r -> %r', _prev_location, _cur_location)
        w._interior_mif_name = None
        w._interior_facility_name = None
        w._entry_door_pos = None
    if effective_in_interior and (not field_active):
        if interior_facility_name is None:
            interior_facility_name = getattr(w, '_interior_facility_name', None)
        if interior_mif_name is None:
            interior_mif_name = getattr(w, '_interior_mif_name', None)
            if interior_mif_name:
                display_mif_name = interior_mif_name
    w._interior_mif_name = interior_mif_name
    w._interior_facility_name = interior_facility_name
    if _cur_location:
        w._interior_location_name = _cur_location
    if interior_facility_name:
        w._log_location_hint = interior_facility_name
    else:
        try:
            _mn = gs.get('MapName') or ''
            if _mn:
                import location_lookup as _loc_ll
                w._log_location_hint = _loc_ll.lookup(_mn) or _mn
            else:
                w._log_location_hint = ''
        except Exception:
            pass
    _checkpoint(w, 'interior_facility')
    return (display_mif_name, interior_mif_name, interior_facility_name, _just_entered_interior, effective_in_interior, field_active)

def _poll_chargen_normal_play_transition(w, *, mif_name, _img_name_early):
    from arena_bridge import CHARGEN_DONE_OFFSET
    try:
        from top_level.chargen_transition import normal_play_entry_reason
        try:
            _chargen_done_live_for_top = w._analyzer.read_bytes(w._anchor + CHARGEN_DONE_OFFSET, 1)[0]
        except (OSError, AttributeError):
            _chargen_done_live_for_top = getattr(w, '_chargen_done_prev', 0)
        _post_chargen_reached_early = getattr(w, '_chargen_opening_displayed', False) or bool(getattr(w, '_chargen_opening_text_prev', ''))
        _chargen_normal_reason = normal_play_entry_reason(top_level_state=_current_top_level(w), mif_name=mif_name, img_name=_img_name_early, post_chargen_reached=_post_chargen_reached_early, chargen_done=_chargen_done_live_for_top)
        if _chargen_normal_reason:
            w._transition_top_level('normal-play', _chargen_normal_reason)
            w._chargen_opening_retry = 0
            w._chargen_opening_text_prev = ''
            w._set_chargen_ui_state(False)
            try:
                w._chargen._reset_chargen_state_for_restart(reason='normal-play transition')
            except (AttributeError, RuntimeError) as exc:
                _log.debug('chargen reset on normal-play transition skipped: %s', exc)
            try:
                w._ui_router.clear_display('')
            except (AttributeError, RuntimeError) as exc:
                _log.debug('chargen clear on normal-play transition skipped: %s', exc)
            if (mif_name or '').lower() == 'start.mif':
                w._dungeon_entry_cleared = True
            _log.info('chargen: normal-play transition (%s, img=%r)', _chargen_normal_reason, _img_name_early)
    except Exception:
        _log.exception('chargen normal-play transition failed')

def _poll_resolve_loading_state(w, *, _img_name_early):
    _img_name_early_upper = (_img_name_early or '').upper()
    _loadsave_now = _img_name_early_upper == 'LOADSAVE.IMG'
    _loadsave_prev = w._loading_loadsave_seen_prev
    if _loadsave_now:
        w._loading_state_active = False
        w._loading_state_post_remaining = 0
    elif _loadsave_prev:
        if _img_name_early_upper == 'OP.IMG':
            w._loading_state_active = False
            w._loading_state_post_remaining = 0
        else:
            w._loading_state_active = True
            w._loading_state_post_remaining = 8
    elif w._loading_state_post_remaining > 0:
        w._loading_state_post_remaining -= 1
        w._loading_state_active = w._loading_state_post_remaining > 0
    else:
        w._loading_state_active = False
    w._loading_loadsave_seen_prev = _loadsave_now
    _load_edge_start = w._loading_state_active and (not getattr(w, '_loading_state_active_prev', False))
    _loading_post_settle_remaining = getattr(w, '_loading_post_settle_remaining', 0)
    if _load_edge_start:
        _loading_post_settle_remaining = 4
    elif _loading_post_settle_remaining > 0:
        _loading_post_settle_remaining -= 1
    w._loading_post_settle_remaining = _loading_post_settle_remaining
    _loading_post_settle = _loading_post_settle_remaining > 0
    if _load_edge_start:
        _arm_city_load_fallback_suppression(w)
    try:
        _a845_for_release = w._analyzer.read_bytes(w._anchor + 43077, 1)[0]
    except (OSError, AttributeError, IndexError):
        _a845_for_release = 0
    _release_completed_load_screen_owner(w, img_name=_img_name_early_upper, save_detected=_detect_save_file_write(w), loading_active=w._loading_state_active, loading_post_settle=_loading_post_settle, screen_id=getattr(w, '_screen_id_prev', '') or '', npc_idle=_a845_for_release == 0)
    w._loading_state_active_prev = w._loading_state_active
    return (_img_name_early_upper, _load_edge_start, _loading_post_settle)

def _poll_resolve_area_and_frame(w, *, mif_name, in_interior, ui_router, field_facility_active=False):
    _resolved_area = ''
    if field_facility_active:
        _resolved_area = 'wilderness'
    elif _current_top_level(w) == 'normal-play':
        _resolved_area, w._last_non_interior_area = _resolve_area_with_indoor_fallback(w._analyzer, w._anchor, mif_name, in_interior=in_interior, last_non_interior_area=getattr(w, '_last_non_interior_area', ''))
    _poll_hierarchy_area = _resolved_area
    _poll_hierarchy = SeparationHierarchy.from_parts(top_level_state=_current_top_level(w), c_area=_poll_hierarchy_area, in_interior=in_interior, npc_active=bool(getattr(w, '_npc_conversation_active', False)))
    if ui_router is not None:
        ui_router.begin_poll_frame(PollFrame.from_window(w, hierarchy=_poll_hierarchy))
    return (_resolved_area, _poll_hierarchy_area)

def _poll_read_game_state(w):
    from arena_bridge import read_game_state, interpret_location, RT_COORD_X_OFFSET, RT_COORD_Z_OFFSET, read_interior_flag
    from play_area_classifier import resolve_in_interior
    gs = read_game_state(w._analyzer, w._anchor)
    try:
        rt_x = struct.unpack_from('<H', w._analyzer.read_bytes(w._anchor + RT_COORD_X_OFFSET, 2))[0]
        rt_z = struct.unpack_from('<H', w._analyzer.read_bytes(w._anchor + RT_COORD_Z_OFFSET, 2))[0]
    except OSError:
        rt_x = rt_z = None
    interior_raw = read_interior_flag(w._analyzer, w._anchor)
    try:
        place_byte = w._analyzer.read_bytes(w._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
    except (OSError, IndexError, AttributeError):
        place_byte = None
    _mif_for_interior = gs.get('LiveMifName') or gs.get('MifName') or ''
    in_interior = resolve_in_interior(interior_raw, place_byte, _mif_for_interior)
    w._in_interior = in_interior
    w._interior_raw = interior_raw
    _checkpoint(w, 'gamestate')
    state = interpret_location(gs)
    if rt_x is not None:
        state['x'] = rt_x
        state['z'] = rt_z
    state['in_interior'] = in_interior
    state['interior_raw'] = interior_raw
    w._tab_translate.update_game_state(state)
    inf_name = (gs.get('InfName') or '').upper()
    mif_name = gs.get('LiveMifName') or gs.get('MifName') or ''
    player_floor = gs.get('PlayerFloor') or 0
    w._active_mif = mif_name
    return (gs, rt_x, rt_z, in_interior, interior_raw, state, inf_name, mif_name, player_floor)

def _poll_read_npc_phase_and_img(w):
    try:
        from active_template_reader import read_current_text_pointer
        _foreground_ptr_early = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:
        _foreground_ptr_early = None
    _npc_phase_early = _foreground_ptr_early >> 8 & 255 if isinstance(_foreground_ptr_early, int) else None
    w._npc_phase = _npc_phase_early
    try:
        from arena_bridge import SCREEN_IMG_OFFSET as _SI_OFF_E, SCREEN_IMG_MAXLEN as _SI_LEN_E
        _img_raw_early = w._analyzer.read_bytes(w._anchor + _SI_OFF_E, _SI_LEN_E)
        _img_name_early = _img_raw_early.split(b'\x00', 1)[0].decode('ascii', errors='replace')
    except Exception:
        _img_name_early = ''
    return (_npc_phase_early, _img_name_early, _foreground_ptr_early)

def _poll_run_session_manager(w, *, _img_name_early, _npc_phase_early, in_interior, _resolved_area, mif_name, interior_mif_name):
    try:
        _session_hierarchy_area = _resolved_area
        _session_ctx = _build_session_context(w, img_name=_img_name_early, screen_id=w._screen_id_prev, top_level_state=_current_top_level(w), in_interior=in_interior, npc_phase=_npc_phase_early, npc_active=bool(getattr(w, '_npc_conversation_active', False)), c_area=_session_hierarchy_area, mif_name=mif_name, interior_mif_name=interior_mif_name or '', facility_kind='', extras={'window': w})
        _t_l3 = _phase_start()
        _poll_normal_play_sessions(w, _session_ctx)
        _phase_record(w, 'L3_session', _t_l3)
        _checkpoint(w, 'session')
    except Exception:
        _log.exception('session_manager.poll failed')

def _log_hierarchy_recognition(w, *, stage: str, hierarchy: SeparationHierarchy, decision: HierarchyRecognitionInput) -> None:
    path = ' > '.join(hierarchy.path_codes) or '(none)'
    names = ' > '.join(hierarchy.path_names) or '(none)'
    transition_key = decision.transition_key(hierarchy)
    if transition_key != getattr(w, '_hierarchy_log_transition_key', None):
        w._hierarchy_log_transition_key = transition_key
        values = decision.values_for_log()
        _recog(_log, 'hierarchy changed stage=%s path=%s names=%s indicator=%s top=%r area=%r interior=%s interior_raw=%s npc_active=%s npc_phase=%s mif=%r img=%r screen=%r owner=%r session=%r interior_mif=%r', stage, path, names, hierarchy.indicator, values['top'], values['area'], values['interior'], _fmt_hex_byte(values['interior_raw']), values['npc_active'], _fmt_hex_byte(values['npc_phase']), values['mif'], values['img'], values['screen'], values['owner'], values['session'], values['interior_mif'])
    anomaly_key = decision.anomaly_key()
    if anomaly_key and anomaly_key != getattr(w, '_hierarchy_log_anomaly_key', None):
        w._hierarchy_log_anomaly_key = anomaly_key
        values = decision.values_for_log()
        _log.warning('hierarchy rejected stage=%s kind=%s path=%s names=%s top=%r area=%r interior=%s interior_raw=%s npc_active=%s npc_phase=%s mif=%r img=%r screen=%r owner=%r session=%r interior_mif=%r', stage, decision.anomaly_kind(), path, names, values['top'], values['area'], values['interior'], _fmt_hex_byte(values['interior_raw']), values['npc_active'], _fmt_hex_byte(values['npc_phase']), values['mif'], values['img'], values['screen'], values['owner'], values['session'], values['interior_mif'])

def _poll_file_lifecycle(w) -> None:
    try:
        from controllers.map_ext_lifecycle import get_lifecycle
        get_lifecycle().poll(w._analyzer, getattr(w, '_anchor', None), str(settings.get('save_dir', '')))
    except Exception:
        _log.exception('map_ext lifecycle poll failed')

def _poll_map_update(w, in_interior, interior_raw, player_floor, display_mif_name, _resolved_area, interior_mif_name, interior_facility_name, state, gs, rt_x, rt_z, _loading_post_settle):
    from arena_bridge import RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK, RT_ANGLE_NORTH_RAW, RT_ANGLE_RANGE
    interior_floor_hyp: int | None = None
    if in_interior and interior_mif_name:
        try:
            from interior_floor import resolve_interior_floor
            interior_floor_hyp = resolve_interior_floor(w._analyzer, w._anchor, interior_mif_name)
        except Exception:
            interior_floor_hyp = None
    w._interior_floor_hyp = interior_floor_hyp
    dungeon_level_hyp = None if interior_mif_name else _resolve_dungeon_level(w, display_mif_name)
    w._dungeon_level_hyp = dungeon_level_hyp
    dungeon_floor: int | None = None
    if not interior_mif_name:
        dungeon_floor, w._dungeon_level_held = _dungeon_floor_with_hold(dungeon_level_hyp, display_mif_name, getattr(w, '_dungeon_level_held', None))
    interior_floor: int | None = None
    if in_interior and interior_mif_name:
        interior_floor, w._interior_floor_held = _dungeon_floor_with_hold(interior_floor_hyp, interior_mif_name, getattr(w, '_interior_floor_held', None))
    else:
        w._interior_floor_held = None
    if dungeon_floor is not None:
        effective_floor = dungeon_floor
    elif in_interior and interior_floor is not None:
        effective_floor = interior_floor
    else:
        effective_floor = int(player_floor)
    if w._mif_matcher and _current_top_level(w) == 'normal-play':
        w._mif_matcher.update_map(display_mif_name, dungeon_floor)
    tab_map = getattr(w, '_tab_map', None)
    if tab_map is not None and _current_top_level(w) == 'chargen':
        if not getattr(w, '_map_cleared_for_chargen', False):
            try:
                tab_map.clear_map()
            except (AttributeError, RuntimeError):
                _log.exception('tab_map.clear_map failed')
            try:
                w._tab_translate.fallback_map_tab().clear_map()
            except (AttributeError, RuntimeError):
                _log.exception('fallback_map.clear_map failed')
            w._map_cleared_for_chargen = True
    elif tab_map is not None and _current_top_level(w) == 'normal-play':
        if getattr(w, '_map_cleared_for_chargen', False):
            w._map_cleared_for_chargen = False
            _restore_chargen_cleared_maps(w, tab_map)
        try:
            _angle_bytes = w._analyzer.read_bytes(w._anchor + RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE)
            if _angle_bytes and len(_angle_bytes) == RT_ANGLE_BYTE_SIZE:
                _angle_u16 = int.from_bytes(_angle_bytes, 'little')
                _angle_raw = _angle_u16 & RT_ANGLE_MASK
                _angle_deg = (_angle_raw - RT_ANGLE_NORTH_RAW) * 360.0 / RT_ANGLE_RANGE % 360.0
            else:
                _angle_raw = None
                _angle_deg = None
        except OSError:
            _angle_raw = None
            _angle_deg = None
        _is_loading_for_map = bool(w._loading_state_active or _loading_post_settle)
        _show_player_x = rt_x
        _show_player_y = rt_z
        _show_angle = _angle_deg
        _map_surface_owner = getattr(w, '_panel_owner', '') or ''
        _gate_loc = (_resolved_area or '', gs.get('MapName') or '', interior_mif_name or '', int(player_floor or 0))
        _load_arrival_coord = None
        try:
            from controllers.map_ext_lifecycle import get_lifecycle
            _arr_entry = get_lifecycle().last_load_arrival()
        except Exception:
            _arr_entry = None
        if _arr_entry is not None:
            _arr_seq, _arr = _arr_entry
            if getattr(w, '_load_arrival_consumed_seq', None) != _arr_seq:
                _load_arrival_coord = (_arr['tile_x'], _arr['tile_y'])
        _gate = _resolve_coord_transition(loc=_gate_loc, prev_loc=getattr(w, '_coord_gate_loc_prev', None), in_transition=bool(getattr(w, '_coord_gate_active', False)), pre_coord=getattr(w, '_coord_gate_pre_coord', None), coord=(rt_x, rt_z), prev_coord=getattr(w, '_coord_gate_coord_prev', None), is_loading=_is_loading_for_map, arrival_coord=_load_arrival_coord)
        w._coord_gate_loc_prev = _gate_loc
        w._coord_gate_active = _gate.in_transition
        w._coord_gate_pre_coord = _gate.pre_coord
        w._coord_gate_coord_prev = (rt_x, rt_z)
        if _load_arrival_coord is not None and (not _is_loading_for_map) and ((rt_x, rt_z) == _load_arrival_coord):
            w._load_arrival_consumed_seq = _arr_seq
        if not _gate.shown:
            _show_player_x = None
            _show_player_y = None
        _coord_log_key = (rt_x, rt_z, _gate.shown)
        if _coord_log_key != getattr(w, '_map_coord_log_prev', None):
            w._map_coord_log_prev = _coord_log_key
            _recog(_log, 'map coord: raw=(%s,%s) shown=%s', rt_x, rt_z, _gate.shown)
        _map_area_eff = _resolved_area or None
        _map_mif_eff = display_mif_name or None
        _map_in_interior_eff = in_interior
        _map_interior_mif_eff = interior_mif_name
        _map_bg_last = getattr(w, '_map_bg_last', None)
        if _is_loading_for_map and _map_bg_last is not None:
            _map_area_eff, _map_mif_eff, _map_in_interior_eff, _map_interior_mif_eff = _map_bg_last
        elif not _is_loading_for_map:
            w._map_bg_last = (_map_area_eff, _map_mif_eff, _map_in_interior_eff, _map_interior_mif_eff)
        _treasure_pickup_open = bool(getattr(w, '_treasure_pickup_open_prev', False))
        _fallback_suppress_map, _fallback_suppress_reason = _city_load_fallback_suppression(w, area=_resolved_area, coord_source='raw', player_x=_show_player_x, player_y=_show_player_y, surface_owner=_map_surface_owner, is_loading=_is_loading_for_map)
        try:
            place_text = _format_place_text(state, in_interior, interior_mif_name, _resolved_area, int(effective_floor), interior_facility_name=interior_facility_name)
            w._log_location_hint = _format_place_text(state, in_interior, interior_mif_name, _resolved_area, int(effective_floor), interior_facility_name=interior_facility_name, include_weather=False)
            diag_area = _detect_play_area(w._analyzer, w._anchor, display_mif_name)
            if diag_area == 'wilderness':
                try:
                    _dump_wild_diag_hex(w._analyzer, w._anchor)
                    _poll_wild_diagnostic(w._analyzer, w._anchor)
                except Exception:
                    _log.exception('wild_diag failed')
            wild_location_name = gs.get('MapName') or '' if diag_area in ('city', 'wilderness') else None
            tab_map.update_map_state(_map_mif_eff, _show_player_x, _show_player_y, _show_angle, player_floor=int(effective_floor), place_text=place_text, location_name=wild_location_name, analyzer=w._analyzer, anchor=w._anchor, interior_mif_name=_map_interior_mif_eff, in_interior=_map_in_interior_eff, area=_map_area_eff, treasure_pickup_open=_treasure_pickup_open, dungeon_floor_fresh=dungeon_level_hyp)
            try:
                w._tab_translate.update_fallback_map_state(_map_mif_eff, _show_player_x, _show_player_y, _show_angle, player_floor=int(effective_floor), place_text=place_text, location_name=wild_location_name, analyzer=w._analyzer, anchor=w._anchor, interior_mif_name=_map_interior_mif_eff, in_interior=_map_in_interior_eff, area=_map_area_eff, treasure_pickup_open=_treasure_pickup_open, dungeon_floor_fresh=dungeon_level_hyp, suppress_map=_fallback_suppress_map, suppress_reason=_fallback_suppress_reason)
            except AttributeError as _e:
                if 'update_fallback_map_state' not in str(_e):
                    _log.warning('fallback_map update AttributeError: %s', _e)
            except Exception:
                _log.exception('fallback_map update failed')
        except Exception:
            _log.exception('tab_map update failed')

def _is_pre_screen_system_menu(*, img_name: str, menu_active_now: int, menu_active_prev: int, city_npc_active: int) -> bool:
    from screen_detector import is_city_npc_dialog_active
    img = (img_name or '').upper()
    return img == 'OP.IMG' and menu_active_now == 0 and (menu_active_prev == 0) and (not is_city_npc_dialog_active(city_npc_active))

def _poll_screen_detect_and_label(w, _img_name, mif_name, _resolved_area, player_floor, in_interior, _shop_state, _shop_img_name, _level_up_continue, _b30_dialog_active, _b30_dialog_active_prev, _b30_red_changed, _npc_dialog_changed):
    try:
        from screen_detector import detect_screen, get_chargen_subscreen, MENU_ACTIVE_OFFSET
        chargen_hint = get_chargen_subscreen(w)
        if chargen_hint is not None:
            w._chargen_subscreen_last = chargen_hint
        try:
            _menu_raw = w._analyzer.read_bytes(w._anchor + MENU_ACTIVE_OFFSET, 2)
            _menu_active_now = _menu_raw[0] | _menu_raw[1] << 8
        except (OSError, AttributeError):
            _menu_active_now = 65535
        _menu_active_was_zero = _menu_active_now == 0 and getattr(w, '_menu_active_prev', 65535) == 0
        w._menu_active_prev = _menu_active_now
        _screen_id, _screen_name = detect_screen(w._analyzer, w._anchor, _img_name, chargen_hint, menu_active_was_zero=_menu_active_was_zero, top_level_state=_current_top_level(w), last_chargen_subscreen=w._chargen_subscreen_last, mif_name=mif_name, area=_resolved_area or None)
        if getattr(w, '_travel_l4_active', False):
            _screen_id = 'game_screen'
            _screen_name = i18n.tr('screen.game_screen')
        from play_area_classifier import area_suffix_ja
        _suffix_area = _resolved_area
        if _screen_id == 'game_screen' and _suffix_area == 'dungeon' and (player_floor > 0):
            _screen_name += area_suffix_ja(_suffix_area, player_floor)
        w._loading_data_select_active = _screen_id == 'loadsave_in_play'
        if w._loading_data_select_active:
            _screen_name = i18n.tr('screen.loadsave_in_play')
        elif w._loading_state_active:
            _screen_name = i18n.tr('screen.loading_in_play')
        _top_state = _current_top_level(w)
        _feed = getattr(w, '_translation_feed', None)
        if _feed is not None:
            try:
                _feed.on_screen_context(top_level=_top_state, screen_id=_screen_id)
            except Exception:
                _log.exception('translation_feed.on_screen_context failed')
        _area = _resolved_area
        _travel_l4_active_for_label = bool(getattr(w, '_travel_l4_active', False))
        _screen_suppresses_conversation_label = _travel_l4_active_for_label or _screen_id in ('system_menu', 'loadsave_in_play', 'automap', 'logbook')
        _active_session_for_label = None
        try:
            if not _screen_suppresses_conversation_label:
                _active_session_for_label = w._session_manager.active_session()
        except (AttributeError, ImportError):
            _active_session_for_label = None
        _hierarchy_for_label = SeparationHierarchy.from_parts(top_level_state=_top_state, c_area=_area, in_interior=in_interior, npc_active=False if _screen_suppresses_conversation_label else bool(getattr(w, '_npc_conversation_active', False)) or _active_session_for_label is not None)
        _indicator = _hierarchy_for_label.indicator
        _active_session_name_for_label = ''
        if _active_session_for_label is not None:
            _active_session_name_for_label = _active_session_for_label.name
        _facility_label = ''
        _facility_key = ''
        try:
            from controllers.recognition_label import facility_recognition_key, known_facility_kind
            _shop_owner_for_label = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
            if not in_interior:
                w._interior_facility_kind = ''
            else:
                _kind = known_facility_kind(_active_session_name_for_label, _shop_owner_for_label)
                if _kind:
                    w._interior_facility_kind = _kind
            _facility_key = facility_recognition_key(getattr(w, '_interior_mif_name', None) or '', in_interior, active_session_name=_active_session_name_for_label, shop_owner_kind=_shop_owner_for_label, persisted_facility_kind=getattr(w, '_interior_facility_kind', '') or '', area=_area or '')
            if _facility_key:
                _facility_label = i18n.tr(_facility_key)
        except (AttributeError, ImportError):
            pass
        _conv_label = ''
        try:
            if _active_session_name_for_label:
                if _active_session_name_for_label == 'tavern':
                    _conv_label = i18n.tr('recognition.conv_shop_owner')
                elif _active_session_name_for_label == 'temple':
                    _conv_label = i18n.tr('recognition.conv_priest')
                elif _active_session_name_for_label == 'negotiation':
                    _conv_label = i18n.tr('recognition.conv_negotiation')
                elif _active_session_name_for_label == 'npc_chat':
                    _conv_label = i18n.tr('recognition.conv_npc')
                elif _active_session_name_for_label == 'equipment':
                    _conv_label = i18n.tr('recognition.conv_shop_owner')
                elif _active_session_name_for_label == 'mages_guild':
                    _conv_label = i18n.tr('recognition.conv_shop_owner')
            elif not _screen_suppresses_conversation_label and (getattr(w, '_npc_conversation_active', False) or _screen_id == 'npc_dialog'):
                _conv_label = i18n.tr('recognition.conv_npc')
        except (AttributeError, ImportError):
            pass
        if _facility_key == 'recognition.facility_equipment' and _active_session_name_for_label == 'equipment':
            try:
                from controllers.recognition_label import equipment_sub_state_key
                from normal_play.equipment_l4_state import peek_equipment_l4_state
                _eq_snap = peek_equipment_l4_state(w)
                _eq_state = _eq_snap.state if _eq_snap is not None else ''
                _eq_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
                _eq_sub_key = equipment_sub_state_key(_eq_state, active_template_surface=_eq_surface, img_name=_shop_img_name, negot_counter_active=bool(getattr(w, '_negot_counter_active', False)))
                if _eq_sub_key:
                    _conv_label = _conv_label + i18n.tr(_eq_sub_key)
            except (AttributeError, ImportError):
                pass
        if _facility_key == 'recognition.facility_mages' and _active_session_name_for_label == 'mages_guild':
            try:
                from controllers.recognition_label import mages_sub_state_key
                _mg_owner = getattr(w, '_panel_owner', '') or ''
                _mg_sub_key = mages_sub_state_key(_mg_owner, _shop_img_name, getattr(w, '_mages_list_title_en', '') or '')
                if _mg_sub_key:
                    _conv_label = _conv_label + i18n.tr(_mg_sub_key)
            except (AttributeError, ImportError):
                pass
        _is_temple_ctx = _facility_key == 'recognition.facility_temple'
        if _is_temple_ctx or getattr(w, '_temple_view_dbg_prev_ctx', False):
            try:
                from controllers.recognition_label import temple_sub_state_key
                _temple_owner = getattr(w, '_panel_owner', '') or ''
                _temple_surface = ''
                if _temple_owner in ('temple_cost', 'temple_prompt'):
                    _temple_surface = getattr(w, '_temple_cost_current_surface', '') or ''
                    _temple_text = getattr(w, '_temple_cost_current_text', '') or ''
                elif _temple_owner == 'temple_priest_reply':
                    _temple_text = getattr(w, '_temple_dialog_current_text', '') or ''
                else:
                    _temple_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
                    _temple_text = ''
                _temple_sub_key = temple_sub_state_key(_temple_surface, _temple_owner, _shop_img_name, _temple_text)
            except (AttributeError, ImportError):
                _temple_owner = ''
                _temple_surface = ''
                _temple_text = ''
                _temple_sub_key = ''
            if _is_temple_ctx and _active_session_name_for_label == 'temple' and _temple_sub_key:
                try:
                    _conv_label = _conv_label + i18n.tr(_temple_sub_key)
                except (AttributeError, ImportError):
                    pass
            try:
                _td_raw = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
                _temple_view = _td_raw[0] | _td_raw[1] << 8
            except (OSError, AttributeError):
                _temple_view = None
            try:
                _temple_flag = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
            except (OSError, AttributeError):
                _temple_flag = None
            try:
                from temple_dialog_reader import classify_temple_phase
                _temple_phase, _temple_phase_vals = classify_temple_phase(w._analyzer, w._anchor)
            except Exception:
                _temple_phase = ''
                _temple_phase_vals = {}
            try:
                from active_template_reader import read_active_template_candidates as _ratc, template_surface_kind as _tsk, input_prompt_facility as _ipf
                _temple_cand_descs = []
                for _c in _ratc(w._analyzer, w._anchor):
                    _ck = _tsk(_c) or ''
                    _cf = _ipf(_c) or ''
                    if _ck or _cf:
                        _temple_cand_descs.append(f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
                _temple_cands = ','.join(_temple_cand_descs[:6])
            except Exception:
                _temple_cands = ''
            _temple_dbg_key = (_is_temple_ctx, _temple_sub_key, _temple_owner, _temple_surface, _shop_img_name, _temple_phase, _temple_cands)
            if _temple_dbg_key != getattr(w, '_temple_view_dbg_key', None):
                w._temple_view_dbg_key = _temple_dbg_key
                _log.warning('temple view dbg: sub=%s view(+0x8F6E)=%s flag(+0x8F74)=%s phase=%s vals=%s surface=%r owner=%r img=%r text=%r cands=[%s] ctx_temple=%s', _temple_sub_key.rsplit('.', 1)[-1] if _temple_sub_key else 'none', f'0x{_temple_view:04X}' if _temple_view is not None else 'None', f'0x{_temple_flag:02X}' if _temple_flag is not None else 'None', _temple_phase, _temple_phase_vals, _temple_surface, _temple_owner, _shop_img_name, _temple_text[:48], _temple_cands, _is_temple_ctx)
            w._temple_view_dbg_prev_ctx = _is_temple_ctx
        _is_tavern_ctx = _facility_key == 'recognition.facility_tavern'
        if _is_tavern_ctx or getattr(w, '_tavern_view_dbg_prev_ctx', False):
            try:
                _tv_sub_key = getattr(getattr(w, '_tavern_view', None), 'bar_key', '') or ''
                _tv_shop_kind = getattr(_shop_state, 'kind', 'none') if _shop_state is not None else 'none'
                _tv_owner_kind = getattr(_shop_state, 'owner_kind', '') if _shop_state is not None else ''
                _tv_surface = getattr(w, '_active_tmpl_surface_kind_prev', '') or ''
                _tv_owner = getattr(w, '_panel_owner', '') or ''
            except (AttributeError, ImportError):
                _tv_sub_key = ''
                _tv_shop_kind = 'none'
                _tv_owner_kind = ''
                _tv_surface = ''
                _tv_owner = ''
            _tv_cands = ''
            try:
                from active_template_reader import read_active_template_candidates as _ratc, template_surface_kind as _tsk, input_prompt_facility as _ipf
                _cand_descs = []
                for _c in _ratc(w._analyzer, w._anchor):
                    _ck = _tsk(_c) or ''
                    _cf = _ipf(_c) or ''
                    if _ck or _cf:
                        _cand_descs.append(f"{_c.source}:{_ck or '-'}/{_cf or '-'}")
                _tv_cands = ','.join(_cand_descs[:6])
            except Exception:
                _tv_cands = ''
            try:
                _vd_raw = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_DESC_OFFSET, 2)
                _tv_view = _vd_raw[0] | _vd_raw[1] << 8
            except (OSError, AttributeError):
                _tv_view = None
            try:
                _tv_flag = w._analyzer.read_bytes(w._anchor + _TAVERN_VIEW_FLAG_OFFSET, 1)[0]
            except (OSError, AttributeError):
                _tv_flag = None
            try:
                _tv_ptr = getattr(_shop_state, 'ptr', None) if _shop_state is not None else None
            except AttributeError:
                _tv_ptr = None
            if _is_tavern_ctx and _tv_sub_key:
                try:
                    _conv_label = _conv_label + i18n.tr(_tv_sub_key)
                except (AttributeError, ImportError):
                    pass
            _tv_npcconv = bool(getattr(w, '_npc_conversation_active', False))
            _tv_sess = _active_session_name_for_label or ''
            _tv_dbg_key = (_is_tavern_ctx, _tv_sub_key, _tv_shop_kind, _tv_owner_kind, _tv_surface, _tv_owner, _tv_cands, _shop_img_name or '', _tv_npcconv, _tv_sess)
            if _tv_dbg_key != getattr(w, '_tavern_view_dbg_key', None):
                w._tavern_view_dbg_key = _tv_dbg_key
                _log.warning('tavern view dbg: sub=%s view(+0x8F6E)=%s flag(+0x8F74)=%s shop_kind=%s owner_kind=%r surface=%r owner=%r ptr=%s img=%r cands=[%s] npcconv=%s sess=%r recov=%s ctx_tavern=%s', _tv_sub_key.rsplit('.', 1)[-1] if _tv_sub_key else 'none', f'0x{_tv_view:04X}' if _tv_view is not None else 'None', f'0x{_tv_flag:02X}' if _tv_flag is not None else 'None', _tv_shop_kind, _tv_owner_kind, _tv_surface, _tv_owner, f'0x{_tv_ptr:04X}' if _tv_ptr is not None else 'None', _shop_img_name, _tv_cands, _tv_npcconv, _tv_sess, getattr(w, '_yesno_menu_recovery_last', False), _is_tavern_ctx)
            w._tavern_view_dbg_prev_ctx = _is_tavern_ctx
        if not _conv_label:
            _travel_label_key = {'region_select': 'recognition.travel_region', 'detail': 'recognition.travel_detail', 'hover_name': 'recognition.travel_detail', 'estimate': 'recognition.travel_estimate', 'input': 'recognition.travel_input', 'list': 'recognition.travel_list'}.get(getattr(w, '_travel_l4_state', 'none'))
            if _travel_label_key:
                try:
                    _conv_label = i18n.tr(_travel_label_key)
                except (AttributeError, ImportError):
                    pass
        w._anchor_lbl.setText(i18n.tr('connection.img_info', img=_img_name or '—'))
        _screen_id_stable = _screen_id
        try:
            _b126_flag_status = w._analyzer.read_bytes(w._anchor + 4794, 1)[0]
        except (OSError, AttributeError):
            _b126_flag_status = 0
        try:
            _b126_dialog_byte = w._analyzer.read_bytes(w._anchor + 43077, 1)[0]
        except (OSError, AttributeError):
            _b126_dialog_byte = 0
        try:
            _b126_bonus_pts = w._analyzer.read_bytes(w._anchor + 4764, 1)[0]
        except (OSError, AttributeError):
            _b126_bonus_pts = 0
        _in_levelup = bool(getattr(w, '_level_up_active', False))
        from controllers.screen_finalize import resolve_bonus_screen
        _bonus_pre_screen = _screen_id_stable
        _bonus_res = resolve_bonus_screen(_screen_id_stable, _in_levelup, _b126_flag_status, getattr(w, '_bonus_screen_hold', False))
        if _bonus_res.log_start:
            _log.info('bonus_screen hold START (level-up character screen)')
        w._bonus_screen_hold = _bonus_res.hold_active
        if _bonus_res.clear_spell_markers:
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        if _bonus_res.log_end:
            _log.info('bonus_screen hold END (flag_status=%d in_levelup=%s bonus_pts=%d)', _b126_flag_status, _in_levelup, _b126_bonus_pts)
        if _bonus_res.log_override:
            _log.debug('bonus_screen hold OVERRIDE: %s → bonus_screen', _bonus_pre_screen)
        _screen_id_stable = _bonus_res.screen_id_stable
        _CHAR_PAGES = ('status_page', 'equipment', 'spellbook', 'spell_detail')
        if _b126_flag_status == 1 and getattr(w, '_char_screen_flag_prev', 0) == 0:
            w._char_screen_settling = True
            w._char_screen_budget = 20
        w._char_screen_flag_prev = _b126_flag_status
        if _b126_flag_status == 1 and (not _in_levelup) and (_screen_id_stable in _CHAR_PAGES):
            from normal_play.char_screen_page import settle_char_page
            _screen_id_stable, w._char_screen_settling, w._char_screen_budget = settle_char_page(_screen_id_stable, getattr(w, '_char_screen_settling', False), getattr(w, '_char_screen_budget', 0))
        elif _b126_flag_status != 1:
            w._char_screen_settling = False
            w._char_screen_budget = 0
        from controllers.recognition_label import resolve_stable_screen_name, format_recognition_label
        if settings.get('show_recognition_screen', True):
            _stable_screen_name = resolve_stable_screen_name(_screen_id_stable, _screen_id, _screen_name, i18n.tr)
            _label_top_normal = _current_top_level(w) == 'normal-play'
            _recog_label = format_recognition_label(_stable_screen_name, _indicator, _facility_label if _label_top_normal else '', _conv_label if _label_top_normal else '', screen_id_stable=_screen_id_stable)
            w._status_lbl.setText(i18n.tr('connection.status_connected', screen=_recog_label))
        else:
            w._status_lbl.setText(i18n.tr('connection.status_connected_no_screen'))
        _PLAY_SCREEN_IDS = {'game_screen', 'status_page', 'bonus_screen', 'equipment', 'spellbook', 'spell_detail', 'automap', 'logbook'}
        _desired_chargen_ui = _screen_id_stable not in _PLAY_SCREEN_IDS
        if w._is_in_chargen != _desired_chargen_ui:
            w._set_chargen_ui_state(_desired_chargen_ui)
        try:
            if _screen_id_stable in ('status_page', 'bonus_screen') and _current_top_level(w) == 'normal-play':
                w._ui_router.set_panel_mode('choose_attributes', priority=_SCREEN_PANEL_PRIORITY, reason='screen:status')
                w._b24_status_mode_active = True
            elif getattr(w, '_b24_status_mode_active', False):
                w._ui_router.set_panel_mode('translate', reason='screen:status_exit')
                w._b24_status_mode_active = False
        except (AttributeError, RuntimeError):
            pass
        _propose_automap_screen_mode(w, screen_id_stable=_screen_id_stable, top_level=_current_top_level(w))
        from normal_play.status_overlay import classify_status_panel_state
        _status_panel_state = classify_status_panel_state(top_level=_current_top_level(w), screen_id_stable=_screen_id_stable)
        try:
            w._tab_status.set_chargen_mode(_status_panel_state.chargen_mode)
            w._tab_status.set_is_bonus_screen(_status_panel_state.is_bonus_screen)
        except AttributeError:
            pass
        if _screen_id_stable != w._screen_id_prev:
            w._screen_id_prev = _screen_id_stable
            w._img_screen.on_screen_id_changed(_screen_id_stable)
        _poll_screen_panel_and_spell_detail(w, _screen_id_stable)
        if _level_up_continue:
            from normal_play.level_up_module import consume_level_up_display as _consume_level_up_display
            _consume_level_up_display(w, screen_id_stable=_screen_id_stable, b30_dialog_active=_b30_dialog_active, b30_dialog_active_prev=_b30_dialog_active_prev, b30_red_changed=_b30_red_changed, npc_dialog_changed=_npc_dialog_changed)
        from normal_play.modal_overlay import classify_modal_overlay as _classify_modal_overlay
        _modal_kind = _classify_modal_overlay(_screen_id_stable)
        from normal_play.journal_module import poll_journal as _poll_journal
        _poll_journal(w, modal_kind=_modal_kind)
    except (ImportError, OSError, AttributeError):
        pass
from normal_play import normal_play_render as _normal_play_render
from normal_play.normal_play_render import poll_c1_surface_dispatch as _poll_c1_surface_dispatch, poll_cinematic_dispatch as _poll_cinematic_dispatch, _poll_npc_popup_display, _poll_facility_render_dispatch, _poll_l4_dialog_dispatch, _close_facility_story_units
from normal_play.travel_map_module import STATE_NONE as _TRAVEL_STATE_NONE, classify_travel_l4 as _classify_travel_l4, render_travel_l4 as _render_travel_l4
from screen_detector_play_common import is_inventory_screen_img as _is_inventory_screen_img
_ASK_ABOUT_MAIN_RECOVERY_STATE = _normal_play_render._ASK_ABOUT_MAIN_RECOVERY_STATE
blocks_ask_about_main = _normal_play_render.blocks_ask_about_main
ask_about_main_display_allowed = _normal_play_render.ask_about_main_display_allowed
_render_ask_about_main_recovery = _normal_play_render._render_ask_about_main_recovery
_classify_popup11_substate = _normal_play_render._classify_popup11_substate
_render_popup11_substate = _normal_play_render._render_popup11_substate
_poll_npc_conversation_foreground = _normal_play_render._poll_npc_conversation_foreground
_unified_facility_node = _normal_play_render._unified_facility_node
_UNIFIED_DISPATCH_FACILITIES = _normal_play_render._UNIFIED_DISPATCH_FACILITIES
_poll_compute_temple_gate = _normal_play_render._poll_compute_temple_gate
_poll_shared_negotiation_and_template = _normal_play_render._poll_shared_negotiation_and_template

def _poll_screen_panel_and_spell_detail(w, _screen_id_stable):
    try:
        panel = w._tab_translate.panel_mode()
        if _screen_id_stable == 'spell_detail':
            try:
                marker = w._analyzer.read_bytes(w._anchor + 22554, 16)
            except (OSError, AttributeError):
                marker = b''
            try:
                text_marker = w._analyzer.read_bytes(w._anchor + 4164, 96)
            except (OSError, AttributeError):
                text_marker = b''
            marker_prev = getattr(w, '_spell_detail_marker', None)
            text_marker_prev = getattr(w, '_spell_detail_text_marker', None)
            text_ready = getattr(w, '_spell_detail_text_ready', True)
            if panel != 'spell_detail' or marker != marker_prev or text_marker != text_marker_prev or (not text_ready):
                w._spell_detail_marker = marker
                w._spell_detail_text_marker = text_marker
                w._img_screen._show_spell_detail_screen()
        elif _screen_id_stable == 'equipment':
            try:
                _inv_marker = w._analyzer.read_bytes(w._anchor + 530, 19 * 40)
            except (OSError, AttributeError):
                _inv_marker = None
            if panel != 'equipment' or _inv_marker != w._equipment_marker:
                w._equipment_marker = _inv_marker
                w._img_screen._show_equipment_screen()
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        elif _screen_id_stable == 'spellbook':
            if panel != 'equipment':
                w._img_screen._show_spellbook_screen()
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        elif _screen_id_stable == 'race_select':
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
        else:
            if panel in ('race_list', 'equipment', 'spell_detail'):
                w._ui_router.set_panel_mode('translate', reason='screen:exit')
            w._spell_detail_marker = None
            w._spell_detail_text_marker = None
            w._spell_detail_text_ready = True
    except (AttributeError, RuntimeError):
        pass

class PollController:

    def __init__(self, window):
        self._w = window

    def poll(self):
        w = self._w
        if not w._analyzer:
            return
        w._poll_phase_times = {}
        w._poll_t0 = time.perf_counter()
        w._poll_checkpoints = []
        w._poll_seq = int(getattr(w, '_poll_seq', 0)) + 1
        ui_router = getattr(w, '_ui_router', None)
        _poll_file_lifecycle(w)
        try:
            from arena_bridge import read_game_state, interpret_location, check_trigger_flag, get_trigger_text_by_index, TRIGGER_BLOCK_OFFSET, TRIGGER_BLOCK_READ, RT_COORD_X_OFFSET, RT_COORD_Z_OFFSET, RT_ANGLE_OFFSET, RT_ANGLE_BYTE_SIZE, RT_ANGLE_MASK, RT_ANGLE_RANGE, RT_ANGLE_NORTH_RAW, read_live_buffer, NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN, CHARGEN_STATE_OFFSET, CHARGEN_Q_SEQ_OFFSET, CHARGEN_Q_ARRAY_OFFSET, CHARGEN_DONE_OFFSET, NPC_PHASE_ASKING, NPC_PHASE_IDLE, NPC_PHASE_RESPONDING, NPC_PHASE_BUILDING_ENTRY, read_interior_flag, is_in_interior
            gs, rt_x, rt_z, in_interior, interior_raw, state, inf_name, mif_name, player_floor = _poll_read_game_state(w)
            _top_is_normal_play = _current_top_level(w) == 'normal-play'
            _field_facility_active = False
            if _top_is_normal_play:
                display_mif_name, interior_mif_name, interior_facility_name, _, _effective_in_interior, _field_facility_active = _poll_resolve_interior_entry(w, in_interior=in_interior, rt_x=rt_x, rt_z=rt_z, interior_raw=interior_raw, mif_name=mif_name, gs=gs)
                in_interior = _effective_in_interior
                w._in_interior = in_interior
            else:
                display_mif_name, interior_mif_name, interior_facility_name = (mif_name, None, None)
            _npc_phase_early, _img_name_early, _foreground_ptr_early = _poll_read_npc_phase_and_img(w)
            _resolved_area, _poll_hierarchy_area = _poll_resolve_area_and_frame(w, mif_name=mif_name, in_interior=in_interior, ui_router=ui_router, field_facility_active=_field_facility_active)
            _poll_chargen_normal_play_transition(w, mif_name=mif_name, _img_name_early=_img_name_early)
            _img_name_early_upper, _load_edge_start, _loading_post_settle = _poll_resolve_loading_state(w, _img_name_early=_img_name_early)
            _poll_run_session_manager(w, _img_name_early=_img_name_early, _npc_phase_early=_npc_phase_early, in_interior=in_interior, _resolved_area=_resolved_area, mif_name=mif_name, interior_mif_name=interior_mif_name)
            if _top_is_normal_play:
                _active_facility_name, _tavern_active_now, _temple_active_now, _temple_just_started, _equipment_active_now, _equipment_just_started, _mages_active_now, _mages_just_started, _facility_active_now, _facility_just_started = _poll_track_facility_latch(w)
                _poll_reset_temple_keys_on_img_transition(w, _img_name_early=_img_name_early, _temple_active_now=_temple_active_now)
                _poll_update_npc_conversation_latch(w, _facility_active_now=_facility_active_now, _facility_just_started=_facility_just_started, _npc_phase_early=_npc_phase_early)
            else:
                _active_facility_name, _tavern_active_now, _temple_active_now, _temple_just_started, _equipment_active_now, _equipment_just_started, _mages_active_now, _mages_just_started, _facility_active_now, _facility_just_started = ('', False, False, False, False, False, False, False, False, False)
            _poll_log_hierarchy_recognition_post_session(w, _resolved_area=_resolved_area, in_interior=in_interior, _npc_phase_early=_npc_phase_early, mif_name=mif_name, _img_name_early=_img_name_early, interior_mif_name=interior_mif_name, interior_raw=interior_raw)
            _poll_map_update(w, in_interior, interior_raw, player_floor, display_mif_name, _resolved_area, interior_mif_name, interior_facility_name, state, gs, rt_x, rt_z, _loading_post_settle)
            _shop_state = None
            _shop_menu_visible = False
            _shop_buy_active = False
            _shop_img_name = ''
            _tavern_l4_kind = ''
            try:
                from arena_bridge import SCREEN_IMG_OFFSET as _SI_OFF_S, SCREEN_IMG_MAXLEN as _SI_LEN_S
                _img_raw_s = w._analyzer.read_bytes(w._anchor + _SI_OFF_S, _SI_LEN_S)
                _shop_img_name = _img_raw_s.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
            except (OSError, AttributeError, ImportError):
                _shop_img_name = ''
            if _top_is_normal_play:
                _allow_yesno_menu_recovery = _poll_resolve_yesno_menu_recovery(w, _shop_img_name=_shop_img_name, _temple_active_now=_temple_active_now)
            else:
                _allow_yesno_menu_recovery = False
            _shop_state = _poll_detect_shop_state(w, _shop_img_name=_shop_img_name, in_interior=in_interior, _active_facility_name=_active_facility_name, _allow_yesno_menu_recovery=_allow_yesno_menu_recovery, area=_poll_hierarchy_area)
            if _top_is_normal_play:
                _tview, _tavern_l4_kind, _facility_tavern = _poll_classify_tavern_view_and_log(w, _shop_state=_shop_state, _shop_img_name=_shop_img_name, in_interior=in_interior, _tavern_active_now=_tavern_active_now)
            else:
                _tview, _tavern_l4_kind, _facility_tavern = (None, '', False)
            _c1_dialog_axis_now = None
            if _poll_hierarchy_area == 'dungeon':
                try:
                    from normal_play.c1_dialog_axis import read_c1_dialog_axis
                    _b30_in_gameplay_now = getattr(w, '_screen_id_prev', None) in (None, 'game_screen', 'combat', 'npc_dialog', 'shop', 'loading') and (_img_name_early or '').upper() not in ('MRSHIRT.IMG', 'PAGE2.IMG', 'CHARSTAT.IMG')
                    _c1_dialog_axis_now = read_c1_dialog_axis(w, c_area=_poll_hierarchy_area, in_gameplay=_b30_in_gameplay_now, update_prev=True)
                except Exception:
                    _c1_dialog_axis_now = None
            w._c1_dialog_axis_now = _c1_dialog_axis_now
            _screen_display_active = _screen_state_display_active(w)
            if _screen_display_active:
                _negot_handled, _active_tmpl_handled = (False, False)
            else:
                _negot_handled, _active_tmpl_handled, _shop_menu_visible, _shop_buy_active = _poll_facility_render_dispatch(w, _shop_state=_shop_state, _shop_img_name=_shop_img_name, _facility_tavern=_facility_tavern, _tview=_tview, _temple_active_now=_temple_active_now, _tavern_active_now=_tavern_active_now, _tavern_l4_kind=_tavern_l4_kind, _poll_hierarchy_area=_poll_hierarchy_area, _shop_menu_visible=_shop_menu_visible, _shop_buy_active=_shop_buy_active, _facility_foreground_ptr=_foreground_ptr_early)
            _poll_detect_dungeon_entry(w, mif_name=mif_name)
            if _top_is_normal_play:
                _poll_handle_triggers(w, rt_x=rt_x, rt_z=rt_z, inf_name=inf_name)
            npc_dialog = read_live_buffer(w._analyzer, w._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN)
            _npc_dialog_changed = npc_dialog != w._npc_dialog_prev
            try:
                msg_buf = read_live_buffer(w._analyzer, w._anchor + 39582, 512)
            except (OSError, AttributeError):
                msg_buf = ''
            _msg_buf_prev = getattr(w, '_msg_buf_prev', '')
            _msg_buf_changed = msg_buf != _msg_buf_prev
            w._msg_buf_prev = msg_buf
            if _top_is_normal_play:
                _newpop_gate, _is_corpse_loot = _poll_compute_newpop_gate(w, npc_dialog=npc_dialog)
            else:
                _newpop_gate, _is_corpse_loot = (False, False)
            _npc_phase_raw = _npc_phase_early
            _entry_phase = _npc_phase_raw == NPC_PHASE_BUILDING_ENTRY
            _entry_phase_prev = getattr(w, '_entry_phase_prev', False)
            w._entry_phase_prev = _entry_phase
            _building_entry_pending = bool(getattr(w, '_building_entry_pending', False))
            try:
                from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
                _img_now_raw = w._analyzer.read_bytes(w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
                _img_name_now = _img_now_raw.split(b'\x00', 1)[0].decode('ascii', errors='replace').upper()
            except (OSError, AttributeError, ImportError):
                _img_name_now = ''
            _inventory_screen_now = _is_inventory_screen_img(_img_name_now)
            from normal_play.building_entry_module import should_poll_building_entry as _should_poll_building_entry
            _building_entry_active = _should_poll_building_entry(entry_phase=_entry_phase, panel_owner=w._panel_owner, pending=_building_entry_pending, img_name=_img_name_now)
            try:
                from screen_detector import MENU_ACTIVE_OFFSET, CITY_NPC_ACTIVE_OFFSET, _read_u16_le
                _menu_active_now = _read_u16_le(w._analyzer, w._anchor + MENU_ACTIVE_OFFSET)
                _city_npc_active = _read_u16_le(w._analyzer, w._anchor + CITY_NPC_ACTIVE_OFFSET)
                _pre_system_menu = _is_pre_screen_system_menu(img_name=_img_name_now, menu_active_now=_menu_active_now, menu_active_prev=getattr(w, '_menu_active_prev', 65535), city_npc_active=_city_npc_active)
            except (OSError, AttributeError, ImportError):
                _pre_system_menu = False
            _travel_view = _classify_travel_l4(w, _img_name_now)
            w._travel_l4_active = _travel_view.state != _TRAVEL_STATE_NONE
            _entry_handled = False
            _instore_resp_handled = False
            if _top_is_normal_play:
                if _screen_display_active:
                    _close_facility_story_units(w)
                elif _pre_system_menu:
                    _close_facility_story_units(w)
                    try:
                        for _owner in ('npc_conversation', 'npc_dialog', 'npc_message'):
                            w._ui_router.clear_if_owner(_owner, mode='translate', clear_place_list=True)
                        w._npc_conversation_active = False
                        w._ask_about_menu_active_prev = False
                        w._ask_about_current_ptr_prev = -1
                        w._popup11_list_state_prev = ''
                        w._popup11_exit_pending_ask_about = False
                    except Exception:
                        pass
                elif w._travel_l4_active:
                    _close_facility_story_units(w)
                else:
                    _entry_handled, _instore_resp_handled = _poll_l4_dialog_dispatch(w, in_interior=in_interior, msg_buf=msg_buf, npc_dialog=npc_dialog, _npc_dialog_changed=_npc_dialog_changed, _npc_phase_raw=_npc_phase_raw, _img_name_now=_img_name_now, _building_entry_active=_building_entry_active, _entry_phase_prev=_entry_phase_prev, _shop_state=_shop_state, _shop_img_name=_shop_img_name, _shop_menu_visible=_shop_menu_visible, _shop_buy_active=_shop_buy_active, _facility_active_now=_facility_active_now, _poll_hierarchy_area=_poll_hierarchy_area, _temple_active_now=_temple_active_now, _temple_just_started=_temple_just_started, _equipment_active_now=_equipment_active_now, _equipment_just_started=_equipment_just_started, _mages_active_now=_mages_active_now, _mages_just_started=_mages_just_started, _negot_handled=_negot_handled, _active_tmpl_handled=_active_tmpl_handled, _inventory_screen=_inventory_screen_now)
            else:
                _close_facility_story_units(w)
            from top_level.chargen_state import handle_npc_dialog as _chargen_handle_npc_dialog
            _chargen_handle_npc_dialog(w, npc_dialog=npc_dialog, entry_handled=False, is_corpse_loot=_is_corpse_loot)
            if _npc_dialog_changed:
                w._npc_dialog_prev = npc_dialog
                w._b21_owns_panel = False
            if _top_is_normal_play:
                _poll_status_template_parse(w, _entry_handled=_entry_handled)
            from normal_play.trigger_module import compute_b30_state as _compute_b30_state
            _b30 = _compute_b30_state(w, screen_id=getattr(w, '_screen_id_prev', None), c_area=_poll_hierarchy_area, c1_axis=getattr(w, '_c1_dialog_axis_now', None))
            _b30_dialog_flag = _b30['dialog_flag']
            _b30_red_str = _b30['red_str']
            _b30_red_changed = _b30['red_changed']
            _b30_dialog_active = _b30['dialog_active']
            _b30_dialog_active_prev = _b30['dialog_active_prev']
            _b30_img_name = _b30['img_name']
            _b30_in_gameplay = _b30['in_gameplay']
            _poll_cinematic_dispatch(w, _b30)
            if not _screen_display_active:
                _poll_c1_surface_dispatch(w, _b30, npc_dialog_changed=_npc_dialog_changed, inf_name=inf_name, mif_name=mif_name, instore_resp_handled=_instore_resp_handled, c_area=_poll_hierarchy_area)
            from normal_play.level_up_module import produce_level_up_state as _produce_level_up_state
            _level_up_continue = _produce_level_up_state(w, loading_active=w._loading_state_active, load_edge_start=_load_edge_start, loading_post_settle=_loading_post_settle)
            from normal_play.item_pickup_module import poll_item_pickup as _poll_item_pickup
            _poll_item_pickup(w, newpop_gate=_newpop_gate, b30_img_name=_b30_img_name, npc_dialog=npc_dialog, shop_buy_active=_shop_buy_active, shop_menu_visible=_shop_menu_visible, screen_id=getattr(w, '_screen_id_prev', None), facility_active=bool(_active_facility_name), inventory_screen=_inventory_screen_now)
            w._treasure_pickup_open_prev = bool(getattr(w, '_b32_newpop_open', False) and (not getattr(w, '_b32_was_corpse', False)))
            _img_name = _poll_detect_img_name(w)
            pass
            _npc_phase = _npc_phase_early
            _poll_npc_popup_display(w, _img_name, _shop_menu_visible, _shop_buy_active)
            _render_travel_l4(w, _travel_view)
            from top_level.pregame_state import check_load_save_transition
            check_load_save_transition(w, mif_name=mif_name, img_name=_img_name)
            _poll_screen_detect_and_label(w, _img_name, mif_name, _resolved_area, player_floor, in_interior, _shop_state, _shop_img_name, _level_up_continue, _b30_dialog_active, _b30_dialog_active_prev, _b30_red_changed, _npc_dialog_changed)
            from top_level.chargen_state import poll as _poll_chargen
            _poll_chargen(w)
            if ui_router is not None:
                ui_router.flush_poll_display()
        except OSError:
            w._disconnect()
        except Exception as exc:
            _log.exception('Poll error: %s', exc)
            w._sb.showMessage(f'Poll error: {exc}', 5000)
