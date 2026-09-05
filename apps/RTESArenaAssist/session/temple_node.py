from __future__ import annotations
import logging
from hierarchy_state import facility_owners_for_session
from .facility_node import FacilityNode, register_facility_node
_log = logging.getLogger('RTESArenaAssist')
_PLACE_LIST_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message'})

class TempleNode(FacilityNode):
    name = 'temple'
    menu_signatures = ((frozenset({'Bless', 'Cure', 'Heal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'),)

    def classify_view(self, w, *, shop_state=None, shop_img_name: str='', **_signals):
        from normal_play.temple_render_module import classify_temple_view
        view = classify_temple_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        w._temple_view_l4_visible = bool(view.l4_visible)
        return view

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ctx):
        from normal_play.temple_render_module import classify_temple_view, render_temple_view
        if view is None:
            view = classify_temple_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_temple_view(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)

    def on_exit(self, w) -> None:
        from normal_play.temple_render_module import MENU_KEY
        current = getattr(w, '_panel_owner', '') or ''
        if current in facility_owners_for_session(self.name):
            _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r)', self.name, current)
            try:
                w._ui_router.clear_if_owner(current, mode='translate', clear_place_list=current in _PLACE_LIST_OWNERS)
            except (AttributeError, RuntimeError) as exc:
                _log.debug('facility stop display clear skipped: %s', exc)
        try:
            setattr(w, MENU_KEY, None)
        except AttributeError:
            pass
        try:
            from normal_play.temple_cost_module import reset_temple_cost_on_stop
            reset_temple_cost_on_stop(w)
        except Exception:
            pass

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.temple_render_module import render_no_session_menu
        if render_no_session_menu(w, shop_state=shop_state, shop_img_name=shop_img_name):
            shop_menu_visible = True
        return (shop_buy_active, shop_menu_visible)
TEMPLE_NODE = TempleNode()
register_facility_node(TEMPLE_NODE)
__all__ = ['TempleNode', 'TEMPLE_NODE']
