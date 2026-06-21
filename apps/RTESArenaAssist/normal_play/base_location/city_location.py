"""base_location/city_location.py — 分離階層 L2 (= 基本居場所) C2 街。

データソース: テンプレ MIF + citySeed から expand_city_plan_with_random で
plan + block 配置 (= 既存 city_voxel_assembler.build_city_voxel_grid_by_name)。

判定:
  - `location_type == "city"` かつ `in_interior == False`
  - location_name (= 街名 "Moonguard" 等) 必須

描画:
  - 街全体 voxel grid (= テンプレ MIF サイズ、典型 200×200 等)
  - 全 cell 判明扱い (= bitmap 全 3)
  - 建物入口 (= MENU voxel) を赤マス overlay

注意: `map/city.py` から本 path へ移管。共通基底は
当面 normal_play/map/base.py を再利用 (= 後段で統合予定)。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from common_draw.automap_canvas import CanvasData
from services.city_voxel_assembler import (
    build_city_voxel_grid_by_name, detect_menu_cells,
)

from normal_play.map.base import MapContext, MapSessionBase

_log = logging.getLogger("base_location.city")


class CityMapSession(MapSessionBase):
    """C2 街マップ。テンプレ MIF + citySeed で街全体 grid を組立。"""

    def __init__(self) -> None:
        super().__init__()
        self._city_name: Optional[str] = None
        self._walkable: Optional[np.ndarray] = None
        self._map1:     Optional[np.ndarray] = None
        self._flor:     Optional[np.ndarray] = None
        self._bitmap:   Optional[np.ndarray] = None
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        # 表示
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle:    Optional[float] = None
        # 設定値
        self._show_grid = True

    # 軸選択 (旧 try_start 自前判定: C2 かつ非屋内) は classify_map_axis が
    # 単一決定する (= 判定は session に置かない)。

    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        # 街名が変わったら state clear (= 同じ街なら再進入時にキャッシュ再利用)
        if ctx.location_name and ctx.location_name != self._city_name:
            self._reset_state()

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)
        # state は保持

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._player_x = ctx.player_tile_x
        self._player_y = ctx.player_tile_y
        self._angle = ctx.angle_deg
        self._show_grid = ctx.show_grid

        if ctx.location_name and ctx.location_name != self._city_name:
            self._load_city_grid(ctx.location_name)
            self._city_name = ctx.location_name

    def get_canvas_data(self) -> CanvasData:
        return CanvasData(
            walkable=self._walkable,
            map1=self._map1,
            flor=self._flor,
            bitmap_grid=self._bitmap,
            notes=[],
            player_x=int(self._player_x) if self._player_x is not None else None,
            player_y=int(self._player_y) if self._player_y is not None else None,
            player_angle_deg=self._angle,
            level_up_index=None,
            level_down_index=None,
            entrance_cells=self._entrance_cells,
            is_wilderness=False,
            hidden_door_ids=frozenset(),
            menu_texture_indices=frozenset(),
        )

    def reset_progress(self) -> None:
        # 街は全 cell 判明扱いなので、grid 再構築で十分
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)

    # ── 内部 ──────────────────────────────────────────────

    def _reset_state(self) -> None:
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        self._entrance_cells = ()
        self._city_name = None

    def _load_city_grid(self, location_name: str) -> None:
        try:
            grid = build_city_voxel_grid_by_name(location_name)
        except Exception:  # noqa: BLE001
            _log.exception("build_city_voxel_grid_by_name failed: %s",
                           location_name)
            grid = None
        if grid is None:
            self._walkable = None
            self._map1 = None
            self._flor = None
            self._bitmap = None
            self._entrance_cells = ()
            return

        self._map1 = grid.map1
        self._flor = grid.flor
        self._walkable = (grid.map1 == 0) | ((grid.map1 & 0xF000) == 0x8000)
        # 全 cell 判明
        self._bitmap = np.full((grid.depth, grid.width), 3, dtype=np.uint8)
        self._entrance_cells = grid.menu_cells


__all__ = ["CityMapSession"]
