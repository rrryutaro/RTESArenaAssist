from __future__ import annotations
import math
import numpy as np
ARENA_REVEAL_STENCIL: tuple[str, ...] = ('1..111...', '11122211.', '11222221.', '112333211', '112333211', '112333211', '.1222221.', '.1111111.', '...111...')

def iter_arena_reveal_offsets():
    for row_idx, row in enumerate(ARENA_REVEAL_STENCIL):
        dy = row_idx - 4
        for col_idx, ch in enumerate(row):
            dx = col_idx - 4
            if ch != '.':
                yield (dx, dy, int(ch))

def apply_reveal_stencil(bitmap: np.ndarray, player_x: int, player_y: int) -> int:
    changes = 0
    for dx, dy, value in iter_arena_reveal_offsets():
        x = player_x + dx & 127
        y = player_y + dy & 127
        old = int(bitmap[y, x])
        if value > old:
            bitmap[y, x] = value
            changes += 1
    return changes

def apply_reveal_stencil_with_los(bitmap: np.ndarray, map1: np.ndarray | None, player_x: int, player_y: int, flor: np.ndarray | None=None, in_first_block: bool=False) -> int:
    if map1 is None:
        return apply_reveal_stencil(bitmap, player_x, player_y)
    use_l1 = in_first_block and flor is not None
    changes = 0
    H, W = flor.shape if use_l1 else map1.shape
    raised_threshold = resolve_raised_sight_threshold()
    for dx, dy, value in iter_arena_reveal_offsets():
        x = player_x + dx & 127
        y = player_y + dy & 127
        old = int(bitmap[y, x])
        if value <= old:
            continue
        if 0 <= x < W and 0 <= y < H:
            if use_l1:
                if _line_of_sight_blocked_l1(flor, player_x, player_y, x, y):
                    continue
            elif _line_of_sight_blocked(map1, player_x, player_y, x, y, raised_threshold):
                continue
        bitmap[y, x] = value
        changes += 1
    return changes

def rebuild_seen_cells_from_bitmap(bitmap: np.ndarray) -> set[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    if bitmap is None:
        return seen
    ys, xs = np.where(bitmap == 3)
    for x, y in zip(xs.tolist(), ys.tolist()):
        seen.add((int(x), int(y)))
    return seen
RAISED_HEIGHT_STEP_PERCENT = 12.5
RAISED_THICKNESS_STEP_PERCENT = 6.25
RAISED_SIGHT_THRESHOLD_DEFAULT = 0
FULL_RAISED_AS_WALL_DEFAULT = True

def raised_extent_percent(value: int) -> tuple[float, float] | None:
    if value == 0 or value & 32768 != 0:
        return None
    most = (value & 32512) >> 8
    least = value & 127
    if most == least:
        return None
    height_index = most & 7
    thickness_index = (most & 120) >> 3
    bottom = height_index * RAISED_HEIGHT_STEP_PERCENT
    top = bottom + (thickness_index + 1) * RAISED_THICKNESS_STEP_PERCENT
    return (bottom, top)

def is_full_height_raised(value: int) -> bool:
    extent = raised_extent_percent(value)
    if extent is None:
        return False
    bottom, top = extent
    return bottom == 0.0 and top >= 100.0

def raised_blocks_sight(value: int, threshold_percent: float) -> bool:
    extent = raised_extent_percent(value)
    if extent is None:
        return True
    return extent[1] >= threshold_percent

def resolve_raised_sight_threshold() -> float:
    try:
        import assist_settings
        value = float(assist_settings.get('map_raised_sight_threshold', RAISED_SIGHT_THRESHOLD_DEFAULT))
    except (ImportError, TypeError, ValueError):
        return float(RAISED_SIGHT_THRESHOLD_DEFAULT)
    return min(max(value, 0.0), 100.0)

def resolve_full_raised_as_wall() -> bool:
    try:
        import assist_settings
        return bool(assist_settings.get('map_full_raised_as_wall', FULL_RAISED_AS_WALL_DEFAULT))
    except ImportError:
        return FULL_RAISED_AS_WALL_DEFAULT

def _map1_kind(value: int) -> str:
    if value == 0:
        return 'none'
    high = value >> 12 & 15
    if high == 8:
        return 'entity'
    if value & 32768 == 0:
        most = (value & 32512) >> 8
        least = value & 127
        return 'wall' if most == least else 'raised'
    if high == 9:
        return 'transparent'
    if high == 10:
        return 'edge'
    if high == 11:
        return 'door'
    if high == 12:
        return 'none'
    if high == 13:
        return 'diagonal'
    return 'wall'

def _is_blocker(value: int, raised_sight_threshold: float=0.0) -> bool:
    kind = _map1_kind(value)
    if kind == 'raised':
        return raised_blocks_sight(value, raised_sight_threshold)
    if kind in ('wall', 'edge', 'door'):
        return True
    if kind == 'transparent':
        return value & 256 == 0
    return False

def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = (x0, y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        cells.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return cells

def line_of_sight_blocked(map1: np.ndarray, px: int, py: int, tx: int, ty: int) -> bool:
    return _line_of_sight_blocked(map1, px, py, tx, ty)
VIEW_REVEAL_RADIUS = 6.0
VIEW_REVEAL_HALF_ANGLE_DEG = 45.0
_VIEW_COS_HALF_ANGLE = math.cos(math.radians(VIEW_REVEAL_HALF_ANGLE_DEG))

def cell_visible_in_cone(map1: np.ndarray | None, px: int, py: int, facing_dx: float, facing_dy: float, tx: int, ty: int, *, ignore_walls: bool=False) -> bool:
    ddx = tx - px
    ddy = ty - py
    dist = math.hypot(ddx, ddy)
    if dist > VIEW_REVEAL_RADIUS:
        return False
    if dist <= 0:
        return True
    dot = (ddx * facing_dx + ddy * facing_dy) / dist
    if dot < _VIEW_COS_HALF_ANGLE:
        return False
    if not ignore_walls and map1 is not None:
        if _line_of_sight_blocked(map1, px, py, tx, ty):
            return False
    return True

def _line_of_sight_blocked(map1: np.ndarray, px: int, py: int, tx: int, ty: int, raised_sight_threshold: float | None=None) -> bool:
    if (px, py) == (tx, ty):
        return False
    if raised_sight_threshold is None:
        raised_sight_threshold = resolve_raised_sight_threshold()
    H, W = map1.shape
    line = _bresenham(px, py, tx, ty)
    prev_cx, prev_cy = (px, py)
    for cx, cy in line:
        if (cx, cy) == (px, py):
            prev_cx, prev_cy = (cx, cy)
            continue
        if (cx, cy) == (tx, ty):
            return False
        if not (0 <= cx < W and 0 <= cy < H):
            prev_cx, prev_cy = (cx, cy)
            continue
        step_dx = cx - prev_cx
        step_dy = cy - prev_cy
        if step_dx != 0 and step_dy != 0:
            orth_a = (prev_cx + step_dx, prev_cy)
            orth_b = (prev_cx, prev_cy + step_dy)
            a_blocked = False
            b_blocked = False
            if 0 <= orth_a[0] < W and 0 <= orth_a[1] < H:
                a_blocked = _is_blocker(int(map1[orth_a[1], orth_a[0]]), raised_sight_threshold)
            if 0 <= orth_b[0] < W and 0 <= orth_b[1] < H:
                b_blocked = _is_blocker(int(map1[orth_b[1], orth_b[0]]), raised_sight_threshold)
            if a_blocked or b_blocked:
                return True
        if _is_blocker(int(map1[cy, cx]), raised_sight_threshold):
            return True
        prev_cx, prev_cy = (cx, cy)
    return False
_CHASM_FLOOR_IDS = (12, 13, 14)

def _is_chasm_floor(flor_val: int) -> bool:
    return flor_val >> 8 & 255 in _CHASM_FLOOR_IDS

def resolve_first_block(map1: np.ndarray | None, flor: np.ndarray | None, px: int, py: int, prev: bool) -> bool:
    if flor is None:
        return False
    H, W = flor.shape
    if not (0 <= px < W and 0 <= py < H):
        return prev
    if not _is_chasm_floor(int(flor[py, px])):
        return False
    kind = _map1_kind(int(map1[py, px])) if map1 is not None else 'none'
    if kind in ('none', 'wall'):
        return True
    return prev

def wall_passage_cell_visible(flor: np.ndarray | None, px: int, py: int, facing_dx: float, facing_dy: float, tx: int, ty: int, *, in_first_block: bool=False, ignore_walls: bool=False) -> bool:
    if not cell_visible_in_cone(None, px, py, facing_dx, facing_dy, tx, ty):
        return False
    if ignore_walls:
        return True
    if flor is None or not in_first_block:
        return False
    if (px, py) == (tx, ty):
        return True
    return not _line_of_sight_blocked_l1(flor, px, py, tx, ty)

def _line_of_sight_blocked_l1(flor: np.ndarray, px: int, py: int, tx: int, ty: int) -> bool:
    if (px, py) == (tx, ty):
        return False
    H, W = flor.shape
    line = _bresenham(px, py, tx, ty)
    prev_cx, prev_cy = (px, py)
    for cx, cy in line:
        if (cx, cy) == (px, py):
            prev_cx, prev_cy = (cx, cy)
            continue
        if (cx, cy) == (tx, ty):
            return False
        if not (0 <= cx < W and 0 <= cy < H):
            prev_cx, prev_cy = (cx, cy)
            continue
        step_dx = cx - prev_cx
        step_dy = cy - prev_cy
        if step_dx != 0 and step_dy != 0:
            orth_a = (prev_cx + step_dx, prev_cy)
            orth_b = (prev_cx, prev_cy + step_dy)
            a_blocked = False
            b_blocked = False
            if 0 <= orth_a[0] < W and 0 <= orth_a[1] < H:
                a_blocked = not _is_chasm_floor(int(flor[orth_a[1], orth_a[0]]))
            if 0 <= orth_b[0] < W and 0 <= orth_b[1] < H:
                b_blocked = not _is_chasm_floor(int(flor[orth_b[1], orth_b[0]]))
            if a_blocked or b_blocked:
                return True
        if not _is_chasm_floor(int(flor[cy, cx])):
            return True
        prev_cx, prev_cy = (cx, cy)
    return False
