from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

COST_OWNER = "temple_cost"
PROMPT_OWNER = "temple_prompt"
_KEY = "_temple_cost_key_prev"

_COST_SURFACE_KINDS = frozenset({"tavern_cost_show", "tavern_cost_confirm"})
_PROMPT_SURFACE_KINDS = frozenset({"temple_donate_amount"})
_ACCEPTED_SURFACE_KINDS = _COST_SURFACE_KINDS | _PROMPT_SURFACE_KINDS

_IMG_ALLOWED_SURFACE_KINDS = {
    "YESNO.IMG": frozenset({"tavern_cost_confirm", "temple_donate_amount"}),
    "NEWPOP.IMG": frozenset({"tavern_cost_show", "temple_donate_amount"}),
    "MENU_RT.IMG": frozenset({"tavern_cost_show", "temple_donate_amount"}),
}


def _with_yesno_buttons(img_name: str, kind: str,
                        en: str, ja: str) -> tuple[str, str]:
    if kind not in _COST_SURFACE_KINDS:
        return en, ja
    if (img_name or "").upper() != "YESNO.IMG":
        return en, ja
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile("YESNO.IMG")
    except ImportError:
        profile = None
    if not profile:
        return en, ja
    en_buttons = "  ".join(profile["buttons_en"])
    ja_buttons = "  ".join(profile["buttons_ja"])
    return f"{en_buttons}\n{en}", f"{ja_buttons}\n{ja}"


def _select(candidates, img: str, lookup_hit):
    from active_template_reader import template_surface_kind
    allowed = _IMG_ALLOWED_SURFACE_KINDS.get((img or "").upper())
    for want_source in ("current_ptr", "active_slot"):
        for c in candidates:
            if c.source != want_source:
                continue
            kind = template_surface_kind(c)
            if kind not in _ACCEPTED_SURFACE_KINDS:
                continue
            if allowed is not None and kind not in allowed:
                continue
            try:
                if lookup_hit(c.text):
                    return c, kind
            except Exception:  # noqa: BLE001
                continue
    return None, ""


def poll_temple_cost(w, *, img_name: str) -> bool:
    img = (img_name or "").upper()
    try:
        from active_template_reader import (
            read_active_template_candidates,
            read_current_text_pointer,
        )
        candidates = read_active_template_candidates(w._analyzer, w._anchor)
        _cur_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("temple_cost active_template read failed")
        _cleanup(w)
        return False

    try:
        import npc_dialog_lookup as _ndl
    except Exception:  # noqa: BLE001
        _log.exception("temple_cost npc_dialog_lookup import failed")
        _ndl = None

    selected = None
    kind = ""
    if _ndl is not None and candidates:
        def _hit(text: str, _ndl=_ndl) -> bool:
            try:
                return _ndl.lookup(text) is not None
            except Exception:  # noqa: BLE001
                return False
        selected, kind = _select(candidates, img, _hit)

    if selected is None or _ndl is None:
        _cleanup(w)
        return False

    en = selected.text.rstrip()
    try:
        _r = _ndl.lookup(en)
    except Exception:  # noqa: BLE001
        _r = None
    if not _r:
        _cleanup(w)
        return False

    owner = PROMPT_OWNER if kind in _PROMPT_SURFACE_KINDS else COST_OWNER
    _ja_tmpl, _ph = _r
    ja = _ndl.format_japanese(_ja_tmpl, _ph)
    en_text, ja_text = _with_yesno_buttons(img, kind, en, ja)
    w._temple_cost_current_owner = owner
    w._temple_cost_current_surface = kind
    w._temple_cost_current_text = en

    key = (owner, en_text, ja_text)
    owner_taken = (w._panel_owner != owner)
    if key != getattr(w, _KEY, None) or owner_taken:
        setattr(w, _KEY, key)
        w._ui_router.update_translation(owner, en_text, ja_text)
        _log.info(
            "temple_cost translated: owner=%s kind=%s img=%r en=%r ja=%r",
            owner, kind, img, en[:80], ja[:80])
    return True


def _cleanup(w) -> None:
    if getattr(w, _KEY, None) is not None:
        setattr(w, _KEY, None)
    for attr in (
        "_temple_cost_current_owner",
        "_temple_cost_current_surface",
        "_temple_cost_current_text",
    ):
        try:
            setattr(w, attr, "")
        except AttributeError:
            pass
    for owner in (COST_OWNER, PROMPT_OWNER):
        try:
            if w._panel_owner == owner:
                w._ui_router.clear_if_owner(owner)
        except AttributeError:
            pass


__all__ = ["poll_temple_cost", "COST_OWNER", "PROMPT_OWNER"]
