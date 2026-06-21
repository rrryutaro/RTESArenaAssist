
from __future__ import annotations

import copy
import logging
from typing import Optional

import assist_settings as settings

_log = logging.getLogger("screen_judge.registry")
_SETTINGS_KEY = "screen_judge_obs_points"


def _validate(entry: dict) -> bool:
    try:
        name = entry.get("name", "")
        xy = entry["arena_xy"]
        rgb = entry["expected_rgb"]
        tol = entry.get("tolerance", 20)
        role = entry.get("role", "")
        assert isinstance(name, str)
        assert len(xy) == 2 and all(isinstance(v, int) for v in xy)
        assert len(rgb) == 3 and all(isinstance(v, int) for v in rgb)
        assert isinstance(tol, int) and tol >= 0
        assert isinstance(role, str)
        return True
    except (KeyError, AssertionError, TypeError):
        return False


class ObsRegistry:

    def __init__(self):
        self._points: list[dict] = []
        self._load()


    def _load(self) -> None:
        raw = settings.get(_SETTINGS_KEY, [])
        if not isinstance(raw, list):
            _log.warning("screen_judge_obs_points: invalid type, reset")
            raw = []
        loaded = []
        for entry in raw:
            if _validate(entry):
                loaded.append(copy.deepcopy(entry))
            else:
                _log.warning("invalid obs entry skipped: %s", entry)
        self._points = loaded
        _log.info("ObsRegistry: loaded %d entries", len(self._points))

    def save(self) -> None:
        settings.set_val(_SETTINGS_KEY, copy.deepcopy(self._points))
        _log.info("ObsRegistry: saved %d entries", len(self._points))


    def all(self) -> list[dict]:
        return copy.deepcopy(self._points)

    def get(self, name: str) -> Optional[dict]:
        for p in self._points:
            if p["name"] == name:
                return copy.deepcopy(p)
        return None

    def add(self, entry: dict) -> bool:
        if not _validate(entry):
            _log.warning("add: invalid entry: %s", entry)
            return False
        if any(p["name"] == entry["name"] for p in self._points):
            _log.warning("add: duplicate name '%s'", entry["name"])
            return False
        self._points.append(copy.deepcopy(entry))
        self.save()
        return True

    def upsert(self, entry: dict) -> bool:
        if not _validate(entry):
            _log.warning("upsert: invalid entry: %s", entry)
            return False
        for i, p in enumerate(self._points):
            if p["name"] == entry["name"]:
                self._points[i] = copy.deepcopy(entry)
                self.save()
                return True
        self._points.append(copy.deepcopy(entry))
        self.save()
        return True

    def delete(self, name: str) -> bool:
        before = len(self._points)
        self._points = [p for p in self._points if p["name"] != name]
        if len(self._points) == before:
            return False
        self.save()
        return True

    def clear(self) -> None:
        self._points = []
        self.save()

    def replace_all(self, points: list[dict]) -> bool:
        validated = []
        for entry in points:
            if not _validate(entry):
                _log.warning("replace_all: invalid entry: %s", entry)
                return False
            validated.append(copy.deepcopy(entry))
        self._points = validated
        self.save()
        return True

    def __len__(self) -> int:
        return len(self._points)
