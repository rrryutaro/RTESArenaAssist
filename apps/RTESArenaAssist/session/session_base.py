"""session/session_base.py — 会話・対話セッションの共通基底。

通常プレイ中の対話・会話セッションが守るべきインタフェースを規定する。
各セッション (通常 NPC 会話 / 宿屋 / 寺院 / 武具店 / 魔術師ギルド / 宮殿)
は本クラスを継承して開始・終了境界の判定 / 内部処理 / クリーンアップを
実装する。

session_manager (本パッケージ) が複数セッションを統括し、相互排他
(同時 on にならない) を保証する。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from hierarchy_state import SeparationHierarchy


@dataclass
class SessionContext:
    """各セッションが poll 時に参照する共通コンテキスト。

    memory アクセスや画面状態シグナルをまとめて持たせ、各セッションは
    本コンテキスト経由で外部状態を取得する。直接 assist_window に依存
    させないことで、テスト容易性と疎結合を確保する。

    フィールドは段階的に拡張する (= 各セッション実装時に必要となった
    シグナルを追加していく)。
    """
    analyzer: object              # ArenaMemoryAnalyzer 相当
    anchor: int
    img_name: str = ""
    screen_id: str = ""
    top_level_state: str = ""    # "pregame" | "chargen" | "normal-play"
    in_interior: bool = False
    # NPC 会話判定信号 (+0xA845)。session_manager が読んで詰める。
    npc_phase: Optional[int] = None
    # 場所識別情報。施設会話セッションが入店境界を判定するために使う。
    # mif_name           - 現在の MIF 名 (街路上 = 街マップ MIF / 在室中 = 街マップ MIF)
    # interior_mif_name  - 在室中なら Interior MIF 名 (例: "TAVERN8.MIF")、街路上は None
    # facility_kind      - CityViewer の FacilityPlacement.menu_type 由来の文字列
    #                      ("TAVERN" / "TEMPLE" / "EQUIPMENT" / "MAGES_GUILD" /
    #                       "PALACE" 等)。取得不可なら ""。
    mif_name: str = ""
    interior_mif_name: Optional[str] = None
    facility_kind: str = ""
    hierarchy: Optional[SeparationHierarchy] = None
    # 拡張領域: 各セッションが必要に応じて利用する追加情報。
    # 例: window 参照 (= UI 更新コールバック)、共有 latch など。
    extras: dict = None

    def __post_init__(self) -> None:
        if self.extras is None:
            self.extras = {}
        if self.hierarchy is None:
            self.hierarchy = SeparationHierarchy.from_parts(
                top_level_state=self.top_level_state,
                in_interior=self.in_interior,
                npc_active=False,
            )


class SessionBase:
    """会話・対話セッションの共通基底。

    サブクラスで `name` を上書きし、`try_start` / `try_stop` / `poll` /
    `on_other_session_started` を必要に応じて override する。

    latch 状態 (`_active`) は基底クラスが管理し、外部からは
    `is_active()` で参照する。サブクラスは `_set_active(True/False)`
    で latch を更新する。
    """

    name: str = "<unnamed>"

    def __init__(self) -> None:
        self._active: bool = False

    # ------------------------------------------------------------------
    # latch 状態
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        """latch on か否か。"""
        return self._active

    def _set_active(self, value: bool) -> None:
        """サブクラスから latch 状態を更新する内部 API。"""
        self._active = bool(value)

    # ------------------------------------------------------------------
    # ライフサイクル (サブクラスで override)
    # ------------------------------------------------------------------

    def try_start(self, ctx: SessionContext) -> bool:
        """開始境界が成立すれば latch on にする。

        Returns:
          新たに on に切り替わったら True、現状維持なら False。
          既に active なら呼ばれない (session_manager が制御)。
        """
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        """終了境界が成立すれば latch off + cleanup を実行する。

        Returns:
          新たに off に切り替わったら True、継続なら False。
          active な間に session_manager から毎 poll 呼ばれる。
        """
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理 (翻訳タブ・パネル更新等)。

        try_stop が False を返した直後に呼ばれる。サブクラスで override。
        """
        # default: no-op
        return None

    def on_other_session_started(self, ctx: SessionContext) -> None:
        """他のセッションが先に on に切り替わった時の強制 off。

        相互排他保証のため session_manager から呼ばれる。サブクラスは
        必要なら cleanup を追加実装する。基底実装は latch off のみ。
        """
        self._active = False

    # ------------------------------------------------------------------
    # 表現
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} active={self._active}>"


__all__ = ["SessionBase", "SessionContext"]
