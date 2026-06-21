"""session/session_manager.py — 全セッション統括。

通常プレイ中の対話・会話セッション (通常 NPC 会話 / 宿屋 / 寺院 / 武具店 /
魔術師ギルド / 宮殿) を一括で poll し、以下を保証する:

- **相互排他**: 同時に複数 latch が on にならない。active が確定したら
  他セッションには on_other_session_started を通知して強制 off にする
  (defensive)。
- **優先順位**: register された順序 = 優先順位。先に登録された方が
  active 確定の判定で優先される。
- **active 継続中の他開始抑止**: いずれかが active な間、他の
  try_start は呼ばれない (= ある会話が始まったら終わるまで保持)。

設計原則:
- 通常 NPC 会話 latch との相互排他は npc_chat_session 側 (or 本マネージャ)
  で `+0xA845` の状態管理を統括する。施設会話 latch on 中は通常 NPC 会話
  latch の更新を抑止する。
"""
from __future__ import annotations

from typing import List, Optional

from .session_base import SessionBase, SessionContext


class SessionManager:
    """会話・対話セッション群の統括。"""

    def __init__(self) -> None:
        self._sessions: List[SessionBase] = []
        self._active: Optional[SessionBase] = None

    # ------------------------------------------------------------------
    # 登録
    # ------------------------------------------------------------------

    def register(self, session: SessionBase) -> None:
        """セッションを登録。登録順 = 優先順位。

        同一インスタンスの二重登録は無効化 (= 重複 register でも 1 つだけ
        保持)。
        """
        if session in self._sessions:
            return
        self._sessions.append(session)

    def sessions(self) -> List[SessionBase]:
        """登録済セッションを登録順で返す (debug / 検査用)。"""
        return list(self._sessions)

    def active_session(self) -> Optional[SessionBase]:
        """現在 active なセッション (なければ None)。"""
        return self._active

    def is_any_active(self) -> bool:
        """いずれかのセッションが active か。"""
        return self._active is not None

    # ------------------------------------------------------------------
    # poll
    # ------------------------------------------------------------------

    def poll(self, ctx: SessionContext) -> None:
        """各セッションの開始・終了判定と内部処理を実行する。

        フロー:
          1. active session があれば try_stop を試す
             - stop 成立 → active = None、stopped_this_poll に記録、ステップ 2 へ
             - 継続 → poll を呼んで return (= 他セッションの try_start
               は呼ばない)
          2. active なし → 登録順に try_start を試す
             - stopped_this_poll を skip (同 poll 内での即 restart 防止)
             - on に変わったセッションがあれば active 確定、他に
               on_other_session_started 通知、poll 実行、return
             - どれも開始しなければ何もしない (= 通常プレイ普段時)
        """
        # 1. active セッションがあれば終了判定 + 継続処理
        stopped_this_poll: Optional[SessionBase] = None
        if self._active is not None:
            if self._active.try_stop(ctx):
                # latch off に変わった。同 poll で即再 start させない
                stopped_this_poll = self._active
                self._active = None
            else:
                # 継続: poll のみ呼ぶ (他セッションの try_start は呼ばない)
                self._active.poll(ctx)
                return

        # 2. active なし → 登録順に try_start を試す (stopped セッションは skip)
        for s in self._sessions:
            if s is stopped_this_poll:
                continue
            if s.try_start(ctx):
                # 他セッションに通知 (= defensive、二重 active 防止)
                for other in self._sessions:
                    if other is not s and other.is_active():
                        other.on_other_session_started(ctx)
                self._active = s
                # 開始直後の同 poll で内部処理も実行する
                s.poll(ctx)
                return

        # 3. どれも開始せず active なし = 通常プレイ普段時
        # session_manager 側では何もしない (= poll_controller 側で扱う)
        return None


__all__ = ["SessionManager"]
