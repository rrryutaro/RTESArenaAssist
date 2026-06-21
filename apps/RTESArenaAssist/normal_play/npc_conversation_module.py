from __future__ import annotations

import logging

from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("RTESArenaAssist")

NPC_CONVERSATION_OWNER = "npc_conversation"


def poll_npc_conversation(
        w, ctx, *, npc_dialog: str, npc_dialog_changed: bool,
        dialog_just_opened: bool, in_interior: bool,
        facility_active_now: bool, npc_translated: bool) -> None:
    _route4_eligible = (
        not npc_translated and bool(npc_dialog)
        and (npc_dialog_changed or dialog_just_opened)
        and (w._npc_conversation_active or in_interior)
        and not facility_active_now
    )
    if _route4_eligible:
        try:
            import npc_dialog_lookup as _ndl
            _ndl_result = _ndl.lookup(npc_dialog)
            if _ndl_result:
                _ndl_ja_tmpl, _ndl_ph = _ndl_result
                _ndl_ja = _ndl.format_japanese(_ndl_ja_tmpl, _ndl_ph)
                if ctx.panel_only_interior_message:
                    w._ui_router.update_panel_translation(
                        npc_dialog, _ndl_ja, speech_role="conversation")
                else:
                    w._ui_router.update_translation(
                        NPC_CONVERSATION_OWNER, npc_dialog, _ndl_ja,
                        speech_role="conversation")
                _log.info(
                    "npc_dialog message displayed "
                    "(route=ask_about panel_only=%s text=%r)",
                    ctx.panel_only_interior_message, npc_dialog)
            else:
                _log.info(
                    "route4 lookup miss "
                    "(npc_conv=%s in_interior=%s changed=%s "
                    "just_opened=%s text=%r)",
                    w._npc_conversation_active, in_interior,
                    npc_dialog_changed, dialog_just_opened,
                    npc_dialog[:120])
        except (ImportError, AttributeError):
            pass
    elif (npc_dialog
            and _current_top_level(w) == "normal-play"
            and w._npc_conversation_active):
        _r4_reasons = []
        if npc_translated:
            _r4_reasons.append("translated_by_route2")
        if not (npc_dialog_changed or dialog_just_opened):
            _r4_reasons.append("no_change_no_edge")
        if not (w._npc_conversation_active or in_interior):
            _r4_reasons.append("no_conv_no_interior")
        if facility_active_now:
            _r4_reasons.append("facility_active")
        if _r4_reasons:
            _route4_skip_key = (tuple(_r4_reasons), npc_dialog[:80])
            _prev_skip_key = getattr(w, "_b263_route4_skip_prev", None)
            if _route4_skip_key != _prev_skip_key:
                w._b263_route4_skip_prev = _route4_skip_key
                _log.info(
                    "route4 skipped (reasons=%s text=%r)",
                    "|".join(_r4_reasons), npc_dialog[:80])


__all__ = ["poll_npc_conversation", "NPC_CONVERSATION_OWNER"]
