from __future__ import annotations
from common_draw.automap_canvas import facing_target_cell
from services.inf_file_parser import ITEM_POINT_CONTAINER, ITEM_POINT_KEY, ITEM_POINT_QUEST_ITEM, item_point_flat_kinds, parse_inf
from services.map_ext_store import SECTION_TREASURE_PILES

def pickup_kinds(*, pickup_list_open: bool, red_text_open: bool, runtime_dialog_accepted: bool) -> frozenset:
    kinds = set()
    if pickup_list_open:
        kinds.add(ITEM_POINT_CONTAINER)
    if red_text_open:
        kinds.add(ITEM_POINT_KEY)
    if runtime_dialog_accepted:
        kinds.add(ITEM_POINT_QUEST_ITEM)
    return frozenset(kinds)

def item_point_cells(entities, inf_path) -> dict[str, frozenset]:
    if inf_path is None:
        return {}
    flat_kinds = item_point_flat_kinds(parse_inf(inf_path))
    cells: dict[str, set] = {}
    for e in entities or ():
        kind = flat_kinds.get(int(e.flat_index))
        if kind is not None:
            cells.setdefault(kind, set()).add((int(e.x), int(e.y)))
    return {kind: frozenset(c) for kind, c in cells.items()}

def note_item_pickups(ext_store, location_key, *, kinds: frozenset, prev_kinds: frozenset, player_x, player_y, angle_deg, cells_by_kind: dict) -> None:
    if ext_store is None or not location_key:
        return
    for kind in kinds - prev_kinds:
        cell = facing_target_cell(player_x, player_y, angle_deg, cells_by_kind.get(kind, frozenset()))
        if cell is not None:
            ext_store.note_discovery(location_key, cell[0], cell[1], SECTION_TREASURE_PILES)
__all__ = ['pickup_kinds', 'item_point_cells', 'note_item_pickups']
