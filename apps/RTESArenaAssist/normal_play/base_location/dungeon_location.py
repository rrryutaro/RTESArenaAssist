from __future__ import annotations
import dataclasses
import logging
from pathlib import Path
from typing import Optional
import numpy as np
from common_draw.automap_canvas import CanvasData, _classify_cell, _is_hidden_door_cell, _is_wall_passage_cell, facing_delta
from services.inf_file_parser import ITEM_POINT_CONTAINER, ITEM_POINT_QUEST_ITEM
from services.map_ext_store import SECTION_TREASURE_PILES, SECTION_WALL_PASSAGES
from services.automap_file import AutomapCache, EXPECTED_FILE_SIZE, cache_for_level_hash, level_index_of_hash, parse_automap_file, read_current_level_hash
from services.arena_reveal_stencil import apply_reveal_stencil, apply_reveal_stencil_with_los, resolve_first_block, wall_passage_cell_visible
from runtime_paths import resolve_arena_install_dir
from services.mif_loader import DEFAULT_INF_DIR, DEFAULT_MIF_DIR, _extract_entities, load_mif, parse_inf_level_transitions, parse_inf_menu_indices, parse_inf_walls_hidden_door_ids, resolve_inf_for_mif
from normal_play.map.base import MapContext, MapSessionBase
from normal_play.map.item_points import all_item_point_cells, item_point_cells, note_item_pickups, quest_item_point_cells
from assist_log import RECOGNITION_LEVEL as _RECOG_LEVEL
_log = logging.getLogger('base_location.dungeon')

class DungeonMapSession(MapSessionBase):

    def __init__(self) -> None:
        super().__init__()
        self._mif_dirs = [d for d in (DEFAULT_MIF_DIR, resolve_arena_install_dir()) if d is not None]
        self._inf_dir = DEFAULT_INF_DIR
        self._mif_name: Optional[str] = None
        self._floor: int = 0
        self._walkable: Optional[np.ndarray] = None
        self._map1: Optional[np.ndarray] = None
        self._flor: Optional[np.ndarray] = None
        self._bitmap: Optional[np.ndarray] = None
        self._level_store_key: Optional[str] = None
        self._notes: list[tuple[int, int, str]] = []
        self._level_up_index: Optional[int] = None
        self._level_down_index: Optional[int] = None
        self._hidden_door_ids: frozenset[int] = frozenset()
        self._menu_texture_indices: frozenset[int] = frozenset()
        self._ext_store = None
        self._private_store = None
        self._location_key: Optional[str] = None
        self._await_axis_reconfirm: bool = False
        self._record_ok: bool = False
        self._stair_cells: frozenset[tuple[int, int]] = frozenset()
        self._migrated_mifs: set[str] = set()
        self._mif_level_count: int = 1
        self._discovered_hd: frozenset[tuple[int, int]] = frozenset()
        self._discovered_wp: frozenset[tuple[int, int]] = frozenset()
        self._last_player_pos: Optional[tuple[int, int]] = None
        self._active_cache_index: Optional[int] = None
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle: Optional[float] = None
        self._reveal_all = False
        self._show_unexplored_floor = False
        self._center_on_player = True
        self._show_grid = True
        self._item_point_cells: dict[str, frozenset] = {}
        self._item_point_history: dict[str, frozenset] = {}
        self._live_reference_level = None
        self._generated_level = None
        self._live_grid_pending: bool = False
        self._live_grid_attempts: int = 0
        self._live_map1: Optional[list] = None
        self._live_flats: dict[int, int] = {}
        self._last_live_raw: Optional[list] = None
        self._last_live_hash: Optional[int] = None
        self._stale_live: Optional[list] = None
        self._stale_hash: Optional[int] = None
        self._live_grid_stale_polls: int = 0
        self._level_down_cells: frozenset = frozenset()
        self._artifact_chest_logged: Optional[tuple] = None
        self._flat_marks_all: tuple[tuple[int, int, str], ...] = ()
        self._show_static_flats = False
        self._known_treasure: frozenset = frozenset()
        self._item_pickup_kinds_prev: frozenset = frozenset()
        self._wall_los_enabled = False
        self._import_request = False
        self._wall_passage_cells: tuple[tuple[int, int], ...] = ()
        self._view_scan_key: tuple | None = None
        self._in_first_block: bool = False
        self._diag_reset_first: dict[str, bool] = {}
        self._diag_prev_update: tuple = ()
        self._diag_prev_merge_reason: str | None = None

    def start(self, ctx: MapContext) -> None:
        _log.info('dungeon_diag[id=%x]: start mif=%r save_dir=%r analyzer=%s anchor=%r', id(self), ctx.mif_name, ctx.save_dir, ctx.analyzer is not None, ctx.anchor)
        super().start(ctx)
        self._diag_prev_merge_reason = None

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._player_x = ctx.player_tile_x
        self._player_y = ctx.player_tile_y
        self._angle = ctx.angle_deg
        self._reveal_all = ctx.reveal_all
        self._show_unexplored_floor = ctx.show_unexplored_floor
        self._center_on_player = ctx.center_on_player
        self._show_grid = ctx.show_grid
        self._wall_los_enabled = ctx.wall_los_enabled
        self._show_static_flats = bool(getattr(ctx, 'wild_show_static_flats', False))
        self._ext_store = ctx.ext_store
        upd_key = (ctx.mif_name, ctx.player_tile_x, ctx.player_tile_y, self._mif_name, self._bitmap is None)
        if upd_key != self._diag_prev_update:
            self._diag_prev_update = upd_key
            _log.info('dungeon_diag[id=%x]: update ctx_mif=%r self_mif=%r player=(%s,%s) bitmap=%s', id(self), ctx.mif_name, self._mif_name, ctx.player_tile_x, ctx.player_tile_y, 'set' if self._bitmap is not None else 'None')
        if self._diag_reset_first.get('level') and ctx.dungeon_floor_fresh is not None:
            self._diag_reset_first['level'] = False
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: first level after reset (#%d)', id(self), int(ctx.dungeon_floor_fresh))
        floor = ctx.dungeon_floor
        if ctx.mif_name and floor is not None and (ctx.mif_name != self._mif_name or floor != self._floor):
            self._load_mif(ctx.mif_name, int(floor))
            self._mif_name = ctx.mif_name
            self._floor = int(floor)
        self._overlay_live_grid_if_pending(ctx)
        self._refresh_live_objects(ctx)
        self._refresh_level_axis(ctx)
        self._location_key = self._level_store_key
        self._update_record_gate(ctx)
        if self._import_request:
            self._import_request = False
            self._maybe_merge_automap(ctx)
        if self._record_ok and ctx.player_tile_x is not None and (ctx.player_tile_y is not None):
            self._in_first_block = resolve_first_block(self._map1, self._flor, int(ctx.player_tile_x), int(ctx.player_tile_y), self._in_first_block)
        if self._record_ok and ctx.player_tile_x is not None and (ctx.player_tile_y is not None) and (self._bitmap is not None):
            ix = int(ctx.player_tile_x)
            iy = int(ctx.player_tile_y)
            if 0 <= ix < 128 and 0 <= iy < 128:
                pos = (ix, iy)
                if pos != self._last_player_pos:
                    if self._wall_los_enabled:
                        apply_reveal_stencil(self._bitmap, ix, iy)
                    else:
                        apply_reveal_stencil_with_los(self._bitmap, self._map1, ix, iy, flor=self._flor, in_first_block=self._in_first_block)
                    self._note_hidden_door_if_any(ix, iy)
                    self._last_player_pos = pos
        self._note_wall_passages_in_view(ctx)
        self._note_item_pickups_if_any(ctx)
        if self._ext_store is not None and self._location_key:
            self._discovered_hd = self._ext_store.discovered_cells(self._location_key)
            self._known_treasure = self._ext_store.discovered_cells(self._location_key, SECTION_TREASURE_PILES)
            self._discovered_wp = self._ext_store.discovered_cells(self._location_key, SECTION_WALL_PASSAGES)
        else:
            self._discovered_hd = frozenset()
            self._known_treasure = frozenset()
            self._discovered_wp = frozenset()
        if ctx.player_tile_x is not None and ctx.player_tile_y is not None and self._stair_cells:
            _pos = (int(ctx.player_tile_x), int(ctx.player_tile_y))
            if _pos in self._stair_cells:
                self._await_axis_reconfirm = True

    def get_canvas_data(self) -> CanvasData:
        if self._await_axis_reconfirm or self._location_key is None:
            return CanvasData(walkable=None, map1=None, flor=None, bitmap_grid=None, notes=[], player_x=None, player_y=None, player_angle_deg=None, level_up_index=None, level_down_index=None, entrance_cells=(), is_wilderness=False, hidden_door_ids=frozenset(), menu_texture_indices=frozenset(), treasure_cells=frozenset(), discovered_hidden_door_cells=frozenset(), discovered_wall_passage_cells=frozenset(), map_key='dungeon:<transition>', cache_index=None)
        return CanvasData(walkable=self._walkable, map1=self._map1, flor=self._flor, bitmap_grid=self._bitmap, notes=self._notes, player_x=int(self._player_x) if self._player_x is not None else None, player_y=int(self._player_y) if self._player_y is not None else None, player_angle_deg=self._angle, level_up_index=self._level_up_index, level_down_index=self._level_down_index, entrance_cells=(), is_wilderness=False, hidden_door_ids=self._hidden_door_ids, menu_texture_indices=self._menu_texture_indices, treasure_cells=self._known_treasure, all_treasure_cells=all_item_point_cells(self._item_point_cells), quest_treasure_cells=quest_item_point_cells(self._item_point_cells), discovered_hidden_door_cells=self._discovered_hd, discovered_wall_passage_cells=self._discovered_wp, flat_marks=self._visible_flat_marks(), map_key=f'dungeon:{self._location_key}' if self._location_key else 'dungeon:<unknown>', cache_index=self._active_cache_index)
    _LIVE_GRID_MIN_MATCH = 0.95
    _LIVE_GRID_LOG_AFTER = 20

    def _overlay_live_grid_if_pending(self, ctx: MapContext) -> None:
        mif = self._live_reference_level
        if mif is None or not self._live_grid_pending:
            return
        from services.automap_file import read_current_level_hash
        from services.live_level_grid import match_ratio, read_level_map1
        live = read_level_map1(ctx.analyzer, ctx.anchor, mif.width, mif.height)
        if live is None:
            return
        ratio = match_ratio(live, mif.map1)
        if ratio < self._LIVE_GRID_MIN_MATCH:
            self._live_grid_attempts += 1
            if self._live_grid_attempts == self._LIVE_GRID_LOG_AFTER:
                _log.log(_RECOG_LEVEL, 'live level grid not matched: mif=%s level=%d ratio=%.3f attempts=%d', self._mif_name, mif.level_index, ratio, self._live_grid_attempts)
            return
        live_map1 = list(live)
        level_hash = read_current_level_hash(ctx.analyzer, ctx.anchor)
        if self._stale_live is not None and live_map1 == self._stale_live and (level_hash == self._stale_hash):
            self._live_grid_stale_polls += 1
            return
        self._live_grid_pending = False
        self._last_live_raw = list(live_map1)
        self._last_live_hash = level_hash
        differing = sum((1 for a, b in zip(live_map1, mif.map1) if a != b))
        placed: dict[int, int] = {}
        for a, b in zip(live_map1, mif.map1):
            if a != b and a & 61440 == 32768:
                placed[a & 255] = placed.get(a & 255, 0) + 1
        self._apply_live_map1(ctx, mif, live_map1)
        _log.log(_RECOG_LEVEL, 'live level grid applied: mif=%s level=%d ratio=%.4f differing=%d item_points=%d stairs=%d placed=%s previous_level_polls=%d', self._mif_name, mif.level_index, ratio, differing, len(all_item_point_cells(self._item_point_cells)), len(self._stair_cells), ','.join((f'{k}x{n}' for k, n in sorted(placed.items()))) or '-', self._live_grid_stale_polls)

    @staticmethod
    def _flat_cells(map1) -> dict[int, int]:
        return {i: v for i, v in enumerate(map1) if v & 61440 == 32768}

    def _apply_live_map1(self, ctx: MapContext, mif, map1: list) -> None:
        self._live_map1 = list(map1)
        self._live_flats = self._flat_cells(map1)
        self._install_level(self._mif_name, dataclasses.replace(mif, map1=list(map1), entities=_extract_entities(list(map1), list(mif.flor), mif.width, mif.height)))
        self._mark_artifact_quest_chest(ctx, mif)

    def _refresh_live_objects(self, ctx: MapContext) -> None:
        mif = self._live_reference_level
        if mif is None or self._live_grid_pending or self._live_map1 is None:
            return
        from services.automap_file import read_current_level_hash
        from services.live_level_grid import match_ratio, merge_live_cells, read_level_map1
        live = read_level_map1(ctx.analyzer, ctx.anchor, mif.width, mif.height)
        if live is None:
            return
        live = list(live)
        if live == self._last_live_raw:
            return
        if match_ratio(live, mif.map1) < self._LIVE_GRID_MIN_MATCH:
            return
        self._last_live_raw = live
        self._last_live_hash = read_current_level_hash(ctx.analyzer, ctx.anchor)
        before = self._live_map1
        map1 = merge_live_cells(before, live)
        if map1 == before:
            return
        flats = self._flat_cells(map1)
        added = len(set(flats) - set(self._live_flats))
        removed = len(set(self._live_flats) - set(flats))
        other = sum((1 for i in range(len(map1)) if map1[i] != before[i] and i not in flats and (i not in self._live_flats)))
        self._apply_live_map1(ctx, mif, map1)
        _log.log(_RECOG_LEVEL, 'live level grid objects changed: mif=%s level=%d added=%d removed=%d other=%d item_points=%d', self._mif_name, mif.level_index, added, removed, other, len(all_item_point_cells(self._item_point_cells)))

    def _mark_artifact_quest_chest(self, ctx: MapContext, mif) -> None:
        if self._level_down_cells:
            return
        from services.artifact_quest import read_artifact_quest
        from services.random_dungeon import find_random_dungeon_location
        loc = find_random_dungeon_location(self._mif_name or '')
        quest = read_artifact_quest(ctx.analyzer, ctx.anchor)
        if loc is None or quest is None:
            return
        role = quest.dungeon_role(*loc)
        cell = quest.chest_cell() if role else None
        containers = self._item_point_cells.get(ITEM_POINT_CONTAINER, frozenset())
        marked = cell if cell is not None and cell in containers else None
        if marked is not None:
            cells = dict(self._item_point_cells)
            cells[ITEM_POINT_QUEST_ITEM] = cells.get(ITEM_POINT_QUEST_ITEM, frozenset()) | {marked}
            self._item_point_cells = cells
        mark = (self._mif_name, mif.level_index, role, cell, marked)
        if mark != self._artifact_chest_logged:
            self._artifact_chest_logged = mark
            _log.log(_RECOG_LEVEL, 'artifact quest chest: mif=%s level=%d here=%s role=%s map=(%d,%d) artifact=(%d,%d) cell=%s marked=%s', self._mif_name, mif.level_index, loc, role, quest.map_province_id, quest.map_dungeon_id, quest.artifact_province_id, quest.artifact_dungeon_id, cell, marked)

    def _note_item_pickups_if_any(self, ctx: MapContext) -> None:
        kinds = frozenset(ctx.item_pickup_kinds or ())
        prev = self._item_pickup_kinds_prev
        self._item_pickup_kinds_prev = kinds
        if not self._record_ok:
            return
        note_item_pickups(self._ext_store, self._location_key, kinds=kinds, prev_kinds=prev, player_x=ctx.player_tile_x, player_y=ctx.player_tile_y, angle_deg=ctx.angle_deg, cells_by_kind=self._item_point_history)

    def _note_hidden_door_if_any(self, ix: int, iy: int) -> None:
        if self._ext_store is None or not self._location_key:
            return
        m = self._map1
        if m is None or iy >= m.shape[0] or ix >= m.shape[1] or (ix < 0) or (iy < 0):
            return
        if _is_hidden_door_cell(int(m[iy, ix]), self._hidden_door_ids):
            self._ext_store.note_discovery(self._location_key, ix, iy)

    def _note_wall_passages_in_view(self, ctx: MapContext) -> None:
        if not self._record_ok:
            return
        if self._ext_store is None or not self._location_key or (not self._wall_passage_cells):
            return
        if ctx.player_tile_x is None or ctx.player_tile_y is None or ctx.angle_deg is None:
            return
        px, py = (int(ctx.player_tile_x), int(ctx.player_tile_y))
        key = (px, py, int(ctx.angle_deg / 5.0))
        if key == self._view_scan_key:
            return
        self._view_scan_key = key
        fx, fy = facing_delta(ctx.angle_deg)
        for cx, cy in self._wall_passage_cells:
            if wall_passage_cell_visible(self._flor, px, py, fx, fy, cx, cy, in_first_block=self._in_first_block, ignore_walls=self._wall_los_enabled):
                self._ext_store.note_discovery(self._location_key, cx, cy, SECTION_WALL_PASSAGES)

    def request_automap_import(self) -> None:
        self._import_request = True

    def reset_progress(self) -> None:
        self._bitmap = None
        self._private_store = None
        self._level_store_key = None
        self._location_key = None
        self._await_axis_reconfirm = True
        self._diag_reset_first = {'level': True}
        self._view_scan_key = None
        self._in_first_block = False
        self._last_player_pos = None
        self._active_cache_index = None
        self._notes = []

    def _load_mif(self, mif_name: str, player_floor: int=0) -> None:
        if self._last_live_raw is not None:
            self._stale_live = self._last_live_raw
            self._stale_hash = self._last_live_hash
        self._last_live_raw = None
        self._last_live_hash = None
        self._live_grid_stale_polls = 0
        try:
            mif = load_mif(mif_name, self._mif_dirs, level_index_override=player_floor)
        except Exception:
            _log.exception('parse_mif failed: %s', mif_name)
            self._walkable = None
            self._map1 = None
            self._flor = None
            self._generated_level = None
            self._live_reference_level = None
            self._item_point_history = {}
            self._live_grid_pending = False
            return
        if mif is None:
            self._walkable = None
            self._map1 = None
            self._flor = None
            self._level_up_index = None
            self._level_down_index = None
            self._bitmap = None
            self._last_player_pos = None
            self._stair_cells = frozenset()
            self._wall_passage_cells = ()
            self._location_key = None
            self._level_store_key = None
            self._generated_level = None
            self._live_reference_level = None
            self._item_point_history = {}
            self._live_grid_pending = False
            return
        self._live_reference_level = mif
        self._generated_level = mif if getattr(mif, 'generated', False) else None
        self._live_grid_pending = True
        self._live_grid_attempts = 0
        self._live_map1 = None
        self._live_flats = {}
        self._item_point_history = {}
        self._install_level(mif_name, mif)

    def _install_level(self, mif_name: str, mif) -> None:
        map1 = np.array(mif.map1, dtype=np.uint16).reshape(mif.height, mif.width)
        self._map1 = map1
        self._walkable = (map1 == 0) | (map1 & 61440 == 32768)
        self._mif_level_count = int(getattr(mif, 'level_count', 1) or 1)
        if mif.flor and len(mif.flor) >= mif.height * mif.width:
            self._flor = np.array(mif.flor, dtype=np.uint16).reshape(mif.height, mif.width)
        else:
            self._flor = None
        self._wall_passage_cells = ()
        self._view_scan_key = None
        if self._flor is not None:
            cells: list[tuple[int, int]] = []
            for yy in range(mif.height):
                for xx in range(mif.width):
                    if _is_wall_passage_cell(int(map1[yy, xx]), int(self._flor[yy, xx])):
                        cells.append((xx, yy))
            self._wall_passage_cells = tuple(cells)
        self._level_up_index = None
        self._level_down_index = None
        hidden_door_ids: set[int] = set()
        menu_indices: set[int] = set()
        inf_path = resolve_inf_for_mif(mif_name, getattr(mif, 'info_name', ''), self._inf_dir)
        if inf_path is not None:
            try:
                lu, ld = parse_inf_level_transitions(inf_path)
                self._level_up_index = lu
                self._level_down_index = ld
            except Exception:
                pass
            try:
                hidden_door_ids = parse_inf_walls_hidden_door_ids(inf_path)
            except Exception:
                pass
            try:
                menu_indices = parse_inf_menu_indices(inf_path)
            except Exception:
                pass
        self._hidden_door_ids = frozenset(hidden_door_ids)
        self._menu_texture_indices = frozenset(menu_indices)
        stair_cells: list[tuple[int, int]] = []
        down_cells: list[tuple[int, int]] = []
        if self._flor is not None and (self._level_up_index is not None or self._level_down_index is not None):
            for yy in range(mif.height):
                for xx in range(mif.width):
                    kind = _classify_cell(int(map1[yy, xx]), int(self._flor[yy, xx]), self._level_up_index, self._level_down_index)
                    if kind in ('level_up', 'level_down'):
                        stair_cells.append((xx, yy))
                    if kind == 'level_down':
                        down_cells.append((xx, yy))
        self._stair_cells = frozenset(stair_cells)
        self._level_down_cells = frozenset(down_cells)
        try:
            self._item_point_cells = item_point_cells(getattr(mif, 'entities', None), inf_path)
        except Exception:
            self._item_point_cells = {}
        history = {kind: set(cells) for kind, cells in self._item_point_history.items()}
        for kind, cells in self._item_point_cells.items():
            history.setdefault(kind, set()).update(cells)
        self._item_point_history = {kind: frozenset(cells) for kind, cells in history.items()}
        self._flat_marks_all = ()
        if inf_path is not None:
            try:
                from services.wild_flats import classify_flat_name
                from services.mif_loader import parse_inf_flats
                flats = {f.index: f for f in parse_inf_flats(inf_path)}
                marks: list[tuple[int, int, str]] = []
                for e in mif.entities or []:
                    entry = flats.get(int(e.flat_index))
                    if entry is None or entry.item_number is not None:
                        continue
                    marks.append((int(e.x), int(e.y), classify_flat_name(entry.name)))
                self._flat_marks_all = tuple(marks)
            except Exception:
                self._flat_marks_all = ()

    def _migrate_hash_keys(self) -> None:
        if self._ext_store is None or not self._mif_name:
            return
        mif = self._mif_name.upper()
        if mif in self._migrated_mifs:
            return
        self._migrated_mifs.add(mif)
        try:
            keys = self._ext_store.location_keys(f'{mif}#')
        except AttributeError:
            return
        for old_key in keys:
            suffix = old_key[len(mif) + 1:]
            if len(suffix) != 8:
                continue
            try:
                level_hash = int(suffix, 16)
            except ValueError:
                continue
            idx = level_index_of_hash(level_hash)
            if idx is None:
                continue
            new_key = f'{mif}#{idx}'
            try:
                if self._ext_store.migrate_location_key(old_key, new_key):
                    _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: ext discoveries migrated %r -> %r', id(self), old_key, new_key)
            except Exception:
                _log.exception('ext key migration failed')

    def _update_record_gate(self, ctx: MapContext) -> None:
        pos = None
        if ctx.player_tile_x is not None and ctx.player_tile_y is not None:
            ix, iy = (int(ctx.player_tile_x), int(ctx.player_tile_y))
            if 0 <= ix < 128 and 0 <= iy < 128:
                pos = (ix, iy)
        if pos is not None and self._last_player_pos is not None and (abs(pos[0] - self._last_player_pos[0]) + abs(pos[1] - self._last_player_pos[1]) > 6):
            self._await_axis_reconfirm = True
            self._in_first_block = False
        if self._await_axis_reconfirm and ctx.dungeon_floor_fresh is not None and (self._location_key is not None):
            self._await_axis_reconfirm = False
        self._record_ok = not self._await_axis_reconfirm and self._location_key is not None

    def _refresh_level_axis(self, ctx: MapContext) -> None:
        floor = ctx.dungeon_floor
        if floor is None or not self._mif_name:
            return
        if int(floor) != self._floor:
            return
        key = f'{self._mif_name.upper()}#{int(floor)}'
        if key == self._level_store_key:
            return
        self._level_store_key = key
        self._migrate_hash_keys()
        bm = self._reveal_store().reveal_grid_for_update(key)
        self._bitmap = bm
        self._last_player_pos = None
        self._active_cache_index = None
        self._notes = []
        _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: level axis latch key=%r nz=%d', id(self), key, int((bm != 0).sum()))

    def _visible_flat_marks(self) -> tuple[tuple[int, int, str], ...]:
        if not self._show_static_flats or not self._flat_marks_all:
            return ()
        if self._reveal_all:
            return self._flat_marks_all
        bm = self._bitmap
        if bm is None:
            return ()
        return tuple(((x, y, cat) for x, y, cat in self._flat_marks_all if 0 <= y < 128 and 0 <= x < 128 and (bm[y, x] != 0)))

    def _reveal_store(self):
        if self._ext_store is not None:
            return self._ext_store
        if self._private_store is None:
            from services.map_ext_store import MapExtStore
            self._private_store = MapExtStore()
        return self._private_store

    def _diag_log_skip(self, reason: str) -> None:
        if reason != self._diag_prev_merge_reason:
            self._diag_prev_merge_reason = reason
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: merge skip reason=%s', id(self), reason)

    def _maybe_merge_automap(self, ctx: MapContext) -> bool:
        save_dir = ctx.save_dir
        if not save_dir:
            self._diag_log_skip('no_save_dir')
            return False
        cur_hash = read_current_level_hash(ctx.analyzer, ctx.anchor)
        if cur_hash is None:
            self._diag_log_skip('level_hash_unread')
            return False
        if self._location_key is None or level_index_of_hash(cur_hash) != self._floor:
            self._diag_log_skip('level_hash_mismatch')
            return False
        if self._bitmap is None:
            self._diag_log_skip('bitmap_none')
            return False
        ap = Path(save_dir) / 'AUTOMAP.64'
        try:
            st_before = ap.stat()
        except OSError:
            self._diag_log_skip('stat_failed')
            return False
        if st_before.st_size != EXPECTED_FILE_SIZE:
            self._diag_log_skip(f'bad_size={st_before.st_size}')
            return False
        try:
            af = parse_automap_file(ap)
        except Exception:
            _log.exception('automap_merge: parse_automap_file failed')
            return False
        try:
            st_after = ap.stat()
        except OSError:
            return False
        if st_after.st_mtime_ns != st_before.st_mtime_ns or st_after.st_size != st_before.st_size:
            return False
        active: AutomapCache | None = cache_for_level_hash(af, cur_hash)
        if active is None or active.bitmap_grid is None:
            self._diag_log_skip('no_level_hash_match')
            return False
        new_active_index = active.index
        if int((active.bitmap_grid != 0).sum()) >= int(active.bitmap_grid.size):
            self._diag_log_skip('degenerate_full_bitmap')
            return False
        self._bitmap[:] = active.bitmap_grid
        self._notes = [(n.x, n.y, n.text) for n in active.valid_notes]
        self._last_player_pos = None
        self._active_cache_index = new_active_index
        nz = int((self._bitmap != 0).sum())
        _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: merge OK cache=#%s cur_hash=0x%08X bitmap_nz=%d', id(self), new_active_index, cur_hash if cur_hash else 0, nz)
        self._diag_prev_merge_reason = 'ok'
        return True
__all__ = ['DungeonMapSession']
