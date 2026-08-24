from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
import numpy as np
from common_draw.automap_canvas import CanvasData, _classify_cell, _is_hidden_door_cell, _is_wall_passage_cell, facing_delta, facing_target_cell
from services.map_ext_store import SECTION_TREASURE_PILES, SECTION_WALL_PASSAGES
from services.automap_file import AutomapCache, EXPECTED_FILE_SIZE, cache_for_level_hash, parse_automap_file, read_current_level_hash
from services.arena_reveal_stencil import apply_reveal_stencil, apply_reveal_stencil_with_los, rebuild_seen_cells_from_bitmap, resolve_first_block, wall_passage_cell_visible
from runtime_paths import resolve_arena_install_dir
from services.mif_loader import DEFAULT_INF_DIR, DEFAULT_MIF_DIR, load_mif, parse_inf_level_transitions, parse_inf_menu_indices, parse_inf_walls_hidden_door_ids, resolve_inf_for_mif
from normal_play.map.base import MapContext, MapSessionBase
from assist_log import RECOGNITION_LEVEL as _RECOG_LEVEL
_log = logging.getLogger('base_location.dungeon')
_PAIR_CONFIRM_POLLS = 3

def _load_persisted_pairs() -> dict[str, dict[int, int]]:
    try:
        from services.map_ext_store import load_hash_floor_pairs
        return load_hash_floor_pairs()
    except Exception:
        return {}

def _persist_pairs(pairs: dict[str, dict[int, int]]) -> None:
    try:
        from services.map_ext_store import save_hash_floor_pairs
        save_hash_floor_pairs(pairs)
    except Exception:
        _log.exception('pair persist failed')

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
        self._level_hash: Optional[int] = None
        self._level_store_key: Optional[str] = None
        self._level_hash_fresh: Optional[int] = None
        self._seen_cells: set[tuple[int, int]] = set()
        self._notes: list[tuple[int, int, str]] = []
        self._level_up_index: Optional[int] = None
        self._level_down_index: Optional[int] = None
        self._hidden_door_ids: frozenset[int] = frozenset()
        self._menu_texture_indices: frozenset[int] = frozenset()
        self._ext_store = None
        self._private_store = None
        self._location_key: Optional[str] = None
        self._hash_floor_pairs: dict[str, dict[int, int]] = {}
        self._await_axis_reconfirm: bool = False
        self._record_ok: bool = False
        self._stair_cells: frozenset[tuple[int, int]] = frozenset()
        self._axis_aligned: bool = False
        self._pair_candidate: tuple[int, int] | None = None
        self._pair_streak: int = 0
        self._hash_floor_pairs.update(_load_persisted_pairs())
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
        self._treasure_pile_cells: frozenset = frozenset()
        self._flat_marks_all: tuple[tuple[int, int, str], ...] = ()
        self._show_static_flats = False
        self._known_treasure: frozenset = frozenset()
        self._treasure_pickup_was_open = False
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
        self._refresh_level_axis(ctx)
        if self._diag_reset_first.get('hash') and self._level_hash_fresh is not None:
            self._diag_reset_first['hash'] = False
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: first hash after reset (%08X)', id(self), self._level_hash_fresh)
        if self._diag_reset_first.get('hyp') and ctx.dungeon_floor_fresh is not None:
            self._diag_reset_first['hyp'] = False
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: first hyp after reset (#%d)', id(self), int(ctx.dungeon_floor_fresh))
        self._learn_hash_floor_pair(ctx)
        target_floor = self._resolve_target_floor(ctx)
        if ctx.mif_name and (ctx.mif_name != self._mif_name or (target_floor is not None and target_floor != self._floor)):
            self._load_mif(ctx.mif_name, target_floor if target_floor is not None else ctx.player_floor)
            self._mif_name = ctx.mif_name
            self._floor = target_floor if target_floor is not None else ctx.player_floor
        self._location_key = self._level_store_key
        self._refresh_axis_alignment(ctx)
        self._update_record_gate(ctx)
        if self._import_request:
            self._import_request = False
            self._maybe_merge_automap(ctx)
        if self._record_ok and ctx.player_tile_x is not None and (ctx.player_tile_y is not None) and (self._bitmap is not None):
            ix = int(ctx.player_tile_x)
            iy = int(ctx.player_tile_y)
            if 0 <= ix < 128 and 0 <= iy < 128:
                pos = (ix, iy)
                if pos != self._last_player_pos:
                    if pos not in self._seen_cells:
                        self._seen_cells.add(pos)
                        if self._wall_los_enabled:
                            apply_reveal_stencil(self._bitmap, ix, iy)
                        else:
                            apply_reveal_stencil_with_los(self._bitmap, self._map1, ix, iy)
                    self._note_hidden_door_if_any(ix, iy)
                    self._last_player_pos = pos
        self._note_wall_passages_in_view(ctx)
        self._note_treasure_piles_if_any(ctx)
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
        if self._await_axis_reconfirm or not self._axis_aligned or self._location_key is None:
            return CanvasData(walkable=None, map1=None, flor=None, bitmap_grid=None, notes=[], player_x=None, player_y=None, player_angle_deg=None, level_up_index=None, level_down_index=None, entrance_cells=(), is_wilderness=False, hidden_door_ids=frozenset(), menu_texture_indices=frozenset(), treasure_pile_cells=frozenset(), discovered_hidden_door_cells=frozenset(), discovered_wall_passage_cells=frozenset(), map_key='dungeon:<transition>', cache_index=None)
        return CanvasData(walkable=self._walkable, map1=self._map1, flor=self._flor, bitmap_grid=self._bitmap, notes=self._notes, player_x=int(self._player_x) if self._player_x is not None else None, player_y=int(self._player_y) if self._player_y is not None else None, player_angle_deg=self._angle, level_up_index=self._level_up_index, level_down_index=self._level_down_index, entrance_cells=(), is_wilderness=False, hidden_door_ids=self._hidden_door_ids, menu_texture_indices=self._menu_texture_indices, treasure_pile_cells=self._known_treasure, discovered_hidden_door_cells=self._discovered_hd, discovered_wall_passage_cells=self._discovered_wp, flat_marks=self._visible_flat_marks(), map_key=f'dungeon:{self._location_key}' if self._location_key else 'dungeon:<unknown>', cache_index=self._active_cache_index)

    def _note_treasure_piles_if_any(self, ctx: MapContext) -> None:
        opened = bool(ctx.treasure_pickup_open)
        was_open = self._treasure_pickup_was_open
        self._treasure_pickup_was_open = opened
        if not opened or was_open:
            return
        if not self._record_ok:
            return
        if self._ext_store is None or not self._location_key or (not self._treasure_pile_cells):
            return
        cell = facing_target_cell(ctx.player_tile_x, ctx.player_tile_y, ctx.angle_deg, self._treasure_pile_cells)
        if cell is None:
            return
        self._ext_store.note_discovery(self._location_key, cell[0], cell[1], SECTION_TREASURE_PILES)

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
        self._in_first_block = resolve_first_block(self._map1, self._flor, px, py, self._in_first_block)
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
        self._level_hash = None
        self._level_hash_fresh = None
        self._level_store_key = None
        self._location_key = None
        self._await_axis_reconfirm = True
        self._axis_aligned = False
        self._pair_candidate = None
        self._pair_streak = 0
        self._diag_reset_first = {'hash': True, 'hyp': True}
        self._view_scan_key = None
        self._in_first_block = False
        self._seen_cells.clear()
        self._last_player_pos = None
        self._active_cache_index = None
        self._notes = []

    def _load_mif(self, mif_name: str, player_floor: int=0) -> None:
        try:
            mif = load_mif(mif_name, self._mif_dirs, level_index_override=player_floor)
        except Exception:
            _log.exception('parse_mif failed: %s', mif_name)
            self._walkable = None
            self._map1 = None
            self._flor = None
            return
        if mif is None:
            self._walkable = None
            self._map1 = None
            self._flor = None
            self._level_up_index = None
            self._level_down_index = None
            self._bitmap = None
            self._seen_cells.clear()
            self._last_player_pos = None
            self._stair_cells = frozenset()
            self._wall_passage_cells = ()
            self._location_key = None
            self._level_store_key = None
            self._level_hash = None
            return
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
        if self._flor is not None and (self._level_up_index is not None or self._level_down_index is not None):
            for yy in range(mif.height):
                for xx in range(mif.width):
                    kind = _classify_cell(int(map1[yy, xx]), int(self._flor[yy, xx]), self._level_up_index, self._level_down_index)
                    if kind in ('level_up', 'level_down'):
                        stair_cells.append((xx, yy))
        self._stair_cells = frozenset(stair_cells)
        self._treasure_pile_cells = frozenset()
        if inf_path is not None:
            try:
                from services.inf_file_parser import parse_inf, treasure_pile_flat_indices
                piles = treasure_pile_flat_indices(parse_inf(inf_path))
                self._treasure_pile_cells = frozenset(((int(e.x), int(e.y)) for e in mif.entities or [] if int(e.flat_index) in piles))
            except Exception:
                self._treasure_pile_cells = frozenset()
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

    def _resolve_target_floor(self, ctx: MapContext) -> Optional[int]:
        if self._level_hash is None:
            return None
        mif = (ctx.mif_name or self._mif_name or '').upper()
        pairs = self._hash_floor_pairs.get(mif)
        if pairs is not None and self._level_hash in pairs:
            return pairs[self._level_hash]
        return None

    def _learn_hash_floor_pair(self, ctx: MapContext) -> None:
        fresh = self._level_hash_fresh
        if fresh is None or ctx.dungeon_floor_fresh is None or (not self._mif_name):
            return
        cand = (int(fresh), int(ctx.dungeon_floor_fresh))
        if cand != self._pair_candidate:
            self._pair_candidate = cand
            self._pair_streak = 1
            return
        self._pair_streak += 1
        if self._pair_streak < _PAIR_CONFIRM_POLLS:
            return
        mif = self._mif_name.upper()
        fresh, floor = cand
        pairs = self._hash_floor_pairs.setdefault(mif, {})
        if pairs.get(fresh) != floor:
            pairs[fresh] = floor
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: hash-floor pair confirmed %s: %08X -> #%d (streak=%d)', id(self), mif, fresh, floor, self._pair_streak)
            _persist_pairs(self._hash_floor_pairs)
        if self._ext_store is None:
            return
        old_key = f'{mif}#{floor}'
        new_key = f'{mif}#{fresh:08X}'
        try:
            if self._ext_store.migrate_location_key(old_key, new_key):
                _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: ext discoveries migrated %r -> %r', id(self), old_key, new_key)
        except Exception:
            _log.exception('ext key migration failed')

    def _refresh_axis_alignment(self, ctx: MapContext) -> None:
        prev = self._axis_aligned
        if (self._mif_level_count or 1) <= 1:
            aligned = self._location_key is not None
        else:
            pairs = self._hash_floor_pairs.get((self._mif_name or '').upper()) or {}
            mapped = pairs.get(self._level_hash) if self._level_hash is not None else None
            conflict = ctx.dungeon_floor_fresh is not None and mapped is not None and (int(ctx.dungeon_floor_fresh) != mapped)
            aligned = self._location_key is not None and mapped is not None and (mapped == self._floor) and (not conflict)
        self._axis_aligned = aligned
        if aligned != prev:
            _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: axis %s key=%r floor=#%d', id(self), 'aligned' if aligned else 'transition', self._location_key, self._floor)

    def _update_record_gate(self, ctx: MapContext) -> None:
        pos = None
        if ctx.player_tile_x is not None and ctx.player_tile_y is not None:
            ix, iy = (int(ctx.player_tile_x), int(ctx.player_tile_y))
            if 0 <= ix < 128 and 0 <= iy < 128:
                pos = (ix, iy)
        if pos is not None and self._last_player_pos is not None and (abs(pos[0] - self._last_player_pos[0]) + abs(pos[1] - self._last_player_pos[1]) > 6):
            self._await_axis_reconfirm = True
            self._in_first_block = False
        if self._await_axis_reconfirm and self._level_hash_fresh is not None:
            self._await_axis_reconfirm = False
        self._record_ok = not self._await_axis_reconfirm and self._axis_aligned and (self._location_key is not None)

    def _refresh_level_axis(self, ctx: MapContext) -> None:
        fresh = read_current_level_hash(ctx.analyzer, ctx.anchor)
        self._level_hash_fresh = fresh
        if fresh is None or not self._mif_name:
            return
        key = f'{self._mif_name.upper()}#{fresh:08X}'
        if key == self._level_store_key:
            return
        self._level_hash = fresh
        self._level_store_key = key
        self._pair_candidate = None
        self._pair_streak = 0
        bm = self._reveal_store().reveal_grid_for_update(key)
        self._bitmap = bm
        self._seen_cells = rebuild_seen_cells_from_bitmap(bm)
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
        cur_hash = self._level_hash_fresh
        if cur_hash is None or cur_hash != self._level_hash:
            self._diag_log_skip('level_hash_unread')
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
        self._seen_cells = rebuild_seen_cells_from_bitmap(self._bitmap)
        self._notes = [(n.x, n.y, n.text) for n in active.valid_notes]
        self._last_player_pos = None
        self._active_cache_index = new_active_index
        nz = int((self._bitmap != 0).sum())
        _log.log(_RECOG_LEVEL, 'dungeon_diag[id=%x]: merge OK cache=#%s cur_hash=0x%08X bitmap_nz=%d', id(self), new_active_index, cur_hash if cur_hash else 0, nz)
        self._diag_prev_merge_reason = 'ok'
        return True
__all__ = ['DungeonMapSession']
