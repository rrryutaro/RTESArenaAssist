from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass

import save_manager
import save_reader

_log = logging.getLogger("map_ext_lifecycle")

_READ_CHUNK = 1 << 16


@dataclass(frozen=True)
class LifecycleVerdict:
    init_bind: int | None = None
    commits: tuple[int, ...] = ()
    load_slot: int | None = None


def classify_lifecycle_event(
    *,
    initialized: bool,
    prev_mtimes: dict[int, int],
    cur_mtimes: dict[int, int],
    live64_changed: bool,
    matched_slot: int | None,
) -> LifecycleVerdict:
    if not initialized:
        return LifecycleVerdict(init_bind=matched_slot)
    commits = tuple(s for s, m in cur_mtimes.items()
                    if m != prev_mtimes.get(s))
    load_slot = None
    if live64_changed and matched_slot is not None \
            and matched_slot not in commits:
        load_slot = matched_slot
    return LifecycleVerdict(commits=commits, load_slot=load_slot)


def _find(save_dir: str, fname_upper: str) -> str | None:
    target = fname_upper.upper()
    try:
        for f in os.listdir(save_dir):
            if f.upper() == target:
                return os.path.join(save_dir, f)
    except OSError:
        return None
    return None


def _hash_file(path: str | None) -> str | None:
    if not path:
        return None
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                b = f.read(_READ_CHUNK)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


class MapExtLifecycle:

    def __init__(self, store=None) -> None:
        if store is None:
            from services.map_ext_store import get_store
            store = get_store()
        self._store = store
        self._extra_stores: list = []
        self._on_load_callbacks: list = []
        self._bound_slot: int | None = None
        self._bound_save_id: str | None = None
        self._slot_mtimes: dict[int, int] = {}
        self._live64_mtime: int | None = None
        self._initialized = False

    def add_store(self, store) -> None:
        if store in self._extra_stores or store is self._store:
            return
        self._extra_stores.append(store)
        if self._bound_slot is not None:
            try:
                store.bind_slot(self._bound_slot, self._bound_save_id)
            except Exception:  # noqa: BLE001
                pass

    def add_on_load(self, callback) -> None:
        if callback not in self._on_load_callbacks:
            self._on_load_callbacks.append(callback)

    def _all_stores(self) -> list:
        return [self._store, *self._extra_stores]

    def poll(self, analyzer, anchor, save_dir: str | None) -> None:
        if not save_dir or not os.path.isdir(save_dir):
            return

        cur_mtimes = self._scan_slot_mtimes(save_dir)
        live64 = _find(save_dir, "SAVEGAME.64")
        try:
            live64_mtime = os.stat(live64).st_mtime_ns if live64 else None
        except OSError:
            live64_mtime = None
        first = not self._initialized
        live64_changed = first or (
            live64_mtime is not None and live64_mtime != self._live64_mtime)
        matched_slot = (self._match_slot(save_dir, _hash_file(live64))
                        if live64_changed else None)

        verdict = classify_lifecycle_event(
            initialized=self._initialized,
            prev_mtimes=self._slot_mtimes,
            cur_mtimes=cur_mtimes,
            live64_changed=live64_changed,
            matched_slot=matched_slot,
        )

        self._slot_mtimes = cur_mtimes
        self._live64_mtime = live64_mtime
        self._initialized = True

        self._apply_verdict(verdict, save_dir)

    def _apply_verdict(self, verdict: LifecycleVerdict, save_dir: str) -> None:
        if verdict.init_bind is not None:
            self._bind_stores(verdict.init_bind, save_dir)
            return
        for s in verdict.commits:
            save_id = save_reader.read_save_name(save_dir, s)
            for st in self._all_stores():
                st.commit_to_slot(s, save_id)
            self._bound_slot = s
            self._bound_save_id = save_id
        if verdict.load_slot is not None:
            slot = verdict.load_slot
            save_id = save_reader.read_save_name(save_dir, slot)
            _log.warning("LOAD: slot=#%d name=%r (SAVEGAME.0%d)",
                         slot, save_id, slot)
            for st in self._all_stores():
                st.reset_active()
                st.bind_slot(slot, save_id)
            for cb in self._on_load_callbacks:
                try:
                    cb()
                except Exception:  # noqa: BLE001
                    pass
            self._bound_slot = slot
            self._bound_save_id = save_id

    def _bind_stores(self, slot: int, save_dir: str) -> None:
        save_id = save_reader.read_save_name(save_dir, slot)
        for st in self._all_stores():
            st.bind_slot(slot, save_id)
        self._bound_slot = slot
        self._bound_save_id = save_id

    def on_load(self) -> None:
        return

    def _scan_slot_mtimes(self, save_dir: str) -> dict[int, int]:
        out: dict[int, int] = {}
        for slot in save_manager.list_slots(save_dir):
            mt = 0
            for prefix in ("SAVEENGN", "SAVEGAME"):
                p = _find(save_dir, f"{prefix}.0{slot}")
                if p:
                    try:
                        mt = max(mt, os.stat(p).st_mtime_ns)
                    except OSError:
                        pass
            out[slot] = mt
        return out

    def _match_slot(self, save_dir: str, live_hash: str | None) -> int | None:
        if not live_hash:
            return None
        for slot in save_manager.list_slots(save_dir):
            p = _find(save_dir, f"SAVEGAME.0{slot}")
            if p and _hash_file(p) == live_hash:
                return slot
        return None


_SHARED: MapExtLifecycle | None = None


def get_lifecycle() -> "MapExtLifecycle":
    global _SHARED
    if _SHARED is None:
        _SHARED = MapExtLifecycle()
    return _SHARED


__all__ = [
    "MapExtLifecycle", "get_lifecycle",
    "LifecycleVerdict", "classify_lifecycle_event",
]
