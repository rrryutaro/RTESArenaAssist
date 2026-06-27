from __future__ import annotations
import logging
from typing import Optional
import numpy as np
from common_draw.automap_canvas import CanvasData
from services.city_voxel_assembler import build_city_voxel_grid_by_name, detect_menu_cells
from normal_play.map.base import MapContext, MapSessionBase
_log = logging.getLogger('base_location.city')

class CityMapSession(MapSessionBase):

    def __init__(self) -> None:
        super().__init__()
        self._city_name: Optional[str] = None
        self._walkable: Optional[np.ndarray] = None
        self._map1: Optional[np.ndarray] = None
        self._flor: Optional[np.ndarray] = None
        self._bitmap: Optional[np.ndarray] = None
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle: Optional[float] = None
        self._show_grid = True

    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        if ctx.location_name and ctx.location_name != self._city_name:
            self._reset_state()

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)

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
        return CanvasData(walkable=self._walkable, map1=self._map1, flor=self._flor, bitmap_grid=self._bitmap, notes=[], player_x=int(self._player_x) if self._player_x is not None else None, player_y=int(self._player_y) if self._player_y is not None else None, player_angle_deg=self._angle, level_up_index=None, level_down_index=None, entrance_cells=self._entrance_cells, is_wilderness=False, hidden_door_ids=frozenset(), menu_texture_indices=frozenset())

    def reset_progress(self) -> None:
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)

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
        except Exception:
            _log.exception('build_city_voxel_grid_by_name failed: %s', location_name)
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
        self._walkable = (grid.map1 == 0) | (grid.map1 & 61440 == 32768)
        self._bitmap = np.full((grid.depth, grid.width), 3, dtype=np.uint8)
        self._entrance_cells = grid.menu_cells
__all__ = ['CityMapSession']
