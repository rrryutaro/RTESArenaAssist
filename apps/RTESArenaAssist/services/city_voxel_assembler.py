"""city_voxel_assembler.py — 街全体の voxel grid を組み立てる。

OpenTESArena `World/ArenaCityUtils.cpp::generateCity` を Python 移植。

街マップ表示の元データを構築する経路:
  1. (province_id, location_id) から ArenaLocationType (= city_state/town/village) を判定
  2. world_map から街の name / city_seed を取得
  3. city_generation.json から template_filename / reserved_block_list / starting_position を取得
  4. テンプレート MIF を base として MAP1 / FLOR をロード (= 街全体サイズ)
  5. expand_city_plan_with_random で plan + 各 block の MIF 名 + (x_dim, z_dim) を決定
  6. 各 block の MIF を該当 (start_x + x_dim*20, start_z + z_dim*20) に貼り付け
  7. 結果を CityVoxelGrid (= MAP1 + FLOR + 街全体 width/depth + start origin) で返す

返り値の座標系: 街全体 voxel grid の (0, 0) は MIF 原点。プレイヤー座標
(rt_x, rt_z) は同じ grid 上で取得される (= 観測予定)。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .arena_city_utils import expand_city_plan_with_random
from .arena_location_utils import (
    get_city_reserved_block_list_index,
    get_city_starting_position_index,
    get_city_template_count,
    get_city_template_name_index,
    get_global_city_id,
)
from .arena_types import ArenaLocationType
from .city_data import (
    is_data_available, is_world_map_available,
    load_city_generation_data, load_world_map_data,
)
from .mif_loader import DEFAULT_MIF_DIR, load_mif
from .mif_utils import BlockType


_CITY_DIM = {
    ArenaLocationType.CITY_STATE: 6,
    ArenaLocationType.TOWN:       5,
    ArenaLocationType.VILLAGE:    4,
}

_BLOCK_SIZE = 20  # OpenTESArena の city block 1 マス = 20 voxel 角


# 街用 INF (climate × weather) で @MENUS に含まれる texture index の union。
# 観測: TCN/DCN/MCN/TCR/DCR/MCR/TCW/DCW/MCW/TCS/MCS で全て同じ
# {5, 10, 16, 23, 30, 35, 40, 44, 45, 50, 51, 52, 53}（実機確認済）。
# climate / weather 判定を省くため固定値で持つ。
_CITY_MENU_TEXTURE_INDICES: frozenset[int] = frozenset({
    5, 10, 16, 23, 30, 35, 40, 44, 45, 50, 51, 52, 53,
})


@dataclass(frozen=True)
class CityVoxelGrid:
    """街全体の voxel grid。"""
    name:    str            # 街名 (= location.name)
    width:   int            # 街全体 X 軸サイズ (= テンプレート MIF width)
    depth:   int            # 街全体 Z 軸サイズ (= テンプレート MIF height)
    map1:    np.ndarray     # uint16 (depth, width)
    flor:    np.ndarray     # uint16 (depth, width)
    start_x: int            # テンプレート上の block 配置 origin (start_pos.x)
    start_z: int            # 同上 (start_pos.y)
    city_dim: int           # 街グリッド辺長 (= 4/5/6)
    menu_cells: tuple[tuple[int, int], ...] = ()
    # 入口 (= 建物の MENU voxel) 位置のリスト [(x, z), ...]。
    # ArenaCityUtils + INF の @MENUS から検出。街マップ上に赤点で描画する。


def _location_type_from_id(location_id: int) -> Optional[ArenaLocationType]:
    if 0 <= location_id < 8:
        return ArenaLocationType.CITY_STATE
    if 8 <= location_id < 16:
        return ArenaLocationType.TOWN
    if 16 <= location_id < 32:
        return ArenaLocationType.VILLAGE
    return None


def _mif_to_grids(mif) -> tuple[np.ndarray, np.ndarray]:
    """MifMap (= mif_loader.parse_mif の戻り値) から (depth, width) uint16 配列を取り出す。"""
    w = mif.width
    h = mif.height
    map1 = np.zeros((h, w), dtype=np.uint16)
    flor = np.zeros((h, w), dtype=np.uint16)
    if mif.map1 and len(mif.map1) >= h * w:
        map1[:, :] = np.array(mif.map1[: h * w],
                              dtype=np.uint16).reshape(h, w)
    if mif.flor and len(mif.flor) >= h * w:
        flor[:, :] = np.array(mif.flor[: h * w],
                              dtype=np.uint16).reshape(h, w)
    return map1, flor


def detect_menu_cells(map1: np.ndarray,
                      menu_indices: set[int],
                      exclude_texture_indices: set[int] | None = None
                      ) -> list[tuple[int, int]]:
    """MAP1 を走査して MENU voxel (= 入口/出口扉) の (x, z) リストを返す。

    OpenTESArena `tryMakeVoxelTransitionDefGenInfo` (MapGeneration.cpp:991-) と
    同等の判定:
      - wall (= high nibble != 0x8/0x9/0xA/0xB/0xC/0xD/0xE) で
        most_byte == least_byte なら texture_index = most_byte - 1
      - edge (= high nibble == 0xA) なら texture_index = (least_byte & 0x3F) - 1
      - texture_index が menu_indices set に含まれれば MENU

    exclude_texture_indices は除外したい texture (= 階段の level_up/down 等)。
    Interior では level_up/down も @MENUS に含まれる場合があるため、それらは
    別経路で塗り、こちらは「街へ戻る出口」のみ検出するために使う。
    """
    if not menu_indices:
        return []
    excludes = exclude_texture_indices or set()
    cells: list[tuple[int, int]] = []
    depth, width = map1.shape
    for z in range(depth):
        for x in range(width):
            v = int(map1[z, x])
            if v == 0:
                continue
            high_nibble = (v >> 12) & 0x0F
            most_byte = (v >> 8) & 0xFF
            least_byte = v & 0xFF
            if high_nibble == 0xA:
                texture_index = (least_byte & 0x3F) - 1
            elif most_byte == least_byte and most_byte != 0:
                texture_index = most_byte - 1
            else:
                continue
            if texture_index in excludes:
                continue
            if texture_index in menu_indices:
                cells.append((x, z))
    return cells


def build_city_voxel_grid_for(province_id: int, location_id: int
                              ) -> Optional[CityVoxelGrid]:
    """(province_id, location_id) から街全体の voxel grid を組み立てる。

    街以外 (= ダンジョン等) や、city_generation.json / world_map.json が
    取得できない / テンプレート MIF が見つからない場合は None。
    """
    if not (is_data_available() and is_world_map_available()):
        return None
    location_type = _location_type_from_id(location_id)
    if location_type is None:
        return None
    world_map = load_world_map_data()
    if province_id < 0 or province_id >= len(world_map.provinces):
        return None
    province = world_map.provinces[province_id]
    location = province.get_location(location_id)
    if location is None or not location.name:
        return None

    city_gen = load_city_generation_data()
    global_city_id = get_global_city_id(location_id, province_id)
    is_coastal = city_gen.is_coastal(global_city_id)
    is_city_state = (location_type == ArenaLocationType.CITY_STATE)
    template_count = get_city_template_count(is_coastal, is_city_state)
    template_id = global_city_id % template_count

    tpl_name_idx = get_city_template_name_index(location_type, is_coastal)
    tpl_pattern = city_gen.get_template_filename(tpl_name_idx)
    if not tpl_pattern:
        return None
    # OpenTESArena LocationDefinition.cpp:162 に従い template_id+1 (= 1-based) で %d 置換
    tpl_filename = tpl_pattern.replace("%d", str(template_id + 1)).upper()
    # loose dir（dev=docs）→ install VFS（GLOBAL.BSA・MIF 非暗号）で解決（公開版対応）。
    try:
        tpl_mif = load_mif(tpl_filename, [DEFAULT_MIF_DIR])
    except Exception:
        return None
    if tpl_mif is None:
        return None

    rb_idx = get_city_reserved_block_list_index(is_coastal, template_id)
    sp_idx = get_city_starting_position_index(
        location_type, is_coastal, template_id)
    reserved = city_gen.get_reserved_block_list(rb_idx) or []
    start_pos = city_gen.get_starting_position(sp_idx) or (0, 0)
    city_dim = _CITY_DIM[location_type]
    city_seed = location.city_seed()

    # テンプレート MIF (= 街全体サイズの素の地形) は上で load 済み。
    width = tpl_mif.width
    depth = tpl_mif.height
    map1, flor = _mif_to_grids(tpl_mif)

    # plan + block MIF 名取得
    entries, _ = expand_city_plan_with_random(city_seed, city_dim, reserved)

    # 各 non-reserved block を該当位置に貼り付け
    for entry in entries:
        if entry.block_type == BlockType.RESERVED:
            continue
        if not entry.block_mif:
            continue
        try:
            block_mif = load_mif(entry.block_mif, [DEFAULT_MIF_DIR])
        except Exception:
            continue
        if block_mif is None:
            continue
        bw = block_mif.width
        bd = block_mif.height
        bmap1, bflor = _mif_to_grids(block_mif)

        x_offset = start_pos[0] + entry.x_dim * _BLOCK_SIZE
        z_offset = start_pos[1] + entry.z_dim * _BLOCK_SIZE
        # クリップ (grid 範囲外は無視)
        x_end = min(width, x_offset + bw)
        z_end = min(depth, z_offset + bd)
        if x_offset >= width or z_offset >= depth:
            continue
        if x_offset < 0 or z_offset < 0:
            continue
        src_w = x_end - x_offset
        src_d = z_end - z_offset
        map1[z_offset:z_end, x_offset:x_end] = bmap1[:src_d, :src_w]
        flor[z_offset:z_end, x_offset:x_end] = bflor[:src_d, :src_w]

    # 街マップ上の MENU voxel (= 入口) を検出。INF lookup ではなく
    # 観測済の固定 texture index set を使う (= climate に依存しないため)。
    menu_cells_list = detect_menu_cells(map1, set(_CITY_MENU_TEXTURE_INDICES))

    return CityVoxelGrid(
        name=location.name,
        width=width,
        depth=depth,
        map1=map1,
        flor=flor,
        start_x=int(start_pos[0]),
        start_z=int(start_pos[1]),
        city_dim=city_dim,
        menu_cells=tuple(menu_cells_list),
    )


def build_city_voxel_grid_by_name(location_name: str
                                  ) -> Optional[CityVoxelGrid]:
    """街名 (例 "Moonguard") から街全体 voxel grid を組み立てる。"""
    if not location_name or not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, _ = found
    return build_city_voxel_grid_for(province_id, location_id)


__all__ = [
    "CityVoxelGrid",
    "build_city_voxel_grid_by_name",
    "build_city_voxel_grid_for",
    "detect_menu_cells",
]
