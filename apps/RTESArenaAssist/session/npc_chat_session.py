from __future__ import annotations

from .session_base import SessionBase, SessionContext


NPC_PHASE_IDLE = 0x00
NPC_PHASE_ASKING = 0x85
NPC_PHASE_RESPONDING_OR_LOOT = 0x10
NPC_PHASE_BUILDING_ENTRY = 0x9A


_HOLD_PHASES = frozenset({
    NPC_PHASE_RESPONDING_OR_LOOT,
    NPC_PHASE_BUILDING_ENTRY,
})


class NpcChatSession(SessionBase):

    name = "npc_chat"


    def try_start(self, ctx: SessionContext) -> bool:
        if ctx.top_level_state != "normal-play":
            return False
        if ctx.npc_phase == NPC_PHASE_ASKING:
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        if ctx.top_level_state != "normal-play":
            self._set_active(False)
            return True
        if ctx.npc_phase == NPC_PHASE_IDLE:
            self._set_active(False)
            return True
        return False

    def poll(self, ctx: SessionContext) -> None:
        return None


__all__ = [
    "NpcChatSession",
    "NPC_PHASE_IDLE",
    "NPC_PHASE_ASKING",
    "NPC_PHASE_RESPONDING_OR_LOOT",
    "NPC_PHASE_BUILDING_ENTRY",
]
