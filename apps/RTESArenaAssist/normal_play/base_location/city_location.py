from __future__ import annotations
import logging
from typing import Optional
import numpy as np
from common_draw.automap_canvas import CanvasData, FacilityEntranceMarker
from services.arena_types import ArenaMenuType
from services.city_lookup import get_facilities_by_location_name
from services.city_voxel_assembler import build_city_voxel_grid_by_name
from services.wild_flats import extract_flat_marks, get_city_flat_category_map
from normal_play.map.base import MapContext, MapSessionBase
_log = logging.getLogger('base_location.city')
_WRAP_EDGE_MARGIN = 2

def project_wrapped_city_axis(current: int, previous: int | None, size: int, edge_latch: str='') -> tuple[int, str]:
    if size <= 0 or not 0 <= current < size:
        return (current, '')
    low = _WRAP_EDGE_MARGIN
    high = size - 1 - _WRAP_EDGE_MARGIN
    if edge_latch == 'high':
        return (size - 1, 'high') if current <= low else (current, '')
    if edge_latch == 'low':
        return (0, 'low') if current >= high else (current, '')
    if previous is not None and 0 <= previous < size:
        if previous >= high and current <= low:
            return (size - 1, 'high')
        if previous <= low and current >= high:
            return (0, 'low')
    return (current, '')

class CityMapSession(MapSessionBase):

    def __init__(self) -> None:
        super().__init__()
        self._city_name: Optional[str] = None
        self._walkable: Optional[np.ndarray] = None
        self._map1: Optional[np.ndarray] = None
        self._flor: Optional[np.ndarray] = None
        self._bitmap: Optional[np.ndarray] = None
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        self._facility_entrances: tuple[FacilityEntranceMarker, ...] = ()
        self._flat_marks: tuple[tuple[int, int, str], ...] = ()
        self._flat_marks_key: Optional[int] = None
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._player_raw_x: Optional[int] = None
        self._player_raw_y: Optional[int] = None
        self._player_wrap_edge_x = ''
        self._player_wrap_edge_y = ''
        self._angle: Optional[float] = None
        self._show_grid = True
        self._show_static_flats = False

    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        if ctx.location_name and ctx.location_name != self._city_name:
            self._reset_state()

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._angle = ctx.angle_deg
        self._show_grid = ctx.show_grid
        self._show_static_flats = ctx.wild_show_static_flats
        if ctx.location_name and ctx.location_name != self._city_name:
            self._load_city_grid(ctx.location_name)
            self._city_name = ctx.location_name
        self._update_player_position(ctx.player_tile_x, ctx.player_tile_y)

    def get_canvas_data(self) -> CanvasData:
        return CanvasData(walkable=self._walkable, map1=self._map1, flor=self._flor, bitmap_grid=self._bitmap, notes=[], player_x=int(self._player_x) if self._player_x is not None else None, player_y=int(self._player_y) if self._player_y is not None else None, player_angle_deg=self._angle, level_up_index=None, level_down_index=None, entrance_cells=self._entrance_cells, facility_entrances=self._facility_entrances, flat_marks=self._city_flat_marks(), is_wilderness=False, hidden_door_ids=frozenset(), menu_texture_indices=frozenset(), map_key=f'city:{self._city_name}' if self._city_name else 'city:<unknown>')

    def reset_progress(self) -> None:
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)
        if self._city_name and self._map1 is not None:
            self._load_facility_entrances(self._city_name)

    def reset_coordinate_continuity(self) -> None:
        self._player_x = None
        self._player_y = None
        self._player_raw_x = None
        self._player_raw_y = None
        self._player_wrap_edge_x = ''
        self._player_wrap_edge_y = ''

    def observe_facility_name(self, location_name: str, x: int, y: int, display_name: str) -> None:
        if not location_name or not display_name:
            return
        from services.facility_name_store import get_store
        key = (location_name, int(x), int(y))
        if not get_store().note_name(*key, display_name):
            return
        if location_name != self._city_name:
            return
        self._load_facility_entrances(location_name)

    def _city_flat_marks(self) -> tuple[tuple[int, int, str], ...]:
        if self._map1 is None or not self._show_static_flats:
            return ()
        key = id(self._map1)
        if key != self._flat_marks_key:
            cat_map = get_city_flat_category_map()
            self._flat_marks = extract_flat_marks(self._map1, cat_map, skip_unmapped=True)
            self._flat_marks_key = key
        return self._flat_marks

    def _reset_state(self) -> None:
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        self._entrance_cells = ()
        self._facility_entrances = ()
        self._flat_marks = ()
        self._flat_marks_key = None
        self._city_name = None
        self._player_x = None
        self._player_y = None
        self._player_raw_x = None
        self._player_raw_y = None
        self._player_wrap_edge_x = ''
        self._player_wrap_edge_y = ''

    def _update_player_position(self, x: float | None, y: float | None) -> None:
        if x is None or y is None:
            return
        raw_x, raw_y = (int(x), int(y))
        if self._map1 is None:
            self._player_x, self._player_y = (raw_x, raw_y)
        else:
            height, width = self._map1.shape
            self._player_x, self._player_wrap_edge_x = project_wrapped_city_axis(raw_x, self._player_raw_x, width, self._player_wrap_edge_x)
            self._player_y, self._player_wrap_edge_y = project_wrapped_city_axis(raw_y, self._player_raw_y, height, self._player_wrap_edge_y)
        self._player_raw_x, self._player_raw_y = (raw_x, raw_y)

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
            self._facility_entrances = ()
            return
        self._map1 = grid.map1
        self._flor = grid.flor
        self._walkable = (grid.map1 == 0) | (grid.map1 & 61440 == 32768)
        self._bitmap = np.full((grid.depth, grid.width), 3, dtype=np.uint8)
        self._entrance_cells = grid.menu_cells
        self._load_facility_entrances(location_name)

    def _load_facility_entrances(self, location_name: str) -> None:
        if self._map1 is None:
            self._facility_entrances = ()
            return
        try:
            facilities = get_facilities_by_location_name(location_name) or []
        except Exception:
            _log.exception('get_facilities_by_location_name failed: %s', location_name)
            facilities = []
        from services.facility_name_store import get_store
        name_store = get_store()
        kinds = {ArenaMenuType.TAVERN: 'tavern', ArenaMenuType.EQUIPMENT: 'equipment', ArenaMenuType.TEMPLE: 'temple', ArenaMenuType.MAGES_GUILD: 'mages_guild'}
        height, width = self._map1.shape
        self._facility_entrances = tuple((FacilityEntranceMarker(x=item.original_x, y=item.original_y, kind=kinds[item.menu_type], display_name=None if item.menu_type == ArenaMenuType.MAGES_GUILD else name_store.name_for(location_name, item.original_x, item.original_y) or item.translation.ja or item.translation.en or '') for item in facilities if item.menu_type in kinds and 0 <= item.original_x < width and (0 <= item.original_y < height)))
__all__ = ['CityMapSession', 'project_wrapped_city_axis']
