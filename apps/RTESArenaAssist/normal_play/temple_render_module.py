from __future__ import annotations
import logging
from dataclasses import dataclass
from session.facility_node import FacilityView
_log = logging.getLogger('RTESArenaAssist')
MENU_OWNER = 'temple_menu'
MENU_KEY = '_temple_menu_key_prev'

@dataclass(frozen=True)
class TempleView(FacilityView):
    img: str = ''
    shop_state: object = None
    menu_fg: bool = False
    has_menu: bool = False
    reply_foreground: bool = False
    cost_eligible: bool = False

def classify_temple_view(w, *, shop_state=None, shop_img_name: str='', **_ignored) -> 'TempleView':
    img = (shop_img_name or '').upper()
    menu_fg = bool(getattr(w, '_temple_menu_fg', False))
    has_menu = shop_state is not None and shop_state.kind == 'shop_menu' and (getattr(shop_state, 'owner_kind', '') == 'temple')
    reply_foreground = int(getattr(w, '_temple_dialog_hold_polls', 0) or 0) > 0
    cost_eligible = not menu_fg and (not reply_foreground)
    if menu_fg and has_menu:
        l4_kind, owner, reason = ('menu', MENU_OWNER, 'temple_menu')
    else:
        l4_kind, owner, reason = ('none', '', 'temple:seam')
    return TempleView(l4_kind=l4_kind, render_owner=owner, l4_visible=l4_kind != 'none', reason=reason, img=img, shop_state=shop_state, menu_fg=menu_fg, has_menu=has_menu, reply_foreground=reply_foreground, cost_eligible=cost_eligible)

def render_temple_view(w, *, view, shop_state=None, shop_img_name: str='', **_ignored) -> tuple[bool, bool, bool, bool]:
    img = view.img
    shop_state = view.shop_state
    from normal_play.temple_cost_module import poll_temple_cost
    active_tmpl_handled = False
    if view.cost_eligible:
        active_tmpl_handled = poll_temple_cost(w, img_name=shop_img_name)
    menu_visible = False
    if view.menu_fg and view.has_menu and (not active_tmpl_handled):
        menu_visible = _render_menu(w, shop_state, img)
    return (False, active_tmpl_handled, menu_visible, False)

def poll_temple_render(w, *, shop_state=None, shop_img_name: str='', **_ignored) -> tuple[bool, bool, bool, bool]:
    view = classify_temple_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
    return render_temple_view(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)

def _render_menu(w, shop_state, img: str) -> bool:
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        owner_taken = w._panel_owner != MENU_OWNER
        if key_now != getattr(w, MENU_KEY, None) or owner_taken:
            setattr(w, MENU_KEY, key_now)
            menu_tr = translate_shop_menu_items(items, owner_kind='temple')
            title_en = shop_state.menu_title_en or ''
            title_ja = translate_ui_text('temple', title_en) or title_en if title_en else ''
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(MENU_OWNER, tab_en, tab_ja, panel_en=panel_en, panel_ja=panel_ja)
            _log.info('temple_menu update (img=%r title=%r items=%r owner_taken=%s)', img, title_en, items, owner_taken)
    except Exception:
        _log.exception('temple_menu update failed')
    return True
__all__ = ['poll_temple_render', 'classify_temple_view', 'render_temple_view', 'TempleView', 'MENU_OWNER', 'MENU_KEY']
