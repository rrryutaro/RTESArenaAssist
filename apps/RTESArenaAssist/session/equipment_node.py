from __future__ import annotations
import logging
from .facility_node import FacilityNode, register_facility_node
_log = logging.getLogger('RTESArenaAssist')
_PLACE_LIST_OWNERS = frozenset({'npc_dialog', 'npc_conversation', 'npc_message'})

class EquipmentNode(FacilityNode):
    name = 'equipment'
    has_conversation_session = True

    @property
    def panel_owners(self) -> frozenset:
        from normal_play.equipment_l4_state import EQUIPMENT_OWNERS
        return EQUIPMENT_OWNERS

    def bar_sub_label_key(self, w, *, active_session_name: str, screen_suppresses_conversation_label: bool, img_name: str) -> str:
        from session.equipment_bar_label import equipment_bar_sub_label_key
        return equipment_bar_sub_label_key(w, active_session_name=active_session_name, img_name=img_name)
    menu_signatures = ((frozenset({'Buy', 'Sell', 'Repair', 'Steal', 'Exit'}), 'shop_menu', 'MENU OPTIONS'), (frozenset({'Weapon', 'Armor'}), 'shop_menu', 'BUY OPTIONS'))

    def classify_view(self, w, *, shop_state=None, shop_img_name: str='', **_signals):
        from normal_play.equipment_render_module import classify_equipment_view
        return classify_equipment_view(w, shop_state=shop_state, shop_img_name=shop_img_name)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str='', top_level_state: str='', **_ctx):
        from normal_play.equipment_render_module import classify_equipment_view, render_equipment_view
        if view is None:
            view = classify_equipment_view(w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_equipment_view(w, view=view, shop_state=shop_state, shop_img_name=shop_img_name, top_level_state=top_level_state or 'normal-play')

    @staticmethod
    def read_sell_repair_items(analyzer, anchor):
        from equipment_shop_list_reader import read_sell_repair_item_list
        return read_sell_repair_item_list(analyzer, anchor)
    owns_shop_replies = True

    def prepare_render(self, w) -> None:
        w._equipment_reply_polled_in_render = False
        w._equipment_reply_handled_in_render = False

    def on_l3_exit(self, w) -> None:
        self.prepare_render(w)
        super().on_l3_exit(w)

    def poll_reply_unit(self, w, *, shop_state, entry_handled: bool, img_name: str, shop_menu_visible: bool, area: str='') -> tuple[bool, bool]:
        active, started = self.latch(w)
        if entry_handled or not active:
            return (False, False)
        if getattr(w, '_equipment_reply_polled_in_render', False):
            return (True, bool(getattr(w, '_equipment_reply_handled_in_render', False)))
        from normal_play.equipment_reply_module import poll_equipment_reply
        return (True, poll_equipment_reply(w, equipment_active=True, equipment_just_started=started, img_name=img_name, shop_menu_visible=shop_menu_visible))

    def on_exit(self, w) -> None:
        from normal_play.equipment_l4_state import reset_equipment_l4_state
        try:
            from normal_play.equipment_reply_module import reset_equipment_reply_state
            reset_equipment_reply_state(w)
        except Exception:
            pass
        try:
            from normal_play.equipment_render_module import reset_equipment_render_keys
            reset_equipment_render_keys(w)
        except Exception:
            pass
        try:
            reset_equipment_l4_state(w)
        except Exception:
            pass
        current = getattr(w, '_panel_owner', '') or ''
        if current in frozenset(self.panel_owners):
            _log.info('facility session stopped -> clearing L4 display (session=%s owner=%r)', self.name, current)
            try:
                w._ui_router.clear_if_owner(current, mode='translate', clear_place_list=current in _PLACE_LIST_OWNERS)
            except (AttributeError, RuntimeError) as exc:
                _log.debug('facility stop display clear skipped: %s', exc)

    def render_no_session_shop(self, w, *, shop_state, shop_img_name: str, shop_buy_active: bool, shop_menu_visible: bool):
        from normal_play.equipment_render_module import render_no_session_menu
        if render_no_session_menu(w, shop_state=shop_state, shop_img_name=shop_img_name):
            shop_menu_visible = True
        return (shop_buy_active, shop_menu_visible)
EQUIPMENT_NODE = EquipmentNode()
register_facility_node(EQUIPMENT_NODE)
__all__ = ['EquipmentNode', 'EQUIPMENT_NODE']
