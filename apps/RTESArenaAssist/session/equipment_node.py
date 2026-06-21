from __future__ import annotations

from .facility_node import FacilityNode, register_facility_node


class EquipmentNode(FacilityNode):

    name = "equipment"

    menu_signatures = (
        (frozenset({"Buy", "Sell", "Repair", "Steal", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
        (frozenset({"Weapon", "Armor"}), "shop_menu", "BUY OPTIONS"),
    )

    def classify_view(self, w, *, shop_state=None, shop_img_name: str = "",
                      **_signals):
        from normal_play.equipment_render_module import classify_equipment_view
        return classify_equipment_view(
            w, shop_state=shop_state, shop_img_name=shop_img_name)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str = "",
               top_level_state: str = "", **_ctx):
        from normal_play.equipment_render_module import (
            classify_equipment_view, render_equipment_view,
        )
        if view is None:
            view = classify_equipment_view(
                w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_equipment_view(
            w, view=view, shop_state=shop_state, shop_img_name=shop_img_name,
            top_level_state=top_level_state or "normal-play")

    @staticmethod
    def read_sell_repair_items(analyzer, anchor):
        from equipment_shop_list_reader import read_sell_repair_item_list
        return read_sell_repair_item_list(analyzer, anchor)

    def on_exit(self, w) -> None:
        from normal_play.equipment_render_module import (
            MENU_OWNER, LIST_OWNER, NEGOTIATION_OWNER,
        )
        for owner in (MENU_OWNER, LIST_OWNER, NEGOTIATION_OWNER):
            try:
                if w._panel_owner == owner:
                    w._ui_router.clear_if_owner(owner)
            except AttributeError:
                pass


EQUIPMENT_NODE = EquipmentNode()
register_facility_node(EQUIPMENT_NODE)

__all__ = ["EquipmentNode", "EQUIPMENT_NODE"]
