from __future__ import annotations
import logging
from dataclasses import dataclass
from types import SimpleNamespace
from session.facility_node import FacilityView
from normal_play.equipment_l4_state import EquipmentL4State, REPLY_STATES, get_equipment_l4_state, has_equipment_negotiation_foreground
from normal_play.equipment_list_reader import _read_list_items, _stabilize_list_items, _load_static_weapon_items, _LIST_STABLE_ATTR, _LIST_PENDING_ATTR
_log = logging.getLogger('RTESArenaAssist')
MENU_OWNER = 'equipment_menu'
LIST_OWNER = 'equipment_list'
NEGOTIATION_OWNER = 'equipment_negotiation'
REPAIR_OWNER = 'equipment_repair'
from normal_play.equipment_reply_module import REPLY_OWNER
LIST_IMGS = ('POPUP3.IMG', 'POPUP4.IMG', 'NEWPOP.IMG')
_DIALOG_PTR = 30
_LIST_TITLES = {'POPUP3.IMG': ('Weapons', '武器一覧'), 'POPUP4.IMG': ('Armor', '防具一覧'), 'NEWPOP.IMG': ('Inventory', '所持品一覧')}
_MENU_KEY = '_equipment_menu_key_prev'
_LIST_KEY = '_equipment_list_key_prev'
_REPAIR_KEY = '_equipment_repair_key_prev'

@dataclass(frozen=True)
class EquipmentView(FacilityView):
    img: str = ''
    shop_state: object = None
    state: object = None
    snapshot: object = None
    repair_foreground: bool = False
    repair_job_names: tuple = ()
_STATE_ROUTES = {EquipmentL4State.MENU: ('menu', MENU_OWNER, 'equipment_menu'), EquipmentL4State.NEGOTIATION: ('negotiation', NEGOTIATION_OWNER, 'equipment_negotiation'), EquipmentL4State.REPAIR_ESTIMATE: ('reply', REPLY_OWNER, 'equipment_reply'), EquipmentL4State.REPAIR_STATUS_REPLY: ('reply', REPLY_OWNER, 'equipment_reply'), EquipmentL4State.REPAIR_DONE_REPLY: ('reply', REPLY_OWNER, 'equipment_reply'), EquipmentL4State.REPAIR_ENTRY: ('reply', REPLY_OWNER, 'equipment_reply'), EquipmentL4State.ITEM_SELECT: ('list', LIST_OWNER, 'equipment_list'), EquipmentL4State.REPAIR_JOBS: ('repair', REPAIR_OWNER, 'equipment_repair'), EquipmentL4State.REPLY: ('reply', REPLY_OWNER, 'equipment_reply'), EquipmentL4State.BUY_LIST: ('list', LIST_OWNER, 'equipment_list'), EquipmentL4State.NONE: ('none', '', 'equipment:none')}

def classify_equipment_view(w, *, shop_state=None, shop_img_name: str='', **_ignored) -> 'EquipmentView':
    img = (shop_img_name or '').upper()
    snap = get_equipment_l4_state(w, img=img)
    state = snap.state
    if state is EquipmentL4State.MENU and (not is_equipment_menu_foreground(shop_state)):
        fallback_menu_state = read_menu_rt_equipment_menu_state(w, img, allow_sticky_img=True)
        if fallback_menu_state is not None:
            shop_state = fallback_menu_state
    l4_kind, render_owner, reason = _STATE_ROUTES.get(state, ('none', '', 'equipment:none'))
    return EquipmentView(l4_kind=l4_kind, render_owner=render_owner, l4_visible=l4_kind != 'none', reason=reason, img=img, shop_state=shop_state, state=state, snapshot=snap, repair_foreground=state is EquipmentL4State.REPAIR_JOBS, repair_job_names=snap.repair_job_names)

def render_equipment_view(w, *, view, shop_state=None, shop_img_name: str='', top_level_state: str='normal-play', **_ignored) -> tuple[bool, bool, bool, bool]:
    img = view.img
    shop_state = view.shop_state
    state = view.state
    negot_visible = False
    menu_visible = False
    list_visible = False
    repair_visible = False
    reply_visible = False
    setattr(w, '_equipment_reply_polled_in_render', True)
    setattr(w, '_equipment_reply_handled_in_render', False)
    if state is EquipmentL4State.MENU:
        if shop_state is not None and getattr(shop_state, 'menu_items', None):
            menu_visible = _render_menu(w, shop_state, img)
    elif state is EquipmentL4State.NEGOTIATION:
        negot_visible = _render_negotiation(w, img, top_level_state)
    elif state in REPLY_STATES:
        try:
            from normal_play.equipment_reply_module import render_equipment_reply_state
            reply_visible = render_equipment_reply_state(w, view.snapshot)
        except Exception:
            _log.exception('equipment reply render failed')
        setattr(w, '_equipment_reply_handled_in_render', bool(reply_visible))
    elif state is EquipmentL4State.REPAIR_JOBS:
        repair_visible = _render_repair_jobs(w, view.repair_job_names)
    elif state in (EquipmentL4State.ITEM_SELECT, EquipmentL4State.BUY_LIST):
        list_visible = _render_list(w, img)
    _cleanup(w, menu_visible, list_visible, negot_visible, repair_visible=repair_visible, reply_visible=reply_visible)
    return (negot_visible, False, menu_visible, list_visible)

def poll_equipment_render(w, *, shop_state=None, shop_img_name: str='', top_level_state: str='normal-play', **_ignored) -> tuple[bool, bool, bool, bool]:
    view = classify_equipment_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
    return render_equipment_view(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state)

def reset_equipment_render_keys(w) -> None:
    setattr(w, _MENU_KEY, None)
    setattr(w, _LIST_KEY, None)
    setattr(w, _REPAIR_KEY, None)
    setattr(w, _LIST_STABLE_ATTR, {})
    setattr(w, _LIST_PENDING_ATTR, {})

def read_menu_rt_equipment_menu_state(w, img: str, *, allow_sticky_img: bool=False):
    img_u = (img or '').upper()
    if img_u != 'MENU_RT.IMG' and (not allow_sticky_img):
        return None
    try:
        from popup11_response_reader import read_current_text_pointer
        from shop_menu_reader import SHOP_MENU_BUFFER_MAXLEN, SHOP_MENU_BUFFER_OFFSET, parse_menu_groups, select_menu_group_by_ptr
        ptr = read_current_text_pointer(w._analyzer, w._anchor)
        raw = w._analyzer.read_bytes(w._anchor + SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN)
        groups = parse_menu_groups(raw, base_offset=SHOP_MENU_BUFFER_OFFSET)
        group = select_menu_group_by_ptr(groups, ptr)
        if group is None and isinstance(ptr, int):
            group = _read_equipment_menu_group_near_ptr(w, ptr)
        if group is None:
            group = _fallback_equipment_menu_group(groups, w)
        if group is None:
            return None
        items = [it.text for it in group.items]
        hotkeys = [it.hotkey for it in group.items]
        item_key = tuple(items)
        if item_key == ('Buy', 'Sell', 'Repair', 'Steal', 'Exit'):
            title = 'MENU OPTIONS'
        elif item_key == ('Weapon', 'Armor'):
            title = 'BUY OPTIONS'
        else:
            return None
        return SimpleNamespace(kind='shop_menu', owner_kind='equipment', menu_items=items, menu_item_hotkeys=hotkeys, menu_title_en=title, ptr=ptr)
    except Exception:
        return None

def _read_equipment_menu_group_near_ptr(w, ptr: int):
    if ptr < 512:
        return None
    try:
        from shop_menu_reader import parse_menu_groups, select_menu_group_by_ptr
        base = ptr - 512
        raw = w._analyzer.read_bytes(w._anchor + base, 1024)
        groups = parse_menu_groups(raw, base_offset=base)
        return select_menu_group_by_ptr(groups, ptr)
    except Exception:
        return None

def _fallback_equipment_menu_group(groups, w):
    exact_groups = []
    for group in groups:
        items = tuple((it.text for it in group.items))
        if items in (('Buy', 'Sell', 'Repair', 'Steal', 'Exit'), ('Weapon', 'Armor')):
            exact_groups.append(group)
    if len(exact_groups) == 1:
        return exact_groups[0]
    if getattr(w, '_panel_owner', '') == 'equipment_reply':
        for group in exact_groups:
            if tuple((it.text for it in group.items)) == ('Buy', 'Sell', 'Repair', 'Steal', 'Exit'):
                return group
    try:
        from hierarchy_state import active_facility_session_name
        session_name = active_facility_session_name(w)
    except Exception:
        session_name = ''
    if session_name == 'equipment':
        for group in exact_groups:
            if tuple((it.text for it in group.items)) == ('Buy', 'Sell', 'Repair', 'Steal', 'Exit'):
                return group
    return None

def _render_negotiation(w, img: str, top_level_state: str) -> bool:
    try:
        from normal_play.negotiation_module import poll_negotiation, cleanup_if_owner as cleanup_negotiation
        handled = poll_negotiation(w, img_name=img, top_level_state=top_level_state, owner=NEGOTIATION_OWNER)
        if not handled:
            cleanup_negotiation(w, owner=NEGOTIATION_OWNER)
        return handled
    except Exception:
        _log.exception('equipment_negotiation update failed')
        return False

def _render_menu(w, shop_state, img: str) -> bool:
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        owner_taken = w._panel_owner != MENU_OWNER
        if key_now != getattr(w, _MENU_KEY, None) or owner_taken:
            setattr(w, _MENU_KEY, key_now)
            menu_tr = translate_shop_menu_items(items, owner_kind='equipment')
            title_en = shop_state.menu_title_en or ''
            title_ja = translate_ui_text('equipment', title_en) or title_en if title_en else ''
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(MENU_OWNER, tab_en, tab_ja, panel_en=panel_en, panel_ja=panel_ja)
            _log.info('equipment_menu update (img=%r title=%r items=%r owner_taken=%s)', img, title_en, items, owner_taken)
    except Exception:
        _log.exception('equipment_menu update failed')
    return True

def _render_list(w, img: str) -> bool:
    title_en, title_ja = _LIST_TITLES.get(img, ('Items', 'アイテム'))
    items = _stabilize_list_items(w, img, _read_list_items(w, img))
    try:
        owner_taken = w._panel_owner != LIST_OWNER
        tr = []
        source = ''
        if items:
            tr = items
            source = 'memory'
        elif img == 'POPUP3.IMG':
            tr = _load_static_weapon_items()
            source = 'static_weapons'
        if tr:
            key_now = ('list', img, tuple(((it.get('en', ''), it.get('hands', ''), it.get('protects', ''), it.get('protects_ja', ''), it.get('weight', ''), it.get('price_display', '')) for it in tr)))
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_facility_list(LIST_OWNER, tr, title_en, title_ja)
                _log.info('equipment_list update (img=%r items=%d source=%s)', img, len(tr), source)
        else:
            key_now = ('unparsed', img)
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_translation(LIST_OWNER, f'{title_en} (list parsing...)', f'{title_ja} (解析中)')
                _log.info('equipment_list unparsed placeholder (img=%r)', img)
    except Exception:
        _log.exception('equipment_list update failed')
    return True

def _render_repair_jobs(w, job_names) -> bool:
    try:
        from equipment_shop_list_reader import translate_equipment_shop_name
        items = [{'en': en, 'ja': translate_equipment_shop_name(en) or en} for en in job_names]
        owner_taken = w._panel_owner != REPAIR_OWNER
        key_now = ('repair', tuple(job_names))
        if key_now != getattr(w, _REPAIR_KEY, None) or owner_taken:
            setattr(w, _REPAIR_KEY, key_now)
            w._ui_router.update_facility_list(REPAIR_OWNER, items, '', '', list_title_ja='')
            _log.info('equipment_repair update (jobs=%d)', len(items))
    except Exception:
        _log.exception('equipment_repair update failed')
    return True

def is_main_equipment_menu_state(shop_state) -> bool:
    if not (shop_state is not None and shop_state.kind == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'equipment')):
        return False
    title = getattr(shop_state, 'menu_title_en', '') or ''
    items = tuple(getattr(shop_state, 'menu_items', []) or [])
    return title == 'MENU OPTIONS' or items == ('Buy', 'Sell', 'Repair', 'Steal', 'Exit')

def is_equipment_menu_foreground(shop_state) -> bool:
    if not (shop_state is not None and shop_state.kind == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'equipment')):
        return False
    ptr = getattr(shop_state, 'ptr', None)
    if ptr is None:
        return True
    try:
        return int(ptr) != _DIALOG_PTR
    except (TypeError, ValueError):
        return True

def _cleanup(w, menu_visible: bool, list_visible: bool, negot_visible: bool=False, repair_visible: bool=False, reply_visible: bool=False) -> None:
    if not menu_visible and getattr(w, _MENU_KEY, None) is not None:
        setattr(w, _MENU_KEY, None)
        if w._panel_owner == MENU_OWNER:
            w._ui_router.clear_if_owner(MENU_OWNER)
    if not list_visible and getattr(w, _LIST_KEY, None) is not None:
        setattr(w, _LIST_KEY, None)
        setattr(w, _LIST_STABLE_ATTR, {})
        setattr(w, _LIST_PENDING_ATTR, {})
        try:
            if w._tab_translate.panel_mode() == 'facility_list':
                w._ui_router.set_panel_mode('translate')
        except AttributeError:
            pass
        if w._panel_owner == LIST_OWNER:
            w._ui_router.clear_if_owner(LIST_OWNER, mode='translate')
    if not repair_visible and getattr(w, _REPAIR_KEY, None) is not None:
        setattr(w, _REPAIR_KEY, None)
        try:
            if w._tab_translate.panel_mode() == 'facility_list':
                w._ui_router.set_panel_mode('translate')
        except AttributeError:
            pass
        if w._panel_owner == REPAIR_OWNER:
            w._ui_router.clear_if_owner(REPAIR_OWNER, mode='translate')
    if not reply_visible:
        try:
            from normal_play.equipment_reply_module import cleanup_equipment_reply_if_owner
            cleanup_equipment_reply_if_owner(w)
        except Exception:
            _log.exception('equipment_reply cleanup failed')
    if not negot_visible:
        try:
            from normal_play.negotiation_module import cleanup_if_owner as cleanup_negotiation
            cleanup_negotiation(w, owner=NEGOTIATION_OWNER)
        except Exception:
            _log.exception('equipment_negotiation cleanup failed')
__all__ = ['poll_equipment_render', 'classify_equipment_view', 'render_equipment_view', 'EquipmentView', 'MENU_OWNER', 'LIST_OWNER', 'LIST_IMGS', 'REPAIR_OWNER', 'NEGOTIATION_OWNER', 'is_main_equipment_menu_state', 'is_equipment_menu_foreground', 'has_equipment_negotiation_foreground', 'read_menu_rt_equipment_menu_state', 'reset_equipment_render_keys']
