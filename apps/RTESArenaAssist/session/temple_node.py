"""session/temple_node.py — 神殿施設ノード。

宿屋(TavernNode)と同じ形で、神殿神官会話のメニュー判定(1軸)と所有描画を temple
専用領域に閉じる。メニュー描画は ``normal_play.temple_render_module`` (temple_menu
owner) へ委譲し、共有 shop route / 宿屋には流さない (完全分離)。
費用確認/寄付入力 (temple_cost/temple_prompt) も temple_render_module 経由で神殿分離内に
所有し、神官応答 (temple_priest_reply) は poll_controller 後段の temple_dialog_module が
描画する。共有 L4 module への相乗りは行わない。
"""
from __future__ import annotations

from .facility_node import FacilityNode, register_facility_node


class TempleNode(FacilityNode):
    """神殿の施設分離ノード（メニューを temple_menu owner に閉じる）。"""

    name = "temple"

    # 神殿が所有する神官メニュー署名 (分離化)。owner_kind=name="temple"。
    menu_signatures = (
        # 神殿の神官メニュー
        (frozenset({"Bless", "Cure", "Heal", "Exit"}),
         "shop_menu", "MENU OPTIONS"),
    )

    def classify_view(self, w, *, shop_state=None, shop_img_name: str = "",
                      **_signals):
        """神官メニュー / 費用確認・寄付入力 の前景を確定する単一判定 (1軸)。

        判定を `classify_temple_view` に一元化し、返す `TempleView` を render が
        消費する (前景を再判定しない)。
        """
        from normal_play.temple_render_module import classify_temple_view
        return classify_temple_view(
            w, shop_state=shop_state, shop_img_name=shop_img_name)

    def render(self, w, *, view=None, shop_state=None, shop_img_name: str = "",
               top_level_state: str = "", **_ctx):
        """classify_view の結論 (view) を消費して神殿子画面を所有描画する。

        戻り値: (negot_handled, active_tmpl_handled, menu_visible, list_visible)。
        """
        from normal_play.temple_render_module import (
            classify_temple_view, render_temple_view,
        )
        if view is None:
            view = classify_temple_view(
                w, shop_state=shop_state, shop_img_name=shop_img_name)
        return render_temple_view(
            w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)

    def on_exit(self, w) -> None:
        """退出時整理: temple_menu owner のみ閉じる。"""
        from normal_play.temple_render_module import MENU_OWNER
        try:
            if w._panel_owner == MENU_OWNER:
                w._ui_router.clear_if_owner(MENU_OWNER)
        except AttributeError:
            pass


TEMPLE_NODE = TempleNode()
register_facility_node(TEMPLE_NODE)

__all__ = ["TempleNode", "TEMPLE_NODE"]
