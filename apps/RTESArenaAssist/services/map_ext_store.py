from __future__ import annotations
import base64
import binascii
import json
import logging
import os
import numpy as np
from services.automap_file import pack_bitmap_2bit, unpack_bitmap_2bit
_log = logging.getLogger('map_ext_store')
_FILE_VERSION = 3
SECTION_HIDDEN_DOORS = 'hidden_doors'
SECTION_TREASURE_PILES = 'treasure_piles'
SECTION_WALL_PASSAGES = 'wall_passages'
_SECTIONS = (SECTION_HIDDEN_DOORS, SECTION_TREASURE_PILES, SECTION_WALL_PASSAGES)
REVEAL_KEY = 'reveal'
REVEAL_SHAPE = (128, 128)
_REVEAL_BYTES = REVEAL_SHAPE[0] * REVEAL_SHAPE[1] // 4
_Cells = dict

def ext_data_dir() -> str:
    from assist_settings import _settings_path
    if _settings_path:
        return os.path.join(os.path.dirname(_settings_path), 'ext_data')
    return os.path.join(os.path.expanduser('~'), 'RTESArenaAssist_ext_data')

def slot_filename(slot: int) -> str:
    return f'map_ext.0{int(slot)}'
_PAIRS_FILENAME = 'map_level_pairs.json'

def load_hash_floor_pairs() -> dict[str, dict[int, int]]:
    path = os.path.join(ext_data_dir(), _PAIRS_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    out: dict[str, dict[int, int]] = {}
    for mif, pairs in (data.get('pairs') or {}).items():
        if not isinstance(pairs, dict):
            continue
        m: dict[int, int] = {}
        for hex_hash, floor in pairs.items():
            try:
                m[int(str(hex_hash), 16)] = int(floor)
            except (TypeError, ValueError):
                continue
        if m:
            out[str(mif)] = m
    return out

def save_hash_floor_pairs(pairs: dict[str, dict[int, int]]) -> None:
    os.makedirs(ext_data_dir(), exist_ok=True)
    path = os.path.join(ext_data_dir(), _PAIRS_FILENAME)
    obj = {'version': 1, 'pairs': {mif: {f'{h:08X}': int(fl) for h, fl in m.items()} for mif, m in pairs.items()}}
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _loc_dict_to_sets(raw: dict) -> dict[str, set[tuple[int, int]]]:
    out: dict[str, set[tuple[int, int]]] = {}
    if not isinstance(raw, dict):
        return out
    for loc, cells in raw.items():
        s: set[tuple[int, int]] = set()
        if isinstance(cells, list):
            for c in cells:
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    try:
                        s.add((int(c[0]), int(c[1])))
                    except (TypeError, ValueError):
                        continue
        out[str(loc)] = s
    return out

def _loc_sets_to_dict(data: dict[str, set[tuple[int, int]]]) -> dict:
    return {loc: sorted([list(c) for c in cells]) for loc, cells in data.items() if cells}

def _empty_cells() -> dict:
    return {sec: {} for sec in _SECTIONS}

def _reveal_raw_to_grids(raw) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for loc, blob in raw.items():
        if not isinstance(blob, str):
            continue
        try:
            data = base64.b64decode(blob.encode('ascii'), validate=True)
        except (ValueError, binascii.Error):
            continue
        if len(data) != _REVEAL_BYTES:
            continue
        out[str(loc)] = unpack_bitmap_2bit(data, *REVEAL_SHAPE)
    return out

def _reveal_grids_to_raw(grids: dict) -> dict:
    out: dict = {}
    for loc, grid in grids.items():
        if grid is None or not int((grid != 0).sum()):
            continue
        packed = pack_bitmap_2bit(grid, *REVEAL_SHAPE)
        out[str(loc)] = base64.b64encode(packed).decode('ascii')
    return out

class MapExtStore:

    def __init__(self, ext_dir: str | None=None) -> None:
        self._ext_dir_override = ext_dir
        self._active: dict = _empty_cells()
        self._persist: dict = _empty_cells()
        self._active_reveal: dict = {}
        self._persist_reveal: dict = {}
        self._current_slot: int | None = None
        self._current_save_id: str | None = None

    def ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self.ext_dir(), slot_filename(slot))

    def _read_slot_file(self, slot: int) -> tuple[str | None, dict, dict]:
        path = self._slot_path(slot)
        try:
            with open(path, encoding='utf-8') as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return (None, _empty_cells(), {})
        if not isinstance(obj, dict):
            return (None, _empty_cells(), {})
        save_id = obj.get('save_id')
        data = {sec: _loc_dict_to_sets(obj.get(sec, {})) for sec in _SECTIONS}
        try:
            file_version = int(obj.get('version') or 1)
        except (TypeError, ValueError):
            file_version = 1
        if file_version < 3:
            data[SECTION_WALL_PASSAGES] = {}
        reveal = _reveal_raw_to_grids(obj.get(REVEAL_KEY, {}))
        return (save_id, data, reveal)

    def _write_slot_file(self, slot: int, save_id: str | None, data: dict, reveal: dict | None=None) -> None:
        os.makedirs(self.ext_dir(), exist_ok=True)
        obj: dict = {'version': _FILE_VERSION, 'save_id': save_id}
        for sec in _SECTIONS:
            obj[sec] = _loc_sets_to_dict(data.get(sec, {}))
        obj[REVEAL_KEY] = _reveal_grids_to_raw(reveal or {})
        path = self._slot_path(slot)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def bind_slot(self, slot: int | None, save_id: str | None) -> None:
        if slot is None:
            self._current_slot = None
            self._current_save_id = None
            self._persist = _empty_cells()
            self._persist_reveal = {}
            return
        if slot == self._current_slot and save_id == self._current_save_id:
            return
        file_save_id, data, reveal = self._read_slot_file(slot)
        if save_id is not None and file_save_id is not None and (file_save_id != save_id):
            data = _empty_cells()
            reveal = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = data
        self._persist_reveal = reveal

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

    def note_discovery(self, location_key: str, x: int, y: int, section: str=SECTION_HIDDEN_DOORS) -> bool:
        cell = (int(x), int(y))
        s = self._active.setdefault(section, {}).setdefault(location_key, set())
        already = cell in s or cell in self._persist.get(section, {}).get(location_key, set())
        s.add(cell)
        return not already

    def discovered_cells(self, location_key: str, section: str=SECTION_HIDDEN_DOORS) -> frozenset[tuple[int, int]]:
        out = set(self._persist.get(section, {}).get(location_key, set()))
        out |= self._active.get(section, {}).get(location_key, set())
        return frozenset(out)

    def reveal_grid(self, location_key: str):
        grid = self._active_reveal.get(location_key)
        if grid is None:
            grid = self._persist_reveal.get(location_key)
        return grid

    def reveal_grid_for_update(self, location_key: str):
        grid = self._active_reveal.get(location_key)
        if grid is None:
            base = self._persist_reveal.get(location_key)
            grid = base.copy() if base is not None else np.zeros(REVEAL_SHAPE, dtype=np.uint8)
            self._active_reveal[location_key] = grid
        return grid

    def replace_reveal(self, location_key: str, grid) -> None:
        target = self.reveal_grid_for_update(location_key)
        target[:] = np.asarray(grid, dtype=np.uint8)[:REVEAL_SHAPE[0], :REVEAL_SHAPE[1]]

    def migrate_location_key(self, old_key: str, new_key: str) -> bool:
        if not old_key or not new_key or old_key == new_key:
            return False
        moved = False
        for section in _SECTIONS:
            for layer in (self._active, self._persist):
                sec = layer.get(section)
                if not sec or old_key not in sec:
                    continue
                cells = sec.pop(old_key)
                if cells:
                    sec.setdefault(new_key, set()).update(cells)
                    moved = True
        for layer in (self._active_reveal, self._persist_reveal):
            if old_key not in layer:
                continue
            grid = layer.pop(old_key)
            if grid is None or not int((grid != 0).sum()):
                continue
            cur = layer.get(new_key)
            layer[new_key] = grid if cur is None else np.maximum(cur, grid)
            moved = True
        return moved

    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        merged = _empty_cells()
        for sec in _SECTIONS:
            for loc, cells in self._persist.get(sec, {}).items():
                merged[sec][loc] = set(cells)
            for loc, cells in self._active.get(sec, {}).items():
                merged[sec].setdefault(loc, set()).update(cells)
        merged_reveal: dict = {}
        for loc, grid in self._persist_reveal.items():
            merged_reveal[loc] = grid.copy()
        for loc, grid in self._active_reveal.items():
            merged_reveal[loc] = grid.copy()
        self._write_slot_file(slot, save_id, merged, merged_reveal)
        _log.warning('commit: slot=#%d save_id=%r reveal_nz=%s', slot, save_id, {loc: int((g != 0).sum()) for loc, g in merged_reveal.items()})
        self._active = _empty_cells()
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = merged
        self._persist_reveal = merged_reveal

    def reset_active(self) -> None:
        self._active = _empty_cells()
        self._active_reveal = {}

    def reset_slot(self, slot: int) -> None:
        path = self._slot_path(slot)
        try:
            os.remove(path)
        except OSError:
            pass
        if slot == self._current_slot:
            self._persist = _empty_cells()
            self._persist_reveal = {}
_SHARED: MapExtStore | None = None

def get_store() -> MapExtStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = MapExtStore()
    return _SHARED
__all__ = ['MapExtStore', 'ext_data_dir', 'slot_filename', 'get_store', 'SECTION_HIDDEN_DOORS', 'SECTION_TREASURE_PILES', 'SECTION_WALL_PASSAGES', 'REVEAL_KEY', 'REVEAL_SHAPE']
