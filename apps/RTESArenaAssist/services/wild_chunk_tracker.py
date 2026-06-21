"""services/wild_chunk_tracker.py — フィールド centered origin chunk の遷移追跡。

rt_x/rt_z (= anchor +0xA854 / +0xA856) の 32 ↔ 95 大ジャンプを境界跨ぎとして
検出し、chunk_x/chunk_y を自前管理する。

**chunk_x/chunk_y の意味**: これは実 player chunk では
なく、OpenTESArena の `getCenteredWildOrigin()` 相当の **centered origin chunk o**
である。rt は「中心寄せ 128×128 表示窓」内の表示座標（通常 32..95）で、その 32↔95
wrap は実 RMD chunk 境界ではなく origin が 64 ずれる境界を示す。実 chunk と voxel は
消費側で `actual_chunk = o + (rt >= 64)` / `actual_voxel = rt % 64` として復元する。

観測ベースの境界跨ぎ挙動 (= 観測 13+ 回):
  - 通常移動: rt の delta は ±1
  - 東境界 east 跨ぎ: rt_x が 32 ↔ 95 で大ジャンプ (= 過渡値 96 / 31 出現あり)
  - 1 voxel east step → rt_x -1、north step → rt_z -1
  - east 移動で origin chunk_x が減少、north 移動で origin chunk_y が減少

初期 seed:
  - 街中央 chunk (= 31, 31) を仮置き (= 街出口検出未対応時の既定 seed)
  - セーブロード途中着地時は実際の origin chunk_x/y 不明 (= 既知の限界)
"""
from __future__ import annotations

import logging
from typing import Optional

from .wild_voxel_assembler import (
    CITY_ORIGIN_CHUNK_X, CITY_ORIGIN_CHUNK_Y,
    WILD_HEIGHT, WILD_WIDTH,
)


_log = logging.getLogger("wild_chunk_tracker")


# rt_x/rt_z の有効範囲。32..95 が通常範囲、両端に過渡値 (= 東境界跨ぎで 31、
# 西境界跨ぎで 96) が観測されるため余裕を持たせる。
RT_MIN = 30
RT_MAX = 97

# 境界跨ぎ判定の閾値。通常 1 voxel 移動は ±1、境界跨ぎは ±63 前後 (= 過渡値
# 96 / 31 を含むと ±64) なので、中間値で分離する。
BOUNDARY_DELTA_THRESHOLD = 50


def _is_valid_rt(value: int) -> bool:
    return RT_MIN <= value <= RT_MAX


class WildChunkTracker:
    """フィールド chunk 位置 (chunk_x, chunk_y) を rt_x/rt_z 遷移で追跡。

    使用法:
      tracker = WildChunkTracker()
      tracker.update(rt_x, rt_z)       # 毎 poll
      cx, cy = tracker.chunk_x, tracker.chunk_y
    """

    def __init__(self,
                 initial_chunk_x: int = CITY_ORIGIN_CHUNK_X,
                 initial_chunk_y: int = CITY_ORIGIN_CHUNK_Y) -> None:
        self._chunk_x: int = initial_chunk_x
        self._chunk_y: int = initial_chunk_y
        self._prev_rt_x: Optional[int] = None
        self._prev_rt_z: Optional[int] = None

    def reset(self,
              chunk_x: int = CITY_ORIGIN_CHUNK_X,
              chunk_y: int = CITY_ORIGIN_CHUNK_Y) -> None:
        """seed を再設定。prev も None reset (= 次回 update から transition 検出)。"""
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
        """rt_x/rt_z の遷移を取り込み、最新 chunk_x/chunk_y を返す。

        境界跨ぎ検出ルール:
          - rt_x delta > +50: east boundary cross → chunk_x -= 1
          - rt_x delta < -50: west boundary cross → chunk_x += 1
          - rt_z delta > +50: north boundary cross → chunk_y -= 1
          - rt_z delta < -50: south boundary cross → chunk_y += 1

        rt_x/rt_z が想定範囲外の場合は遷移検出を skip し prev を None reset
        (= 過渡値の混入で誤検出するのを防ぐ)。chunk_x/y 変化時は log 出力。
        """
        if not (_is_valid_rt(rt_x) and _is_valid_rt(rt_z)):
            _log.debug("rt out of range (%d, %d) → prev reset", rt_x, rt_z)
            self._prev_rt_x = None
            self._prev_rt_z = None
            return self._chunk_x, self._chunk_y

        prev_cx = self._chunk_x
        prev_cy = self._chunk_y

        if self._prev_rt_x is not None:
            dx = rt_x - self._prev_rt_x
            if dx > BOUNDARY_DELTA_THRESHOLD:
                # 境界外側 centered origin -1 を許容（西/北越え）。
                self._chunk_x = max(-1, self._chunk_x - 1)
                _log.info(
                    "east cross: rt_x %d→%d (dx=%+d) chunk_x %d→%d",
                    self._prev_rt_x, rt_x, dx, prev_cx, self._chunk_x)
            elif dx < -BOUNDARY_DELTA_THRESHOLD:
                self._chunk_x = min(WILD_WIDTH - 1, self._chunk_x + 1)
                _log.info(
                    "west cross: rt_x %d→%d (dx=%+d) chunk_x %d→%d",
                    self._prev_rt_x, rt_x, dx, prev_cx, self._chunk_x)

        if self._prev_rt_z is not None:
            dz = rt_z - self._prev_rt_z
            if dz > BOUNDARY_DELTA_THRESHOLD:
                # 境界外側 centered origin -1 を許容（西/北越え）。
                self._chunk_y = max(-1, self._chunk_y - 1)
                _log.info(
                    "north cross: rt_z %d→%d (dz=%+d) chunk_y %d→%d",
                    self._prev_rt_z, rt_z, dz, prev_cy, self._chunk_y)
            elif dz < -BOUNDARY_DELTA_THRESHOLD:
                self._chunk_y = min(WILD_HEIGHT - 1, self._chunk_y + 1)
                _log.info(
                    "south cross: rt_z %d→%d (dz=%+d) chunk_y %d→%d",
                    self._prev_rt_z, rt_z, dz, prev_cy, self._chunk_y)

        self._prev_rt_x = rt_x
        self._prev_rt_z = rt_z
        return self._chunk_x, self._chunk_y


__all__ = [
    "BOUNDARY_DELTA_THRESHOLD",
    "RT_MAX", "RT_MIN",
    "WildChunkTracker",
]
