from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from common_draw.automap_canvas import CanvasData

@dataclass(frozen=True)
class MapTileProjection:
    offset_x: int = 0
    offset_y: int = 0
    source_limit: Optional[int] = None

    def project(self, x: int, y: int) -> Optional[tuple[int, int]]:
        if self.source_limit is not None and (not (0 <= x < self.source_limit and 0 <= y < self.source_limit)):
            return None
        return (x + self.offset_x, y + self.offset_y)

@dataclass(frozen=True)
class MapPollResult:
    canvas: CanvasData
    axis: Optional[str]
    parent_area: Optional[str]
    source_player: Optional[tuple[int, int]]
    projection: Optional[MapTileProjection]

@dataclass
class MapContext:
    mif_name: Optional[str]
    interior_mif_name: Optional[str]
    location_name: Optional[str]
    player_floor: int
    player_tile_x: Optional[float]
    player_tile_y: Optional[float]
    angle_deg: Optional[float]
    analyzer: Any
    anchor: Optional[int]
    place_text: Optional[str]
    save_dir: str
    in_interior: Optional[bool] = None
    area: Optional[str] = None
    item_pickup_kinds: frozenset = frozenset()
    dungeon_floor: Optional[int] = None
    dungeon_floor_fresh: Optional[int] = None
    location_ref: Any = None
    ext_store: Any = None
    wall_los_enabled: bool = False
    reveal_all: bool = False
    show_unexplored_floor: bool = False
    center_on_player: bool = True
    show_grid: bool = True
    wilderness_compact_view: bool = False
    wild_distinguish_road: bool = True
    wild_show_edge: bool = True
    wild_distinguish_edge: bool = True
    wild_show_crops: bool = True
    wild_show_all_entrances: bool = True
    wild_show_static_flats: bool = True

class MapSessionBase:

    def __init__(self) -> None:
        self._active: bool = False

    def is_active(self) -> bool:
        return self._active

    def start(self, ctx: MapContext) -> None:
        self._active = True

    def stop(self, ctx: MapContext) -> None:
        self._active = False

    def update(self, ctx: MapContext) -> None:
        raise NotImplementedError

    def get_canvas_data(self) -> CanvasData:
        raise NotImplementedError

    def combat_projection(self, ctx: MapContext) -> tuple[Optional[tuple[int, int]], Optional[MapTileProjection]]:
        if ctx.player_tile_x is None or ctx.player_tile_y is None:
            return (None, None)
        return ((int(ctx.player_tile_x), int(ctx.player_tile_y)), MapTileProjection())

    def reset_progress(self) -> None:
        pass

    def request_automap_import(self) -> None:
        pass
__all__ = ['MapContext', 'MapSessionBase']
