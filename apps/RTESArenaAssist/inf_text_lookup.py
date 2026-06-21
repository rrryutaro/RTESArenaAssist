
from __future__ import annotations

import re

import i18n_helper as i18n

_CATEGORY = "inf_text"

_KIND_TYPES = frozenset({"key", "lore", "riddle", "lore_once", "key_lore"})

_INF_STRUCT_SID_RE = re.compile(r"^inf:([^:]+):text:(\d+)$")


def _parse_inf_struct_sid(sid: str | None) -> tuple[str, int] | None:
    if not sid:
        return None
    m = _INF_STRUCT_SID_RE.match(sid)
    if not m:
        return None
    return (m.group(1), int(m.group(2)))

_index: dict[tuple[str, int], dict] = {}
_loaded = False


def _load_v2() -> dict[tuple[str, int], dict]:
    idx: dict[tuple[str, int], dict] = {}
    for e in i18n.v2_category_entries(_CATEGORY):
        sid = e.get("source_id")
        rich = e.get("rich")
        if isinstance(rich, dict) and rich.get("inf") is not None \
                and rich.get("idx") is not None:
            inf = rich.get("inf")
            ridx = rich.get("idx")
            entry = dict(rich)
        else:
            parsed = _parse_inf_struct_sid(sid)
            if parsed is None:
                continue
            inf, ridx = parsed
            entry = {"inf": inf, "idx": ridx}
            orig = e.get("original")
            if orig:
                entry["text"] = orig
                entry["text_panel"] = orig
                entry["text_display"] = orig
        kind = e.get("kind")
        entry["type"] = kind if kind in _KIND_TYPES else None
        entry["_sid"] = sid
        entry["_v2"] = True
        idx[(str(inf).upper(), int(ridx))] = entry
    return idx


def _base_of(entry_id: str) -> str:
    head, _, _ = entry_id.rpartition(".")
    return head or entry_id


def load(path: str | None = None) -> None:
    global _index, _loaded
    if i18n.v2_public_enabled(_CATEGORY):
        try:
            _index = _load_v2()
            _loaded = True
        except (KeyError, ValueError, TypeError):
            _loaded = False
        return
    _index = {}
    try:
        for entry_id, e in i18n.originals(_CATEGORY).items():
            if not isinstance(e, dict):
                continue
            inf = e.get("inf")
            idx = e.get("idx")
            if inf is None or idx is None:
                continue
            entry = dict(e)
            entry["_id"] = entry_id
            _index[(str(inf).upper(), int(idx))] = entry
        _loaded = True
    except (KeyError, ValueError, TypeError):
        _loaded = False
    if not _index and i18n.v2_public_enabled(None):
        try:
            _index = _load_v2()
            _loaded = True
        except (KeyError, ValueError, TypeError):
            pass


def _ensure_loaded() -> None:
    if not _loaded:
        load()


def lookup(inf_name: str, text_index: int) -> dict | None:
    _ensure_loaded()
    return _index.get((inf_name.upper(), text_index))


def lookup_by_text(inf_name: str, body: str, max_prefix: int = 50) -> dict | None:
    _ensure_loaded()
    if not body:
        return None

    def _norm(s: str) -> str:
        return s.replace("\r", " ").replace("\n", " ").strip()

    body_norm = _norm(body)
    inf_upper = inf_name.upper()
    for (inf, _idx), e in _index.items():
        if inf_upper and inf != inf_upper:
            continue
        candidate = e.get("text") or e.get("question") or ""
        cand_norm = _norm(candidate)
        if not cand_norm:
            continue
        if body_norm[:len(cand_norm)].upper() == cand_norm.upper():
            return e
    return None


def lookup_by_substring(inf_name: str, body: str,
                        min_fragment_len: int = 16) -> dict | None:
    _ensure_loaded()
    if not body:
        return None

    def _norm(s: str) -> str:
        return s.replace("\r", " ").replace("\n", " ").strip()

    body_norm = _norm(body)
    if len(body_norm) < min_fragment_len:
        return None
    body_upper = body_norm.upper()
    inf_upper = inf_name.upper()
    matches: list[dict] = []
    for (inf, _idx), e in _index.items():
        if inf_upper and inf != inf_upper:
            continue
        candidate = e.get("text") or e.get("question") or ""
        cand_norm = _norm(candidate)
        if not cand_norm:
            continue
        if body_upper in cand_norm.upper():
            matches.append(e)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


def get_translation(entry: dict, lang: str = "ja") -> str | dict | None:
    if entry is None:
        return None
    if entry.get("type") == "key":
        return None
    if entry.get("_v2"):
        sid = entry.get("_sid") or ""
        if entry.get("type") == "riddle":
            return {
                fld: (i18n.text_by_source_id(f"{sid}:{fld}", category=_CATEGORY) or "")
                for fld in ("question", "correct", "wrong")
            }
        return i18n.text_by_source_id(sid, category=_CATEGORY) or ""
    base = _base_of(entry.get("_id", ""))
    if entry.get("type") == "riddle":
        return {
            fld: (i18n.lang_only(f"{base}.{fld}") or "")
            for fld in ("question", "correct", "wrong")
        }
    return i18n.lang_only(entry.get("_id", "")) or ""


def get_translation_display(entry: dict, lang: str = "ja") -> str | None:
    if entry is None:
        return None
    if entry.get("type") in ("key", "riddle"):
        return None
    if entry.get("_v2"):
        sid = entry.get("_sid") or ""
        val = i18n.text_by_source_id(f"{sid}:display", category=_CATEGORY)
        if val:
            return val
        return i18n.text_by_source_id(sid, category=_CATEGORY)
    base = _base_of(entry.get("_id", ""))
    val = i18n.lang_only(f"{base}.display")
    if val:
        return val
    return i18n.lang_only(entry.get("_id", ""))


def get_text_panel(entry: dict) -> str:
    if entry is None:
        return ""
    return (entry.get("text_panel")
            or entry.get("text_display")
            or entry.get("text", ""))


def get_text_display(entry: dict) -> str:
    if entry is None:
        return ""
    return (entry.get("text_display")
            or entry.get("text_panel")
            or entry.get("text", ""))


def all_entries_for_inf(inf_name: str) -> list[dict]:
    _ensure_loaded()
    inf_upper = inf_name.upper()
    result = [e for (inf, _), e in _index.items() if inf == inf_upper]
    return sorted(result, key=lambda e: e["idx"])


def all_inf_names() -> list[str]:
    _ensure_loaded()
    seen: set[str] = set()
    names = []
    for (inf, _) in _index:
        if inf not in seen:
            seen.add(inf)
            names.append(inf)
    return sorted(names)
