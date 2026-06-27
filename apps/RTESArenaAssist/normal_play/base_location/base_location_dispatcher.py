from __future__ import annotations
from typing import Optional
from common_draw.automap_canvas import CanvasData
from normal_play.map.base import MapContext, MapSessionBase
from .dungeon_location import DungeonMapSession
from .city_location import CityMapSession
from .wilderness_location import WildernessMapSession

class BaseLocationDispatcher:

    def __init__(self) -> None:
        self.dungeon = DungeonMapSession()
        self.city = CityMapSession()
        self.wilderness = WildernessMapSession()
        self._sessions = [('dungeon', self.dungeon), ('city', self.city), ('wilderness', self.wilderness)]
        self._active_key: Optional[str] = None
        self._suspended_key: Optional[str] = None

    def poll(self, ctx: MapContext, *, target_key: Optional[str]) -> None:
        if self._suspended_key is not None and target_key == self._suspended_key:
            self._active_key = target_key
            self._suspended_key = None
            if self._active_key is not None:
                dict(self._sessions)[self._active_key].update(ctx)
            return
        self._suspended_key = None
        if target_key != self._active_key:
            if self._active_key is not None:
                old = dict(self._sessions)[self._active_key]
                old.stop(ctx)
            self._active_key = target_key
            if target_key is not None:
                new = dict(self._sessions)[target_key]
                new.start(ctx)
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].update(ctx)

    def get_canvas_data(self) -> CanvasData:
        if self._active_key is not None:
            return dict(self._sessions)[self._active_key].get_canvas_data()
        if self._suspended_key is not None:
            return dict(self._sessions)[self._suspended_key].get_canvas_data()
        return CanvasData()

    def active_key(self) -> Optional[str]:
        return self._active_key

    def suspended_key(self) -> Optional[str]:
        return self._suspended_key

    def last_known_key(self) -> Optional[str]:
        return self._active_key or self._suspended_key

    def suspend(self, ctx: MapContext) -> None:
        if self._active_key is not None:
            self._suspended_key = self._active_key
            self._active_key = None

    def deactivate(self, ctx: MapContext) -> None:
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].stop(ctx)
            self._active_key = None
        self._suspended_key = None

    def reset_progress(self) -> None:
        if self._active_key is not None:
            dict(self._sessions)[self._active_key].reset_progress()
__all__ = ['BaseLocationDispatcher']
