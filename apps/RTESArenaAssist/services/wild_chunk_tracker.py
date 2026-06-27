from __future__ import annotations
import logging
from typing import Optional
from .wild_voxel_assembler import CITY_ORIGIN_CHUNK_X, CITY_ORIGIN_CHUNK_Y, WILD_HEIGHT, WILD_WIDTH
_log = logging.getLogger('wild_chunk_tracker')
RT_MIN = 30
RT_MAX = 97
BOUNDARY_DELTA_THRESHOLD = 50

def _is_valid_rt(value: int) -> bool:
    return RT_MIN <= value <= RT_MAX

class WildChunkTracker:

    def __init__(self, initial_chunk_x: int=CITY_ORIGIN_CHUNK_X, initial_chunk_y: int=CITY_ORIGIN_CHUNK_Y) -> None:
        self._chunk_x: int = initial_chunk_x
        self._chunk_y: int = initial_chunk_y
        self._prev_rt_x: Optional[int] = None
        self._prev_rt_z: Optional[int] = None

    def reset(self, chunk_x: int=CITY_ORIGIN_CHUNK_X, chunk_y: int=CITY_ORIGIN_CHUNK_Y) -> None:
        self._chunk_x = chunk_x
        self._chunk_y = chunk_y
        self._prev_rt_x = None
        self._prev_rt_z = None

    @property
    def chunk_x(self) -> int:
        return self._chunk_x

    @property
    def chunk_y(self) -> int:
        return self._chunk_y

    def update(self, rt_x: int, rt_z: int) -> tuple[int, int]:
        if not (_is_valid_rt(rt_x) and _is_valid_rt(rt_z)):
            _log.debug('rt out of range (%d, %d) → prev reset', rt_x, rt_z)
            self._prev_rt_x = None
            self._prev_rt_z = None
            return (self._chunk_x, self._chunk_y)
        prev_cx = self._chunk_x
        prev_cy = self._chunk_y
        if self._prev_rt_x is not None:
            dx = rt_x - self._prev_rt_x
            if dx > BOUNDARY_DELTA_THRESHOLD:
                self._chunk_x = max(-1, self._chunk_x - 1)
                _log.info('east cross: rt_x %d→%d (dx=%+d) chunk_x %d→%d', self._prev_rt_x, rt_x, dx, prev_cx, self._chunk_x)
            elif dx < -BOUNDARY_DELTA_THRESHOLD:
                self._chunk_x = min(WILD_WIDTH - 1, self._chunk_x + 1)
                _log.info('west cross: rt_x %d→%d (dx=%+d) chunk_x %d→%d', self._prev_rt_x, rt_x, dx, prev_cx, self._chunk_x)
        if self._prev_rt_z is not None:
            dz = rt_z - self._prev_rt_z
            if dz > BOUNDARY_DELTA_THRESHOLD:
                self._chunk_y = max(-1, self._chunk_y - 1)
                _log.info('north cross: rt_z %d→%d (dz=%+d) chunk_y %d→%d', self._prev_rt_z, rt_z, dz, prev_cy, self._chunk_y)
            elif dz < -BOUNDARY_DELTA_THRESHOLD:
                self._chunk_y = min(WILD_HEIGHT - 1, self._chunk_y + 1)
                _log.info('south cross: rt_z %d→%d (dz=%+d) chunk_y %d→%d', self._prev_rt_z, rt_z, dz, prev_cy, self._chunk_y)
        self._prev_rt_x = rt_x
        self._prev_rt_z = rt_z
        return (self._chunk_x, self._chunk_y)
__all__ = ['BOUNDARY_DELTA_THRESHOLD', 'RT_MAX', 'RT_MIN', 'WildChunkTracker']
