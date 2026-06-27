from __future__ import annotations
from .session_base import SessionBase, SessionContext

class PalaceSession(SessionBase):
    name = 'palace'

    def try_start(self, ctx: SessionContext) -> bool:
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        return False
__all__ = ['PalaceSession']
