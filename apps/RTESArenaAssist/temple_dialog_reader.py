from __future__ import annotations

import re
from typing import NamedTuple, Optional


class TempleResponseCandidate(NamedTuple):
    text: str
    lookup_hit: bool
    source_offset: int
    raw_text: str = ""


_FMT_PREFIX_RE = re.compile(r"^([0-9]{3})([A-Za-z].*)$", re.S)

_HEAL_OFFER_CONTAM_RE = re.compile(
    r"Can I give you some of\s+"
    r"(.+?(?:is in perfect condition|thou art healed).*)$",
    re.S,
)

_HEALED_RESULT_RE = re.compile(
    r"^(?P<subject>.+?)(?P<suffix>,\s*thou art healed.*)$",
    re.S,
)
_PERFECT_RESULT_RE = re.compile(
    r"^(?P<subject>.+?)(?P<suffix>\s+is in perfect condition.*)$",
    re.S,
)


def _strip_heal_offer_prefix(text: str) -> str:
    s = text or ""
    if "Can I give you some of" not in s:
        return s
    m = _HEAL_OFFER_CONTAM_RE.search(s)
    if m:
        return " ".join(m.group(1).split())
    return s


def _last_subject_token(prefix: str) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'_-]*", prefix or "")
    if not tokens:
        return ""
    token = tokens[-1]
    if token[:1].islower():
        for idx, ch in enumerate(token):
            if ch.isupper():
                return token[idx:]
    return token


def _repair_result_subject_prefix(text: str) -> str:
    s = text or ""
    for rx in (_HEALED_RESULT_RE, _PERFECT_RESULT_RE):
        m = rx.match(s)
        if not m:
            continue
        subject = " ".join((m.group("subject") or "").split()).strip()
        if not subject:
            continue
        if not re.search(r"[\s,.;:]", subject):
            return s
        repaired = _last_subject_token(subject)
        if repaired:
            return repaired + m.group("suffix")
    return s


def canonicalize_priest_text(text: str, prev_byte: Optional[int] = None) -> str:
    s = text or ""
    m = _FMT_PREFIX_RE.match(s)
    if m:
        rest = m.group(2)
        if prev_byte == 0x09:
            s = rest
        elif is_temple_priest_text(rest):
            s = rest
    return _repair_result_subject_prefix(_strip_heal_offer_prefix(s))


class TempleResponseRead(NamedTuple):
    candidates: list
    current_ptr: int | None


_RESPONSE_REGIONS: tuple[tuple[int, int], ...] = ((0x929E, 512), (0x1040, 0x200))
_MIN_RESPONSE_LEN = 5

_CURRENT_TEXT_PTR_OFFSET = 0xA844

TEMPLE_MENU_PTR_LO = 0x725F
TEMPLE_MENU_PTR_HI = 0x765F

_POPUP_GATE_OFFSET = 0x8F74
_GATE_MENU_FOREGROUND = 0x51
_GATE_POPUP_OPEN = 0x00


def read_popup_gate(analyzer, anchor: int) -> int | None:
    try:
        raw = analyzer.read_bytes(anchor + _POPUP_GATE_OFFSET, 1)
    except (OSError, AttributeError):
        return None
    if not raw:
        return None
    return raw[0]


def gate_menu_foreground(gate: int | None) -> bool:
    return gate == _GATE_MENU_FOREGROUND


def gate_popup_open(gate: int | None) -> bool:
    return gate == _GATE_POPUP_OPEN


_GATE_HYSTERESIS_POLLS = 2


def temple_gate_foreground(w, analyzer, anchor: int) -> tuple[bool, bool, int]:
    gate = read_popup_gate(analyzer, anchor)
    prev_val = getattr(w, "_temple_gate_stable_value", None)
    prev_cnt = int(getattr(w, "_temple_gate_stable_count", 0) or 0)
    if gate == prev_val:
        cnt = prev_cnt + 1
    else:
        cnt = 1
    w._temple_gate_stable_value = gate
    w._temple_gate_stable_count = cnt
    stable = cnt >= _GATE_HYSTERESIS_POLLS
    menu_fg = bool(stable and gate == _GATE_MENU_FOREGROUND)
    popup_fg = bool(stable and gate == _GATE_POPUP_OPEN)
    return menu_fg, popup_fg, (gate if gate is not None else -1)


_PHASE_NPC_OFFSET = 0xA845
_PHASE_AUX_OFFSET = 0xA847
_PHASE_MODE_OFFSET = 0xA84D
_PHASE_SELECT_OFFSET = 0xA83B
_PHASE_ACTIVE_VALUE = 0x75
_RESULT_VIEW_PTR_OFFSET = 0x8F6E
_RESULT_INTENT_HINT_OFFSET = 0xADB6
_BLESS_RESULT_INTENT_VALUE = 0x77
_BLESS_RESULT_VIEW_LO_BYTES = frozenset({0x59, 0x5A})
_LEGACY_BLESS_RESULT_PTR = 0x1D5A


class TempleViewState(NamedTuple):

    kind: str
    phase: str
    values: dict


def _read_u8(analyzer, anchor: int, off: int) -> int | None:
    try:
        b = analyzer.read_bytes(anchor + off, 1)
        return b[0] if b else None
    except (OSError, AttributeError):
        return None


def _read_u16(analyzer, anchor: int, off: int) -> int | None:
    try:
        b = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if not b or len(b) < 2:
        return None
    return b[0] | (b[1] << 8)


def classify_temple_view(analyzer, anchor: int) -> TempleViewState:
    gate = _read_u8(analyzer, anchor, _POPUP_GATE_OFFSET)
    npc = _read_u8(analyzer, anchor, _PHASE_NPC_OFFSET)
    sel = _read_u8(analyzer, anchor, _PHASE_SELECT_OFFSET)
    aux = _read_u8(analyzer, anchor, _PHASE_AUX_OFFSET)
    mode = _read_u8(analyzer, anchor, _PHASE_MODE_OFFSET)
    result_ptr = _read_u16(analyzer, anchor, _RESULT_VIEW_PTR_OFFSET)
    intent = _read_u8(analyzer, anchor, _RESULT_INTENT_HINT_OFFSET)
    result_lo = (result_ptr & 0xFF) if isinstance(result_ptr, int) else None
    values = {
        "gate": gate,
        "npc": npc,
        "sel": sel,
        "aux": aux,
        "mode": mode,
        "result_ptr": result_ptr,
        "result_lo": result_lo,
        "intent": intent,
    }

    if gate == _GATE_MENU_FOREGROUND:
        return TempleViewState("menu", "menu", values)

    if (
        sel == _PHASE_ACTIVE_VALUE
        and npc == 0x00
        and aux == 0x00
        and (
            result_ptr == _LEGACY_BLESS_RESULT_PTR
            or (
                intent == _BLESS_RESULT_INTENT_VALUE
                and result_lo in _BLESS_RESULT_VIEW_LO_BYTES
            )
        )
    ):
        return TempleViewState("donation_blessing", "select_input", values)

    if sel == _PHASE_ACTIVE_VALUE:
        return TempleViewState("select_input", "select_input", values)

    if npc == _PHASE_ACTIVE_VALUE:
        return TempleViewState("service_result", "result", values)

    return TempleViewState("out", "out", values)

_RESULT_EDGE_OFFSETS = (0x8F7C, 0x8F7E, 0x8F92, 0x8F94)


def classify_temple_phase(analyzer, anchor: int) -> tuple[str, dict]:
    view = classify_temple_view(analyzer, anchor)
    return view.phase, view.values


def read_temple_result_edge_signature(analyzer, anchor: int
                                      ) -> tuple[int, ...] | None:
    try:
        vals = []
        for off in _RESULT_EDGE_OFFSETS:
            b = analyzer.read_bytes(anchor + off, 1)
            if not b:
                return None
            vals.append(b[0])
        return tuple(vals)
    except (OSError, AttributeError):
        return None


def is_temple_priest_text(text: str) -> bool:
    s = " ".join((text or "").split())
    if not s:
        return False
    if s.startswith("Receive our blessings"):
        return True
    if "thou art healed" in s:
        return True
    if "is in perfect condition" in s:
        return True
    if s.startswith("How much do you wish to donate?"):
        return True
    if s.startswith("Curing "):
        return True
    if s.startswith("We humbly beg your forgivness"):
        return True
    if s.startswith("This service will cost"):
        return True
    if s.startswith("Can't you afford it"):
        return True
    return False


def is_transient_priest_text(text: str) -> bool:
    return " ".join((text or "").split()).startswith("Curing ")


def lookup_temple_priest_text(text: str):
    if not is_temple_priest_text(text):
        return None
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        return None
    try:
        return ndl.lookup(text)
    except Exception:  # noqa: BLE001
        return None


def format_temple_priest_text(text: str) -> str | None:
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        return None
    result = lookup_temple_priest_text(text)
    if result is None:
        return None
    ja_tmpl, placeholders = result
    try:
        return ndl.format_japanese(ja_tmpl, placeholders)
    except Exception:  # noqa: BLE001
        return None


def read_current_text_pointer(analyzer, anchor: int) -> int | None:
    try:
        raw = analyzer.read_bytes(anchor + _CURRENT_TEXT_PTR_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if not raw or len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def pointer_in_menu_group(ptr: int | None) -> bool:
    return ptr is not None and TEMPLE_MENU_PTR_LO <= ptr <= TEMPLE_MENU_PTR_HI


def _scan_runs(analyzer, anchor: int) -> list[tuple[int, str, Optional[int]]]:
    out: list[tuple[int, str, Optional[int]]] = []
    for base, length in _RESPONSE_REGIONS:
        try:
            raw = analyzer.read_bytes(anchor + base, length)
        except (OSError, AttributeError):
            continue
        if not raw:
            continue
        n = len(raw)
        i = 0
        while i < n:
            if not (0x20 <= raw[i] <= 0x7E):
                i += 1
                continue
            j = i
            while j < n and 0x20 <= raw[j] <= 0x7E:
                j += 1
            text = raw[i:j].decode("ascii", errors="replace").strip()
            if len(text) >= _MIN_RESPONSE_LEN:
                prev_b = raw[i - 1] if i > 0 else None
                out.append((base + i, text, prev_b))
            i = j + 1
    return out


def read_temple_response_candidates(analyzer, anchor: int
                                    ) -> TempleResponseRead:
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        ndl = None
    candidates: list[TempleResponseCandidate] = []
    seen: set[tuple[int, str]] = set()
    for off, raw_text, prev_b in _scan_runs(analyzer, anchor):
        canon = canonicalize_priest_text(raw_text, prev_b)
        if not is_temple_priest_text(canon):
            continue
        key = (off, canon)
        if key in seen:
            continue
        seen.add(key)
        hit = False
        if ndl is not None:
            try:
                hit = ndl.lookup(canon) is not None
            except Exception:  # noqa: BLE001
                hit = False
        if not hit:
            continue
        candidates.append(TempleResponseCandidate(
            text=canon, lookup_hit=True, source_offset=off,
            raw_text=raw_text))
    try:
        current_ptr = read_current_text_pointer(analyzer, anchor)
    except Exception:  # noqa: BLE001
        current_ptr = None
    return TempleResponseRead(candidates, current_ptr)


def has_temple_response_surface(analyzer, anchor: int) -> bool:
    read = read_temple_response_candidates(analyzer, anchor)
    return bool(read.candidates)


__all__ = [
    "TempleResponseCandidate",
    "TempleResponseRead",
    "TempleViewState",
    "canonicalize_priest_text",
    "classify_temple_phase",
    "classify_temple_view",
    "temple_gate_foreground",
    "format_temple_priest_text",
    "gate_menu_foreground",
    "gate_popup_open",
    "has_temple_response_surface",
    "is_temple_priest_text",
    "is_transient_priest_text",
    "lookup_temple_priest_text",
    "pointer_in_menu_group",
    "read_current_text_pointer",
    "read_popup_gate",
    "read_temple_result_edge_signature",
    "read_temple_response_candidates",
]
