from __future__ import annotations
import json
import os
_FILE_VERSION = 1

def ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir as _dir
    return _dir()

def slot_filename(slot: int) -> str:
    return f'riddle_ext.0{int(slot)}'

def _key(inf, idx) -> tuple[str, int] | None:
    try:
        return (str(inf).upper(), int(idx))
    except (TypeError, ValueError):
        return None

def _clean(rec: dict) -> dict | None:
    if not isinstance(rec, dict):
        return None
    inf = rec.get('inf')
    if not isinstance(inf, str) or not inf.strip():
        return None
    k = _key(inf, rec.get('idx'))
    if k is None:
        return None
    return {'inf': inf, 'idx': k[1], 'place': str(rec.get('place') or ''), 'answers': [str(a) for a in rec.get('answers') or [] if str(a).strip()]}

def _fill_missing(dst: dict, src: dict) -> bool:
    changed = False
    if src.get('place') and (not dst.get('place')):
        dst['place'] = src['place']
        changed = True
    if src.get('answers') and (not dst.get('answers')):
        dst['answers'] = list(src['answers'])
        changed = True
    return changed

class RiddleStore:

    def __init__(self, ext_dir: str | None=None) -> None:
        self._ext_dir_override = ext_dir
        self._active: dict[tuple[str, int], dict] = {}
        self._persist: dict[tuple[str, int], dict] = {}
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
        out: dict[tuple[str, int], dict] = {}
        raw = obj.get('seen')
        if isinstance(raw, list):
            for rec in raw:
                c = _clean(rec)
                if c is not None:
                    out[_key(c['inf'], c['idx'])] = c
        return (obj.get('save_id'), out)

    def _write_slot_file(self, slot: int, save_id: str | None, data: dict) -> None:
        os.makedirs(self._ext_dir(), exist_ok=True)
        obj = {'version': _FILE_VERSION, 'save_id': save_id, 'seen': list(data.values())}
        with open(self._slot_path(slot), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def note_seen(self, inf: str, idx: int, place: str='', answers: list | None=None) -> bool:
        k = _key(inf, idx)
        if k is None or not inf:
            return False
        incoming = {'inf': str(inf), 'idx': k[1], 'place': str(place or ''), 'answers': [str(a) for a in answers or [] if str(a).strip()]}
        cur = self._active.get(k)
        if cur is None:
            base = self._persist.get(k)
            cur = dict(base) if base else {'inf': incoming['inf'], 'idx': k[1], 'place': '', 'answers': []}
            changed = _fill_missing(cur, incoming)
            if base is not None and (not changed):
                return False
            self._active[k] = cur
            return True
        return _fill_missing(cur, incoming)

    def seen_entries(self) -> list[dict]:
        out: dict[tuple[str, int], dict] = {}
        for src in (self._persist, self._active):
            for k, rec in src.items():
                if k in out:
                    _fill_missing(out[k], rec)
                else:
                    out[k] = dict(rec)
        return list(out.values())

    def is_seen(self, inf: str, idx: int) -> bool:
        k = _key(inf, idx)
        return k is not None and (k in self._persist or k in self._active)

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
        merged: dict[tuple[str, int], dict] = {k: dict(v) for k, v in self._persist.items()}
        for k, rec in self._active.items():
            if k in merged:
                _fill_missing(merged[k], rec)
            else:
                merged[k] = dict(rec)
        self._write_slot_file(slot, save_id, merged)
        self._active = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = merged

    def reset_active(self) -> None:
        self._active = {}
_SHARED: RiddleStore | None = None

def get_store() -> RiddleStore:
    global _SHARED
    if _SHARED is None:
        _SHARED = RiddleStore()
    return _SHARED
__all__ = ['RiddleStore', 'get_store', 'ext_data_dir', 'slot_filename']
