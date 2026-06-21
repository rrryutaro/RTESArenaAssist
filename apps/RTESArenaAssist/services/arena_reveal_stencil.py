"""arena_reveal_stencil.py — Arena 原作の AUTOMAP reveal stencil。

特徴:
- brush 形状: 9×9 weighted stencil (= 下記 ARENA_REVEAL_STENCIL)
- 値の更新: max(existing, stencil_value) (= 加算ではない)
- 適用条件: player が未訪問の cell に初めて入った時のみ
- 既訪問 cell への往復移動・回転のみでは bitmap 変化なし
- bitmap は 128×128 で、player 位置が左端付近のとき dx=-4 等は & 0x7F で wrap

「壁の見通し OFF」モード (= apply_reveal_stencil_with_los) では未確認 cell に
対してのみ LoS で壁ブロック判定する。既に判明している cell (= bitmap > 0) は
LoS にかかわらず維持され、マップ上の記録が消えることはない。
"""
from __future__ import annotations

import numpy as np


# 各 row は dy=-4..+4、各 char は dx=-4..+4。"." は 0 (= reveal せず)。
ARENA_REVEAL_STENCIL: tuple[str, ...] = (
    "1..111...",   # dy = -4
    "11122211.",   # dy = -3
    "11222221.",   # dy = -2
    "112333211",   # dy = -1
    "112333211",   # dy =  0
    "112333211",   # dy = +1
    ".1222221.",   # dy = +2
    ".1111111.",   # dy = +3
    "...111...",   # dy = +4
)


def iter_arena_reveal_offsets():
    """Arena reveal stencil の (dx, dy, value) を yield する。"""
    for row_idx, row in enumerate(ARENA_REVEAL_STENCIL):
        dy = row_idx - 4
        for col_idx, ch in enumerate(row):
            dx = col_idx - 4
            if ch != ".":
                yield dx, dy, int(ch)


def apply_reveal_stencil(bitmap: np.ndarray, player_x: int, player_y: int) -> int:
    """壁の見通し ON 用: 9×9 weighted stencil を max() 合成で適用する。

    bitmap は 128×128 uint8。player_x/player_y が左端付近のとき dx=-4 等は
    `& 0x7F` (= modulo 128) で wrap する。
    """
    changes = 0
    for dx, dy, value in iter_arena_reveal_offsets():
        x = (player_x + dx) & 0x7F
        y = (player_y + dy) & 0x7F
        old = int(bitmap[y, x])
        if value > old:
            bitmap[y, x] = value
            changes += 1
    return changes


def apply_reveal_stencil_with_los(
    bitmap: np.ndarray,
    map1: np.ndarray | None,
    player_x: int,
    player_y: int,
) -> int:
    """壁の見通し OFF 用: 未確認 cell に対してのみ LoS で壁ブロック判定する。

    既に判明している (= bitmap > 0) cell は LoS にかかわらず維持されるため、
    マップ上の記録が消えることはない。MIF データが無い場合 (map1=None) は
    LoS チェックをスキップし、apply_reveal_stencil と同じ挙動になる。
    """
    if map1 is None:
        return apply_reveal_stencil(bitmap, player_x, player_y)
    changes = 0
    H, W = map1.shape
    for dx, dy, value in iter_arena_reveal_offsets():
        x = (player_x + dx) & 0x7F
        y = (player_y + dy) & 0x7F
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
    """AUTOMAP.64 取り込み直後に value=3 cell から seen 集合を再構築する。"""
    seen: set[tuple[int, int]] = set()
    if bitmap is None:
        return seen
    ys, xs = np.where(bitmap == 3)
    for x, y in zip(xs.tolist(), ys.tolist()):
        seen.add((int(x), int(y)))
    return seen


# ── LoS 判定 ────────────────────────────────────────────────


def _map1_kind(value: int) -> str:
    if value == 0:
        return "none"
    high = (value >> 12) & 0x0F
    if high == 0x8:
        return "entity"
    if (value & 0x8000) == 0:
        most = (value & 0x7F00) >> 8
        least = value & 0x007F
        return "wall" if most == least else "raised"
    if high == 0x9:
        return "transparent"
    if high == 0xA:
        return "edge"
    if high == 0xB:
        return "door"
    if high == 0xC:
        return "none"
    if high == 0xD:
        return "diagonal"
    return "wall"


def _is_blocker(value: int) -> bool:
    kind = _map1_kind(value)
    if kind in ("wall", "edge", "door"):
        return True
    if kind == "transparent":
        return (value & 0x0100) == 0
    return False


def _bresenham(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
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


def _line_of_sight_blocked(
    map1: np.ndarray, px: int, py: int, tx: int, ty: int,
) -> bool:
    """player (px,py) から (tx,ty) までの LoS が壁で遮られているかを返す。

    対角抜け防止: 斜め step で両側の orth cell どちらかが blocker なら遮断扱い。
    ターゲット自身が blocker でも、そこまでの line が通っていれば可視扱い
    (= ターゲット手前で line を打ち切るため)。
    """
    if (px, py) == (tx, ty):
        return False
    H, W = map1.shape
    line = _bresenham(px, py, tx, ty)
    prev_cx, prev_cy = px, py
    for cx, cy in line:
        if (cx, cy) == (px, py):
            prev_cx, prev_cy = cx, cy
            continue
        if (cx, cy) == (tx, ty):
            return False
        if not (0 <= cx < W and 0 <= cy < H):
            prev_cx, prev_cy = cx, cy
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
        prev_cx, prev_cy = cx, cy
    return False
