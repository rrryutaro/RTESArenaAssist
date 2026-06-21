from __future__ import annotations

from typing import Optional

from .tavern_view import TavernSignals


def _safe(fn, default):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def gather_tavern_signals(
    analyzer,
    anchor: int,
    *,
    shop_kind: str,
    shop_owner: str,
    img: str,
    in_interior: bool,
    facility_tavern: bool,
    npc_phase: Optional[int] = None,
) -> TavernSignals:
    img_u = (img or "").upper()

    active_surfaces: set = set()
    cur_ptr_surface = ""
    try:
        from active_template_reader import (
            read_active_template_candidates,
            template_surface_kind,
        )
        cands = read_active_template_candidates(analyzer, anchor)
        for c in cands:
            k = ""
            try:
                k = template_surface_kind(c) or ""
            except Exception:  # noqa: BLE001
                k = ""
            if k:
                active_surfaces.add(k)
                if getattr(c, "source", "") == "current_ptr" and not cur_ptr_surface:
                    cur_ptr_surface = k
    except Exception:  # noqa: BLE001
        active_surfaces = set()
        cur_ptr_surface = ""

    counter_active = ("negotiation_counter" in active_surfaces)

    negotiation_body = False
    try:
        from negotiation_reader import read_negotiation_diagnostic
        _raw, _canon, _rendered, _text = read_negotiation_diagnostic(
            analyzer, anchor)
        if _text:
            import npc_dialog_lookup as _ndl
            negotiation_body = bool(_safe(lambda: _ndl.lookup(_text), None))
    except Exception:  # noqa: BLE001
        negotiation_body = False

    npc_response_hit = False
    try:
        from popup11_response_reader import (
            read_response_candidates_all,
            read_current_text_pointer as _rcp,
            candidate_contains_pointer,
        )
        _rc = read_response_candidates_all(analyzer, anchor)
        _ptr = _safe(lambda: _rcp(analyzer, anchor), None)
        npc_response_hit = any(
            c.text and c.lookup_hit and candidate_contains_pointer(c, _ptr)
            for c in _rc
        )
    except Exception:  # noqa: BLE001
        npc_response_hit = False

    rumor_marker = False
    try:
        from .npc_chat_session import NPC_PHASE_ASKING
        if npc_phase == NPC_PHASE_ASKING:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import (
                parse_menu, detect_active_sub_menu_title,
            )
            from popup11_list_detector import read_active_menu_marker
            _mk = read_active_menu_marker(analyzer, anchor)
            if _mk:
                _raw2 = read_ask_about_menu(analyzer, anchor)
                _parsed = parse_menu(_raw2)
                rumor_marker = (
                    detect_active_sub_menu_title(_parsed, _mk) == "Rumor Type")
    except Exception:  # noqa: BLE001
        rumor_marker = False

    return TavernSignals(
        in_interior=bool(in_interior),
        facility_tavern=bool(facility_tavern),
        shop_kind=shop_kind or "none",
        shop_owner=shop_owner or "",
        img=img_u,
        active_surfaces=frozenset(active_surfaces),
        cur_ptr_surface=cur_ptr_surface,
        negotiation_body=negotiation_body,
        negotiation_prompts=counter_active,
        counter_active=counter_active,
        npc_response_hit=npc_response_hit,
        rumor_marker=rumor_marker,
    )


__all__ = ["gather_tavern_signals"]
