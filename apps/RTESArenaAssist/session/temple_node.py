from __future__ import annotations

from .facility_node import FacilityNode, register_facility_node


class TempleNode(FacilityNode):

    name = "temple"

    menu_signatures = (
        (frozenset({"Bless", "Cure", "Heal", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
    )

    def classify_view(self, w, *, shop_state=None, shop_img_name: str = "",
                      **_signals):
        from normal_play.temple_render_module import classify_temple_view
        return classify_temple_view(
            w, shop_state=shop_state, shop_img_name=shop_img_name)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str = "",
               top_level_state: str = "", **_ctx):
        from normal_play.temple_render_module import (
            classify_temple_view, render_temple_view,
        )
        if view is None:
            view = classify_temple_view(
                w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_temple_view(
            w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)

    def on_exit(self, w) -> None:
        from normal_play.temple_render_module import MENU_OWNER
        try:
            if w._panel_owner == MENU_OWNER:
                w._ui_router.clear_if_owner(MENU_OWNER)
        except AttributeError:
            pass


TEMPLE_NODE = TempleNode()
register_facility_node(TEMPLE_NODE)

__all__ = ["TempleNode", "TEMPLE_NODE"]
