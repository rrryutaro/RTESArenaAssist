from __future__ import annotations
import logging
from top_level.top_level_dispatcher import current_state as _current_top_level
_log = logging.getLogger('RTESArenaAssist')
STATE_NONE = 'none'
STATE_REGION_SELECT = 'region_select'
STATE_DETAIL = 'detail'
STATE_HOVER_NAME = 'hover_name'
STATE_ESTIMATE = 'estimate'
STATE_INPUT = 'input'
STATE_LIST = 'list'
TRAVEL_HOVER_OWNER = 'travel_hover_location'
TRAVEL_ESTIMATE_OWNER = 'travel_estimate'
TRAVEL_TABLE_OWNER = 'travel_table'
TRAVEL_SEARCH_OWNER = 'travel_search'
_OFF_ADB6 = 44470
_OFF_DIALOG_ACTIVE = 43077
_OFF_TEXT_PTR = 43076
_OFF_DIALOG_FLAG = 27688
_DIALOG_DEBOUNCE_N = 2
_OFF_LIST_FLAG = 47044
_OFF_POPUP_ACTIVE = 47046
_POPUP_INACTIVE = 65535
_OFF_HOVER_X = 36732
_OFF_HOVER_Y = 36734

def dialog_open(w, cur: bool) -> bool:
    cur = bool(cur)
    if cur == getattr(w, '_travel_dlg_cand', None):
        w._travel_dlg_n = getattr(w, '_travel_dlg_n', 0) + 1
    else:
        w._travel_dlg_cand = cur
        w._travel_dlg_n = 1
    if w._travel_dlg_n >= _DIALOG_DEBOUNCE_N:
        w._travel_dlg_open = cur
    return getattr(w, '_travel_dlg_open', False)
_REGION_SELECT_IMGS = ('OUTPROV.CIF', 'MAPOUT.CIF')
_SEARCH_IMG = 'POPUP8.IMG'
_SEARCH_CLOSE_GRACE = 2
_PROVINCE_DETAIL_IMGS = ('HIGHROCK.IMG', 'HAMERFEL.IMG', 'SKYRIM.IMG', 'SUMERSET.IMG', 'ELSWEYR.IMG', 'VALENWOD.IMG', 'VALENWD.IMG', 'MOROWIND.IMG', 'MORROWND.IMG', 'BLACKMAR.IMG', 'BLACKMSH.IMG', 'BLACKMRH.IMG', 'IMPERIAL.IMG', 'CYRODIIL.IMG')
_MAP_DETAIL_IMGS = ('TERRAIN.IMG', 'CITY.IMG', 'TOWN.IMG', 'VILLAGE.IMG', 'DUNGEON.IMG', 'STAFDUNG.CIF', 'MAPBLINK.CIF')
_TRAVEL_MAP_IMGS = frozenset(_REGION_SELECT_IMGS + (_SEARCH_IMG,) + _PROVINCE_DETAIL_IMGS + _MAP_DETAIL_IMGS)
_GAMEPLAY_EXIT_IMGS = ('P1.IMG', 'OP.IMG', 'LOADSAVE.IMG', 'AUTOMAP.IMG', 'LOGBOOK.IMG')

def _is_travel_map_img(img_name: str) -> bool:
    img = (img_name or '').upper()
    return bool(img) and img in _TRAVEL_MAP_IMGS

def in_travel_session(*, on_normal_play: bool, img_name: str, dlg_open: bool, search_open: bool, search_closed_stale: bool, detail_evidence: bool, session_was: bool, grace_left: int, strong_detail_evidence: bool=False):
    img = (img_name or '').upper()
    if not on_normal_play:
        return (False, 0)
    if img in _GAMEPLAY_EXIT_IMGS:
        return (False, 0)
    if img and (not _is_travel_map_img(img)):
        return (False, 0)
    if img in _REGION_SELECT_IMGS or search_open or dlg_open:
        return (True, _SEARCH_CLOSE_GRACE)
    if search_closed_stale:
        if session_was and strong_detail_evidence:
            return (True, _SEARCH_CLOSE_GRACE)
        if session_was and detail_evidence and (grace_left > 0):
            return (True, grace_left - 1)
        return (False, 0)
    if session_was and detail_evidence:
        return (True, _SEARCH_CLOSE_GRACE)
    return (False, 0)

def classify_travel_map_state(*, on_normal_play: bool, session: bool, img_name: str, dlg_open: bool, has_hover_name: bool, list_flag: int, popup_active: int, search_prompt_open: bool=False) -> str:
    if not on_normal_play or not session:
        return STATE_NONE
    img = (img_name or '').upper()
    if img in _REGION_SELECT_IMGS:
        return STATE_REGION_SELECT
    if img == _SEARCH_IMG:
        if list_flag == 0:
            return STATE_LIST
        if popup_active != _POPUP_INACTIVE:
            return STATE_INPUT
    if search_prompt_open:
        return STATE_INPUT
    if dlg_open:
        return STATE_ESTIMATE
    if has_hover_name:
        return STATE_HOVER_NAME
    return STATE_DETAIL

def _read_u8(w, off: int) -> int:
    try:
        return w._analyzer.read_bytes(w._anchor + off, 1)[0]
    except (OSError, AttributeError):
        return 0

def _read_u16(w, off: int) -> int:
    try:
        return int.from_bytes(w._analyzer.read_bytes(w._anchor + off, 2), 'little')
    except (OSError, AttributeError):
        return 0

def _is_response_text_ptr(w) -> bool:
    try:
        from active_template_reader import is_response_text_buffer_pointer
        return bool(is_response_text_buffer_pointer(_read_u16(w, _OFF_TEXT_PTR)))
    except Exception:
        return False
_TABLE_STATES = (STATE_REGION_SELECT, STATE_DETAIL, STATE_HOVER_NAME, STATE_ESTIMATE)

def _clear_state_owner(w, state: str) -> None:
    try:
        if state in _TABLE_STATES:
            w._ui_router.clear_if_owner(TRAVEL_TABLE_OWNER, mode='translate', clear_travel_table=True)
        elif state in (STATE_INPUT, STATE_LIST):
            w._img_screen._clear_travel_city_list()
    except Exception:
        pass

def _reset_travel_state(w) -> None:
    _clear_state_owner(w, getattr(w, '_travel_l4_state', STATE_NONE))
    w._travel_l4_state = STATE_NONE
    w._travel_l4_render_key = None
    w._travel_session = False
    w._travel_search_grace = _SEARCH_CLOSE_GRACE
    w._travel_dlg_open = False
    w._travel_dlg_cand = None
    w._travel_dlg_n = 0
    w._travel_estimate_active = False
    w._travel_estimate_text_key = None
    w._travel_estimate_open_xy = None
    w._travel_estimate_dismissed_key = None
    w._travel_selected = None
    w._travel_search_list_seen = False

def _lookup_estimate(full_text: str):
    if not full_text:
        return (None, None)
    try:
        import npc_dialog_lookup as _ndl
        res = _ndl.lookup(full_text)
        if not res:
            res = _ndl.lookup_prefix_tolerant(full_text)
        if res:
            tmpl, ph = res
            return (_ndl.format_japanese(tmpl, ph), 'conversation')
    except Exception:
        pass
    return (None, None)

def _read_map_name(w) -> str:
    try:
        from arena_logic import read_live_buffer
        from viewer_constants import MAP_NAME_OFFSET, MAP_NAME_MAXLEN
        return (read_live_buffer(w._analyzer, w._anchor + MAP_NAME_OFFSET, MAP_NAME_MAXLEN) or '').strip()
    except Exception:
        return ''
import re as _re
_RE_EST_DEST = _re.compile("^\\s*(.*?)\\s+in\\s+([A-Za-z'][A-Za-z' ]*?)\\s+Province", _re.IGNORECASE)
_RE_EST_DAYS = _re.compile('it will take\\s+(\\d+)\\s+days?', _re.IGNORECASE)
_RE_EST_DIST = _re.compile('total distance is\\s+([\\d,]+)\\s*km', _re.IGNORECASE)
_RE_EST_DEP_JA = _re.compile('日付は(.+?)。')
_RE_EST_ARR_JA = _re.compile('到着予定は(.+?)。')
_RE_EST_DEP_EN = _re.compile('The date is\\s+(.+?)\\s+Based on', _re.IGNORECASE)
_RE_EST_ARR_EN = _re.compile('You should arrive by\\s+(.+?)\\s*\\.?\\s*$', _re.IGNORECASE)

def _parse_estimate_dates(estimate_ja: str):
    dep = arr = None
    m = _RE_EST_DEP_JA.search(estimate_ja or '')
    if m:
        dep = m.group(1).strip()
    m = _RE_EST_ARR_JA.search(estimate_ja or '')
    if m:
        arr = m.group(1).strip()
    return (dep, arr)

def _parse_estimate_dates_en(full_text: str):
    flat = ' '.join((full_text or '').replace('\r', ' ').split())
    dep = arr = None
    m = _RE_EST_DEP_EN.search(flat)
    if m:
        dep = m.group(1).strip()
    m = _RE_EST_ARR_EN.search(flat)
    if m:
        arr = m.group(1).strip()
    return (dep, arr)

def _parse_estimate(full_text: str):
    flat = ' '.join((full_text or '').replace('\r', ' ').split())
    dest = prov = days = km = None
    m = _RE_EST_DEST.search(flat)
    if m:
        dest = m.group(1).strip() or None
        prov = m.group(2).strip() or None
    m = _RE_EST_DAYS.search(flat)
    if m:
        days = m.group(1)
    m = _RE_EST_DIST.search(flat)
    if m:
        km = m.group(1)
    return (dest, prov, days, km)

def _ja_loc(en):
    if not en:
        return None
    try:
        import location_lookup
        return location_lookup.lookup(en)
    except Exception:
        return None

def _ja_settlement(en):
    if not en:
        return None
    try:
        import npc_dialog_lookup as _ndl
        return _ndl._translate_settlement_location(en, 'ja') or en
    except Exception:
        return en

def _current_province_name(map_name: str):
    if not map_name:
        return None
    try:
        from services.city_data import is_world_map_available, load_world_map_data
        if not is_world_map_available():
            return None
        wm = load_world_map_data()
        found = wm.find_location_by_name(map_name)
        if found is None:
            return None
        pid = found[0]
        if 0 <= pid < len(wm.provinces):
            return wm.provinces[pid].name
    except Exception:
        return None
    return None

def _store_travel_selected(w, *, est, dep, arr, dep_en, arr_en) -> None:
    if not est:
        return
    d_en, prov_en, days, km = est
    if not (d_en or prov_en):
        return
    region_en = prov_en or ''
    region_ja = _ja_loc(prov_en) or prov_en if prov_en else ''
    pos_en = d_en or ''
    pos_ja = _ja_settlement(d_en) or d_en if d_en else ''
    _en, _ja = ([], [])
    if dep_en and arr_en:
        _en += [f'Departure: {dep_en}', f'Arrival: {arr_en}']
    if dep and arr:
        _ja += [f'出発: {dep}', f'到着: {arr}']
    if days:
        _en.append(f'Days: {days} days' + (f' / Distance: {km} km' if km else ''))
        _ja.append(f'日数: {days}日' + (f' / 距離: {km} km' if km else ''))
    w._travel_selected = {'region_en': region_en, 'region_ja': region_ja, 'pos_en': pos_en, 'pos_ja': pos_ja, 'time_en': '\n'.join(_en), 'time_ja': '\n'.join(_ja)}

def _build_travel_rows(w, *, state, dest_loc=None):
    map_name = _read_map_name(w)
    cur_pos_en = map_name
    cur_pos_ja = _ja_loc(map_name) or ''
    cur_prov = _current_province_name(map_name)
    cur_region_en = cur_prov or ''
    cur_region_ja = _ja_loc(cur_prov) or '' if cur_prov else ''
    sel = getattr(w, '_travel_selected', None) or {}
    region_en = sel.get('region_en', '')
    region_ja = sel.get('region_ja', '')
    pos_en = sel.get('pos_en', '')
    pos_ja = sel.get('pos_ja', '')
    time_en = sel.get('time_en', '')
    time_ja = sel.get('time_ja', '')
    if not region_en and state != STATE_ESTIMATE:
        try:
            from travel_location_table import read_displayed_province
            dp = read_displayed_province(w._analyzer, w._anchor)
            if dp:
                region_en = dp[1]
                region_ja = _ja_loc(dp[1]) or ''
        except Exception:
            pass
    dest_en = dest_ja = ''
    if dest_loc is not None:
        dest_en, dest_ja = (dest_loc[0], dest_loc[1] or '')
    return [('現在地域', cur_region_en, cur_region_ja), ('現在位置', cur_pos_en, cur_pos_ja), ('移動予定地域', region_en, region_ja), ('移動予定位置', pos_en, pos_ja), ('移動予定時間', time_en, time_ja), ('移動先', dest_en, dest_ja)]

def _compose_estimate_fallback_ja(est, dep_en, arr_en) -> str:
    if not est:
        return ''
    d_en, prov_en, days, km = est
    parts = []
    if d_en:
        pos_ja = _ja_settlement(d_en) or d_en
        if prov_en:
            region_ja = _ja_loc(prov_en) or prov_en
            parts.append(f'{pos_ja}（{region_ja}）')
        else:
            parts.append(pos_ja)
    if days:
        seg = f'所要 {days}日'
        if km:
            seg += f' / 距離 {km} km'
        parts.append(seg)
    if dep_en:
        parts.append(f'出発: {dep_en}')
    if arr_en:
        parts.append(f'到着: {arr_en}')
    return '\u3000'.join(parts)

def _render_state(w, state: str, *, hover, full_text: str, list_key=None, dest_loc=None) -> None:
    if state == STATE_INPUT:
        if state != getattr(w, '_travel_l4_render_key', None):
            w._img_screen._show_travel_search_prompt()
            w._travel_l4_render_key = state
        return
    if state == STATE_LIST:
        if list_key is not None and list_key != getattr(w, '_travel_l4_render_key', None):
            w._img_screen._show_travel_city_list()
            w._travel_l4_render_key = list_key
        return
    speech_role = None
    panel_en, panel_ja = ('', '')
    est = None
    dep = arr = None
    dep_en = arr_en = None
    if state == STATE_ESTIMATE:
        estimate_ja, speech_role = _lookup_estimate(full_text)
        est = _parse_estimate(full_text)
        dep_en, arr_en = _parse_estimate_dates_en(full_text)
        if estimate_ja:
            panel_en, panel_ja = (full_text, estimate_ja)
            dep, arr = _parse_estimate_dates(estimate_ja)
        else:
            speech_role = None
            panel_en = full_text
            panel_ja = _compose_estimate_fallback_ja(est, dep_en, arr_en)
            dep, arr = (None, None)
        _store_travel_selected(w, est=est, dep=dep, arr=arr, dep_en=dep_en, arr_en=arr_en)
    elif state == STATE_HOVER_NAME and hover:
        panel_en, panel_ja = hover
    rows = _build_travel_rows(w, state=state, dest_loc=dest_loc)
    key = (state, tuple(rows), panel_ja)
    if key == getattr(w, '_travel_l4_render_key', None):
        return
    w._travel_l4_render_key = key
    w._ui_router.update_travel_table(TRAVEL_TABLE_OWNER, rows, panel_en=panel_en, panel_ja=panel_ja, speech_role=speech_role)

def _read_estimate_text(w):
    try:
        from arena_logic import read_live_buffer
        from viewer_constants import NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN
        import npc_dialog_lookup as _ndl
        buf = read_live_buffer(w._analyzer, w._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN) or ''
    except Exception:
        return (False, '')
    if not buf:
        return (False, '')
    try:
        is_est = bool(_ndl.is_travel_estimate(buf))
    except Exception:
        is_est = False
    return (is_est, buf)
_ICON_DESC = {'input': ('Input destination', '目的地を名前で入力'), 'execute': ('Travel to selected destination', '選択中の移動先へ移動'), 'exit': ('Exit fast travel', 'ファストトラベルを終了')}

def _resolve_location_only(w):
    try:
        from travel_location_table import read_named_location, hovered_icon, location_type
        if hovered_icon(w._analyzer, w._anchor):
            return None
        res = read_named_location(w._analyzer, w._anchor)
    except Exception:
        return None
    if not res:
        return None
    name, _x, _y, idx = res
    ltype = location_type(idx)
    en = f'The {ltype} of {name}' if ltype else name
    ja = None
    try:
        import npc_dialog_lookup as _ndl
        if ltype:
            ja = _ndl._translate_settlement_location(en, 'ja')
        else:
            ja = _ndl._translate_static_place(name, 'ja')
    except Exception:
        ja = None
    return (en, ja or name)

def _resolve_hover_name(w):
    icon_desc = _resolve_icon_hover(w)
    if icon_desc:
        return icon_desc
    return _resolve_location_only(w)

def _resolve_icon_hover(w):
    try:
        from travel_location_table import hovered_icon
        icon = hovered_icon(w._analyzer, w._anchor)
        if icon:
            return _ICON_DESC.get(icon)
    except Exception:
        pass
    return None

def _diag_travel(w, *, img: str, state: str, dlg: bool, adb6: int, text: str) -> None:
    b7c4 = _read_u8(w, _OFF_LIST_FLAG)
    b7c6 = _read_u16(w, _OFF_POPUP_ACTIVE)
    flag = _read_u8(w, _OFF_DIALOG_FLAG)
    a845 = _read_u8(w, _OFF_DIALOG_ACTIVE)
    snippet = (text or '').replace('\r', ' ').replace('\n', ' ').strip()[:40]
    sig = (img, state, b7c4, b7c6, flag, a845, snippet)
    if sig != getattr(w, '_travel_diag_prev', None):
        w._travel_diag_prev = sig
        _log.warning('TRAVEL_SIG img=%s state=%s B7C4=0x%02X B7C6=0x%04X 0x6C28=0x%02X 0xA845=0x%02X +44470=0x%02X dlg=%s text=%r', img, state, b7c4, b7c6, flag, a845, adb6, dlg, snippet)

def poll_travel_map(w, img_name: str) -> bool:
    on_np = _current_top_level(w) == 'normal-play'
    img = (img_name or '').upper()
    prev_state = getattr(w, '_travel_l4_state', STATE_NONE)
    if not on_np:
        _reset_travel_state(w)
        return False
    _is_est, full_text = _read_estimate_text(w)
    adb6 = _read_u8(w, _OFF_ADB6)
    _dialog_flag = _read_u8(w, _OFF_DIALOG_FLAG) != 0
    _resp_ptr = _is_response_text_ptr(w)
    _on_modal = _dialog_flag and _resp_ptr
    _is_already = full_text.lstrip().startswith('You are already in')
    _is_search = 'name of the city' in full_text and ('for a list' in full_text or 'press Enter' in full_text)
    list_flag = _read_u8(w, _OFF_LIST_FLAG) if img == _SEARCH_IMG else 255
    popup_active = _read_u16(w, _OFF_POPUP_ACTIVE) if img == _SEARCH_IMG else _POPUP_INACTIVE
    search_list_open = img == _SEARCH_IMG and list_flag == 0
    if search_list_open:
        w._travel_search_list_seen = True
    elif img != _SEARCH_IMG:
        w._travel_search_list_seen = False
    _search_after_list_close = img == _SEARCH_IMG and list_flag != 0 and bool(getattr(w, '_travel_search_list_seen', False))
    _in_detail_img = img not in _REGION_SELECT_IMGS and img != _SEARCH_IMG
    _read_detail = _in_detail_img or (img == _SEARCH_IMG and (not search_list_open))
    hover_location_candidate = _resolve_location_only(w) if _read_detail else None
    hover_candidate = hover_location_candidate
    if hover_candidate is None and _read_detail:
        hover_candidate = _resolve_icon_hover(w)
    search_input_open = img == _SEARCH_IMG and list_flag != 0 and (popup_active != _POPUP_INACTIVE) and (hover_location_candidate is None) and (not _search_after_list_close)
    search_open = search_list_open or search_input_open
    search_closed_stale = img == _SEARCH_IMG and (not search_open)
    _search_prompt_open = bool(_is_search and (not search_closed_stale) and (hover_location_candidate is None))
    _estimate_candidate_allowed = not (search_open or search_closed_stale or _search_prompt_open)
    _modal_candidate = _estimate_candidate_allowed and _on_modal and (_is_est or _is_already)
    _cursor_xy = (_read_u16(w, _OFF_HOVER_X), _read_u16(w, _OFF_HOVER_Y))
    _text_key = ' '.join((full_text or '').split())[:160]
    _active_prev = bool(getattr(w, '_travel_estimate_active', False))
    _dismissed_key = getattr(w, '_travel_estimate_dismissed_key', None)
    _stale_after_close = _active_prev and _modal_candidate and (_text_key == getattr(w, '_travel_estimate_text_key', None)) and (hover_candidate is not None) and (_cursor_xy != getattr(w, '_travel_estimate_open_xy', None))
    if _active_prev:
        if _stale_after_close or not _modal_candidate:
            _estimate_active = False
            if _stale_after_close:
                _dismissed_key = _text_key
        else:
            _estimate_active = True
    else:
        _estimate_active = bool(_modal_candidate and _text_key != _dismissed_key)
        if _estimate_active:
            w._travel_estimate_text_key = _text_key
            w._travel_estimate_open_xy = _cursor_xy
    if not _modal_candidate:
        _dismissed_key = None
    if not _estimate_active:
        w._travel_estimate_open_xy = None
    w._travel_estimate_active = _estimate_active
    w._travel_estimate_dismissed_key = _dismissed_key
    dlg = _estimate_active
    try:
        from travel_location_table import read_displayed_province
        _displayed_prov = read_displayed_province(w._analyzer, w._anchor)
    except Exception:
        _displayed_prov = None
    detail_evidence = img in _REGION_SELECT_IMGS or search_open or dlg or _search_prompt_open or (hover_candidate is not None) or bool(_displayed_prov)
    session, _grace = in_travel_session(on_normal_play=on_np, img_name=img, dlg_open=dlg or _search_prompt_open, search_open=search_open, search_closed_stale=search_closed_stale, detail_evidence=detail_evidence, session_was=getattr(w, '_travel_session', False), grace_left=getattr(w, '_travel_search_grace', _SEARCH_CLOSE_GRACE), strong_detail_evidence=hover_location_candidate is not None or (_search_after_list_close and hover_candidate is not None))
    w._travel_search_grace = _grace
    if not session:
        _reset_travel_state(w)
        return False
    w._travel_session = True
    list_key = None
    if search_list_open:
        try:
            from travel_search_list_reader import read_travel_city_list
            _items = read_travel_city_list(w._analyzer, w._anchor)
            if _items:
                list_key = ('list', len(_items), _items[0])
        except Exception:
            list_key = None
    in_detail_map = session and _read_detail
    hover = hover_candidate if in_detail_map and (not dlg) and (not _search_prompt_open) else None
    state = classify_travel_map_state(on_normal_play=on_np, session=session, img_name=img, dlg_open=dlg, has_hover_name=bool(hover), list_flag=list_flag, popup_active=popup_active if search_input_open else _POPUP_INACTIVE, search_prompt_open=_search_prompt_open)
    if session:
        try:
            _diag_travel(w, img=img, state=state, dlg=dlg, adb6=adb6, text=full_text)
        except Exception:
            pass
    if state != prev_state:
        _clear_state_owner(w, prev_state)
        w._travel_l4_render_key = None
    w._travel_l4_state = state
    dest_loc = _resolve_location_only(w) if state == STATE_HOVER_NAME else None
    if state != STATE_NONE:
        _render_state(w, state, hover=hover, full_text=full_text, list_key=list_key, dest_loc=dest_loc)
    return state != STATE_NONE
__all__ = ['STATE_NONE', 'STATE_REGION_SELECT', 'STATE_DETAIL', 'STATE_HOVER_NAME', 'STATE_ESTIMATE', 'STATE_INPUT', 'STATE_LIST', 'TRAVEL_HOVER_OWNER', 'TRAVEL_ESTIMATE_OWNER', 'TRAVEL_TABLE_OWNER', 'TRAVEL_SEARCH_OWNER', 'in_travel_session', 'classify_travel_map_state', 'poll_travel_map']
