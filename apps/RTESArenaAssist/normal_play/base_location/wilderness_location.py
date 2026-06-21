from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from common_draw.automap_canvas import CanvasData
from services.arena_location_utils import get_wilderness_seed
from services.mif_loader import DEFAULT_INF_DIR, parse_inf_menu_texture_map
from services.wild_block_lists import get_block_lists, get_cache_source
from services.wild_flats import extract_flat_marks, get_wild_flat_category_map
from services.wild_chunk_tracker import WildChunkTracker
from services.wild_voxel_assembler import (
    CITY_ORIGIN_CHUNK_X, CITY_ORIGIN_CHUNK_Y,
    WILD_HEIGHT, WILD_WIDTH,
    build_wild_voxel_grid,
)

from normal_play.map.base import MapContext, MapSessionBase
from normal_play.base_location.base_location_view import FieldEntranceContext

_log = logging.getLogger("base_location.wilderness")


_CHUNK = 64
_HALF_CHUNK = _CHUNK // 2
_N_CHUNKS = 3
_GRID_SIZE = _N_CHUNKS * _CHUNK
_RT_MAX_DISPLAY = 2 * _CHUNK - 1
_ROUNDTRIP_TOL = 8
_WILD_ORIGIN_MARGIN = _CHUNK

_PLAYERDATA_WILD_OFF = 0x600
_PLAYERDATA_WILD_LEN = 0x61A - 0x600

_WILD_GAME_MENU_IDS = frozenset({1, 5, 8, 9})
_WILD_EXTENDED_MENU_IDS = frozenset({2, 3, 4, 6, 7})
_WILD_INF_CANDIDATES = ("TWN.INF", "DWN.INF", "MWN.INF")
_WILD_MENU_MAP_FALLBACK = {
    0: 7, 1: 8, 2: 9, 3: 10, 4: 11, 5: 13, 6: 45, 7: 46, 8: 50, 9: 51,
}
_WILD_ENTERABLE_MENU_IDS = frozenset({1, 2, 3, 4, 5, 8, 9})
_MENU_LABELS = {1: "crypt", 2: "house", 3: "tavern", 4: "temple",
                5: "tower", 8: "dungeon", 9: "dungeon"}
_wild_menu_map_cache: Optional[dict[int, int]] = None
_wild_menu_tex_sets: Optional[tuple[frozenset[int], frozenset[int]]] = None


def _get_wild_menu_map() -> dict[int, int]:
    global _wild_menu_map_cache
    if _wild_menu_map_cache is not None:
        return _wild_menu_map_cache
    menu_map: dict[int, int] = {}
    for name in _WILD_INF_CANDIDATES:
        menu_map = parse_inf_menu_texture_map(DEFAULT_INF_DIR / name)
        if menu_map:
            break
    if not menu_map:
        menu_map = dict(_WILD_MENU_MAP_FALLBACK)
    _wild_menu_map_cache = menu_map
    return menu_map


def _wild_texture_to_menu_id() -> dict[int, int]:
    return {tex: mid for mid, tex in _get_wild_menu_map().items()}


def _wild_menu_texture_sets() -> tuple[frozenset[int], frozenset[int]]:
    global _wild_menu_tex_sets
    if _wild_menu_tex_sets is not None:
        return _wild_menu_tex_sets
    menu_map = _get_wild_menu_map()
    game = frozenset(menu_map[m] for m in _WILD_GAME_MENU_IDS if m in menu_map)
    extended = game | frozenset(
        menu_map[m] for m in _WILD_EXTENDED_MENU_IDS if m in menu_map)
    _wild_menu_tex_sets = (game, extended)
    return _wild_menu_tex_sets

_C3_ENTRY_CANDIDATES = [
    (0xA902, "a902"), (0xA900, "a900"), (0xA904, "a904"), (0xA908, "a908"),
    (0xA880, "a880"), (0xA84E, "a84e"), (0xA850, "a850"), (0xA852, "a852"),
    (0xA858, "a858"),
]


class WildernessMapSession(MapSessionBase):

    def __init__(self) -> None:
        super().__init__()
        self._wild_seed: Optional[int] = None
        self._origin_chunk: Optional[tuple[int, int]] = None
        self._walkable: Optional[np.ndarray] = None
        self._map1:     Optional[np.ndarray] = None
        self._flor:     Optional[np.ndarray] = None
        self._bitmap:   Optional[np.ndarray] = None
        self._chunk_tracker = WildChunkTracker()
        self._center_origin: Optional[tuple[int, int]] = None
        self._live_wild_blocks: Optional[tuple[int, ...]] = None
        self._live_origin: Optional[tuple[int, int]] = None
        self._built_live_origin: Optional[tuple[int, int]] = None
        self._built_live_blocks: Optional[tuple[int, ...]] = None
        self._n_chunks: int = _N_CHUNKS
        self._grid_size: int = _GRID_SIZE
        self._place_text: Optional[str] = None
        self._player_x: Optional[float] = None
        self._player_y: Optional[float] = None
        self._angle:    Optional[float] = None
        self._compact_view: bool = False
        self._distinguish_road: bool = True
        self._show_edge: bool = True
        self._distinguish_edge: bool = True
        self._show_crops: bool = True
        self._show_all_entrances: bool = True
        self._show_static_flats: bool = True
        self._entrance_cells: tuple[tuple[int, int], ...] = ()
        self._entrance_key: Optional[tuple[int, bool]] = None
        self._flat_marks: tuple[tuple[int, int, str], ...] = ()
        self._flat_marks_key: Optional[int] = None
        self._edge_marks: tuple[tuple[int, int, str], ...] = ()
        self._edge_marks_key: Optional[int] = None
        self._crop_marks: tuple[tuple[int, int, str], ...] = ()
        self._crop_marks_key: Optional[int] = None
        self._field_entrance_ctx: Optional[FieldEntranceContext] = None
        self._enterable_cells: tuple[tuple[int, int, int], ...] = ()
        self._enterable_key: Optional[int] = None
        self._logged_entrance_mif: Optional[str] = None
        self._logged_temple_name: Optional[str] = None
        self._last_logged_origin: Optional[tuple[int, int]] = None
        self._seed_pending: bool = False
        self._last_rt: Optional[tuple[int, int]] = None
        self._last_wild_seed: Optional[int] = None


    def start(self, ctx: MapContext) -> None:
        super().start(ctx)
        self._wild_seed = None
        self._origin_chunk = None
        self._walkable = None
        self._map1 = None
        self._flor = None
        self._bitmap = None
        self._live_wild_blocks = None
        self._live_origin = None
        self._seed_pending = True

    def stop(self, ctx: MapContext) -> None:
        super().stop(ctx)

    def update(self, ctx: MapContext) -> None:
        self._place_text = ctx.place_text
        self._player_x = ctx.player_tile_x
        self._player_y = ctx.player_tile_y
        self._angle = ctx.angle_deg
        self._compact_view = ctx.wilderness_compact_view
        self._distinguish_road = ctx.wild_distinguish_road
        self._show_edge = ctx.wild_show_edge
        self._distinguish_edge = ctx.wild_distinguish_edge
        self._show_crops = ctx.wild_show_crops
        self._show_all_entrances = ctx.wild_show_all_entrances
        self._show_static_flats = ctx.wild_show_static_flats

        if not ctx.location_name:
            return
        wild_seed = get_wilderness_seed(ctx.location_name)
        if wild_seed == 0:
            _log.warning(
                "wild: location_name='%s' is too short for wildSeed",
                ctx.location_name)
            return

        if ctx.player_tile_x is not None and ctx.player_tile_y is not None:
            ws = self._read_wild_state(ctx, wild_seed)
            if ws is not None:
                rt_x, rt_z, bx, by, wild_blocks = ws
                self._center_origin = (bx, by)
                self._live_wild_blocks = wild_blocks
                self._live_origin = (bx, by)
                self._player_x = rt_x
                self._player_y = rt_z
                if (self._chunk_tracker.chunk_x,
                        self._chunk_tracker.chunk_y) != (bx, by):
                    self._chunk_tracker.reset(bx, by)
                self._seed_pending = False
            else:
                self._live_wild_blocks = None
                self._live_origin = None
                rt_x = int(ctx.player_tile_x)
                rt_z = int(ctx.player_tile_y)
                if self._seed_pending:
                    self._seed_pending = False
                    same_field = (self._last_wild_seed is not None
                                  and self._last_wild_seed == wild_seed)
                    near = (self._last_rt is not None
                            and abs(rt_x - self._last_rt[0]) <= _ROUNDTRIP_TOL
                            and abs(rt_z - self._last_rt[1]) <= _ROUNDTRIP_TOL)
                    if not (same_field and near):
                        seed_x = (CITY_ORIGIN_CHUNK_X if rt_x >= _HALF_CHUNK
                                  else CITY_ORIGIN_CHUNK_X - 1)
                        seed_y = (CITY_ORIGIN_CHUNK_Y if rt_z >= _HALF_CHUNK
                                  else CITY_ORIGIN_CHUNK_Y - 1)
                        self._chunk_tracker.reset(seed_x, seed_y)
                self._chunk_tracker.update(rt_x, rt_z)
                self._center_origin = (self._chunk_tracker.chunk_x,
                                       self._chunk_tracker.chunk_y)
            self._last_rt = (rt_x, rt_z)
            origin, n_chunks, live_origin, live_blocks = \
                self._compute_display_plan(rt_x, rt_z)
            if origin != self._last_logged_origin:
                self._last_logged_origin = origin
                self._log_c3_entry_coords(ctx, rt_x, rt_z, origin)
        elif self._origin_chunk is not None:
            origin = self._origin_chunk
            n_chunks = self._n_chunks
            live_origin = self._built_live_origin
            live_blocks = self._built_live_blocks
        else:
            origin = (CITY_ORIGIN_CHUNK_X - 1, CITY_ORIGIN_CHUNK_Y - 1)
            n_chunks = _N_CHUNKS
            live_origin = None
            live_blocks = None

        if not (wild_seed != self._wild_seed
                or origin != self._origin_chunk
                or n_chunks != self._n_chunks
                or live_origin != self._built_live_origin
                or live_blocks != self._built_live_blocks
                or self._walkable is None):
            return

        blocks = get_block_lists(ctx.analyzer)
        try:
            grid = build_wild_voxel_grid(
                wild_seed=wild_seed,
                blocks=blocks,
                player_voxel_x=0,
                player_voxel_y=0,
                origin_chunk=origin,
                flip_x=False,
                n_chunks=n_chunks,
                live_origin_chunk=live_origin,
                live_wild_blocks=live_blocks,
            )
        except Exception:  # noqa: BLE001
            _log.exception(
                "build_wild_voxel_grid failed (loc=%s seed=0x%08X)",
                ctx.location_name, wild_seed)
            return

        self._map1 = grid.map1
        self._flor = grid.flor
        self._walkable = (grid.map1 == 0) | (
            (grid.map1 & 0xF000) == 0x8000)
        self._bitmap = np.full((grid.depth, grid.width), 3, dtype=np.uint8)
        self._wild_seed = wild_seed
        self._last_wild_seed = wild_seed
        self._origin_chunk = origin
        self._n_chunks = n_chunks
        self._grid_size = n_chunks * _CHUNK
        self._built_live_origin = live_origin
        self._built_live_blocks = live_blocks

        src = get_cache_source() or "unset"
        _log.info(
            "wild: grid built loc=%s seed=0x%08X origin=(%d,%d) "
            "chunks=%s block_lists=%s normal_count=%d "
            "rt=(%s,%s) chunk_track=(%d,%d)",
            ctx.location_name, wild_seed, origin[0], origin[1],
            grid.chunk_ids, src, len(blocks.normal),
            ctx.player_tile_x, ctx.player_tile_y,
            self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)

    def _read_wild_state(self, ctx: MapContext, wild_seed: int
                         ) -> Optional[tuple[int, int, int, int,
                                             tuple[int, ...]]]:
        if ctx.analyzer is None or ctx.anchor is None:
            return None
        try:
            raw = ctx.analyzer.read_bytes(
                ctx.anchor + _PLAYERDATA_WILD_OFF, _PLAYERDATA_WILD_LEN)
        except Exception:  # noqa: BLE001
            return None
        if len(raw) < _PLAYERDATA_WILD_LEN:
            return None
        wild_x = int.from_bytes(raw[0:2], "little")
        wild_y = int.from_bytes(raw[2:4], "little")
        wild_blocks = tuple(raw[4:8])
        block_x = int.from_bytes(raw[8:10], "little", signed=True)
        block_y = int.from_bytes(raw[10:12], "little", signed=True)
        seed = int.from_bytes(raw[22:26], "little")
        if seed != wild_seed:
            return None
        rt_x = wild_x // 128
        rt_z = wild_y // 128
        if not (0 <= rt_x <= _RT_MAX_DISPLAY and 0 <= rt_z <= _RT_MAX_DISPLAY):
            return None
        lo = -_WILD_ORIGIN_MARGIN
        hi = WILD_WIDTH - 1 + _WILD_ORIGIN_MARGIN
        if not (lo <= block_x <= hi and lo <= block_y <= hi):
            return None
        return rt_x, rt_z, block_x, block_y, wild_blocks

    def _compute_origin(self, rt_x: int, rt_z: int) -> tuple[int, int]:
        o = self._center_origin or (
            self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)
        actual_cx = o[0] + (1 if rt_x >= _CHUNK else 0)
        actual_cy = o[1] + (1 if rt_z >= _CHUNK else 0)
        return actual_cx - 1, actual_cy - 1

    def _compute_display_plan(self, rt_x: int, rt_z: int
                              ) -> tuple[tuple[int, int], int,
                                         Optional[tuple[int, int]],
                                         Optional[tuple[int, ...]]]:
        centered = self._compute_origin(rt_x, rt_z)
        live_blocks = self._live_wild_blocks
        live_origin = self._live_origin
        if live_blocks is None or live_origin is None:
            gx = max(0, min(WILD_WIDTH - _N_CHUNKS, centered[0]))
            gy = max(0, min(WILD_HEIGHT - _N_CHUNKS, centered[1]))
            return (gx, gy), _N_CHUNKS, None, None
        gx, gy = centered
        fully_outside = (
            gx + _N_CHUNKS - 1 < 0 or gx > WILD_WIDTH - 1
            or gy + _N_CHUNKS - 1 < 0 or gy > WILD_HEIGHT - 1)
        if fully_outside:
            return live_origin, 2, live_origin, live_blocks
        return (gx, gy), _N_CHUNKS, live_origin, live_blocks

    def _wild_entrance_cells(self) -> tuple[tuple[int, int], ...]:
        if self._map1 is None:
            return ()
        key = (id(self._map1), self._show_all_entrances)
        if key != self._entrance_key:
            from services.city_voxel_assembler import detect_menu_cells
            game, extended = _wild_menu_texture_sets()
            tex_set = extended if self._show_all_entrances else game
            self._entrance_cells = tuple(
                detect_menu_cells(self._map1, set(tex_set)))
            self._entrance_key = key
        return self._entrance_cells

    def _wild_flat_marks(self) -> tuple[tuple[int, int, str], ...]:
        if self._map1 is None or not self._show_static_flats:
            return ()
        key = id(self._map1)
        if key != self._flat_marks_key:
            cat_map = get_wild_flat_category_map()
            self._flat_marks = extract_flat_marks(self._map1, cat_map)
            self._flat_marks_key = key
        return self._flat_marks

    def _wild_edge_marks(self) -> tuple[tuple[int, int, str], ...]:
        if (self._map1 is None or not self._show_edge
                or not self._distinguish_edge):
            return ()
        key = id(self._map1)
        if key != self._edge_marks_key:
            from services.wild_edges import (
                get_wild_edge_category_map, extract_edge_marks)
            cat_map = get_wild_edge_category_map()
            self._edge_marks = extract_edge_marks(self._map1, cat_map)
            self._edge_marks_key = key
        return self._edge_marks

    def _wild_crop_marks(self) -> tuple[tuple[int, int, str], ...]:
        if self._map1 is None or not self._show_crops:
            return ()
        key = id(self._map1)
        if key != self._crop_marks_key:
            from services.wild_edges import (
                get_wild_crop_category_map, extract_crop_marks)
            cat_map = get_wild_crop_category_map()
            self._crop_marks = extract_crop_marks(self._map1, cat_map)
            self._crop_marks_key = key
        return self._crop_marks

    def _enterable_menu_cells(self) -> tuple[tuple[int, int, int], ...]:
        if self._map1 is None:
            return ()
        key = id(self._map1)
        if key != self._enterable_key:
            tex2menu = _wild_texture_to_menu_id()
            enter_tex = {tex: mid for tex, mid in tex2menu.items()
                         if mid in _WILD_ENTERABLE_MENU_IDS}
            cells: list[tuple[int, int, int]] = []
            m1 = self._map1
            h, w = m1.shape
            for z in range(h):
                for x in range(w):
                    v = int(m1[z, x])
                    if v == 0:
                        continue
                    high = (v >> 12) & 0x0F
                    most = (v >> 8) & 0xFF
                    least = v & 0xFF
                    if high == 0xA:
                        tex = (least & 0x3F) - 1
                    elif most == least and most != 0:
                        tex = most - 1
                    else:
                        continue
                    mid = enter_tex.get(tex)
                    if mid is not None:
                        cells.append((x, z, mid))
            self._enterable_cells = tuple(cells)
            self._enterable_key = key
        return self._enterable_cells

    def _resolve_field_door_mif(self, abs_x: int, abs_y: int,
                                menu_id: int) -> Optional[str]:
        try:
            from services.arena_level_utils import get_door_voxel_mif_name
            from services.arena_voxel_utils import MapType
            from services.arena_types import ArenaCityType
            return get_door_voxel_mif_name(
                abs_x, abs_y, menu_id, 0, False,
                ArenaCityType.CITY_STATE, MapType.WILDERNESS)
        except Exception:  # noqa: BLE001
            _log.exception("field door mif resolve failed")
            return None

    def _update_field_entrance_hint(self, local_x: Optional[int],
                                    local_y: Optional[int]) -> None:
        if local_x is None or local_y is None or self._origin_chunk is None:
            return
        nearest = None
        best_d = 99
        for cx, cz, mid in self._enterable_menu_cells():
            d = max(abs(cx - local_x), abs(cz - local_y))
            if d <= 4 and d < best_d:
                best_d = d
                nearest = (cx, cz, mid)
        if nearest is None:
            self._field_entrance_ctx = None
            self._logged_entrance_mif = None
            return
        cx, cz, mid = nearest
        abs_x = self._origin_chunk[0] * _CHUNK + cx
        abs_y = self._origin_chunk[1] * _CHUNK + cz
        mif = self._resolve_field_door_mif(abs_x, abs_y, mid)
        name_en, name_ja = self._resolve_field_facility_name(abs_x, abs_y, mid)
        self._field_entrance_ctx = FieldEntranceContext(
            interior_mif_name=mif,
            menu_label=_MENU_LABELS.get(mid, str(mid)),
            name_en=name_en, name_ja=name_ja)
        if mif != self._logged_entrance_mif:
            self._logged_entrance_mif = mif
            self._log_field_entrance_calibration(abs_x, abs_y, cx, cz, mid, mif)

    def _resolve_field_facility_name(self, abs_x: int, abs_y: int,
                                     menu_id: int) -> tuple[str, Optional[str]]:
        we, sn = abs_x // _CHUNK, abs_y // _CHUNK
        try:
            if menu_id == 3:
                from services.building_name_generator import (
                    generate_wild_tavern_name_opentes,
                    make_wild_chunk_name_seed)
                from services.dynamic_translation import translate_tavern
                tav = generate_wild_tavern_name_opentes(we, sn)
                tr = translate_tavern(tav)
                if (tr.en or "") != getattr(self, "_logged_tavern_name", None):
                    self._logged_tavern_name = tr.en or ""
                    _log.warning(
                        "FIELD_TAVERN_NAME[OpenTES] block(WE=%d,SN=%d) "
                        "seed=0x%08X prefix=%d suf=%d en=%r ja=%r",
                        we, sn, make_wild_chunk_name_seed(we, sn),
                        tav.prefix_index, tav.suffix_index, tr.en, tr.ja)
                return (tr.en or "", tr.ja)
            if menu_id == 4:
                wild_seed = self._wild_seed or 0
                from services.building_name_generator import (
                    generate_wild_temple_name_calibrated,
                    make_wild_temple_name_seed_calibrated)
                from services.dynamic_translation import translate_temple
                tname = generate_wild_temple_name_calibrated(we, sn, wild_seed)
                tr = translate_temple(tname)
                if (tr.en or "") != getattr(self, "_logged_temple_name", None):
                    self._logged_temple_name = tr.en or ""
                    _log.warning(
                        "FIELD_TEMPLE_NAME[calibrated] block(WE=%d,SN=%d) "
                        "wildSeed=0x%08X seed=0x%08X model=%d suf=%d en=%r ja=%r",
                        we, sn, wild_seed,
                        make_wild_temple_name_seed_calibrated(we, sn, wild_seed),
                        tname.model, tname.suffix_index, tr.en, tr.ja)
                return (tr.en or "", tr.ja)
            return ("", None)
        except Exception:  # noqa: BLE001
            _log.exception("field facility name resolve failed")
            return ("", None)

    def _log_field_entrance_calibration(self, abs_x: int, abs_y: int,
                                        cx: int, cz: int, menu_id: int,
                                        mif: Optional[str]) -> None:
        from services.arena_level_utils import get_door_voxel_mif_name
        from services.arena_voxel_utils import MapType
        from services.arena_types import ArenaCityType
        cand = {}
        for name, (x, y) in {
            "noswap(abs_x,abs_y)=OTA採用": (abs_x, abs_y),
            "swap(abs_y,abs_x)": (abs_y, abs_x),
        }.items():
            try:
                cand[name] = get_door_voxel_mif_name(
                    x, y, menu_id, 0, False,
                    ArenaCityType.CITY_STATE, MapType.WILDERNESS)
            except Exception:  # noqa: BLE001
                cand[name] = "<err>"
        _log.warning(
            "FIELD_ENTRANCE menu=%s(id=%d) cell=(%d,%d) abs=(%d,%d) "
            "mif=%s || cand: %s",
            _MENU_LABELS.get(menu_id, str(menu_id)), menu_id, cx, cz,
            abs_x, abs_y, mif,
            " / ".join(f"{k}={v}" for k, v in cand.items()))

    def field_entrance_hint(self) -> Optional[FieldEntranceContext]:
        return self._field_entrance_ctx

    def _log_c3_entry_coords(self, ctx: MapContext,
                             rt_x: int, rt_z: int,
                             origin: tuple[int, int]) -> None:
        o_x = self._chunk_tracker.chunk_x
        o_y = self._chunk_tracker.chunk_y
        ac_x = o_x + (1 if rt_x >= _CHUNK else 0)
        ac_y = o_y + (1 if rt_z >= _CHUNK else 0)
        mk_x = (o_x * _CHUNK + rt_x) - origin[0] * _CHUNK
        mk_y = (o_y * _CHUNK + rt_z) - origin[1] * _CHUNK
        cand = ""
        if ctx.analyzer is not None and ctx.anchor is not None:
            try:
                parts = []
                for off, name in _C3_ENTRY_CANDIDATES:
                    raw = ctx.analyzer.read_bytes(ctx.anchor + off, 4)
                    u16 = int.from_bytes(raw[:2], "little")
                    u32 = int.from_bytes(raw, "little")
                    parts.append("%s@0x%04X=u16:%d/u32:%d" % (name, off, u16, u32))
                cand = " | ".join(parts)
            except Exception:  # noqa: BLE001
                cand = "<cand read error>"
        _log.warning(
            "C3_ENTRY loc=%s rt=(%d,%d) hi=(%d,%d) center_origin=(%d,%d) "
            "actual_chunk=(%d,%d) voxel=(%d,%d) grid_origin=(%d,%d) "
            "marker=(%d,%d) || %s",
            ctx.location_name, rt_x, rt_z,
            (rt_x >> 8) & 0xFF, (rt_z >> 8) & 0xFF,
            o_x, o_y, ac_x, ac_y, rt_x % _CHUNK, rt_z % _CHUNK,
            origin[0], origin[1], mk_x, mk_y, cand)

    def get_canvas_data(self) -> CanvasData:
        local_x: Optional[int] = None
        local_y: Optional[int] = None
        if (self._player_x is not None and self._player_y is not None
                and self._origin_chunk is not None):
            rt_x = int(self._player_x)
            rt_z = int(self._player_y)
            o = self._center_origin or (
                self._chunk_tracker.chunk_x, self._chunk_tracker.chunk_y)
            if (0 <= rt_x <= _RT_MAX_DISPLAY
                    and 0 <= rt_z <= _RT_MAX_DISPLAY):
                abs_x = o[0] * _CHUNK + rt_x
                abs_y = o[1] * _CHUNK + rt_z
                lx = abs_x - self._origin_chunk[0] * _CHUNK
                ly = abs_y - self._origin_chunk[1] * _CHUNK
                if 0 <= lx < self._grid_size and 0 <= ly < self._grid_size:
                    local_x = lx
                    local_y = ly

        self._update_field_entrance_hint(local_x, local_y)

        return CanvasData(
            walkable=self._walkable,
            map1=self._map1,
            flor=self._flor,
            bitmap_grid=self._bitmap,
            notes=[],
            player_x=local_x,
            player_y=local_y,
            player_angle_deg=self._angle,
            level_up_index=None,
            level_down_index=None,
            entrance_cells=self._wild_entrance_cells(),
            flat_marks=self._wild_flat_marks(),
            edge_marks=self._wild_edge_marks(),
            crop_marks=self._wild_crop_marks(),
            wild_show_crops=self._show_crops,
            is_wilderness=True,
            chunk_origin=self._origin_chunk,
            wilderness_compact_view=self._compact_view,
            wild_distinguish_road=self._distinguish_road,
            wild_show_edge=self._show_edge,
            hidden_door_ids=frozenset(),
            menu_texture_indices=frozenset(),
        )

    def reset_progress(self) -> None:
        if self._walkable is not None:
            self._bitmap = np.full(self._walkable.shape, 3, dtype=np.uint8)


__all__ = ["WildernessMapSession"]
