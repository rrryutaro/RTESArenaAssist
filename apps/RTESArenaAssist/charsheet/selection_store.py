from __future__ import annotations
import json
import os
_FILE_VERSION = 1
KIND_POTIONS = 'potions'
KIND_MAGIC_ITEMS = 'magic_items'
KINDS: tuple[str, ...] = (KIND_POTIONS, KIND_MAGIC_ITEMS)

def ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir as _dir
    return _dir()

def slot_filename(slot: int) -> str:
    return f'charsheet_ext.0{int(slot)}'

def _clean_names(raw) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[str] = []
    for value in raw:
        name = value.strip() if isinstance(value, str) else ''
        if name and name not in out:
            out.append(name)
    return tuple(out)

class SheetSelectionStore:

    def __init__(self, ext_dir: str | None=None) -> None:
        self._ext_dir_override = ext_dir
        self._active: dict[str, tuple[str, ...]] = {}
        self._persist: dict[str, tuple[str, ...]] = {}
        self._current_slot: int | None = None
        self._current_save_id: str | None = None

    def _ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self._ext_dir(), slot_filename(slot))

    def _read_slot_file(self, slot: int) -> tuple[str | None, dict]:
        try:
            with open(self._slot_path(slot), encoding='utf-8') as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return (None, {})
        if not isinstance(obj, dict):
            return (None, {})
        data = {kind: _clean_names(obj.get(kind)) for kind in KINDS if kind in obj}
        return (obj.get('save_id'), data)

    def _write_slot_file(self, slot: int, save_id: str | None, data: dict) -> None:
        os.makedirs(self._ext_dir(), exist_ok=True)
        obj = {'version': _FILE_VERSION, 'save_id': save_id}
        for kind in KINDS:
            obj[kind] = list(data.get(kind, ()))
        with open(self._slot_path(slot), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def get(self, kind: str) -> tuple[str, ...]:
        if kind in self._active:
            return self._active[kind]
        return self._persist.get(kind, ())

    def set(self, kind: str, names) -> None:
        if kind not in KINDS:
            raise ValueError(kind)
        self._active[kind] = _clean_names(list(names))

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

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

    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        merged = dict(self._persist)
        merged.update(self._active)
        self._write_slot_file(slot, save_id, merged)
        self._active = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = merged

    def reset_active(self) -> None:
        self._active = {}
_SHARED: SheetSelectionStore | None = None

def get_store() -> SheetSelectionStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = SheetSelectionStore()
    return _SHARED
__all__ = ['SheetSelectionStore', 'get_store', 'ext_data_dir', 'slot_filename', 'KIND_POTIONS', 'KIND_MAGIC_ITEMS', 'KINDS']
