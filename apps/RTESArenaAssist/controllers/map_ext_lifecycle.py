"""controllers/map_ext_lifecycle.py — マップ拡張データのライフサイクル駆動。

ゲーム側イベントを検知して MapExtStore を遷移させる:

  - スロット識別: Arena のライブ用ファイル ``SAVEGAME.64`` は、セーブ/ロード時に
    スロット側 ``SAVEGAME.0N`` と byte 単位で一致する（実測確認済み）。
    NAMES.DAT のスロット表示名はキャラクター名ではなくセーブ表示名（例: "001-2"）
    のため名前一致では識別できない。よって ``SAVEGAME.64`` の内容が一致する
    ``SAVEGAME.0N`` を現在スロットとして識別する。
  - セーブ確定: ``SAVEGAME.0N`` / ``SAVEENGN.0N`` の mtime 進行を検知し、書かれた
    スロットへアクティブ層を確定する（同名上書きも mtime で拾える）。
  - ロード検知: ``SAVEGAME.64`` の内容が変化し、いずれかの ``SAVEGAME.0N`` と一致
    したとき（= そのスロットをロード）→ アクティブ層を破棄し、そのスロットへ再束縛
    する。``.64`` mtime を安価なゲートに使い、変化時のみハッシュ照合する。

本モジュールはファイル I/O のみ。画面検知は呼び出し側（tab_map）。
"""
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
    """poll 1 回分のライフサイクル結論（単一軸）。

    分類器 ``classify_lifecycle_event`` が全信号から 1 つだけ返し、消費側
    （``MapExtLifecycle._apply_verdict``）は **再判定せず** これを順に適用する
    だけ。早期 return や相互排他ガードは持たない（= 1軸化）。

    フィールド:
      - ``init_bind``: 起動 poll で現ライブ一致スロットへ束縛する（無ければ None）。
      - ``commits``: セーブ確定スロット群（``SAVEGAME.0N`` mtime 進行）。
      - ``load_slot``: ロード再束縛スロット（本物のロードのみ・無ければ None）。
    """
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
    """セーブ/ロードのファイル信号から poll 1 回の結論を 1 つ返す（純関数）。

    入力は I/O 済みの信号のみ（読み取りは呼び出し側）:
      - ``prev_mtimes`` / ``cur_mtimes``: スロットの最終更新時刻（セーブ検知）。
      - ``live64_changed``: ライブ ``SAVEGAME.64`` の mtime が前回から変化したか。
      - ``matched_slot``: そのライブ内容に一致した ``SAVEGAME.0N`` のスロット
        （照合は変化時のみ・不一致/未照合は None）。

    判定（単一軸・ここで全結論を確定する）:
      - 起動 poll（``initialized=False``）: ``init_bind=matched_slot`` のみ。
      - 以降: ``commits`` = mtime 進行スロット群。ロードは「``.64`` が変化し、かつ
        一致スロットが **commit 対象でない**（= セーブ自身の ``.64`` 反映でない
        本物のロード）」時に ``load_slot`` へ。

    セーブ/ロードが 1 poll に合流しても、両者を 1 つの結論として返す（セーブを
    見た時点で打ち切らない）。これにより消費側に相互排他ガードが不要になる。
    """
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
    """MapExtStore のライフサイクル駆動。poll ごとに呼ばれる。"""

    def __init__(self, store=None) -> None:
        if store is None:
            from services.map_ext_store import get_store
            store = get_store()
        self._store = store
        # 同じセーブ/ロード契機で駆動する追加ストア（翻訳ログ等）。
        # bind_slot / commit_to_slot / reset_active を同シグネチャで実装する。
        self._extra_stores: list = []
        # ロード検知時に呼ぶコールバック（読み上げ重複ガードのクリア等）。
        self._on_load_callbacks: list = []
        self._bound_slot: int | None = None
        self._bound_save_id: str | None = None
        self._slot_mtimes: dict[int, int] = {}
        self._live64_mtime: int | None = None
        self._initialized = False

    def add_store(self, store) -> None:
        """セーブ/ロード契機を共有する追加ストアを登録する。

        既に束縛済みなら、登録時に現在スロットへ即時束縛して同期する。
        """
        if store in self._extra_stores or store is self._store:
            return
        self._extra_stores.append(store)
        if self._bound_slot is not None:
            try:
                store.bind_slot(self._bound_slot, self._bound_save_id)
            except Exception:  # noqa: BLE001
                pass

    def add_on_load(self, callback) -> None:
        """ロード検知時に呼ぶコールバックを登録する（例: 読み上げガードのクリア）。"""
        if callback not in self._on_load_callbacks:
            self._on_load_callbacks.append(callback)

    def _all_stores(self) -> list:
        return [self._store, *self._extra_stores]

    # ── poll（信号採取 → 単一分類 → 消費）───────────────────
    def poll(self, analyzer, anchor, save_dir: str | None) -> None:
        if not save_dir or not os.path.isdir(save_dir):
            return

        # ① 信号採取（I/O のみ・判定しない）。
        cur_mtimes = self._scan_slot_mtimes(save_dir)
        live64 = _find(save_dir, "SAVEGAME.64")
        try:
            live64_mtime = os.stat(live64).st_mtime_ns if live64 else None
        except OSError:
            live64_mtime = None
        # 起動 poll は baseline 未確立。ライブ一致スロットへ束縛するため照合する。
        # 以降は .64 mtime 変化時のみハッシュ照合する（安価ゲート）。
        first = not self._initialized
        live64_changed = first or (
            live64_mtime is not None and live64_mtime != self._live64_mtime)
        matched_slot = (self._match_slot(save_dir, _hash_file(live64))
                        if live64_changed else None)

        # ② 単一分類（純関数で poll 1 回の結論を 1 つ確定）。
        verdict = classify_lifecycle_event(
            initialized=self._initialized,
            prev_mtimes=self._slot_mtimes,
            cur_mtimes=cur_mtimes,
            live64_changed=live64_changed,
            matched_slot=matched_slot,
        )

        # ③ baseline 記録（状態更新・判定ではない）。
        self._slot_mtimes = cur_mtimes
        self._live64_mtime = live64_mtime
        self._initialized = True

        # ④ 消費（再判定なし・結論を順に適用するだけ）。
        self._apply_verdict(verdict, save_dir)

    def _apply_verdict(self, verdict: LifecycleVerdict, save_dir: str) -> None:
        """分類結論を適用する（消費のみ・内部で再判定しない）。

        順序は init→commit→load 固定（消費順であって判定ではない）。
        """
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
            # ロード契機の診断ログ（イベント駆動・常時出力ではない）。
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
        """全ストアを指定スロットへ束縛する（起動 poll の消費）。"""
        save_id = save_reader.read_save_name(save_dir, slot)
        for st in self._all_stores():
            st.bind_slot(slot, save_id)
        self._bound_slot = slot
        self._bound_save_id = save_id

    def on_load(self) -> None:
        """ロード画面契機。実際の破棄＋再束縛は poll の SAVEGAME.64 一致で行うため
        ここでは何もしない（ロード取消時に未保存分を失わないため）。"""
        return

    # ── 内部 ──────────────────────────────────────────────
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
        """SAVEGAME.0N の内容が live_hash と一致するスロットを返す。"""
        if not live_hash:
            return None
        for slot in save_manager.list_slots(save_dir):
            p = _find(save_dir, f"SAVEGAME.0{slot}")
            if p and _hash_file(p) == live_hash:
                return slot
        return None


# ── アプリ共有シングルトン ────────────────────────────────
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
