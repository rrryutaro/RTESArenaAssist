"""normal_play/temple_render_module.py — 神殿 L4 会話メニューの描画オーナー。

完全分離: 神殿神官会話のメニュー (Bless/Cure/Heal/Exit) を temple 専用
owner ``temple_menu`` に閉じて描画する。従来は共有 shop route が ``shop_menu`` owner で
描画していた残存を temple 専用 route へ移す (= 宿屋・共有 shop route から分離)。

費用確認 / 寄付額入力は本モジュールが ``normal_play.temple_cost_module``
(temple_cost / temple_prompt owner) へ委譲し、神官応答は ``temple_dialog_module``
(temple_priest_reply owner) が poll_controller 後段で描画する。いずれも神殿分離内に
閉じ、共有 L4 module (active_template_module / negotiation_module / npc_dialog_module)
への相乗りは撤廃済み。共有するのは副作用なしの純粋 helper
(build_menu_display / translate_shop_menu_items / 辞書lookup) と owner 引数の
UiRouter API のみ。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from session.facility_node import FacilityView

_log = logging.getLogger("RTESArenaAssist")

MENU_OWNER = "temple_menu"
MENU_KEY = "_temple_menu_key_prev"


@dataclass(frozen=True)
class TempleView(FacilityView):
    """神殿 L4 の単一判定 (1軸) 結論 (FacilityView 拡張)。

    ``classify_temple_view`` が前景子画面 (メニュー / 費用確認・寄付入力 / なし)
    を 1 回だけ確定し、``render_temple_view`` が消費して描画する (前景判定を
    再計算しない = 1軸化)。費用の実描画可否は temple_cost 側
    (サブ描画) が確定する点は武具店応答と同型。
    """
    img: str = ""
    shop_state: object = None
    menu_fg: bool = False
    has_menu: bool = False
    reply_foreground: bool = False
    cost_eligible: bool = False


def classify_temple_view(w, *, shop_state=None, shop_img_name: str = "",
                         **_ignored) -> "TempleView":
    """神官メニュー / 費用確認 / 寄付入力の前景を 1 つだけ確定する単一判定 (1軸)。

    神殿メニュー描画は +0x8F74 ゲート(ヒステリシス付)を粗い menu hint として使う
    (poll_controller が `_temple_menu_fg` に設定済み)。ゲートはメニュー中も振動
    するため結果前景の単独根拠にはしないが、メニュー再描画可否には使える。
    """
    img = (shop_img_name or "").upper()
    menu_fg = bool(getattr(w, "_temple_menu_fg", False))
    has_menu = (shop_state is not None
                and shop_state.kind == "shop_menu"
                and getattr(shop_state, "owner_kind", "") == "temple")
    # 直近 poll で神官応答/費用を表示・保持中か (bounded hold、temple_dialog が設定)。
    reply_foreground = int(
        getattr(w, "_temple_dialog_hold_polls", 0) or 0) > 0
    # 費用確認 (temple_cost) / 寄付入力 (temple_prompt) を試みてよい poll か。
    # メニュー前景でなく応答 hold 中でもないときのみ。実際に費用が前景かは
    # temple_cost 側 (サブ描画) が確定する。
    cost_eligible = (not menu_fg and not reply_foreground)
    if menu_fg and has_menu:
        l4_kind, owner, reason = "menu", MENU_OWNER, "temple_menu"
    else:
        # 費用は描画試行の成否で確定するため classify では前景断定しない
        # (= seam/none。実描画は render が temple_cost で確定)。
        l4_kind, owner, reason = "none", "", "temple:seam"
    return TempleView(
        l4_kind=l4_kind, render_owner=owner,
        l4_visible=(l4_kind != "none"), reason=reason,
        img=img, shop_state=shop_state, menu_fg=menu_fg, has_menu=has_menu,
        reply_foreground=reply_foreground, cost_eligible=cost_eligible)


def render_temple_view(w, *, view, shop_state=None, shop_img_name: str = "",
                       **_ignored) -> tuple[bool, bool, bool, bool]:
    """classify_temple_view の結論 (view) を消費して神殿子画面を所有描画する。

    前景判定は再計算せず view を参照する (1軸化)。
    戻り値: (negot_handled, active_tmpl_handled, menu_visible, list_visible)。
    神官応答は神殿専用 ``temple_dialog_module`` (temple_priest_reply owner) が
    poll_controller 後段で描画する。
    """
    img = view.img
    shop_state = view.shop_state
    # 費用確認 / 寄付入力を神殿分離内で所有描画する (描画試行で前景を確定)。
    from normal_play.temple_cost_module import poll_temple_cost
    active_tmpl_handled = False
    if view.cost_eligible:
        active_tmpl_handled = poll_temple_cost(w, img_name=shop_img_name)
    # メニューはゲートがメニュー前景かつ shop_state がメニューを提供し、費用を
    # 描いていない poll のみ描画する (結果の上にメニューを重ねない)。
    menu_visible = False
    if view.menu_fg and view.has_menu and not active_tmpl_handled:
        menu_visible = _render_menu(w, shop_state, img)
    return (False, active_tmpl_handled, menu_visible, False)


def poll_temple_render(w, *, shop_state=None, shop_img_name: str = "",
                       **_ignored) -> tuple[bool, bool, bool, bool]:
    """互換 entry: 判定 (classify) → 描画 (render) を 1 回ずつ実行する薄いラッパ。"""
    view = classify_temple_view(
        w, shop_state=shop_state, shop_img_name=shop_img_name)
    return render_temple_view(
        w, view=view, shop_state=shop_state, shop_img_name=shop_img_name)


def _render_menu(w, shop_state, img: str) -> bool:
    """MENU OPTIONS (Bless/Cure/Heal/Exit) を temple_menu owner で描画。"""
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        owner_taken = (w._panel_owner != MENU_OWNER)
        if key_now != getattr(w, MENU_KEY, None) or owner_taken:
            setattr(w, MENU_KEY, key_now)
            # 神殿メニューは context-aware 直引き。
            menu_tr = translate_shop_menu_items(items, owner_kind="temple")
            title_en = shop_state.menu_title_en or ""
            title_ja = ((translate_ui_text("temple", title_en) or title_en)
                        if title_en else "")
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(
                menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(
                MENU_OWNER, tab_en, tab_ja,
                panel_en=panel_en, panel_ja=panel_ja)
            _log.info(
                "temple_menu update (img=%r title=%r items=%r owner_taken=%s)",
                img, title_en, items, owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("temple_menu update failed")
    return True


__all__ = [
    "poll_temple_render", "classify_temple_view", "render_temple_view",
    "TempleView", "MENU_OWNER", "MENU_KEY",
]
