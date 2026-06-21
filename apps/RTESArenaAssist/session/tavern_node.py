from __future__ import annotations

from typing import Optional

from .facility_node import FacilityNode, register_facility_node


class TavernNode(FacilityNode):

    name = "tavern"

    menu_signatures = (
        (frozenset({"Buy Drinks", "Get a Room", "Sneak into a Room",
                    "Rumors", "Exit"}), "shop_menu", "MENU OPTIONS"),
        (frozenset({"Buy Drinks", "Rumors", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
        (frozenset({"General", "Work"}), "shop_rumor_type", "Rumor Type"),
    )


    DRINKS_PRICE_CACHE_SIG = b"200\x00"

    @staticmethod
    def read_shop_buy_span(analyzer, anchor):
        from shop_item_list_reader import (
            SHOP_ITEM_LIST_OFFSET,
            SHOP_ITEM_LIST_MAXLEN,
            parse_shop_item_list,
        )
        try:
            raw = analyzer.read_bytes(
                anchor + SHOP_ITEM_LIST_OFFSET, SHOP_ITEM_LIST_MAXLEN)
        except (OSError, AttributeError):
            return [], None
        items = parse_shop_item_list(raw)
        if not items:
            return [], None
        span = (SHOP_ITEM_LIST_OFFSET,
                SHOP_ITEM_LIST_OFFSET + SHOP_ITEM_LIST_MAXLEN)
        return items, span

    @staticmethod
    def read_room_items(analyzer, anchor):
        from room_list_reader import read_room_list
        return read_room_list(analyzer, anchor)

    @staticmethod
    def is_room_list_context(*, interior_mif_name: str,
                             active_facility_name: str) -> bool:
        _mif_u = (interior_mif_name or "").upper()
        _active_facility = (active_facility_name or "").lower()
        _non_tavern_active = _active_facility in (
            "temple", "equipment", "mages_guild", "magesguild")
        return (
            not _non_tavern_active
            and (_active_facility == "tavern"
                 or (not _mif_u)
                 or _mif_u.startswith("TAVERN")))

    def classify_view(
        self,
        w,
        *,
        shop_kind: str = "none",
        shop_owner: str = "",
        img: str = "",
        in_interior: bool = False,
        facility_tavern: bool = False,
        npc_phase: Optional[int] = None,
    ):
        from session.tavern_signals import gather_tavern_signals
        from session.tavern_view import classify_tavern_view
        return classify_tavern_view(gather_tavern_signals(
            w._analyzer, w._anchor,
            shop_kind=shop_kind, shop_owner=shop_owner,
            img=img, in_interior=in_interior,
            facility_tavern=facility_tavern, npc_phase=npc_phase))

    def render(
        self,
        w,
        *,
        view,
        shop_state=None,
        shop_img_name: str = "",
        top_level_state: str = "",
    ):
        from normal_play.tavern_render_module import poll_tavern_render
        return poll_tavern_render(
            w,
            tview=view,
            shop_state=shop_state,
            shop_img_name=shop_img_name,
            top_level_state=top_level_state,
        )


    def render_no_session_shop(
        self, w, *, shop_state, shop_img_name: str,
        shop_buy_active: bool, shop_menu_visible: bool,
    ):
        from normal_play.tavern_render_module import (
            render_no_session_shop)
        return render_no_session_shop(
            w, shop_state=shop_state, shop_img_name=shop_img_name,
            shop_buy_active=shop_buy_active,
            shop_menu_visible=shop_menu_visible)


TAVERN_NODE = TavernNode()
register_facility_node(TAVERN_NODE)


__all__ = ["TavernNode", "TAVERN_NODE"]
