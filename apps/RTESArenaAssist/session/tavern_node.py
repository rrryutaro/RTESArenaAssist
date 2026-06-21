"""session/tavern_node.py — 宿屋施設ノード（参照実装）。

宿屋店主会話を ``FacilityNode`` の形に載せた**参照実装**。判定（1軸）と所有描画を
既存の確定実装へ委譲する:
  - classify_view : ``session.tavern_view.classify_tavern_view``
                    （材料は ``session.tavern_signals.gather_tavern_signals``）
  - render        : ``normal_play.tavern_render_module.poll_tavern_render``

薄い委譲のみを行う。他施設（神殿/装備品店/魔術師ギルド/宮殿）は本ノードと同じ
形の seam として順次実装する。
"""
from __future__ import annotations

from typing import Optional

from .facility_node import FacilityNode, register_facility_node


class TavernNode(FacilityNode):
    """宿屋店主会話の施設分離ノード（参照実装）。"""

    name = "tavern"

    # 宿屋が所有する店主メニュー署名 (分離化)。owner_kind=name="tavern"。
    menu_signatures = (
        # 部屋未契約時の店主メニュー
        (frozenset({"Buy Drinks", "Get a Room", "Sneak into a Room",
                    "Rumors", "Exit"}), "shop_menu", "MENU OPTIONS"),
        # 部屋契約済の店主メニュー
        (frozenset({"Buy Drinks", "Rumors", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
        # 噂種別 popup
        (frozenset({"General", "Work"}), "shop_rumor_type", "Rumor Type"),
    )

    # ============ 宿屋 NEWPOP 一覧 (酒一覧/部屋一覧) の判定材料 ============
    # 分離化: detector は判定順序・相互排他 (中枢固有) のみを所有し、
    # 宿屋固有の signature・バッファ読取・文脈判定は宿屋ノードが所有する。
    # 各実装は shop_popup_detector から verbatim 移設 (挙動不変)。

    # drinks popup 表示中の価格 prefix キャッシュ signature (+0xA836-A839)。
    # drinks 表示中は ASCII "200\0"、rooms 表示中は binary。4 byte 完全一致で
    # drinks 判定する。
    DRINKS_PRICE_CACHE_SIG = b"200\x00"

    @staticmethod
    def read_shop_buy_span(analyzer, anchor):
        """酒一覧バッファ (+0x1040) を parse し (items, anchor 相対 span) を
        返す (宿屋所有の読取)。"""
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
        """部屋一覧 static area (+0x2892) を読む (宿屋所有の読取)。"""
        from room_list_reader import read_room_list
        return read_room_list(analyzer, anchor)

    @staticmethod
    def is_room_list_context(*, interior_mif_name: str,
                             active_facility_name: str) -> bool:
        """NEWPOP 一覧を宿屋部屋一覧として確定してよい文脈か (宿屋所有の判定)。

        room 一覧 static area は他施設の NEWPOP 一覧でも stale data が残り
        得るため、interior_mif が宿屋と判る場合のみ宿屋部屋一覧とする。
        interior_mif 未指定 (後方互換の呼出) は従来どおり宿屋とみなすが、
        active facility が非宿屋を示す場合は施設 L4 分離境界を優先する。
        """
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
        """店主会話の前景子画面 (L4) を 1 つだけ確定する単一判定 (1軸)。

        材料収集 (gather_tavern_signals) → 単一分類 (classify_tavern_view) に
        委譲する。例外処理は呼出側 (poll_controller) が担う（従来挙動を維持）。
        """
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
        """view に従って店主会話を所有描画する。

        戻り値: (negot_handled, active_tmpl_handled, shop_menu_visible,
                 shop_buy_active)（poll_controller 後段が参照）。
        """
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
        """非施設文脈 (session 非active) の宿屋 shop surface 描画を
        宿屋ノードが所有する (宿屋描画の dispatch 入口を node へ単一化。
        実装は tavern_render_module = session active 経路と同一 helper)。
        """
        from normal_play.tavern_render_module import (
            render_no_session_shop)
        return render_no_session_shop(
            w, shop_state=shop_state, shop_img_name=shop_img_name,
            shop_buy_active=shop_buy_active,
            shop_menu_visible=shop_menu_visible)


#: 宿屋ノードの singleton（poll_controller / registry が参照）。
TAVERN_NODE = TavernNode()
register_facility_node(TAVERN_NODE)


__all__ = ["TavernNode", "TAVERN_NODE"]
