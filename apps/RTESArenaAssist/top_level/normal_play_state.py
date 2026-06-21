from __future__ import annotations

from session.session_base import SessionContext
from top_level.top_level_dispatcher import build_session_context


def poll_sessions(w, ctx: SessionContext) -> None:
    if ctx.top_level_state != "normal-play":
        try:
            if not w._session_manager.is_any_active():
                return None
        except AttributeError:
            return None
    w._session_manager.poll(ctx)
    return None


def poll(w, ctx: SessionContext | None = None) -> None:
    if ctx is None:
        ctx = build_session_context(w)
    poll_sessions(w, ctx)


__all__ = ["poll", "poll_sessions"]
