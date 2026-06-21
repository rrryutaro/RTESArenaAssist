from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from common_draw.automap_canvas import CanvasData
from services.city_voxel_assembler import detect_menu_cells
from runtime_paths import resolve_arena_install_dir
from services.mif_loader import (
    DEFAULT_INF_DIR, DEFAULT_MIF_DIR,
    load_mif,
    parse_inf_level_transitions,
    parse_inf_menu_indices,
    parse_inf_walls_hidden_door_ids,
    resolve_inf_for_mif,
)

from .base import MapContext, MapSessionBase

_log = logging.getLogger("map.interior")


class InteriorMapSession(MapSessionBase):

    def __init__(self) -> None:
        super().__init__()
        self._mif_dirs = [d for d in (DEFAULT_MIF_DIR, resolve_arena_install_dir())
                          if d is not None]
        self._inf_dir = DEFAULT_INF_DIR
        self._mif_name:   Optional[str] = None
        self._floor:      int = 0
        self._walkable:   Optional[np.ndarray] = None
        self._map1:       Optional[np.ndarray] = None
        self._flor:       Optional[np.ndarray] = None
        self._bitmap:     Optional[np.ndarray] = None
        self._level_up_index:   Optional[int] = None
        self._level_down_index: Optional[int] = None
        self._hidden_door_ids: frozenset[int] = frozenset()
        self._menu_texture_indices: frozenset[int] = frozenset()
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        self._entry_center: Optional[tuple[int, int]] = None
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle:    Optional[float] = None


    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        if (ctx.interior_mif_name
                and ctx.interior_mif_name != self._mif_name):
            self._reset_state()

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._player_x = ctx.player_tile_x
        self._player_y = ctx.player_tile_y
        self._angle = ctx.angle_deg

        target_mif = ctx.interior_mif_name
        if not target_mif:
            if getattr(self, "_diag_last", None) != "no_mif":
                self._diag_last = "no_mif"
                _log.warning("interior update: interior_mif_name 未解決 → 空表示")
            return
        if target_mif != self._mif_name or ctx.player_floor != self._floor:
            self._load_mif(target_mif, ctx.player_floor)
            self._mif_name = target_mif
            self._floor = ctx.player_floor
            wshape = None if self._walkable is None else self._walkable.shape
            _log.warning(
                "interior loaded mif=%s floor=%s walkable=%s entrance=%s",
                target_mif, ctx.player_floor, wshape, self._entrance_cells)
            self._diag_last = "loaded"

    def get_canvas_data(self) -> CanvasData:
        px = int(self._player_x) if self._player_x is not None else None
        py = int(self._player_y) if self._player_y is not None else None
        angle = self._angle
        if not self._coord_in_bounds(px, py) and self._entry_center is not None:
            px, py = self._entry_center
        return CanvasData(
            walkable=self._walkable,
            map1=self._map1,
            flor=self._flor,
            bitmap_grid=self._bitmap,
            notes=[],
            player_x=px,
            player_y=py,
            player_angle_deg=angle,
            level_up_index=self._level_up_index,
            level_down_index=self._level_down_index,
            entrance_cells=self._entrance_cells,
            is_wilderness=False,
            hidden_door_ids=self._hidden_door_ids,
            menu_texture_indices=self._menu_texture_indices,
        )

    def reset_progress(self) -> None:
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)


    def _reset_state(self) -> None:
        self._mif_name = None
        self._floor = 0
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        self._level_up_index = None
        self._level_down_index = None
        self._hidden_door_ids = frozenset()
        self._menu_texture_indices = frozenset()
        self._entrance_cells = ()
        self._entry_center = None

    def _load_mif(self, mif_name: str, player_floor: int = 0) -> None:
        try:
            mif = load_mif(mif_name, self._mif_dirs, player_floor=player_floor)
        except Exception:  # noqa: BLE001
            _log.exception("parse_mif failed: %s", mif_name)
            self._reset_state()
            return
        if mif is None:
            self._reset_state()
            return

        map1 = np.array(mif.map1, dtype=np.uint16).reshape(mif.height, mif.width)
        self._map1 = map1
        self._walkable = (map1 == 0) | ((map1 & 0xF000) == 0x8000)
        if mif.flor and len(mif.flor) >= mif.height * mif.width:
            self._flor = np.array(mif.flor, dtype=np.uint16).reshape(
                mif.height, mif.width)
        else:
            self._flor = None

        self._level_up_index = None
        self._level_down_index = None
        hidden_door_ids: set[int] = set()
        menu_indices: set[int] = set()
        inf_path = resolve_inf_for_mif(
            mif_name, getattr(mif, "info_name", ""), self._inf_dir)
        if inf_path is not None:
            try:
                lu, ld = parse_inf_level_transitions(inf_path)
                self._level_up_index = lu
                self._level_down_index = ld
            except Exception:  # noqa: BLE001
                pass
            try:
                hidden_door_ids = parse_inf_walls_hidden_door_ids(inf_path)
            except Exception:  # noqa: BLE001
                pass
            try:
                menu_indices = parse_inf_menu_indices(inf_path)
            except Exception:  # noqa: BLE001
                pass
        self._hidden_door_ids = frozenset(hidden_door_ids)
        self._menu_texture_indices = frozenset(menu_indices)

        self._bitmap = np.full((mif.height, mif.width), 3, dtype=np.uint8)

        if menu_indices:
            excludes: set[int] = set()
            if self._level_up_index is not None:
                excludes.add(int(self._level_up_index))
            if self._level_down_index is not None:
                excludes.add(int(self._level_down_index))
            try:
                cells = detect_menu_cells(map1, menu_indices, excludes)
                self._entrance_cells = tuple(cells)
            except Exception:  # noqa: BLE001
                _log.exception("detect_menu_cells failed for interior MIF")
                self._entrance_cells = ()
        else:
            self._entrance_cells = ()

        self._entry_center = self._compute_entry_center()

    def _coord_in_bounds(self, px: Optional[int], py: Optional[int]) -> bool:
        if px is None or py is None or self._walkable is None:
            return False
        h, w = self._walkable.shape
        return 0 <= px < w and 0 <= py < h

    def _compute_entry_center(self) -> Optional[tuple[int, int]]:
        if self._walkable is None or not self._entrance_cells:
            return None
        h, w = self._walkable.shape
        ex, ey = self._entrance_cells[0]
        for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nx, ny = ex + dx, ey + dy
            if 0 <= nx < w and 0 <= ny < h and bool(self._walkable[ny][nx]):
                return (nx, ny)
        if 0 <= ex < w and 0 <= ey < h:
            return (ex, ey)
        return None


__all__ = ["InteriorMapSession"]
