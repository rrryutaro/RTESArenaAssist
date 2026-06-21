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
    owner = tview.render_owner
    l4_kind = tview.l4_kind
    shop_menu_visible = False
    shop_buy_active = False

    if owner == "shop_buy" and shop_state is not None:
        if l4_kind == "rooms" and shop_state.kind == "shop_rooms":
            shop_buy_active = True
            _render_shop_rooms(w, shop_state)
        elif shop_state.kind == "shop_buy":
            shop_buy_active = True
            _render_shop_drinks(w, shop_state)

    elif (owner in ("shop_menu", "shop_rumor_type")
            and shop_state is not None
            and shop_state.kind in ("shop_menu", "shop_rumor_type")):
        shop_menu_visible = True
        _render_shop_menu(w, shop_state, shop_img_name)

    _cleanup_shop_buy(w, shop_buy_active, shop_menu_visible, shop_img_name)
    _cleanup_shop_menu(w, shop_menu_visible, shop_buy_active, shop_img_name)

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

    from normal_play.active_template_module import (
        poll_active_template as _poll_active_template,
        cleanup_if_owner as _cleanup_active_template,
    )
    if negot_handled:
        active_tmpl_handled = False
    elif owner != "active_template":
        active_tmpl_handled = False
    else:
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



def _render_shop_drinks(w, shop_state) -> None:
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


def render_no_session_shop(
        w, *, shop_state, shop_img_name: str,
        shop_buy_active: bool, shop_menu_visible: bool,
) -> tuple[bool, bool]:
    if shop_state is not None:
        _kind = shop_state.kind
        if _kind == "shop_buy":
            shop_buy_active = True
            _render_shop_drinks(w, shop_state)
        elif _kind == "shop_rooms":
            shop_buy_active = True
            _render_shop_rooms(w, shop_state)
        elif _kind in ("shop_menu", "shop_rumor_type"):
            shop_menu_visible = True
            _render_shop_menu(w, shop_state, shop_img_name)
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
