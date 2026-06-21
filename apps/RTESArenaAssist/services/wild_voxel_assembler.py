from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .arena_random import ArenaRandom
from .rmd_loader import (
    RMD_DEPTH, RMD_WIDTH, RmdChunk,
    DEFAULT_RMD_DIR,
    load_rmd_chunk,
)
from .wild_block_lists import WildBlockLists


WILD_WIDTH = 64
WILD_HEIGHT = WILD_WIDTH
CITY_ORIGIN_CHUNK_X = (WILD_WIDTH // 2) - 1
CITY_ORIGIN_CHUNK_Y = (WILD_HEIGHT // 2) - 1


@dataclass(frozen=True)
class WildVoxelGrid:
    width:   int
    depth:   int
    map1:    np.ndarray
    flor:    np.ndarray
    origin_chunk_x: int
    origin_chunk_y: int
    chunk_ids: tuple[tuple[int, ...], ...]
    menu_cells: tuple[tuple[int, int], ...] = ()


def make_wild_chunk_seed(wild_x: int, wild_y: int) -> int:
    return ((wild_y & 0xFFFF) << 16) + (wild_x & 0xFFFF)


def generate_wilderness_indices(wild_seed: int,
                                blocks: WildBlockLists) -> np.ndarray:
    NORMAL_VAL = 0x6666
    VILLAGE_VAL = 0x4000
    DUNGEON_VAL = 0x2666
    TAVERN_VAL = 0x1999

    random = ArenaRandom(wild_seed)
    indices = np.zeros((WILD_HEIGHT, WILD_WIDTH), dtype=np.uint8)
    for y in range(WILD_HEIGHT):
        for x in range(WILD_WIDTH):
            rand_val = random.next()
            if rand_val < NORMAL_VAL:
                block_list = blocks.normal
            else:
                rand_val -= NORMAL_VAL
                if rand_val < VILLAGE_VAL:
                    block_list = blocks.village
                else:
                    rand_val -= VILLAGE_VAL
                    if rand_val < DUNGEON_VAL:
                        block_list = blocks.dungeon
                    else:
                        rand_val -= DUNGEON_VAL
                        if rand_val < TAVERN_VAL:
                            block_list = blocks.tavern
                        else:
                            block_list = blocks.temple
            if block_list:
                bid_index = (random.next() & 0xFF) % len(block_list)
                indices[y, x] = block_list[bid_index]
            else:
                _ = random.next()

    indices[CITY_ORIGIN_CHUNK_Y, CITY_ORIGIN_CHUNK_X] = 1
    indices[CITY_ORIGIN_CHUNK_Y, CITY_ORIGIN_CHUNK_X + 1] = 2
    indices[CITY_ORIGIN_CHUNK_Y + 1, CITY_ORIGIN_CHUNK_X] = 3
    indices[CITY_ORIGIN_CHUNK_Y + 1, CITY_ORIGIN_CHUNK_X + 1] = 4
    return indices


def get_centered_wild_origin_chunk(player_voxel_x: int,
                                   player_voxel_y: int
                                   ) -> tuple[int, int]:
    cx = max(player_voxel_x - 32, 0) // RMD_WIDTH
    cy = max(player_voxel_y - 32, 0) // RMD_DEPTH
    cx = min(cx, WILD_WIDTH - 2)
    cy = min(cy, WILD_HEIGHT - 2)
    cx = max(cx, 0)
    cy = max(cy, 0)
    return cx, cy


def _empty_chunk() -> RmdChunk:
    z = np.zeros((RMD_DEPTH, RMD_WIDTH), dtype=np.uint16)
    return RmdChunk(flor=z.copy(), map1=z.copy(), map2=z.copy())


def build_wild_voxel_grid(
    wild_seed: int,
    blocks: WildBlockLists,
    player_voxel_x: int,
    player_voxel_y: int,
    steam_dir: Path | None = None,
    fallback_dir: Path = DEFAULT_RMD_DIR,
    origin_chunk: Optional[tuple[int, int]] = None,
    flip_x: bool = True,
    n_chunks: int = 2,
    live_origin_chunk: Optional[tuple[int, int]] = None,
    live_wild_blocks: Optional[tuple[int, ...]] = None,
) -> WildVoxelGrid:
    if n_chunks < 1:
        raise ValueError(f"n_chunks must be >= 1, got {n_chunks}")

    indices = generate_wilderness_indices(wild_seed, blocks)
    if origin_chunk is not None:
        cx, cy = origin_chunk
    else:
        cx, cy = get_centered_wild_origin_chunk(player_voxel_x, player_voxel_y)

    def _resolve_block_id(chunk_x: int, chunk_y: int) -> int:
        if live_origin_chunk is not None and live_wild_blocks is not None:
            lx, ly = live_origin_chunk
            dx = chunk_x - lx
            dy = chunk_y - ly
            if 0 <= dx < 2 and 0 <= dy < 2:
                return int(live_wild_blocks[dy * 2 + dx])
        if 0 <= chunk_x < WILD_WIDTH and 0 <= chunk_y < WILD_HEIGHT:
            return int(indices[chunk_y, chunk_x])
        return 0

    def _load(bid: int) -> RmdChunk:
        if bid == 0:
            return _empty_chunk()
        chunk = load_rmd_chunk(bid, steam_dir, fallback_dir)
        if chunk is None:
            return _empty_chunk()
        return chunk

    H = RMD_DEPTH
    W = RMD_WIDTH
    map1 = np.zeros((n_chunks * H, n_chunks * W), dtype=np.uint16)
    flor = np.zeros((n_chunks * H, n_chunks * W), dtype=np.uint16)
    chunk_ids_rows: list[tuple[int, ...]] = []
    for dy in range(n_chunks):
        row_ids: list[int] = []
        for dx in range(n_chunks):
            bid = _resolve_block_id(cx + dx, cy + dy)
            chunk = _load(bid)
            map1[dy * H:(dy + 1) * H, dx * W:(dx + 1) * W] = chunk.map1
            flor[dy * H:(dy + 1) * H, dx * W:(dx + 1) * W] = chunk.flor
            row_ids.append(bid)
        chunk_ids_rows.append(tuple(row_ids))

    if flip_x:
        map1 = np.ascontiguousarray(np.flip(map1, axis=1))
        flor = np.ascontiguousarray(np.flip(flor, axis=1))

    return WildVoxelGrid(
        width=n_chunks * W,
        depth=n_chunks * H,
        map1=map1,
        flor=flor,
        origin_chunk_x=cx,
        origin_chunk_y=cy,
        chunk_ids=tuple(chunk_ids_rows),
        menu_cells=(),
    )


__all__ = [
    "WildVoxelGrid",
    "WILD_WIDTH", "WILD_HEIGHT",
    "CITY_ORIGIN_CHUNK_X", "CITY_ORIGIN_CHUNK_Y",
    "make_wild_chunk_seed",
    "generate_wilderness_indices",
    "get_centered_wild_origin_chunk",
    "build_wild_voxel_grid",
]
