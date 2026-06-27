from __future__ import annotations
import logging
from typing import Optional
from common_draw.automap_canvas import CanvasData
from normal_play.base_location import BaseLocationDispatcher
from normal_play.base_location.base_location_view import classify_map_axis
from .base import MapContext, MapSessionBase
from .interior import InteriorMapSession
_log = logging.getLogger('map.dispatcher')

class MapDispatcher:

    def __init__(self) -> None:
        self.base_location = BaseLocationDispatcher()
        self.interior = InteriorMapSession()
        self.dungeon = self.base_location.dungeon
        self.city = self.base_location.city
        self.wilderness = self.base_location.wilderness
        self._active_path: Optional[str] = None
        self._diag_prev_axis: Optional[str] = '(init)'

    def poll(self, ctx: MapContext) -> None:
        axis = classify_map_axis(ctx.analyzer, ctx.anchor, mif_name=ctx.mif_name, interior_mif_name=ctx.interior_mif_name, in_interior=ctx.in_interior, area=ctx.area)
        if axis != self._diag_prev_axis:
            _log.info('map axis: %s -> %s (mif=%r interior_mif=%r)', self._diag_prev_axis, axis, ctx.mif_name, ctx.interior_mif_name)
            self._diag_prev_axis = axis
        if axis == 'interior':
            self._poll_interior(ctx)
        else:
            self._poll_base_location(ctx, axis)

    def _poll_interior(self, ctx: MapContext) -> None:
        if self._active_path != 'interior':
            self.base_location.suspend(ctx)
            self.interior.start(ctx)
            self._active_path = 'interior'
        if self.interior.is_active():
            self.interior.update(ctx)

    def _poll_base_location(self, ctx: MapContext, axis: Optional[str]) -> None:
        if self._active_path != 'base_location':
            if self.interior.is_active():
                self.interior.stop(ctx)
            self._active_path = 'base_location'
        self.base_location.poll(ctx, target_key=axis)

    def get_canvas_data(self) -> CanvasData:
        if self._active_path == 'interior':
            if self.interior.is_active():
                return self.interior.get_canvas_data()
            return CanvasData()
        if self._active_path == 'base_location':
            return self.base_location.get_canvas_data()
        return CanvasData()

    def active_key(self) -> Optional[str]:
        if self._active_path == 'interior':
            return 'interior' if self.interior.is_active() else None
        if self._active_path == 'base_location':
            return self.base_location.active_key()
        return None

    def reset_progress(self) -> None:
        if self._active_path == 'interior':
            if self.interior.is_active():
                self.interior.reset_progress()
        elif self._active_path == 'base_location':
            self.base_location.reset_progress()

    def poll_automap_file(self) -> bool:
        if self._active_path == 'base_location' and self.base_location.active_key() == 'dungeon':
            return self.base_location.dungeon.poll_automap_file()
        return False
__all__ = ['MapDispatcher']
