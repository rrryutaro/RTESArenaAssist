"""controllers/poll_diag.py — poll 診断計時 helper (中立・純粋)。

poll_controller と normal-play 描画 node (normal_play_render) の両方が
状態遷移判断の所要計測に使う。副作用は w 側 dict/list への追記のみで、
表示単位・判定経路には関与しない (= 純粋中立 helper)。
"""
from __future__ import annotations

import time


def _phase_start() -> float:
    """状態遷移判断の計測開始時刻を返す (perf_counter)。"""
    return time.perf_counter()


def _phase_record(w, name: str, t0: float) -> None:
    """状態遷移判断 ``name`` の所要 (ms) を w._poll_phase_times に記録する。

    フリーズ調査用の計測。記録は副作用なしの dict 追記のみで、出力は poll 1 回の
    完了後に assist_window._poll() がまとめて 1 行で行う (= 過剰出力を避ける)。
    """
    try:
        w._poll_phase_times[name] = (time.perf_counter() - t0) * 1000.0
    except (AttributeError, TypeError):
        pass


def _checkpoint(w, name: str) -> None:
    """poll 開始からの累積経過 (ms) を記録する (フリーズ区間の粗い局所化用)。

    連続するチェックポイント間の差分が、その区間の所要を表す。総時間が計測
    フェーズに現れない場合に、どの区間で時間を食っているかを切り分ける。
    """
    try:
        w._poll_checkpoints.append(
            (name, (time.perf_counter() - w._poll_t0) * 1000.0))
    except (AttributeError, TypeError):
        pass

__all__ = ["_phase_start", "_phase_record", "_checkpoint"]
