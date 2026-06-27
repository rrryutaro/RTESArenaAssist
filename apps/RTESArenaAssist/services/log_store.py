from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from typing import Callable, Optional
_FILE_VERSION = 1

@dataclass(frozen=True)
class LogEntry:
    seq: int
    ts: float
    category: str
    location: str
    original: str
    text: str
DEFAULT_LOG_DATETIME_FORMAT = 'yyyy/MM/dd(aaa) HH:mm:ss'
_JP_WEEKDAYS = ('月', '火', '水', '木', '金', '土', '日')

def format_datetime(dt, fmt: str) -> str:
    try:
        wd = _JP_WEEKDAYS[dt.weekday()]
        return fmt.replace('yyyy', f'{dt.year:04d}').replace('MM', f'{dt.month:02d}').replace('dd', f'{dt.day:02d}').replace('HH', f'{dt.hour:02d}').replace('mm', f'{dt.minute:02d}').replace('ss', f'{dt.second:02d}').replace('aaa', wd)
    except Exception:
        return ''
_CATEGORY_KEYS = {'situation': 'log.category.situation', 'conversation': 'log.category.conversation'}

def category_i18n_key(category: str) -> Optional[str]:
    return _CATEGORY_KEYS.get(category)

def ext_data_dir() -> str:
    from services.map_ext_store import ext_data_dir as _dir
    return _dir()

def slot_filename(slot: int) -> str:
    return f'log_ext.0{int(slot)}'

def _entry_to_dict(e: LogEntry) -> dict:
    return asdict(e)

def _dict_to_entry(d: dict) -> Optional[LogEntry]:
    try:
        return LogEntry(seq=int(d.get('seq', 0)), ts=float(d.get('ts', 0.0)), category=str(d.get('category', '')), location=str(d.get('location', '')), original=str(d.get('original', '')), text=str(d.get('text', '')))
    except (TypeError, ValueError):
        return None

class LogStore:

    def __init__(self, max_entries: int=2000, ext_dir: str | None=None) -> None:
        self._max = max_entries
        self._ext_dir_override = ext_dir
        self._active: list[LogEntry] = []
        self._persist: list[LogEntry] = []
        self._seq = 0
        self._current_slot: int | None = None
        self._current_save_id: str | None = None
        self._append_observer: Optional[Callable[[LogEntry], None]] = None
        self._changed_observer: Optional[Callable[[], None]] = None
        self._last_key: Optional[tuple[str, str]] = None

    def set_max_entries(self, max_entries: int) -> None:
        try:
            n = int(max_entries)
        except (TypeError, ValueError):
            return
        if n < 1:
            n = 1
        if n == self._max:
            return
        self._max = n
        if len(self._active) > n:
            self._active = self._active[-n:]
        if len(self._persist) > n:
            self._persist = self._persist[-n:]
        self._notify_changed()

    def set_observer(self, callback: Optional[Callable[[LogEntry], None]]) -> None:
        self._append_observer = callback

    def set_changed_observer(self, callback: Optional[Callable[[], None]]) -> None:
        self._changed_observer = callback

    def _notify_changed(self) -> None:
        if self._changed_observer is not None:
            try:
                self._changed_observer()
            except Exception:
                pass

    def _ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self._ext_dir(), slot_filename(slot))

    def _read_slot_file(self, slot: int) -> tuple[str | None, list[LogEntry]]:
        path = self._slot_path(slot)
        try:
            with open(path, encoding='utf-8') as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return (None, [])
        if not isinstance(obj, dict):
            return (None, [])
        save_id = obj.get('save_id')
        raw = obj.get('entries', [])
        entries = []
        if isinstance(raw, list):
            for d in raw:
                if isinstance(d, dict):
                    e = _dict_to_entry(d)
                    if e is not None:
                        entries.append(e)
        return (save_id, entries)

    def _write_slot_file(self, slot: int, save_id: str | None, entries: list[LogEntry]) -> None:
        os.makedirs(self._ext_dir(), exist_ok=True)
        obj = {'version': _FILE_VERSION, 'save_id': save_id, 'entries': [_entry_to_dict(e) for e in entries[-self._max:]]}
        with open(self._slot_path(slot), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def append(self, *, ts: float, category: str, text: str, original: str='', location: str='') -> Optional[LogEntry]:
        if not text:
            return None
        key = (category, text)
        if key == self._last_key:
            return None
        self._last_key = key
        self._seq += 1
        entry = LogEntry(seq=self._seq, ts=float(ts), category=category, location=location, original=original, text=text)
        self._active.append(entry)
        if len(self._active) > self._max:
            self._active = self._active[-self._max:]
        if self._append_observer is not None:
            try:
                self._append_observer(entry)
            except Exception:
                pass
        return entry

    def entries(self, *, newest_first: bool=True, category: str | None=None, location: str | None=None) -> list[LogEntry]:
        merged = self._persist + self._active
        if category:
            merged = [e for e in merged if e.category == category]
        if location:
            merged = [e for e in merged if e.location == location]
        if newest_first:
            return list(reversed(merged))
        return list(merged)

    def distinct_locations(self) -> list[str]:
        seen: list[str] = []
        for e in self._persist + self._active:
            if e.location and e.location not in seen:
                seen.append(e.location)
        return seen

    def clear(self) -> None:
        self._active = []
        self._last_key = None
        self._notify_changed()

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

    def bind_slot(self, slot: int | None, save_id: str | None) -> None:
        if slot is None:
            self._current_slot = None
            self._current_save_id = None
            self._persist = []
            self._notify_changed()
            return
        if slot == self._current_slot and save_id == self._current_save_id:
            return
        file_save_id, entries = self._read_slot_file(slot)
        if save_id is not None and file_save_id is not None and (file_save_id != save_id):
            entries = []
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = entries
        self._seq = max([self._seq] + [e.seq for e in entries])
        self._notify_changed()

    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        merged = (self._persist + self._active)[-self._max:]
        self._write_slot_file(slot, save_id, merged)
        self._active = []
        self._last_key = None
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = merged
        self._notify_changed()

    def reset_active(self) -> None:
        self._active = []
        self._last_key = None
        self._notify_changed()
__all__ = ['LogStore', 'LogEntry', 'category_i18n_key', 'ext_data_dir', 'slot_filename', 'format_datetime', 'DEFAULT_LOG_DATETIME_FORMAT']
