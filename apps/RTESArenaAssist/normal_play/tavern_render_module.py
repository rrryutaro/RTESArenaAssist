"""normal_play/tavern_render_module.py — 宿屋店主会話の描画オーナー。

宿屋分離化が active な poll で、店主会話の各子画面 (L4) の描画・終了時整理を
**この 1 モジュールに閉じて所有**する (判定描画セット分離)。

設計 (1軸化):
- 「いまどの子画面を描くか」は単一判定 `session.tavern_view.TavernView`
  (= `_tview`) の `render_owner` だけを見て決める。各描画は render_owner に
  従う renderer に徹する (= 複数経路の食い違いによる崩れを構造的に排除)。
- 描画オーナーが扱う owner:
    shop_menu / shop_rumor_type : 店主メニュー / 噂種別 popup
    shop_buy                    : 酒一覧 (drinks) / 部屋一覧 (rooms)
    negotiation                 : 宿泊金額交渉 (normal_play/negotiation_module へ委譲)
    active_template             : 宿泊日数/忍込確認・結果/部屋契約/費用 (active_template_module へ委譲)
- 以下は本モジュールでは描かず、既存の判定描画セットを再利用する:
    npc_dialog (店内応答=酒/噂応答) … normal_play/npc_dialog_module
    tavern_rumor_type (ASK ABOUT 借用の噂種別) … session/tavern_session.poll()
    死亡演出 … normal_play/trigger_module.poll_death_cinematic
    クエスト/店主クリック NPC … 既存 NPC / journal 経路

共通描画 (店主メニューの表示テキスト生成) は `shop_render_common.build_menu_display`
を呼ぶ (= 副作用なし契約)。「どの owner で描くか」は本モジュールが決め、
神殿等は従来の共有経路を残す (今回は宿屋のみ移植、神殿は次フェーズで同枠移植)。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")


def poll_tavern_render(
    w,
    *,
    tview,
    shop_state,
    shop_img_name: str,
    top_level_state: str,
) -> tuple[bool, bool, bool, bool]:
    """宿屋店主会話の子画面を render_owner に従って描画する。

    戻り値: (negot_handled, active_tmpl_handled, shop_menu_visible,
             shop_buy_active)
    poll_controller の後段 (map_safe_coord / active_template gate / 接続バー
    診断ログ等) が参照するため、判定結果を 4 フラグで返す。
    """
    owner = tview.render_owner
    l4_kind = tview.l4_kind
    shop_menu_visible = False
    shop_buy_active = False

    # ------------------------------------------------------------------
    # 1. 一覧 (酒 drinks / 部屋 rooms) … render_owner == "shop_buy"
    # ------------------------------------------------------------------
    if owner == "shop_buy" and shop_state is not None:
        if l4_kind == "rooms" and shop_state.kind == "shop_rooms":
            # 部屋一覧: static rooms area 由来のため累積不要 (毎 poll 全件表示)。
            shop_buy_active = True
            _render_shop_rooms(w, shop_state)
        elif shop_state.kind == "shop_buy":
            # 酒一覧: 表示順に累積 (popup スクロールで一部しか見えないため)。
            shop_buy_active = True
            _render_shop_drinks(w, shop_state)

    # ------------------------------------------------------------------
    # 2. 店主メニュー / 噂種別 popup … render_owner in (shop_menu, shop_rumor_type)
    # ------------------------------------------------------------------
    elif (owner in ("shop_menu", "shop_rumor_type")
            and shop_state is not None
            and shop_state.kind in ("shop_menu", "shop_rumor_type")):
        shop_menu_visible = True
        _render_shop_menu(w, shop_state, shop_img_name)

    # ------------------------------------------------------------------
    # 3. 終了時整理: 一覧 / メニューが前景でない時の残置クリア。
    # ------------------------------------------------------------------
    _cleanup_shop_buy(w, shop_buy_active, shop_menu_visible, shop_img_name)
    _cleanup_shop_menu(w, shop_menu_visible, shop_buy_active, shop_img_name)

    # ------------------------------------------------------------------
    # 4. 宿泊金額交渉 … render_owner == "negotiation"
    # ------------------------------------------------------------------
    from normal_play.negotiation_module import (
        poll_negotiation as _poll_negotiation,
        cleanup_if_owner as _cleanup_negotiation,
    )
    if owner == "negotiation":
        negot_handled = _poll_negotiation(
            w, img_name=shop_img_name, top_level_state=top_level_state)
        if not negot_handled:
            _cleanup_negotiation(w)
    else:
        negot_handled = False
        _cleanup_negotiation(w)

    # ------------------------------------------------------------------
    # 5. 直接描画テンプレ (active_template) … render_owner == "active_template"
    #    確認/結果/入力/契約/費用。negotiation が描いた poll では走らせない。
    # ------------------------------------------------------------------
    from normal_play.active_template_module import (
        poll_active_template as _poll_active_template,
        cleanup_if_owner as _cleanup_active_template,
    )
    if negot_handled:
        active_tmpl_handled = False
    elif owner != "active_template":
        active_tmpl_handled = False
    else:
        # 宿屋描画オーナーは _facility_tavern 中のみ呼ばれるため、施設文脈は常に
        # tavern。会話 latch (tavern_active_now) が未開始の中途接続でも宿屋 surface
        # を採用できるよう active_facility="tavern" を渡す (active_template_reader
        # が facility 一致を active_slot 候補の採用条件に使うため)。render_owner が
        # "active_template" の poll でしか到達しないので過剰描画にはならない。
        active_tmpl_handled = _poll_active_template(
            w,
            shop_img_name=shop_img_name,
            shop_menu_visible=shop_menu_visible,
            shop_buy_active=shop_buy_active,
            active_facility="tavern",
            allow_during_shop_menu=True,
            tavern_l4_kind=l4_kind,
        )
    if not active_tmpl_handled and not negot_handled:
        _cleanup_active_template(w)

    return (negot_handled, active_tmpl_handled,
            shop_menu_visible, shop_buy_active)


# ----------------------------------------------------------------------
# 描画ヘルパ (本モジュール内に閉じる。poll_controller から物理移植)
# ----------------------------------------------------------------------

def _render_shop_drinks(w, shop_state) -> None:
    """酒一覧 (shop_buy) を 3 列 UI に描画する (表示順に累積)。"""
    try:
        from shop_item_list_reader import translate_shop_item_list
        _buy_now_tr = translate_shop_item_list(
            shop_state.buy_items, section="drinks")
        _seen = list(getattr(w, "_shop_buy_seen_items", []) or [])
        _seen_keys = {it["en"] for it in _seen}
        _added: list[str] = []
        for it in _buy_now_tr:
            if it["en"] not in _seen_keys:
                _seen.append(it)
                _seen_keys.add(it["en"])
                _added.append(it["en"])
        w._shop_buy_seen_items = _seen
        try:
            if w._tab_translate.panel_mode() != "shop_buy":
                w._ui_router.set_panel_mode("shop_buy")
                _log.info("panel_mode -> shop_buy (initial)")
        except AttributeError:
            pass
        _buy_key_now = tuple(
            (it["en"], it["price_display"]) for it in _seen)
        _prev_buy_key = getattr(w, "_shop_buy_key_prev", None)
        _owner_taken = (w._panel_owner != "shop_buy")
        if _buy_key_now != _prev_buy_key or _owner_taken:
            w._shop_buy_key_prev = _buy_key_now
            w._ui_router.update_shop_buy_list(
                "shop_buy", _seen, "Buy Drinks", "酒を買う")
            if _added or _owner_taken:
                _log.info(
                    "shop_buy update (seen=%d added=%r "
                    "visible=%r owner_taken=%s)",
                    len(_seen), _added,
                    [it["en"] for it in _buy_now_tr],
                    _owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("shop_buy update failed")


def _render_shop_rooms(w, shop_state) -> None:
    """部屋一覧 (shop_rooms) を shop_buy と同じ 3 列 UI に描画する。"""
    try:
        from room_list_reader import translate_room_list
        _room_tr = translate_room_list(shop_state.room_items, section="rooms")
        w._shop_buy_seen_items = _room_tr
        try:
            if w._tab_translate.panel_mode() != "shop_buy":
                w._ui_router.set_panel_mode("shop_buy")
                _log.info("panel_mode -> shop_buy (rooms initial)")
        except AttributeError:
            pass
        _room_key_now = tuple(
            (it["en"], it["price_display"]) for it in _room_tr)
        _prev_buy_key = getattr(w, "_shop_buy_key_prev", None)
        _owner_taken = (w._panel_owner != "shop_buy")
        if _room_key_now != _prev_buy_key or _owner_taken:
            w._shop_buy_key_prev = _room_key_now
            w._ui_router.update_shop_buy_list(
                "shop_buy", _room_tr, "Get a Room", "部屋を取る")
            _log.info(
                "shop_rooms update (rooms=%d items=%r owner_taken=%s)",
                len(_room_tr),
                [it["en"] for it in _room_tr],
                _owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("shop_rooms update failed")


def _render_shop_menu(w, shop_state, shop_img_name: str) -> None:
    """店主メニュー / 噂種別 popup を翻訳タブ・パネルに描画する。

    panel_owner は shop_menu / shop_rumor_type で分離する。
    タイトルは state.menu_title_en から取得し、表示テキスト生成は共通描画
    `shop_render_common.build_menu_display` (副作用なし) に委ねる。
    """
    _shop_kind = shop_state.kind
    try:
        from shop_menu_reader import (
            translate_shop_menu_items, translate_ui_text,
        )
        from normal_play.shop_render_common import build_menu_display
        _menu_items = shop_state.menu_items
        _menu_hotkeys = shop_state.menu_item_hotkeys
        _menu_key = (_shop_kind,
                     tuple(_menu_items),
                     tuple(_menu_hotkeys))
        _prev_menu_key = getattr(w, "_shop_menu_key_prev", None)
        _owner_taken = (w._panel_owner != _shop_kind)
        if _menu_key != _prev_menu_key or _owner_taken:
            w._shop_menu_key_prev = _menu_key
            # 宿屋メニューは context-aware 直引き (公開版安全)。
            _menu_tr = translate_shop_menu_items(_menu_items, owner_kind="tavern")
            _title_en = shop_state.menu_title_en or ""
            _title_ja = ((translate_ui_text("tavern", _title_en) or _title_en)
                         if _title_en else "")
            (_tab_en_text, _tab_ja_text,
             _panel_en_text, _panel_ja_text) = build_menu_display(
                _menu_tr, _menu_hotkeys, _title_en, _title_ja)
            w._ui_router.update_translation(
                _shop_kind,
                _tab_en_text, _tab_ja_text,
                panel_en=_panel_en_text,
                panel_ja=_panel_ja_text)
            _log.info(
                "%s update (img=%r title=%r items=%r "
                "hotkeys=%r owner_taken=%s)",
                _shop_kind, shop_img_name, _title_en,
                _menu_items, _menu_hotkeys, _owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("%s update failed", _shop_kind)


def _cleanup_shop_buy(w, shop_buy_active: bool, shop_menu_visible: bool,
                      shop_img_name: str) -> None:
    """一覧 (shop_buy) が前景でない時の残置クリア (= 終了時整理)。

    空更新は「自分自身が所有者だったとき」のみに限定する。他経路が所有して
    いる場合は seen_items / key_prev 残置クリアは行うが翻訳表示の空更新はしない
    (= 他経路の表示を不正に上書きしない)。
    """
    if shop_buy_active:
        return
    _was_shop_buy_owner = (w._panel_owner == "shop_buy")
    _had_shop_buy = bool(
        getattr(w, "_shop_buy_seen_items", None)
        or getattr(w, "_shop_buy_key_prev", None) is not None
        or _was_shop_buy_owner
    )
    if not _had_shop_buy:
        return
    w._shop_buy_seen_items = []
    w._shop_buy_key_prev = None
    try:
        if w._tab_translate.panel_mode() == "shop_buy":
            w._ui_router.set_panel_mode("translate")
    except AttributeError:
        pass
    if _was_shop_buy_owner:
        if not shop_menu_visible:
            w._ui_router.clear_if_owner("shop_buy", mode="translate")
        else:
            w._ui_router.release_if_owner("shop_buy")
    _log.info(
        "shop_buy exit (img=%r next=%s was_owner=%s)",
        shop_img_name,
        "shop_menu" if shop_menu_visible else "none",
        _was_shop_buy_owner)


def _cleanup_shop_menu(w, shop_menu_visible: bool, shop_buy_active: bool,
                       shop_img_name: str) -> None:
    """店主メニュー / 噂種別 popup が前景でない時の残置クリア (= 終了時整理)。

    panel_owner が shop_menu / shop_rumor_type のいずれでもクリアする。
    """
    if shop_menu_visible:
        return
    _had_shop_menu = bool(
        getattr(w, "_shop_menu_key_prev", None) is not None
        or w._panel_owner in ("shop_menu", "shop_rumor_type")
    )
    if not _had_shop_menu:
        return
    w._shop_menu_key_prev = None
    if w._panel_owner in ("shop_menu", "shop_rumor_type"):
        _was_owner = w._panel_owner
        if not shop_buy_active:
            w._ui_router.clear_if_owner(_was_owner)
        else:
            w._ui_router.release_if_owner(_was_owner)
        _log.info(
            "%s exit (img=%r next=%s)",
            _was_owner, shop_img_name,
            "shop_buy" if shop_buy_active else "none")


# 公開 API (宿屋 shop surface 描画の1本化): 共有 dispatch
# (poll_controller の _poll_shared_shop_route) が session 非active 文脈でも
# 同一実装で宿屋 shop surface を描画できるよう公開する。active 経路
# (poll_tavern_render) と pre-session 経路で実装を複製しない。
def render_no_session_shop(
        w, *, shop_state, shop_img_name: str,
        shop_buy_active: bool, shop_menu_visible: bool,
) -> tuple[bool, bool]:
    """非施設文脈 (宿屋 session 非active 等) の shop surface 描画 +
    離脱クリーンアップ (宿屋 L4 分離化単位の所有)。

    呼出は施設ディスパッチの非施設分岐 (`_unified_node is None and not
    _facility_tavern`) でのみ行う (相互排他はディスパッチ構造で保証)。
    描画/クリーンアップは session active 経路 (poll_tavern_render) と
    同一 helper = 単一実装。戻り値: (shop_buy_active, shop_menu_visible)。
    """
    if shop_state is not None:
        _kind = shop_state.kind
        if _kind == "shop_buy":
            shop_buy_active = True
            _render_shop_drinks(w, shop_state)
        elif _kind == "shop_rooms":
            shop_buy_active = True  # cleanup 経路を共通化
            _render_shop_rooms(w, shop_state)
        elif _kind in ("shop_menu", "shop_rumor_type"):
            shop_menu_visible = True
            _render_shop_menu(w, shop_state, shop_img_name)
    # 離脱処理: 前景でない surface の残置クリア。
    _cleanup_shop_buy(w, shop_buy_active, shop_menu_visible, shop_img_name)
    _cleanup_shop_menu(w, shop_menu_visible, shop_buy_active, shop_img_name)
    return shop_buy_active, shop_menu_visible


render_shop_drinks = _render_shop_drinks
render_shop_rooms = _render_shop_rooms
render_shop_menu = _render_shop_menu
cleanup_shop_buy = _cleanup_shop_buy
cleanup_shop_menu = _cleanup_shop_menu


__all__ = [
    "poll_tavern_render",
    "render_no_session_shop",
    "render_shop_drinks",
    "render_shop_rooms",
    "render_shop_menu",
    "cleanup_shop_buy",
    "cleanup_shop_menu",
]
