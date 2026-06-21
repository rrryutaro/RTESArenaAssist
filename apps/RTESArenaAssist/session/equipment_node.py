"""session/equipment_node.py — 装備品店 施設ノード。

宿屋(TavernNode)と同じ形で、武具店 L4 会話の判定(1軸)と所有描画を自施設に閉じる。
描画は equipment_* owner 名前空間に閉じた ``normal_play.equipment_render_module`` へ
委譲し、宿屋・神殿・魔術師ギルドには一切流さない (完全分離)。
"""
from __future__ import annotations

from .facility_node import FacilityNode, register_facility_node


class EquipmentNode(FacilityNode):
    """武具店の施設分離ノード（自施設 owner 名前空間に閉じる）。"""

    name = "equipment"

    # 武具店が所有する店主メニュー署名 (分離化)。owner_kind=name="equipment"。
    menu_signatures = (
        # 武具店メニュー
        (frozenset({"Buy", "Sell", "Repair", "Steal", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
        # 武具店 Buy サブメニュー
        (frozenset({"Weapon", "Armor"}), "shop_menu", "BUY OPTIONS"),
    )

    def classify_view(self, w, *, shop_state=None, shop_img_name: str = "",
                      **_signals):
        """武具店の前景子画面 (L4) を 1 つだけ確定する単一判定 (1軸)。

        終端応答ホールド / メニュー復帰 / 前景フラグ追跡を含む全前景判定を
        ``classify_equipment_view`` に一元化した (= 判定が 1 本)。返す
        ``EquipmentView`` を render が消費する (前景を再判定しない)。
        """
        from normal_play.equipment_render_module import classify_equipment_view
        return classify_equipment_view(
            w, shop_state=shop_state, shop_img_name=shop_img_name)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str = "",
               top_level_state: str = "", **_ctx):
        """classify_view の結論 (view) を消費して武具店会話を所有描画する。

        戻り値: (negot_handled, active_tmpl_handled, menu_visible, list_visible)。
        """
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
        """Sell/Repair 所持品一覧 (+0x9A6E) を読む (武具店所有の読取)。

        分離化: detector は判定順序・相互排他のみを所有し、武具店固有の
        バッファ読取は武具店ノードが所有する (shop_popup_detector から移設)。
        """
        from equipment_shop_list_reader import read_sell_repair_item_list
        return read_sell_repair_item_list(analyzer, anchor)

    def on_exit(self, w) -> None:
        """退出時整理: 自施設 owner のみ閉じる (他 owner を壊さない)。"""
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
