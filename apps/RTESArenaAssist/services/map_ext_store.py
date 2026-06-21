"""services/map_ext_store.py — マップ用拡張データ保存機構（セーブスロット連動）。

Arena のセーブデータ本体は改変せず、Assist 側で各セーブスロットに
連動した「マップ用拡張データ」を、スロットごとの個別ファイル
``ext_data/map_ext.0N``（N=スロット番号 0〜9）として保持する。

2層モデル:
  - アクティブ層 (= メモリ上・未保存): 今回のプレイで発見した分。
    セーブしなければ消える（Arena 本来の「セーブしてなければ無かったこと」と一致）。
  - 永続層 (= スロット別ファイル): セーブ確定済みの分。
  表示はこの2層の和集合を使う。

セクション:
  現状は隠し扉 (``hidden_doors``) のみ。ロケーション(``<MIF>#<階層>``)ごとに
  発見した扉セル (x, y) を集合で持つ。

スロット同一性は ``save_id`` (= NAMES.DAT のスロット表示名) で判定する。束縛時に
ファイル内 save_id と相違していれば別データによる上書きとみなし永続層をリセットする
(= tab_save の game_save_name 比較と同契機)。

ライフサイクル駆動 (どのスロットに束縛 / セーブ確定 / ロード破棄) は呼び出し側
(poll_controller) が行う。本モジュールはデータの保持・永続化・和集合提供に専念する。
"""
from __future__ import annotations

import json
import os

_FILE_VERSION = 1
_SECTION = "hidden_doors"


def ext_data_dir() -> str:
    """拡張データフォルダ ``ext_data/`` の絶対パスを返す（saves_backup と同階層）。"""
    from assist_settings import _settings_path
    if _settings_path:
        return os.path.join(os.path.dirname(_settings_path), "ext_data")
    return os.path.join(os.path.expanduser("~"), "RTESArenaAssist_ext_data")


def slot_filename(slot: int) -> str:
    """スロット番号 → マップ拡張データのファイル名 (例: 0 → map_ext.00)。"""
    return f"map_ext.0{int(slot)}"


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
    return {
        loc: sorted([list(c) for c in cells])
        for loc, cells in data.items() if cells
    }


class MapExtStore:
    """マップ用拡張データの2層ストア（アクティブ＋永続スロット別ファイル）。"""

    def __init__(self, ext_dir: str | None = None) -> None:
        self._ext_dir_override = ext_dir
        # アクティブ層 (未保存): loc -> set[(x, y)]
        self._active: dict[str, set[tuple[int, int]]] = {}
        # 現在束縛しているスロットの永続層キャッシュ: loc -> set[(x, y)]
        self._persist: dict[str, set[tuple[int, int]]] = {}
        self._current_slot: int | None = None
        self._current_save_id: str | None = None

    # ── パス ──────────────────────────────────────────────
    def ext_dir(self) -> str:
        return self._ext_dir_override or ext_data_dir()

    def _slot_path(self, slot: int) -> str:
        return os.path.join(self.ext_dir(), slot_filename(slot))

    # ── 永続層 read/write ─────────────────────────────────
    def _read_slot_file(self, slot: int) -> tuple[str | None, dict[str, set[tuple[int, int]]]]:
        """(save_id, {loc: cells}) を返す。無ければ (None, {})。"""
        path = self._slot_path(slot)
        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None, {}
        save_id = obj.get("save_id") if isinstance(obj, dict) else None
        raw = obj.get(_SECTION, {}) if isinstance(obj, dict) else {}
        return save_id, _loc_dict_to_sets(raw)

    def _write_slot_file(self, slot: int, save_id: str | None,
                         data: dict[str, set[tuple[int, int]]]) -> None:
        os.makedirs(self.ext_dir(), exist_ok=True)
        obj = {
            "version": _FILE_VERSION,
            "save_id": save_id,
            _SECTION: _loc_sets_to_dict(data),
        }
        path = self._slot_path(slot)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    # ── 束縛 ──────────────────────────────────────────────
    def bind_slot(self, slot: int | None, save_id: str | None) -> None:
        """現在のスロットを束縛し、その永続層を読み込む。

        slot=None で未束縛（永続層なし＝アクティブのみ表示）。
        ファイル内 save_id と引数 save_id が相違していれば別データ上書きとみなし
        永続層をリセットする。
        """
        if slot is None:
            self._current_slot = None
            self._current_save_id = None
            self._persist = {}
            return
        if slot == self._current_slot and save_id == self._current_save_id:
            return
        file_save_id, data = self._read_slot_file(slot)
        if save_id is not None and file_save_id is not None and file_save_id != save_id:
            # 別データで上書きされている → 永続層リセット
            data = {}
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = data

    @property
    def current_slot(self) -> int | None:
        return self._current_slot

    # ── 記録・参照 ────────────────────────────────────────
    def note_discovery(self, location_key: str, x: int, y: int) -> bool:
        """発見をアクティブ層に記録する。新規発見（未記録）なら True。"""
        cell = (int(x), int(y))
        s = self._active.setdefault(location_key, set())
        already = cell in s or cell in self._persist.get(location_key, set())
        s.add(cell)
        return not already

    def discovered_cells(self, location_key: str) -> frozenset[tuple[int, int]]:
        """表示用の発見集合（アクティブ ∪ 永続）を返す。"""
        out = set(self._persist.get(location_key, set()))
        out |= self._active.get(location_key, set())
        return frozenset(out)

    # ── ライフサイクル ────────────────────────────────────
    def commit_to_slot(self, slot: int, save_id: str | None) -> None:
        """セーブ検知時: アクティブ層を該当スロットの永続層へ確定し、アクティブをクリア。"""
        file_save_id, data = self._read_slot_file(slot)
        if save_id is not None and file_save_id is not None and file_save_id != save_id:
            data = {}
        # アクティブ ∪ 永続
        for loc, cells in self._active.items():
            data.setdefault(loc, set()).update(cells)
        self._write_slot_file(slot, save_id, data)
        self._active.clear()
        self._current_slot = slot
        self._current_save_id = save_id
        self._persist = data

    def reset_active(self) -> None:
        """ロード検知時: アクティブ層を破棄する。"""
        self._active.clear()

    def reset_slot(self, slot: int) -> None:
        """スロット上書き/新規時: 該当スロットの永続層ファイルを削除する。"""
        path = self._slot_path(slot)
        try:
            os.remove(path)
        except OSError:
            pass
        if slot == self._current_slot:
            self._persist = {}


# ── アプリ共有シングルトン ────────────────────────────────
# map / fallback の両 TabMap と poll ライフサイクルが同一ストアを共有する。
_SHARED: MapExtStore | None = None


def get_store() -> MapExtStore:
    """アプリ共有の MapExtStore を返す（無ければ生成）。"""
    global _SHARED
    if _SHARED is None:
        _SHARED = MapExtStore()
    return _SHARED


__all__ = ["MapExtStore", "ext_data_dir", "slot_filename", "get_store"]
