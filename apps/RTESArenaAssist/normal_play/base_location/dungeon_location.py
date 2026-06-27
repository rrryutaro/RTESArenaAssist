from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional
import numpy as np
from common_draw.automap_canvas import CanvasData, _is_hidden_door_cell
from services.automap_file import AutomapCache, CURRENT_LEVEL_HASH_OFFSET, EXPECTED_FILE_SIZE, find_active_cache, parse_automap_file
from services.arena_reveal_stencil import apply_reveal_stencil, apply_reveal_stencil_with_los, rebuild_seen_cells_from_bitmap
from runtime_paths import resolve_arena_install_dir
from services.mif_loader import DEFAULT_INF_DIR, DEFAULT_MIF_DIR, load_mif, parse_inf_level_transitions, parse_inf_menu_indices, parse_inf_walls_hidden_door_ids, resolve_inf_for_mif
from normal_play.map.base import MapContext, MapSessionBase
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
        self._seen_cells: set[tuple[int, int]] = set()
        self._notes: list[tuple[int, int, str]] = []
        self._level_up_index: Optional[int] = None
        self._level_down_index: Optional[int] = None
        self._hidden_door_ids: frozenset[int] = frozenset()
        self._menu_texture_indices: frozenset[int] = frozenset()
        self._ext_store = None
        self._location_key: Optional[str] = None
        self._discovered_hd: frozenset[tuple[int, int]] = frozenset()
        self._last_player_pos: Optional[tuple[int, int]] = None
        self._last_automap_mtime_ns: Optional[int] = None
        self._last_automap_size: int = 0
        self._active_cache_index: Optional[int] = None
        self._reset_retry_remaining: int = 0
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle: Optional[float] = None
        self._reveal_all = False
        self._show_unexplored_floor = False
        self._center_on_player = True
        self._show_grid = True
        self._wall_los_enabled = False
        self._diag_prev_update: tuple = ()
        self._diag_prev_merge_reason: str | None = None

    def start(self, ctx: MapContext) -> None:
        _log.info('dungeon_diag[id=%x]: start mif=%r save_dir=%r analyzer=%s anchor=%r', id(self), ctx.mif_name, ctx.save_dir, ctx.analyzer is not None, ctx.anchor)
        super().start(ctx)
        self._mif_name = None
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        self._seen_cells.clear()
        self._last_player_pos = None
        self._last_automap_mtime_ns = None
        self._last_automap_size = 0
        self._active_cache_index = None
        self._notes = []
        self._hidden_door_ids = frozenset()
        self._menu_texture_indices = frozenset()
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
        self._ext_store = ctx.ext_store
        upd_key = (ctx.mif_name, ctx.player_tile_x, ctx.player_tile_y, self._mif_name, self._bitmap is None)
        if upd_key != self._diag_prev_update:
            self._diag_prev_update = upd_key
            _log.info('dungeon_diag[id=%x]: update ctx_mif=%r self_mif=%r player=(%s,%s) bitmap=%s', id(self), ctx.mif_name, self._mif_name, ctx.player_tile_x, ctx.player_tile_y, 'set' if self._bitmap is not None else 'None')
        if ctx.mif_name and (ctx.mif_name != self._mif_name or ctx.player_floor != self._floor):
            self._load_mif(ctx.mif_name, ctx.player_floor)
            self._mif_name = ctx.mif_name
            self._floor = ctx.player_floor
        if self._mif_name:
            self._location_key = f'{self._mif_name.upper()}#{self._floor}'
        else:
            self._location_key = None
        self._maybe_merge_automap(ctx)
        if ctx.player_tile_x is not None and ctx.player_tile_y is not None and (self._bitmap is not None):
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
        if self._ext_store is not None and self._location_key:
            self._discovered_hd = self._ext_store.discovered_cells(self._location_key)
        else:
            self._discovered_hd = frozenset()

    def get_canvas_data(self) -> CanvasData:
        return CanvasData(walkable=self._walkable, map1=self._map1, flor=self._flor, bitmap_grid=self._bitmap, notes=self._notes, player_x=int(self._player_x) if self._player_x is not None else None, player_y=int(self._player_y) if self._player_y is not None else None, player_angle_deg=self._angle, level_up_index=self._level_up_index, level_down_index=self._level_down_index, entrance_cells=(), is_wilderness=False, hidden_door_ids=self._hidden_door_ids, menu_texture_indices=self._menu_texture_indices, hidden_door_gating=True, discovered_hidden_door_cells=self._discovered_hd)

    def _note_hidden_door_if_any(self, ix: int, iy: int) -> None:
        if self._ext_store is None or not self._location_key:
            return
        m = self._map1
        if m is None or iy >= m.shape[0] or ix >= m.shape[1]:
            return
        if _is_hidden_door_cell(int(m[iy, ix])):
            self._ext_store.note_discovery(self._location_key, ix, iy)

    def reset_progress(self) -> None:
        if self._bitmap is None:
            self._bitmap = np.zeros((128, 128), dtype=np.uint8)
        self._bitmap[:] = 0
        self._seen_cells.clear()
        self._last_player_pos = None
        self._last_automap_mtime_ns = None
        self._last_automap_size = 0
        self._active_cache_index = None
        self._notes = []
        self._reset_retry_remaining = 20

    def poll_automap_file(self) -> bool:
        return False

    def _load_mif(self, mif_name: str, player_floor: int=0) -> None:
        try:
            mif = load_mif(mif_name, self._mif_dirs, player_floor=player_floor)
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
            return
        map1 = np.array(mif.map1, dtype=np.uint16).reshape(mif.height, mif.width)
        self._map1 = map1
        self._walkable = (map1 == 0) | (map1 & 61440 == 32768)
        if mif.flor and len(mif.flor) >= mif.height * mif.width:
            self._flor = np.array(mif.flor, dtype=np.uint16).reshape(mif.height, mif.width)
        else:
            self._flor = None
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
        self._bitmap = np.zeros((128, 128), dtype=np.uint8)
        self._seen_cells.clear()
        self._last_player_pos = None
        self._last_automap_mtime_ns = None
        self._last_automap_size = 0
        self._active_cache_index = None
        self._notes = []

    def _diag_log_skip(self, reason: str) -> None:
        if reason != self._diag_prev_merge_reason:
            self._diag_prev_merge_reason = reason
            _log.info('dungeon_diag[id=%x]: merge skip reason=%s', id(self), reason)

    def _maybe_merge_automap(self, ctx: MapContext) -> bool:
        save_dir = ctx.save_dir
        if not save_dir:
            self._diag_log_skip('no_save_dir')
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
        in_retry = self._reset_retry_remaining > 0
        same_stamp = self._last_automap_mtime_ns is not None and st_before.st_mtime_ns == self._last_automap_mtime_ns and (st_before.st_size == self._last_automap_size)
        if in_retry:
            self._reset_retry_remaining -= 1
        elif same_stamp:
            self._diag_log_skip('same_mtime')
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
        matched = find_active_cache(af, ctx.analyzer, ctx.anchor)
        cur_hash = None
        try:
            if ctx.analyzer is not None and ctx.anchor is not None:
                raw = ctx.analyzer.read_bytes(ctx.anchor + CURRENT_LEVEL_HASH_OFFSET, 4)
                cur_hash = int.from_bytes(raw, 'little')
        except (OSError, AttributeError):
            cur_hash = None
        if matched is not None and cur_hash is not None and (cur_hash != 0) and (matched.level_hash == cur_hash):
            active: AutomapCache | None = matched
            new_active_index = matched.index
        else:
            cached_index = self._active_cache_index
            if cached_index is not None and 0 <= cached_index < len(af.caches):
                active = af.caches[cached_index]
                new_active_index = cached_index
            else:
                active = matched
                new_active_index = matched.index if matched is not None else None
        if active is None or active.bitmap_grid is None:
            self._diag_log_skip('no_active_cache')
            return False
        self._bitmap[:] = active.bitmap_grid
        self._seen_cells = rebuild_seen_cells_from_bitmap(self._bitmap)
        self._notes = [(n.x, n.y, n.text) for n in active.valid_notes]
        self._last_player_pos = None
        self._last_automap_mtime_ns = st_before.st_mtime_ns
        self._last_automap_size = st_before.st_size
        self._active_cache_index = new_active_index
        nz = int((self._bitmap != 0).sum())
        _log.info('dungeon_diag[id=%x]: merge OK cache=#%s cur_hash=0x%08X bitmap_nz=%d', id(self), new_active_index, cur_hash if cur_hash else 0, nz)
        self._diag_prev_merge_reason = 'ok'
        return True
__all__ = ['DungeonMapSession']
