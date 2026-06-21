"""session/npc_chat_session.py — 通常 NPC 会話セッション。

NPC 会話判定信号 `+0xA845` で規定される通常 NPC 会話の latch を、
SessionBase インタフェースに適合させた実装。

判定信号 `+0xA845` の値マッピング:

| 観測値 | 動作 |
|---|---|
| `0x00` | latch off (会話終了) |
| `0x85` | latch on  (会話開始 = 質問中) |
| `0x9A` | 状態保持 (街中オーバーレイ = 入店メッセージ表示中) |
| `0x10` | 状態保持 (応答中 または 死体クリック中) |
| 未知値 | 状態保持 (警告ログ出力は呼び出し側の責任) |

スコープ:
- latch 管理を実装する (try_start / try_stop)
- 具体的な翻訳タブ・パネル更新は既存 `controllers/poll_controller.py` /
  `controllers/img_screen_controller.py` が並行して動作する (= 挙動互換)
"""
from __future__ import annotations

from .session_base import SessionBase, SessionContext


# +0xA845 観測値マッピング
NPC_PHASE_IDLE = 0x00              # 待機 (= 会話終了)
NPC_PHASE_ASKING = 0x85            # 質問中 (= 会話開始)
NPC_PHASE_RESPONDING_OR_LOOT = 0x10  # 応答中 / 死体クリック中 (状態保持)
NPC_PHASE_BUILDING_ENTRY = 0x9A    # 街中オーバーレイ = 入店メッセージ (状態保持)


# 状態保持となる値 (= latch を変更しない)
_HOLD_PHASES = frozenset({
    NPC_PHASE_RESPONDING_OR_LOOT,
    NPC_PHASE_BUILDING_ENTRY,
})


class NpcChatSession(SessionBase):
    """通常 NPC 会話セッション。

    SessionBase インタフェースに沿った latch 管理:
      - try_start: `+0xA845 == 0x85` 観測で latch on
      - try_stop:  `+0xA845 == 0x00` または normal-play 離脱で latch off
      - その他観測値: 状態保持

    トップレベル状態が `normal-play` 以外では発火しない (= 通常プレイ中の
    独立状態)。
    """

    name = "npc_chat"

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def try_start(self, ctx: SessionContext) -> bool:
        """`+0xA845 == 0x85` 観測で latch on。

        normal-play 以外では発火しない。
        """
        if ctx.top_level_state != "normal-play":
            return False
        if ctx.npc_phase == NPC_PHASE_ASKING:
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        """`+0xA845 == 0x00` 観測または normal-play 離脱で latch off。

        `0x9A` / `0x10` / 未知値は状態保持 (= False を返して継続)。
        """
        if ctx.top_level_state != "normal-play":
            self._set_active(False)
            return True
        if ctx.npc_phase == NPC_PHASE_IDLE:
            self._set_active(False)
            return True
        # 状態保持 (継続) — 未知値も同じ扱い
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理。

        現状は no-op (= 既存 poll_controller / img_screen_controller
        が翻訳タブ・パネル更新を担う)。
        """
        return None


__all__ = [
    "NpcChatSession",
    "NPC_PHASE_IDLE",
    "NPC_PHASE_ASKING",
    "NPC_PHASE_RESPONDING_OR_LOOT",
    "NPC_PHASE_BUILDING_ENTRY",
]
