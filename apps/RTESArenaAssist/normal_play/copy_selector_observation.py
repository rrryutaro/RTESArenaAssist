from __future__ import annotations

import json
import logging
import os

_log = logging.getLogger("RTESArenaAssist")

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
    ctx: dict = {}
    for label, attr in _CONTEXT_ATTRS:
        try:
            val = getattr(w, attr, None)
        except Exception:  # noqa: BLE001
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
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ext_data", "copy_obs.jsonl")


def observe(w, meta: dict, en_text: str, *, src: str | None = None,
            path: str | None = None, timestamp: str | None = None) -> bool:
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
    except Exception:  # noqa: BLE001
        _log.debug("copy_selector_observation: skipped", exc_info=True)
        return False


__all__ = ["observe", "gather_context", "build_record", "should_log"]
