from __future__ import annotations
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

def apply_reveal_stencil_with_los(bitmap: np.ndarray, map1: np.ndarray | None, player_x: int, player_y: int) -> int:
    if map1 is None:
        return apply_reveal_stencil(bitmap, player_x, player_y)
    changes = 0
    H, W = map1.shape
    for dx, dy, value in iter_arena_reveal_offsets():
        x = player_x + dx & 127
        y = player_y + dy & 127
        old = int(bitmap[y, x])
        if value <= old:
            continue
        if 0 <= x < W and 0 <= y < H:
            if _line_of_sight_blocked(map1, player_x, player_y, x, y):
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

def _is_blocker(value: int) -> bool:
    kind = _map1_kind(value)
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

def _line_of_sight_blocked(map1: np.ndarray, px: int, py: int, tx: int, ty: int) -> bool:
    if (px, py) == (tx, ty):
        return False
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
                a_blocked = _is_blocker(int(map1[orth_a[1], orth_a[0]]))
            if 0 <= orth_b[0] < W and 0 <= orth_b[1] < H:
                b_blocked = _is_blocker(int(map1[orth_b[1], orth_b[0]]))
            if a_blocked or b_blocked:
                return True
        if _is_blocker(int(map1[cy, cx])):
            return True
        prev_cx, prev_cy = (cx, cy)
    return False
