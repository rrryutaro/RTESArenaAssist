from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from common_draw.automap_canvas import CanvasData

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

    def reset_progress(self) -> None:
        pass
__all__ = ['MapContext', 'MapSessionBase']
