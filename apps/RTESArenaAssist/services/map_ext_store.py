from __future__ import annotations
import json
import os
_FILE_VERSION = 1
_SECTION = 'hidden_doors'

def ext_data_dir() -> str:
    from assist_settings import _settings_path
    if _settings_path:
        return os.path.join(os.path.dirname(_settings_path), 'ext_data')
    return os.path.join(os.path.expanduser('~'), 'RTESArenaAssist_ext_data')

def slot_filename(slot: int) -> str:
    return f'map_ext.0{int(slot)}'

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

class MapExtStore:

    def __init__(self, ext_dir: str | None=None) -> None:
        self._ext_dir_override = ext_dir
        self._active: dict[str, set[tuple[int, int]]] = {}
        self._persist: dict[str, set[tuple[int, int]]] = {}
        self._current_slot: int | None = None
        self._current_save_id: str | None = None

    def ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self.ext_dir(), slot_filename(slot))

    def _read_slot_file(self, slot: int) -> tuple[str | None, dict[str, set[tuple[int, int]]]]:
        path = self._slot_path(slot)
        try:
            with open(path, encoding='utf-8') as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return (None, {})
        save_id = obj.get('save_id') if isinstance(obj, dict) else None
        raw = obj.get(_SECTION, {}) if isinstance(obj, dict) else {}
        return (save_id, _loc_dict_to_sets(raw))

    def _write_slot_file(self, slot: int, save_id: str | None, data: dict[str, set[tuple[int, int]]]) -> None:
        os.makedirs(self.ext_dir(), exist_ok=True)
        obj = {'version': _FILE_VERSION, 'save_id': save_id, _SECTION: _loc_sets_to_dict(data)}
        path = self._slot_path(slot)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def bind_slot(self, slot: int | None, save_id: str | None) -> None:
        if slot is None:
            self._current_slot = None
            self._current_save_id = None
            self._persist = {}
            return
        if slot == self._current_slot and save_id == self._current_save_id:
            return
        file_save_id, data = self._read_slot_file(slot)
        if save_id is not None and file_save_id is not None and (file_save_id != save_id):
            data = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = data

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

    def note_discovery(self, location_key: str, x: int, y: int) -> bool:
        cell = (int(x), int(y))
        s = self._active.setdefault(location_key, set())
        already = cell in s or cell in self._persist.get(location_key, set())
        s.add(cell)
        return not already

    def discovered_cells(self, location_key: str) -> frozenset[tuple[int, int]]:
        out = set(self._persist.get(location_key, set()))
        out |= self._active.get(location_key, set())
        return frozenset(out)

    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        merged: dict[str, set[tuple[int, int]]] = {loc: set(cells) for loc, cells in self._persist.items()}
        for loc, cells in self._active.items():
            merged.setdefault(loc, set()).update(cells)
        self._write_slot_file(slot, save_id, merged)
        self._active.clear()
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = merged

    def reset_active(self) -> None:
        self._active.clear()

    def reset_slot(self, slot: int) -> None:
        path = self._slot_path(slot)
        try:
            os.remove(path)
        except OSError:
            pass
        if slot == self._current_slot:
            self._persist = {}
_SHARED: MapExtStore | None = None

def get_store() -> MapExtStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = MapExtStore()
    return _SHARED
__all__ = ['MapExtStore', 'ext_data_dir', 'slot_filename', 'get_store']
