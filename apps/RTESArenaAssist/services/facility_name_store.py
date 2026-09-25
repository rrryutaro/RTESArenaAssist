from __future__ import annotations
import json
import logging
import os
_FILE_VERSION = 1
_log = logging.getLogger('facility_name_store')

def ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir as _dir
    return _dir()

def slot_filename(slot: int) -> str:
    return f'facility_names.0{int(slot)}'

def _key(location_name: str, x: int, y: int) -> tuple[str, int, int] | None:
    try:
        location = str(location_name).strip()
        if not location:
            return None
        return (location, int(x), int(y))
    except (TypeError, ValueError):
        return None

class FacilityNameStore:

    def __init__(self, ext_dir: str | None=None) -> None:
        self._ext_dir_override = ext_dir
        self._names: dict[tuple[str, int, int], str] = {}
        self._current_slot: int | None = None
        self._current_save_id: str | None = None

    def _ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self._ext_dir(), slot_filename(slot))

    def _read(self, slot: int) -> tuple[str | None, dict]:
        try:
            with open(self._slot_path(slot), encoding='utf-8') as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return (None, {})
        if not isinstance(obj, dict):
            return (None, {})
        names: dict[tuple[str, int, int], str] = {}
        raw_names = obj.get('names', [])
        if not isinstance(raw_names, list):
            return (obj.get('save_id'), names)
        for rec in raw_names:
            if not isinstance(rec, dict):
                continue
            key = _key(rec.get('location', ''), rec.get('x'), rec.get('y'))
            name = str(rec.get('name') or '').strip()
            if key is not None and name:
                names[key] = name
        return (obj.get('save_id'), names)

    def _write(self, slot: int, save_id: str | None) -> None:
        os.makedirs(self._ext_dir(), exist_ok=True)
        records = [{'location': loc, 'x': x, 'y': y, 'name': name} for (loc, x, y), name in sorted(self._names.items())]
        with open(self._slot_path(slot), 'w', encoding='utf-8') as f:
            json.dump({'version': _FILE_VERSION, 'save_id': save_id, 'names': records}, f, ensure_ascii=False, indent=2)

    def name_for(self, location_name: str, x: int, y: int) -> str | None:
        key = _key(location_name, x, y)
        return self._names.get(key) if key is not None else None

    def note_name(self, location_name: str, x: int, y: int, display_name: str) -> bool:
        key = _key(location_name, x, y)
        name = str(display_name or '').strip()
        if key is None or not name or self._names.get(key) == name:
            return False
        self._names[key] = name
        if self._current_slot is not None:
            try:
                self._write(self._current_slot, self._current_save_id)
            except OSError as exc:
                _log.warning('facility name cache write failed: %s', exc)
        return True

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

    def bind_slot(self, slot: int | None, save_id: str | None) -> None:
        if slot is None:
            self._current_slot = None
            self._current_save_id = None
            self._names = {}
            return
        if slot == self._current_slot and save_id == self._current_save_id:
            return
        file_save_id, names = self._read(slot)
        if save_id is not None and file_save_id is not None and (file_save_id != save_id):
            names = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._names = names

    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        self._write(slot, save_id)
        self._current_slot = slot
        self._current_save_id = save_id

    def reset_active(self) -> None:
        pass
_SHARED: FacilityNameStore | None = None

def get_store() -> FacilityNameStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = FacilityNameStore()
    return _SHARED
__all__ = ['FacilityNameStore', 'get_store', 'slot_filename']
