"""base_location/base_location_dispatcher.py — 分離階層 L2 統括 dispatcher。

分離階層モデル。L2 (= 基本居場所 C1/C2/C3) のうち、単一分類器
``classify_map_axis`` が確定した軸 1 個だけが描画権を持つ (= classify→
dispatch・1軸化。旧「3 軸の try_start を毎 poll 並列評価し優先順で選定」
する構造を是正)。

注意: 屋内 (= L3) は本 dispatcher の対象外。axis=="interior" は呼び出し側
(= map/dispatcher.py) が interior 経路に分岐する。

active 切替時に旧 active を stop() し、新 active を start() する。
これにより、軸間で state が leak しない (= 各 session 内に state 閉鎖)。
"""
from __future__ import annotations

from typing import Optional

from common_draw.automap_canvas import CanvasData

from normal_play.map.base import MapContext, MapSessionBase

from .dungeon_location import DungeonMapSession
from .city_location import CityMapSession
from .wilderness_location import WildernessMapSession


class BaseLocationDispatcher:
    """L2 (= 基本居場所) 3 session を統括し、active 1 個だけが描画権を持つ。

    suspend/resume 機構:
      L3 (= 屋内) 突入時に `suspend()` で L2 active を一時停止し、退出時に
      next `poll()` で resume する。同じ L2 axis に戻る場合は session の
      start() を呼ばず内部 state (= chunk_tracker 等) を保持したまま
      update() のみ実行する。これにより親 L2 情報が L3 跨ぎで保持される
      (「スタック的な親参照」)。
    """

    def __init__(self) -> None:
        # 評価順 (= 優先度高 → 低)
        self.dungeon    = DungeonMapSession()
        self.city       = CityMapSession()
        self.wilderness = WildernessMapSession()
        self._sessions = [
            ("dungeon",    self.dungeon),
            ("city",       self.city),
            ("wilderness", self.wilderness),
        ]
        self._active_key: Optional[str] = None
        # 一時停止中の親 L2 軸。L3 (= 屋内) 突入時に保存し、退出後の
        # 再 active 化時に同一 axis なら start() を呼ばず resume する。
        self._suspended_key: Optional[str] = None

    def poll(self, ctx: MapContext, *,
             target_key: Optional[str]) -> None:
        """1 poll: 確定済み軸 (target_key) の start/stop/update。

        target_key は ``classify_map_axis`` の結論 ("dungeon"/"city"/
        "wilderness"/None)。本 dispatcher は判定を持たず結論を消費する。

        Resume 経路: 一時停止中で同一 axis へ戻る場合、session の start()
        は呼ばず update() のみ実行 (= 親 L2 state 保持)。
        """
        # Resume: 一時停止と同一 axis に戻る → start() スキップで state 保持
        if (self._suspended_key is not None
                and target_key == self._suspended_key):
            self._active_key = target_key
            self._suspended_key = None
            if self._active_key is not None:
                dict(self._sessions)[self._active_key].update(ctx)
            return

        # 通常の切替 (= 一時停止状態を解除、別 axis に推移)
        self._suspended_key = None

        # 軸切替: 旧 active を stop、新 active を start
        if target_key != self._active_key:
            if self._active_key is not None:
                old = dict(self._sessions)[self._active_key]
                old.stop(ctx)
            self._active_key = target_key
            if target_key is not None:
                new = dict(self._sessions)[target_key]
                new.start(ctx)

        # active 中なら update
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].update(ctx)

    def get_canvas_data(self) -> CanvasData:
        """active session の CanvasData を返す。非 active なら空。

        suspend 中は suspended session の最後の canvas を返す (= L3 active
        時にも L2 の最後の表示は保持される)。
        """
        if self._active_key is not None:
            return dict(self._sessions)[self._active_key].get_canvas_data()
        if self._suspended_key is not None:
            return dict(self._sessions)[self._suspended_key].get_canvas_data()
        return CanvasData()

    def active_key(self) -> Optional[str]:
        """現在 active な L2 axis (= "dungeon"/"city"/"wilderness")、無ければ None。"""
        return self._active_key

    def suspended_key(self) -> Optional[str]:
        """一時停止中の L2 axis (= L3 active 中の親情報)、無ければ None。"""
        return self._suspended_key

    def last_known_key(self) -> Optional[str]:
        """active or suspended (= L3 中も含めて直近の L2 axis を返す)。"""
        return self._active_key or self._suspended_key

    def suspend(self, ctx: MapContext) -> None:
        """active を一時停止 (= L3 突入時用)。state は session 内に保持。

        session の stop() は呼ばない (= start() を呼んで restart する事態を
        避けるため、resume 経路で start() スキップが意味を持つ)。
        """
        if self._active_key is not None:
            self._suspended_key = self._active_key
            self._active_key = None

    def deactivate(self, ctx: MapContext) -> None:
        """active を強制 off + suspended もクリア (= 完全リセット用)。

        suspend と異なり、resume 機構には乗らない。ロード等の完全リセット時
        に使う。
        """
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].stop(ctx)
            self._active_key = None
        self._suspended_key = None

    def reset_progress(self) -> None:
        """active session の探索状態をリセット (= ロード時等)。"""
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].reset_progress()


__all__ = ["BaseLocationDispatcher"]
