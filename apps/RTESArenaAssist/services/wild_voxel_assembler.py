"""wild_voxel_assembler.py — wilderness 周辺 2×2 chunks の voxel grid を組み立てる。

OpenTESArena `World/ArenaWildUtils.cpp` を Python 移植。

経路:
  1. location.name から wildSeed を算出 (= arena_location_utils.get_wilderness_seed)
  2. wildSeed + WildBlockLists で 64×64 wildBlockID grid を deterministic 生成
  3. 中央 (31,31)-(32,32) を ID 1-4 (= 街中央) で強制
  4. プレイヤー voxel 座標 → 周辺 2×2 chunks の origin chunk 決定
  5. 4 chunks 分の RMD をロード (= 中央 4 chunks は Arena インストールフォルダ、
     その他はローカルの RMD データディレクトリ)
  6. 128×128 voxel grid を結合して WildVoxelGrid を返す

中央 4 chunks (= ID 1-4) は Arena が `reviseWildCityBlock` 変換済の RMD
を Arena インストールフォルダに動的書き出しするので、変換ロジックは Python 側で
持たない (= 単純に RMD としてロード)。
"""
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
CITY_ORIGIN_CHUNK_X = (WILD_WIDTH // 2) - 1   # 31
CITY_ORIGIN_CHUNK_Y = (WILD_HEIGHT // 2) - 1  # 31


@dataclass(frozen=True)
class WildVoxelGrid:
    """周辺 n×n chunks (= 64n × 64n voxel) の組み立て結果。"""
    width:   int                  # 64 * n_chunks (= 128 for 2x2, 192 for 3x3)
    depth:   int                  # 64 * n_chunks
    map1:    np.ndarray           # (depth, width) uint16
    flor:    np.ndarray           # (depth, width) uint16
    # origin chunk (= 表示される範囲の左上 chunk index)。
    # signed を保持する: 境界外側を表示する場合 -1 等の負値や 63 超を取り得る
    # （0..63 に clamp しない。範囲外 chunk は live 2×2 overlay か空 chunk で埋める）。
    origin_chunk_x: int
    origin_chunk_y: int
    # n×n chunks 各位置の wildBlockID (= row-major、北→南、東→西)
    chunk_ids: tuple[tuple[int, ...], ...]
    menu_cells: tuple[tuple[int, int], ...] = ()


def make_wild_chunk_seed(wild_x: int, wild_y: int) -> int:
    """ArenaWildUtils::makeWildChunkSeed 移植。"""
    return ((wild_y & 0xFFFF) << 16) + (wild_x & 0xFFFF)


def generate_wilderness_indices(wild_seed: int,
                                blocks: WildBlockLists) -> np.ndarray:
    """64×64 wildBlockID grid を生成 (= ArenaWildUtils::generateWildernessIndices)。

    戻り値: (WILD_HEIGHT, WILD_WIDTH) uint8 配列。indices[y, x] が
    wildBlockID (1-255、通常 1-70)。中央 (31,31)-(32,32) は ID 1-4 で上書き。

    blocks の各リストが空の場合、その分岐の cell は 0 のままになる
    (= block list 未取得時のフォールバック挙動、wild_block_lists で警告済)。
    """
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
                # list 空 → 0 のまま。`random.next()` は呼ばないと LCG
                # シーケンスがずれるので注意 (= OpenTESArena は必ず呼ぶ)。
                _ = random.next()

    # 中央 4 chunks を強制 (= city center)
    indices[CITY_ORIGIN_CHUNK_Y, CITY_ORIGIN_CHUNK_X] = 1
    indices[CITY_ORIGIN_CHUNK_Y, CITY_ORIGIN_CHUNK_X + 1] = 2
    indices[CITY_ORIGIN_CHUNK_Y + 1, CITY_ORIGIN_CHUNK_X] = 3
    indices[CITY_ORIGIN_CHUNK_Y + 1, CITY_ORIGIN_CHUNK_X + 1] = 4
    return indices


def get_centered_wild_origin_chunk(player_voxel_x: int,
                                   player_voxel_y: int
                                   ) -> tuple[int, int]:
    """player 絶対 voxel 座標 → 周辺 2×2 chunks の左上 chunk index。

    OpenTESArena `getCenteredWildOrigin` 移植。
    voxel 単位で max(voxel - 32, 0) // 64 して chunk index に変換、
    結果は chunk 単位 (= 0-63 範囲想定)。

    player_voxel_x/y は 0-4095 範囲の絶対 voxel 座標 (= 64×64 chunks × 64
    voxel) を想定。範囲外の場合は clamp する。
    """
    cx = max(player_voxel_x - 32, 0) // RMD_WIDTH
    cy = max(player_voxel_y - 32, 0) // RMD_DEPTH
    # 2×2 chunk が WILD_WIDTH に収まるよう clamp
    cx = min(cx, WILD_WIDTH - 2)
    cy = min(cy, WILD_HEIGHT - 2)
    cx = max(cx, 0)
    cy = max(cy, 0)
    return cx, cy


def _empty_chunk() -> RmdChunk:
    """ID=0 等で chunk が取得できないときの空 chunk (= 全 0)。"""
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
    """周辺 n×n chunks (= 64n × 64n voxel) の WildVoxelGrid を組み立てる。

    n_chunks=2 で 2×2 (= 128 voxel)、3 で 3×3 (= 192 voxel)。
    OpenTESArena では n=3 (= ChunkDistance=1) を使用、周辺 1 chunk を
    pre-load することで境界での見切れを防ぐ。

    origin_chunk が指定されればその chunk 位置を左上として n×n 取得。signed の
    まま使い 0..63 に clamp しない（境界外側 chunk を描くため）。None なら
    player_voxel_x/y から get_centered_wild_origin_chunk で計算。

    各 chunk ID の解決順:
      1. live_origin_chunk/live_wild_blocks が与えられ、対象 chunk が live 2×2
         window 内 → live_wild_blocks（row order: TL, TR, BL, BR）。
         これは DOS 実機が現在保持する 2×2 RMD block ID（= 一次情報）で、
         境界外側 (= seed grid 0..63 に存在しない virtual chunk) を埋める。
      2. それ以外で 0 <= x < 64 かつ 0 <= y < 64 → seed grid の値。
      3. いずれにも該当しない範囲外 → 空 chunk (= ID 0)。

    flip_x=True で grid 全体を X 軸方向に反転する (= cartographic west-left)。
    """
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

    # n×n chunks 取得 + 結合
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
        menu_cells=(),  # 入口検出は呼び出し側で行う
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
