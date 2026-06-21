"""map/dispatcher.py — 分離階層 L2 + L3 屋内 統括 dispatcher。

L2 (= 基本居場所) + L3 屋内 の 2 階層を統括する。軸選択は単一分類器
``classify_map_axis`` (1軸・判定1回) が決定し、本 dispatcher はその結論を
消費して経路を確定する (= classify→dispatch。旧「各 session が try_start
で memory を再 read して並列判定し優先順で選定」する構造を是正)。

構成:
  - L2 = BaseLocationDispatcher (= dungeon / city / wilderness の経路保持)
  - L3 屋内 = InteriorMapSession

公開 API (= MapDispatcher.poll / get_canvas_data / active_key /
reset_progress / poll_automap_file) は維持し、tab_map / poll_controller
からの呼出は変更不要。
"""
from __future__ import annotations

import logging
from typing import Optional

from common_draw.automap_canvas import CanvasData

from normal_play.base_location import BaseLocationDispatcher
from normal_play.base_location.base_location_view import classify_map_axis

from .base import MapContext, MapSessionBase
from .interior import InteriorMapSession

_log = logging.getLogger("map.dispatcher")


class MapDispatcher:
    """分離階層 L2 + L3 屋内 を統括し、active 1 個だけが描画権を持つ。"""

    def __init__(self) -> None:
        # L2 (= 基本居場所): dungeon / city / wilderness
        self.base_location = BaseLocationDispatcher()
        # L3 屋内
        self.interior = InteriorMapSession()
        # 利便性のため L2 sessions も直接公開 (= 段階 8 で廃止予定)
        self.dungeon    = self.base_location.dungeon
        self.city       = self.base_location.city
        self.wilderness = self.base_location.wilderness

        # 現在 active な経路 ("interior" or "base_location" or None)
        self._active_path: Optional[str] = None
        # 軸変化の診断ログ用 (変化時のみ出力)
        self._diag_prev_axis: Optional[str] = "(init)"

    def poll(self, ctx: MapContext) -> None:
        """1 poll: classify_map_axis (単一判定) の結論で経路を確定する。

        axis=="interior" は L3 屋内経路、それ以外 (dungeon/city/wilderness/
        None) は L2 BaseLocationDispatcher へ結論ごと委譲する。"""
        axis = classify_map_axis(
            ctx.analyzer, ctx.anchor,
            mif_name=ctx.mif_name,
            interior_mif_name=ctx.interior_mif_name,
            in_interior=ctx.in_interior,
            area=ctx.area,
        )
        if axis != self._diag_prev_axis:
            _log.info("map axis: %s -> %s (mif=%r interior_mif=%r)",
                      self._diag_prev_axis, axis,
                      ctx.mif_name, ctx.interior_mif_name)
            self._diag_prev_axis = axis
        if axis == "interior":
            self._poll_interior(ctx)
        else:
            self._poll_base_location(ctx, axis)

    def _poll_interior(self, ctx: MapContext) -> None:
        """L3 屋内経路: InteriorMapSession を active 化、L2 は suspend。

        L2 を suspend (= deactivate ではなく) することで、内部 state
        (= chunk_tracker 等) を保持。退出時に同 L2 axis に戻る場合は
        start() を呼ばず resume する。
        """
        # 経路切替時: L2 を一時停止 (= state は保持、resume 待機)
        if self._active_path != "interior":
            self.base_location.suspend(ctx)
            self.interior.start(ctx)
            self._active_path = "interior"
        # active 中は update のみ
        if self.interior.is_active():
            self.interior.update(ctx)

    def _poll_base_location(self, ctx: MapContext,
                            axis: Optional[str]) -> None:
        """L2 経路: 確定済み軸 (axis) を BaseLocationDispatcher へ委譲。"""
        # 経路切替時: interior を停止
        if self._active_path != "base_location":
            if self.interior.is_active():
                self.interior.stop(ctx)
            self._active_path = "base_location"
        # L2 dispatcher は確定済み軸を消費して start/stop/update を実行
        self.base_location.poll(ctx, target_key=axis)

    def get_canvas_data(self) -> CanvasData:
        """active 経路の CanvasData を返す。非 active なら空。"""
        if self._active_path == "interior":
            if self.interior.is_active():
                return self.interior.get_canvas_data()
            return CanvasData()
        if self._active_path == "base_location":
            return self.base_location.get_canvas_data()
        return CanvasData()

    def active_key(self) -> Optional[str]:
        """active session の key (= "interior" / "dungeon" / "city" /
        "wilderness" / None)。互換のため従来形式で返す。
        """
        if self._active_path == "interior":
            return "interior" if self.interior.is_active() else None
        if self._active_path == "base_location":
            return self.base_location.active_key()
        return None

    def reset_progress(self) -> None:
        """active session の探索状態をリセット (= ロード時等)。"""
        if self._active_path == "interior":
            if self.interior.is_active():
                self.interior.reset_progress()
        elif self._active_path == "base_location":
            self.base_location.reset_progress()

    def poll_automap_file(self) -> bool:
        """active が dungeon の場合のみ AUTOMAP.NN を再取込試行。

        互換: tab_map.poll_automap_file の呼出元 (= poll_controller) のため。
        他軸 active 時は何もしない (= AUTOMAP はダンジョン専用)。
        """
        if (self._active_path == "base_location"
                and self.base_location.active_key() == "dungeon"):
            return self.base_location.dungeon.poll_automap_file()
        return False


__all__ = ["MapDispatcher"]
