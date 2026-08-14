from __future__ import annotations
import logging
from typing import Optional
from viewer_constants import ANCHOR_DOS_SEGMENT, LEVEL_BUFFER_ROW_CELLS, LEVEL_BUFFER_SEG_OFFSET, STAIR_DOWN_FLAG_OFFSET, STAIR_UP_FLAG_OFFSET
_log = logging.getLogger('interior_floor')
_GEOMETRY_MATCH_RATIO = 0.9
_LEVEL_BUFFER_REL_MIN = 65536
_LEVEL_BUFFER_REL_MAX = 589824
_level_data_cache: dict[str, Optional[tuple[list, list]]] = {}

def read_stair_flags(analyzer, anchor: int) -> Optional[tuple[bool, bool]]:
    try:
        up = analyzer.read_bytes(anchor + STAIR_UP_FLAG_OFFSET, 1)[0]
        down = analyzer.read_bytes(anchor + STAIR_DOWN_FLAG_OFFSET, 1)[0]
    except (OSError, IndexError, TypeError):
        return None
    return (up != 0, down != 0)

def read_loaded_level_map1(analyzer, anchor: int, width: int, height: int):
    if width <= 0 or height <= 0 or width > LEVEL_BUFFER_ROW_CELLS:
        return None
    try:
        import numpy as np
        raw = analyzer.read_bytes(anchor + LEVEL_BUFFER_SEG_OFFSET, 2)
        seg = raw[0] | raw[1] << 8
        rel = seg - ANCHOR_DOS_SEGMENT << 4
        if not _LEVEL_BUFFER_REL_MIN <= rel <= _LEVEL_BUFFER_REL_MAX:
            return None
        stride = LEVEL_BUFFER_ROW_CELLS * 2
        buf = analyzer.read_bytes(anchor + rel, stride * height)
        arr = np.frombuffer(buf, dtype='<u2').reshape(height, LEVEL_BUFFER_ROW_CELLS)
        return arr[:, :width]
    except (OSError, IndexError, TypeError, ValueError):
        return None

def match_floor_by_geometry(level_maps, live_map1) -> Optional[int]:
    if not level_maps or live_map1 is None:
        return None
    best_idx: Optional[int] = None
    best_score = -1.0
    for i, lm in enumerate(level_maps):
        if lm is None or lm.shape != live_map1.shape:
            continue
        score = float((lm == live_map1).mean())
        if score > best_score:
            best_score = score
            best_idx = i
    if best_idx is None or best_score < _GEOMETRY_MATCH_RATIO:
        return None
    return best_idx

def match_floor_by_topology(signatures, up_exists: bool, down_exists: bool) -> Optional[int]:
    if not signatures:
        return None
    any_stairs = any((u or d for u, d in signatures))
    matched = [i for i, (u, d) in enumerate(signatures) if ((u or d) or not any_stairs) and (u, d) == (up_exists, down_exists)]
    if len(matched) == 1:
        return matched[0]
    return None

def level_stair_signatures(mif_name: str):
    data = _level_data(mif_name)
    return data[0] if data else None

def level_map1_arrays(mif_name: str):
    data = _level_data(mif_name)
    return data[1] if data else None

def _level_data(mif_name: str):
    if not mif_name:
        return None
    key = mif_name.upper()
    if key in _level_data_cache:
        return _level_data_cache[key]
    data = _compute_level_data(mif_name)
    _level_data_cache[key] = data
    return data

def _compute_level_data(mif_name: str):
    try:
        import numpy as np
        from common_draw.automap_canvas import _classify_cell
        from runtime_paths import resolve_arena_install_dir
        from services.mif_loader import DEFAULT_INF_DIR, DEFAULT_MIF_DIR, load_mif, parse_inf_level_transitions, resolve_inf_for_mif
    except Exception:
        return None
    mif_dirs = [d for d in (DEFAULT_MIF_DIR, resolve_arena_install_dir()) if d is not None]
    sigs: list[tuple[bool, bool]] = []
    maps: list = []
    try:
        for lvl in range(8):
            mif = load_mif(mif_name, mif_dirs, player_floor=lvl)
            if mif is None:
                break
            level_count = int(mif.level_count or 1)
            if lvl >= level_count:
                break
            map1 = np.array(mif.map1, dtype=np.uint16).reshape(mif.height, mif.width)
            if mif.flor and len(mif.flor) >= mif.height * mif.width:
                flor = np.array(mif.flor, dtype=np.uint16).reshape(mif.height, mif.width)
            else:
                flor = np.zeros_like(map1)
            lu = ld = None
            inf_path = resolve_inf_for_mif(mif_name, getattr(mif, 'info_name', ''), DEFAULT_INF_DIR)
            if inf_path is not None:
                try:
                    lu, ld = parse_inf_level_transitions(inf_path)
                except Exception:
                    lu = ld = None
            has_up = has_down = False
            for y in range(mif.height):
                for x in range(mif.width):
                    kind = _classify_cell(int(map1[y, x]), int(flor[y, x]), lu, ld)
                    if kind == 'level_up':
                        has_up = True
                    elif kind == 'level_down':
                        has_down = True
                if has_up and has_down:
                    break
            sigs.append((has_up, has_down))
            maps.append(map1)
    except Exception:
        _log.exception('level data failed: %s', mif_name)
        return None
    if not sigs:
        return None
    return (sigs, maps)

def resolve_interior_floor(analyzer, anchor: Optional[int], mif_name: Optional[str]) -> Optional[int]:
    if analyzer is None or anchor is None or (not mif_name):
        return None
    data = _level_data(mif_name)
    if data is None:
        return None
    sigs, maps = data
    if maps:
        h, w = maps[0].shape
        live = read_loaded_level_map1(analyzer, anchor, w, h)
        floor = match_floor_by_geometry(maps, live)
        if floor is not None:
            return floor
    flags = read_stair_flags(analyzer, anchor)
    if flags is None:
        return None
    return match_floor_by_topology(sigs, *flags)
__all__ = ['read_stair_flags', 'read_loaded_level_map1', 'match_floor_by_geometry', 'match_floor_by_topology', 'level_stair_signatures', 'level_map1_arrays', 'resolve_interior_floor']
