from __future__ import annotations
from typing import List, Optional
from .session_base import SessionBase, SessionContext

class SessionManager:

    def __init__(self) -> None:
        self._sessions: List[SessionBase] = []
        self._active: Optional[SessionBase] = None

    def register(self, session: SessionBase) -> None:
        if session in self._sessions:
            return
        self._sessions.append(session)

    def sessions(self) -> List[SessionBase]:
        return list(self._sessions)

    def active_session(self) -> Optional[SessionBase]:
        return self._active

    def is_any_active(self) -> bool:
        return self._active is not None

    def poll(self, ctx: SessionContext) -> None:
        stopped_this_poll: Optional[SessionBase] = None
        if self._active is not None:
            if self._active.try_stop(ctx):
                stopped_this_poll = self._active
                self._active = None
            else:
                self._active.poll(ctx)
                return
        for s in self._sessions:
            if s is stopped_this_poll:
                continue
            if s.try_start(ctx):
                for other in self._sessions:
                    if other is not s and other.is_active():
                        other.on_other_session_started(ctx)
                self._active = s
                s.poll(ctx)
                return
        return None
__all__ = ['SessionManager']
