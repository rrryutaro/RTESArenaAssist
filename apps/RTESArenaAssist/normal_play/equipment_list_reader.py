from __future__ import annotations

import logging

import i18n_helper as i18n

_log = logging.getLogger("RTESArenaAssist")

_LIST_STABLE_ATTR = "_equipment_list_stable_by_img"
_LIST_PENDING_ATTR = "_equipment_list_pending_by_img"
_STATIC_WEAPON_ITEMS: list[dict] | None = None


def _read_list_items(w, img: str) -> list[dict]:
    if img == "POPUP3.IMG":
        try:
            from equipment_shop_list_reader import read_buy_weapon_list
            return read_buy_weapon_list(w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            _log.exception("equipment weapon buy list read failed")
            return []
    if img == "POPUP4.IMG":
        try:
            from equipment_shop_list_reader import read_buy_armor_list
            return read_buy_armor_list(w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            _log.exception("equipment armor buy list read failed")
            return []
    if img == "NEWPOP.IMG":
        try:
            from equipment_shop_list_reader import read_sell_repair_item_list
            return read_sell_repair_item_list(w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            _log.exception("equipment sell/repair list read failed")
            return []
    return []


def _stabilize_list_items(w, img: str, items: list[dict]) -> list[dict]:
    if img not in ("POPUP3.IMG", "POPUP4.IMG"):
        return items
    stable_by_img = getattr(w, _LIST_STABLE_ATTR, {})
    pending_by_img = getattr(w, _LIST_PENDING_ATTR, {})
    stable = stable_by_img.get(img, [])
    if not stable:
        if items:
            stable_by_img[img] = [dict(it) for it in items]
            setattr(w, _LIST_STABLE_ATTR, stable_by_img)
        return items
    if not items:
        _log.info("equipment_list transient empty suppressed (img=%r)", img)
        return [dict(it) for it in stable]

    stable_sig = _list_signature(stable)
    sig = _list_signature(items)
    if sig == stable_sig:
        pending_by_img.pop(img, None)
        setattr(w, _LIST_PENDING_ATTR, pending_by_img)
        return [dict(it) for it in stable]

    if len(items) < len(stable):
        prev_sig, count = pending_by_img.get(img, (None, 0))
        count = count + 1 if prev_sig == sig else 1
        pending_by_img[img] = (sig, count)
        setattr(w, _LIST_PENDING_ATTR, pending_by_img)
        if count < 3:
            _log.info(
                "equipment_list transient partial suppressed "
                "(img=%r stable=%d candidate=%d count=%d)",
                img, len(stable), len(items), count)
            return [dict(it) for it in stable]

    stable_by_img[img] = [dict(it) for it in items]
    pending_by_img.pop(img, None)
    setattr(w, _LIST_STABLE_ATTR, stable_by_img)
    setattr(w, _LIST_PENDING_ATTR, pending_by_img)
    return items


def _list_signature(items: list[dict]) -> tuple:
    return tuple(
        (it.get("en", ""), it.get("hands", ""), it.get("protects", ""),
         it.get("protects_ja", ""), it.get("weight", ""),
         it.get("price_display", ""))
        for it in items)


def _load_static_weapon_items() -> list[dict]:
    global _STATIC_WEAPON_ITEMS
    if _STATIC_WEAPON_ITEMS is not None:
        return [dict(it) for it in _STATIC_WEAPON_ITEMS]
    out: list[dict] = []
    orig = i18n.originals("items")
    for id_, entry in orig.items():
        if "items.weapons." not in id_:
            continue
        if not isinstance(entry, dict):
            continue
        en = entry.get("original", "")
        if not en:
            continue
        ja = i18n.text_opt(id_)
        data = entry.get("data", {}) or {}
        price = data.get("price")
        price_text = "" if price is None else str(price)
        out.append({
            "en": en,
            "ja": ja,
            "hands": _format_static_hands(data.get("handed")),
            "weight": _format_weight(data.get("weight")),
            "price_raw": price_text,
            "price_display": price_text,
        })
    _STATIC_WEAPON_ITEMS = out
    return [dict(it) for it in out]


def _format_weight(raw_weight) -> str:
    try:
        weight = float(raw_weight) / 256.0
    except (TypeError, ValueError):
        return ""
    return str(int(weight)) if weight.is_integer() else str(weight)


def _format_static_hands(raw_hands) -> str:
    if raw_hands == 1:
        return "片手"
    if raw_hands == 2:
        return "両手"
    return "" if raw_hands is None else str(raw_hands)


__all__ = [
    "_read_list_items",
    "_stabilize_list_items",
    "_load_static_weapon_items",
]
