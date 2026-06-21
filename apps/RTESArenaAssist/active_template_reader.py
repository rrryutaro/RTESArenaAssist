from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from arena_bridge import ArenaMemoryAnalyzer


CURRENT_TEXT_PTR_OFFSET = 0xA844

_RESPONSE_TEXT_BUFFER_RANGES = (
    (0x1044, 512),
    (0x929E, 512),
    (0x9A9E, 512),
)
_RUNTIME_MESSAGE_BUFFER_RANGES = (
    (0x7979, 68),
)


def is_runtime_message_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any(start <= ptr < start + length
               for start, length in _RUNTIME_MESSAGE_BUFFER_RANGES)


def is_response_text_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any(start <= ptr < start + length
               for start, length in _RESPONSE_TEXT_BUFFER_RANGES)


def is_response_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    if is_response_text_buffer_pointer(ptr):
        return True
    return is_runtime_message_buffer_pointer(ptr)


ACTIVE_TEMPLATE_PTR_OFFSETS = tuple(
    range(0xFAB8, 0xFAD8, 2)
)
ACTIVE_TEMPLATE_PTR_OFFSET = 0xFACC

TEMPLATE_RANGE_LOW = 0x4000
TEMPLATE_RANGE_HIGH = 0xC000

TEMPLATE_MAX_LEN = 256

MIN_TEMPLATE_LEN = 4


def _read_template_at(analyzer, anchor, ptr_offset) -> Optional[str]:
    try:
        raw = analyzer.read_bytes(anchor + ptr_offset, 2)
        if len(raw) < 2:
            return None
        ptr = raw[0] | (raw[1] << 8)
    except (OSError, AttributeError):
        return None
    if not (TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH):
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    if not text:
        return None
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def read_active_template(analyzer: "ArenaMemoryAnalyzer",
                          anchor: int) -> Optional[str]:
    return _read_template_at(analyzer, anchor, ACTIVE_TEMPLATE_PTR_OFFSET)


def read_active_templates(analyzer: "ArenaMemoryAnalyzer",
                           anchor: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        t = _read_template_at(analyzer, anchor, off)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


@dataclass(frozen=True)
class ActiveTemplateCandidate:
    source: str
    ptr_slot: Optional[int]
    ptr: int
    text: str


def _read_template_from_ptr(analyzer, anchor, ptr: int) -> Optional[str]:
    if not (TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH):
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    if not text:
        return None
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def read_current_text_pointer(analyzer: "ArenaMemoryAnalyzer",
                              anchor: int) -> Optional[int]:
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        if len(raw) < 2:
            return None
        return raw[0] | (raw[1] << 8)
    except (OSError, AttributeError):
        return None


def read_active_template_candidates(
    analyzer: "ArenaMemoryAnalyzer",
    anchor: int,
) -> list[ActiveTemplateCandidate]:
    out: list[ActiveTemplateCandidate] = []
    seen_ptrs: set[int] = set()

    cur_ptr = read_current_text_pointer(analyzer, anchor)
    if cur_ptr is not None and not is_response_buffer_pointer(cur_ptr):
        text = _read_template_from_ptr(analyzer, anchor, cur_ptr)
        if text is not None:
            out.append(ActiveTemplateCandidate(
                source="current_ptr",
                ptr_slot=None,
                ptr=cur_ptr,
                text=text,
            ))
            seen_ptrs.add(cur_ptr)

    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = analyzer.read_bytes(anchor + off, 2)
            if len(raw) < 2:
                continue
            ptr = raw[0] | (raw[1] << 8)
        except (OSError, AttributeError):
            continue
        if is_response_buffer_pointer(ptr):
            continue
        if ptr in seen_ptrs:
            continue
        text = _read_template_from_ptr(analyzer, anchor, ptr)
        if text is None:
            continue
        out.append(ActiveTemplateCandidate(
            source="active_slot",
            ptr_slot=off,
            ptr=ptr,
            text=text,
        ))
        seen_ptrs.add(ptr)

    return out


def candidate_signature(
    c: "ActiveTemplateCandidate",
) -> tuple[str, Optional[int], int, str]:
    return (c.source, c.ptr_slot, c.ptr, c.text.rstrip())


_INPUT_PROMPT_FACILITY: dict[int, str] = {
    0x75F7: "temple",
    0x739E: "tavern",
    0x7379: "tavern",
    0x65CA: "negotiation",
}

_INPUT_PROMPT_KIND: dict[int, str] = {
    0x75F7: "donate_amount",
    0x739E: "stay_days",
    0x7379: "sneak_yesno",
    0x65CA: "counter_offer",
}


def input_prompt_facility(c: "ActiveTemplateCandidate") -> str:
    return _INPUT_PROMPT_FACILITY.get(c.ptr, "")


def input_prompt_kind(c: "ActiveTemplateCandidate") -> str:
    return _INPUT_PROMPT_KIND.get(c.ptr, "")


_TEMPLATE_SURFACE_KIND: dict[int, str] = {
    0x739E: "tavern_stay_days",
    0x7361: "tavern_sneak_result",
    0x7379: "tavern_sneak_confirm",
    0x73C6: "tavern_sneak_result",
    0x73EA: "tavern_room_contract",
    0x7420: "tavern_cost_show",
    0x7434: "tavern_cost_confirm",
    0x75F7: "temple_donate_amount",
    0x65CA: "negotiation_counter",
}


def template_surface_kind(c: "ActiveTemplateCandidate") -> str:
    return _TEMPLATE_SURFACE_KIND.get(c.ptr, "")


def select_facility_surface_candidate(
    candidates: list["ActiveTemplateCandidate"],
    accepted_surface_kinds: set,
    lookup_hit: callable,
) -> tuple[Optional["ActiveTemplateCandidate"], list[tuple[str, str]]]:
    decisions: list[tuple[str, str]] = []
    selected: Optional["ActiveTemplateCandidate"] = None
    selected_priority = 999

    for c in candidates:
        kind = template_surface_kind(c)
        if kind not in accepted_surface_kinds:
            decisions.append(("rejected", "surface_mismatch"))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(("rejected", "no_lookup_hit"))
                continue
        except Exception:
            decisions.append(("rejected", "lookup_error"))
            continue
        if c.source == "current_ptr":
            prio = 0
        elif c.source == "active_slot":
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(("selected", "ok"))
        else:
            decisions.append(("rejected", "priority_lower"))
    return selected, decisions


def is_active_template_input_prompt(c: "ActiveTemplateCandidate") -> bool:
    return c.ptr in _INPUT_PROMPT_FACILITY


def select_facility_yesno_candidate(
    candidates: list["ActiveTemplateCandidate"],
    expected_prompt_kind: str,
    lookup_hit: callable,
) -> tuple[Optional["ActiveTemplateCandidate"], list[tuple[str, str]]]:
    decisions: list[tuple[str, str]] = []
    selected: Optional["ActiveTemplateCandidate"] = None
    selected_priority = 999

    for c in candidates:
        kind = input_prompt_kind(c)
        if kind != expected_prompt_kind:
            decisions.append(("rejected", "kind_mismatch"))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(("rejected", "no_lookup_hit"))
                continue
        except Exception:
            decisions.append(("rejected", "lookup_error"))
            continue
        if c.source == "current_ptr":
            prio = 0
        elif c.source == "active_slot":
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(("selected", "ok"))
        else:
            decisions.append(("rejected", "priority_lower"))
    return selected, decisions


_IMG_ALLOWED_INPUT_KINDS: dict[str, frozenset] = {
    "YESNO.IMG":   frozenset({"sneak_yesno"}),
    "NEWPOP.IMG":  frozenset({"stay_days", "donate_amount", "counter_offer"}),
    "MENU_RT.IMG": frozenset({"stay_days", "donate_amount", "counter_offer"}),
}
_IMG_ALLOWED_SURFACE_KINDS: dict[str, frozenset] = {
    "YESNO.IMG": frozenset({
        "tavern_sneak_confirm",
        "tavern_sneak_result",
        "tavern_cost_confirm",
    }),
    "NEWPOP.IMG": frozenset({
        "tavern_stay_days", "tavern_sneak_result", "tavern_room_contract",
        "tavern_cost_show", "temple_donate_amount", "negotiation_counter",
    }),
    "MENU_RT.IMG": frozenset({
        "tavern_stay_days", "tavern_sneak_result", "tavern_room_contract",
        "tavern_cost_show", "temple_donate_amount", "negotiation_counter",
    }),
}


def _allowed_input_kinds_for_img(img_name: str) -> Optional[frozenset]:
    return _IMG_ALLOWED_INPUT_KINDS.get((img_name or "").upper())


def _allowed_surface_kinds_for_img(img_name: str) -> Optional[frozenset]:
    return _IMG_ALLOWED_SURFACE_KINDS.get((img_name or "").upper())


def select_active_template_candidate(
    candidates: list["ActiveTemplateCandidate"],
    ctx_key: tuple,
    prev_ctx_key: Optional[tuple],
    prev_signatures: frozenset,
    lookup_hit: callable,
    active_facility: str = "",
    img_name: str = "",
) -> Optional["ActiveTemplateCandidate"]:
    _allowed_input_kinds = _allowed_input_kinds_for_img(img_name)
    _allowed_surface_kinds = _allowed_surface_kinds_for_img(img_name)

    for c in candidates:
        if c.source != "current_ptr":
            continue
        try:
            if lookup_hit(c.text):
                return c
        except Exception:  # noqa: BLE001
            continue

    if active_facility:
        for c in candidates:
            if c.source != "active_slot":
                continue
            facility = input_prompt_facility(c)
            if not facility:
                continue
            if facility != active_facility:
                continue
            if _allowed_input_kinds is not None:
                if input_prompt_kind(c) not in _allowed_input_kinds:
                    continue
            try:
                if lookup_hit(c.text):
                    return c
            except Exception:  # noqa: BLE001
                continue

    if active_facility:
        for c in candidates:
            if c.source != "active_slot":
                continue
            kind = template_surface_kind(c)
            if not kind:
                continue
            kind_facility = kind.split("_", 1)[0]
            if kind_facility != active_facility:
                continue
            if _allowed_surface_kinds is not None:
                if kind not in _allowed_surface_kinds:
                    continue
            try:
                if lookup_hit(c.text):
                    return c
            except Exception:  # noqa: BLE001
                continue

    _ = (ctx_key, prev_ctx_key, prev_signatures)
    return None


__all__ = [
    "ACTIVE_TEMPLATE_PTR_OFFSETS",
    "ACTIVE_TEMPLATE_PTR_OFFSET",
    "CURRENT_TEXT_PTR_OFFSET",
    "TEMPLATE_RANGE_LOW",
    "TEMPLATE_RANGE_HIGH",
    "ActiveTemplateCandidate",
    "candidate_signature",
    "input_prompt_facility",
    "is_active_template_input_prompt",
    "is_response_buffer_pointer",
    "is_response_text_buffer_pointer",
    "is_runtime_message_buffer_pointer",
    "read_active_template",
    "read_active_templates",
    "read_active_template_candidates",
    "read_current_text_pointer",
    "select_active_template_candidate",
]
