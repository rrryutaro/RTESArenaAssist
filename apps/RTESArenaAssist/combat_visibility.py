from __future__ import annotations
from common_draw.automap_canvas import facing_delta
from normal_play.map.base import MapPollResult
from services.arena_reveal_stencil import cell_visible_in_cone
_ARENA_UNITS_PER_TILE = 128

def visible_enemy_slots(snapshot, map_result: MapPollResult | None) -> frozenset[int] | None:
    if map_result is None or map_result.axis is None or (not map_result.parent_area) or (map_result.source_player is None) or (map_result.projection is None):
        return None
    canvas_data = map_result.canvas
    if canvas_data is None or canvas_data.map1 is None:
        return None
    map1 = canvas_data.map1
    if getattr(map1, 'ndim', None) != 2:
        return None
    height, width = map1.shape
    if map_result.source_player != (snapshot.player_x, snapshot.player_z):
        return None
    player = map_result.projection.project(*map_result.source_player)
    if player is None:
        return None
    px, py = player
    if canvas_data.player_x != px or canvas_data.player_y != py or (not (0 <= px < width and 0 <= py < height)):
        return None
    positions: list[tuple[int, int, int, tuple[float, float]]] = []
    for enemy in snapshot.enemies:
        cx = enemy.x // _ARENA_UNITS_PER_TILE
        cy = enemy.y // _ARENA_UNITS_PER_TILE
        point = map_result.projection.project(cx, cy)
        if point is None:
            return None
        ex, ey = point
        if not (0 <= ex < width and 0 <= ey < height):
            return None
        exact = (ex + (enemy.x - cx * _ARENA_UNITS_PER_TILE) / _ARENA_UNITS_PER_TILE, ey + (enemy.y - cy * _ARENA_UNITS_PER_TILE) / _ARENA_UNITS_PER_TILE)
        positions.append((enemy.slot, ex, ey, exact))
    facing_x, facing_y = facing_delta(snapshot.player_angle_deg)
    return frozenset((slot for slot, ex, ey, exact in positions if cell_visible_in_cone(map1, px, py, facing_x, facing_y, ex, ey, target_point=exact)))
__all__ = ['visible_enemy_slots']
