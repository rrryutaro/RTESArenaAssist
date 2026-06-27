from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from hierarchy_state import SeparationHierarchy

@dataclass
class SessionContext:
    analyzer: object
    anchor: int
    img_name: str = ''
    screen_id: str = ''
    top_level_state: str = ''
    in_interior: bool = False
    npc_phase: Optional[int] = None
    mif_name: str = ''
    interior_mif_name: Optional[str] = None
    facility_kind: str = ''
    hierarchy: Optional[SeparationHierarchy] = None
    extras: dict = None

    def __post_init__(self) -> None:
        if self.extras is None:
            self.extras = {}
        if self.hierarchy is None:
            self.hierarchy = SeparationHierarchy.from_parts(top_level_state=self.top_level_state, in_interior=self.in_interior, npc_active=False)

class SessionBase:
    name: str = '<unnamed>'

    def __init__(self) -> None:
        self._active: bool = False

    def is_active(self) -> bool:
        return self._active

    def _set_active(self, value: bool) -> None:
        self._active = bool(value)

    def try_start(self, ctx: SessionContext) -> bool:
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        return False

    def poll(self, ctx: SessionContext) -> None:
        return None

    def on_other_session_started(self, ctx: SessionContext) -> None:
        self._active = False

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} name={self.name!r} active={self._active}>'
__all__ = ['SessionBase', 'SessionContext']
