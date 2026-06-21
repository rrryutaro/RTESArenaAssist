"""copy_selector_observation.py — 入店メッセージ tileset copy 選択軸の観測ログ。

「copy 選択器は観測ログ整備後の別段階」を支える
**データ収集専用**モジュール。入店メッセージが照合された瞬間に、

  - 照合された source_id / copy / 候補（source_id_candidates）
  - その時点で得られる場所シグナル（外装 MIF / 内装 MIF / 施設名・種別 /
    場所ヒント / 屋内フラグ / フィールド位置 / province・location id 等）

を 1 件ずつ JSONL へ追記する。**選択軸は断定しない**（CITY/TOWN/VILLAGE=copy0/1/2 を
未検証で固定しない）。複数都市・複数施設で記録を貯め、後段で copy↔シグナルの対応表を
作ってから selector を実装する。

設計上の制約:
  - **変化時のみ発火**（常時ログ禁止）。同一 source_id の連続 poll は記録しない。
  - poll を絶対に壊さない。context 収集は getattr ベースで例外を出さない。
  - これはローカル診断ログ（公開物に含めない）。
"""
from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger("RTESArenaAssist")

# 場所シグナルとして best-effort で拾う w の属性名（getattr・既定 None）。
# 存在しない属性は記録に含めない。runtime のシグナル拡充に合わせて増やせる。
_CONTEXT_ATTRS: tuple[tuple[str, str], ...] = (
    ("exterior_mif", "_active_mif"),
    ("interior_mif", "_interior_mif_name"),
    ("facility_name", "_interior_facility_name"),
    ("facility_kind", "_interior_facility_kind"),
    ("location_hint", "_log_location_hint"),
    ("wilderness_location", "_wilderness_location"),
    ("in_interior", "_in_interior"),
    ("province_id", "_province_id"),
    ("location_id", "_location_id"),
    ("city_type", "_city_type"),
    ("coastal", "_coastal"),
)


def gather_context(w) -> dict:
    """w から場所シグナルを best-effort で収集する（例外を出さない）。

    存在し非 None の属性のみ含める。JSON 化できない値は文字列化する。
    """
    ctx: dict = {}
    for label, attr in _CONTEXT_ATTRS:
        try:
            val = getattr(w, attr, None)
        except Exception:  # noqa: BLE001 - 観測は poll を壊さない
            val = None
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            ctx[label] = val
        else:
            ctx[label] = str(val)
    return ctx


def build_record(meta: dict, en_text: str, context: dict,
                 *, timestamp: str | None = None, src: str | None = None) -> dict:
    """観測 1 件のレコード（純関数・決定論）。

    en は照合の手掛かりとしてローカル診断用に短い抜粋のみ保持する。
    """
    rec = {
        "source_id": meta.get("source_id"),
        "copy": meta.get("copy"),
        "source_id_candidates": list(meta.get("source_id_candidates") or []),
        "matched_key": meta.get("matched_key"),
        "matched_letter": meta.get("matched_letter"),
        "en_excerpt": (en_text or "")[:60],
        "candidate_src": src,
        "context": context,
    }
    if timestamp is not None:
        rec["ts"] = timestamp
    return rec


def should_log(w, source_id: str | None) -> bool:
    """同一 source_id の連続発火を抑止する（変化時のみ True）。

    w._be_obs_last_sid に直近記録の source_id を保持。新しい入店メッセージ
    （source_id が変わった）時だけ True を返し、状態を更新する。
    """
    if not source_id:
        return False
    last = getattr(w, "_be_obs_last_sid", None)
    if last == source_id:
        return False
    try:
        w._be_obs_last_sid = source_id
    except Exception:  # noqa: BLE001
        pass
    return True


def _default_log_path() -> str:
    """観測 JSONL の既定パス（ext_data/ 配下・書き込み不可なら None 相当の空）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # app dir
    return os.path.join(base, "ext_data", "copy_obs.jsonl")


def observe(w, meta: dict, en_text: str, *, src: str | None = None,
            path: str | None = None, timestamp: str | None = None) -> bool:
    """入店メッセージ照合時に呼ぶ観測フック。記録したら True。

    変化ゲート（should_log）を通った時だけ 1 行 JSONL を追記する。
    いかなる失敗も poll を壊さないよう握りつぶす（戻り値 False）。
    """
    try:
        source_id = meta.get("source_id") if isinstance(meta, dict) else None
        if not should_log(w, source_id):
            return False
        rec = build_record(meta, en_text, gather_context(w),
                           timestamp=timestamp, src=src)
        target = path or _default_log_path()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001 - 観測は poll を壊さない
        _log.debug("copy_selector_observation: skipped", exc_info=True)
        return False


__all__ = ["observe", "gather_context", "build_record", "should_log"]
