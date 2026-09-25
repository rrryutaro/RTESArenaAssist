from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
import numpy as np
from .city_data import is_world_map_available, load_world_map_data
from .city_door_detector import texture_to_menu_id, voxel_texture_index
from .city_lookup import CityPlan, resolve_city_plan
from .mif_loader import DEFAULT_MIF_DIR, load_mif
from .mif_utils import BlockType
_BLOCK_SIZE = 20
_CITY_MENU_TEXTURE_INDICES: frozenset[int] = frozenset(texture_to_menu_id())

@dataclass(frozen=True)
class CityVoxelPlacement:
    mif_name: str
    original_x: int
    original_y: int
    width: int
    depth: int

@dataclass(frozen=True)
class CityVoxelGrid:
    name: str
    width: int
    depth: int
    map1: np.ndarray
    flor: np.ndarray
    start_x: int
    start_z: int
    city_dim: int
    placements: tuple[CityVoxelPlacement, ...] = ()
    menu_cells: tuple[tuple[int, int], ...] = ()

def _mif_to_grids(mif) -> tuple[np.ndarray, np.ndarray]:
    w = mif.width
    h = mif.height
    map1 = np.zeros((h, w), dtype=np.uint16)
    flor = np.zeros((h, w), dtype=np.uint16)
    if mif.map1 and len(mif.map1) >= h * w:
        map1[:, :] = np.array(mif.map1[:h * w], dtype=np.uint16).reshape(h, w)
    if mif.flor and len(mif.flor) >= h * w:
        flor[:, :] = np.array(mif.flor[:h * w], dtype=np.uint16).reshape(h, w)
    return (map1, flor)

def detect_menu_cells(map1: np.ndarray, menu_indices: set[int], exclude_texture_indices: set[int] | None=None) -> list[tuple[int, int]]:
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
            texture_index = voxel_texture_index(v)
            if texture_index is None:
                continue
            if texture_index in excludes:
                continue
            if texture_index in menu_indices:
                cells.append((x, z))
    return cells

def build_city_voxel_grid(plan: CityPlan) -> Optional[CityVoxelGrid]:
    try:
        tpl_mif = load_mif(plan.base_mif_name, [DEFAULT_MIF_DIR])
    except Exception:
        return None
    if tpl_mif is None:
        return None
    width = tpl_mif.width
    depth = tpl_mif.height
    map1, flor = _mif_to_grids(tpl_mif)
    placements: list[CityVoxelPlacement] = [CityVoxelPlacement(mif_name=plan.base_mif_name, original_x=0, original_y=0, width=width, depth=depth)]
    entries = () if plan.premade else plan.entries
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
        x_offset = plan.start_position[0] + entry.x_dim * _BLOCK_SIZE
        z_offset = plan.start_position[1] + entry.z_dim * _BLOCK_SIZE
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
        placements.append(CityVoxelPlacement(mif_name=entry.block_mif, original_x=x_offset, original_y=z_offset, width=src_w, depth=src_d))
    menu_cells_list = detect_menu_cells(map1, set(texture_to_menu_id()))
    return CityVoxelGrid(name=plan.name, width=width, depth=depth, map1=map1, flor=flor, start_x=plan.start_position[0], start_z=plan.start_position[1], city_dim=plan.city_dim, placements=tuple(placements), menu_cells=tuple(menu_cells_list))

def build_city_voxel_grid_for(province_id: int, location_id: int) -> Optional[CityVoxelGrid]:
    plan = resolve_city_plan(province_id, location_id)
    if plan is None:
        return None
    return build_city_voxel_grid(plan)

def build_city_voxel_grid_by_name(location_name: str) -> Optional[CityVoxelGrid]:
    if not location_name or not is_world_map_available():
        return None
    world_map = load_world_map_data()
    found = world_map.find_location_by_name(location_name)
    if found is None:
        return None
    province_id, location_id, _ = found
    return build_city_voxel_grid_for(province_id, location_id)
__all__ = ['CityVoxelGrid', 'CityVoxelPlacement', 'build_city_voxel_grid', 'build_city_voxel_grid_by_name', 'build_city_voxel_grid_for', 'detect_menu_cells']
