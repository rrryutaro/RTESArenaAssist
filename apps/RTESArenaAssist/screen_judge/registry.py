"""
screen_judge/registry.py — 観測点定義の永続化・管理

観測点エントリ形式:
  {
    "name":         str,          # 識別名
    "arena_xy":     [int, int],   # Arena 内部座標 (0-319, 0-199)
    "expected_rgb": [int, int, int],  # 期待 RGB
    "tolerance":    int,          # 許容誤差（チャンネルごとの最大差分）
    "purpose":      str,          # 用途メモ（任意）
  }

assist_settings.json の "screen_judge_obs_points" キーで永続化する。
"""

from __future__ import annotations

import copy
import logging
from typing import Optional

import assist_settings as settings

_log = logging.getLogger("screen_judge.registry")
_SETTINGS_KEY = "screen_judge_obs_points"


def _validate(entry: dict) -> bool:
    """最低限のキーとデータ型を検証する。"""
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
    """観測点リストの CRUD + 永続化。"""

    def __init__(self):
        self._points: list[dict] = []
        self._load()

    # ------------------------------------------------------------------
    # 永続化
    # ------------------------------------------------------------------

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
        """現在のリストを assist_settings.json に書き込む。"""
        settings.set_val(_SETTINGS_KEY, copy.deepcopy(self._points))
        _log.info("ObsRegistry: saved %d entries", len(self._points))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def all(self) -> list[dict]:
        """全観測点のコピーを返す。"""
        return copy.deepcopy(self._points)

    def get(self, name: str) -> Optional[dict]:
        for p in self._points:
            if p["name"] == name:
                return copy.deepcopy(p)
        return None

    def add(self, entry: dict) -> bool:
        """観測点を追加して保存する。同名が存在する場合は False を返す。"""
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
        """追加または上書き保存。"""
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
        """名前で観測点を削除する。存在しない場合は False。"""
        before = len(self._points)
        self._points = [p for p in self._points if p["name"] != name]
        if len(self._points) == before:
            return False
        self.save()
        return True

    def clear(self) -> None:
        """全観測点を削除して保存する。"""
        self._points = []
        self.save()

    def replace_all(self, points: list[dict]) -> bool:
        """リストをまるごと置き換える。不正エントリが 1 件でもあれば中止して False。"""
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
