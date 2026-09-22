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
    bm_h, bm_w = bitmap.shape
    for dx, dy, value in iter_arena_reveal_offsets():
        x = player_x + dx
        y = player_y + dy
        if not (0 <= x < bm_w and 0 <= y < bm_h):
            continue
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
    bm_h, bm_w = bitmap.shape
    raised_threshold = resolve_raised_sight_threshold()
    for dx, dy, value in iter_arena_reveal_offsets():
        x = player_x + dx
        y = player_y + dy
        if not (0 <= x < W and 0 <= y < H and (0 <= x < bm_w) and (0 <= y < bm_h)):
            continue
        old = int(bitmap[y, x])
        if value <= old:
            continue
        if use_l1:
            if _line_of_sight_blocked_l1(flor, player_x, player_y, x, y):
                continue
        elif _line_of_sight_blocked(map1, player_x, player_y, x, y, raised_threshold):
            continue
        bitmap[y, x] = value
        changes += 1
    return changes
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

def map1_diagonal_is_slash(value: int) -> bool:
    return value & 256 != 0
SIGHT_OPEN = 0
SIGHT_SOLID = 1
SIGHT_DIAG_MAIN = 2
SIGHT_DIAG_ANTI = 3

def _sight_occluder(value: int, raised_sight_threshold: float=0.0) -> int:
    kind = _map1_kind(value)
    if kind == 'raised':
        return SIGHT_SOLID if raised_blocks_sight(value, raised_sight_threshold) else SIGHT_OPEN
    if kind in ('wall', 'edge', 'door'):
        return SIGHT_SOLID
    if kind == 'transparent':
        return SIGHT_SOLID if value & 256 == 0 else SIGHT_OPEN
    if kind == 'diagonal':
        return SIGHT_DIAG_ANTI if map1_diagonal_is_slash(value) else SIGHT_DIAG_MAIN
    return SIGHT_OPEN
_SIGHT_FRAMES = tuple(((sx, sy, swap) for sx in (1, -1) for sy in (1, -1) for swap in (False, True)))

def _sight_blocked(occluder, width: int, height: int, px: int, py: int, tx: int, ty: int) -> bool:
    if (px, py) == (tx, ty):
        return False
    dx = tx - px
    dy = ty - py
    if abs(dx) + abs(dy) == 1:
        return False
    for sx, sy, swap in _SIGHT_FRAMES:
        u, v = (sx * dx, sy * dy)
        if swap:
            u, v = (v, u)
        if u < 1 or v < 0 or v > u + 1:
            continue
        if _free_line_exists(occluder, width, height, px, py, sx, sy, swap, u, v):
            return False
    return True

def _free_line_exists(occluder, width: int, height: int, px: int, py: int, sx: int, sy: int, swap: bool, u: int, v: int) -> bool:
    plates: list[tuple[int, int, int]] = []
    for k in range(u + 1):
        for r in range(v + 1):
            if k == 0 and r == 0 or (k == u and r == v):
                continue
            a, b = (r, k) if swap else (k, r)
            wx, wy = (px + sx * a, py + sy * b)
            if not (0 <= wx < width and 0 <= wy < height):
                continue
            kind = occluder(wx, wy)
            if kind == SIGHT_OPEN:
                continue
            if kind == SIGHT_DIAG_MAIN or kind == SIGHT_DIAG_ANTI:
                if sx * sy < 0:
                    kind = SIGHT_DIAG_ANTI if kind == SIGHT_DIAG_MAIN else SIGHT_DIAG_MAIN
            if kind == SIGHT_DIAG_MAIN:
                plates.append((k, r, r + 1))
            else:
                plates.append((k, r + 1, r))
    if not plates:
        return True
    poly = [(0, 0, 1), (1, -1, 1), (1, 1, 1), (0, 1, 1)]
    poly = _clip(poly, u, 1, v + 1)
    poly = _clip(poly, -(u + 1), -1, -v)
    pieces = [poly] if _has_area(poly) else []
    for k, h0, h1 in plates:
        if not pieces:
            break
        rest = []
        for piece in pieces:
            above = _clip(_clip(piece, -k, -1, -h0), -(k + 1), -1, -h1)
            if _has_area(above):
                rest.append(above)
            below = _clip(_clip(piece, k, 1, h0), k + 1, 1, h1)
            if _has_area(below):
                rest.append(below)
        pieces = rest
    return bool(pieces)

def _clip(poly, a: int, b: int, d: int):
    out = []
    if not poly:
        return out
    prev = poly[-1]
    ps = a * prev[0] + b * prev[1] - d * prev[2]
    for cur in poly:
        cs = a * cur[0] + b * cur[1] - d * cur[2]
        if cs <= 0:
            if ps > 0:
                out.append(_cut(prev, ps, cur, cs))
            out.append(cur)
        elif ps <= 0:
            out.append(_cut(prev, ps, cur, cs))
        prev, ps = (cur, cs)
    return out

def _cut(p, ps: int, q, qs: int):
    pm, pc, pw = p
    qm, qc, qw = q
    m = qm * ps - pm * qs
    c = qc * ps - pc * qs
    w = ps * qw - qs * pw
    if w < 0:
        m, c, w = (-m, -c, -w)
    g = math.gcd(math.gcd(abs(m), abs(c)), w)
    if g > 1:
        m //= g
        c //= g
        w //= g
    return (m, c, w)

def _has_area(poly) -> bool:
    n = len(poly)
    if n < 3:
        return False
    m0, c0, w0 = poly[0]
    for i in range(1, n):
        m1, c1, w1 = poly[i]
        if m1 * w0 == m0 * w1 and c1 * w0 == c0 * w1:
            continue
        for j in range(i + 1, n):
            m2, c2, w2 = poly[j]
            det = m0 * (c1 * w2 - c2 * w1) - c0 * (m1 * w2 - m2 * w1) + w0 * (m1 * c2 - m2 * c1)
            if det != 0:
                return True
        return False
    return False

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
    if raised_sight_threshold is None:
        raised_sight_threshold = resolve_raised_sight_threshold()
    H, W = map1.shape

    def occluder(x: int, y: int) -> int:
        return _sight_occluder(int(map1[y, x]), raised_sight_threshold)
    return _sight_blocked(occluder, W, H, px, py, tx, ty)
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
    H, W = flor.shape

    def occluder(x: int, y: int) -> int:
        return SIGHT_OPEN if _is_chasm_floor(int(flor[y, x])) else SIGHT_SOLID
    return _sight_blocked(occluder, W, H, px, py, tx, ty)
