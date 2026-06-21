"""session/ パッケージ — 会話・対話セッションの分離管理。

通常プレイ中の対話状態を「通常 NPC 会話」「施設会話」の 2 段 latch で
管理する。各セッションは独立ファイルで定義し、session_manager が相互
排他を保証する。
"""
from .session_base import SessionBase, SessionContext
from .session_manager import SessionManager
from .npc_chat_session import NpcChatSession
from .tavern_session import TavernSession
from .temple_session import TempleSession
from .equipment_session import EquipmentSession
from .mages_guild_session import MagesGuildSession

__all__ = [
    "SessionBase",
    "SessionContext",
    "SessionManager",
    "NpcChatSession",
    "TavernSession",
    "TempleSession",
    "EquipmentSession",
    "MagesGuildSession",
]
