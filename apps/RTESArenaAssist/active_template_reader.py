from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from arena_bridge import ArenaMemoryAnalyzer
CURRENT_TEXT_PTR_OFFSET = 43076
_MESSAGE_TEXT_BUFFER_RANGE = (39582, 512)
_RESPONSE_TEXT_BUFFER_RANGES = ((4164, 512), (37534, 512), _MESSAGE_TEXT_BUFFER_RANGE)
_RUNTIME_MESSAGE_BUFFER_RANGES = ((31097, 68),)

def is_runtime_message_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any((start <= ptr < start + length for start, length in _RUNTIME_MESSAGE_BUFFER_RANGES))
_DEATH_POPUP_TEXT_PTRS = frozenset({31535, 31594})

def is_death_popup_text_pointer(ptr: int | None) -> bool:
    return ptr in _DEATH_POPUP_TEXT_PTRS

def is_response_text_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    return any((start <= ptr < start + length for start, length in _RESPONSE_TEXT_BUFFER_RANGES))

def is_message_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    start, length = _MESSAGE_TEXT_BUFFER_RANGE
    return start <= ptr < start + length

def message_buffer_remaining(ptr: int | None) -> int | None:
    if ptr is None:
        return None
    start, length = _MESSAGE_TEXT_BUFFER_RANGE
    end = start + length
    if not start <= ptr < end:
        return None
    return end - ptr

def is_response_buffer_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    if is_response_text_buffer_pointer(ptr):
        return True
    return is_runtime_message_buffer_pointer(ptr)

def is_dialog_text_pointer(ptr: int | None) -> bool:
    if ptr is None:
        return False
    if is_response_buffer_pointer(ptr):
        return True
    return TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH

def read_dialog_text_foreground(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> tuple[bool, Optional[int]]:
    ptr = read_current_text_pointer(analyzer, anchor)
    return (is_dialog_text_pointer(ptr), ptr)
ACTIVE_TEMPLATE_PTR_OFFSETS = tuple(range(64184, 64216, 2))
ACTIVE_TEMPLATE_PTR_OFFSET = 64204
TEMPLATE_RANGE_LOW = 16384
TEMPLATE_RANGE_HIGH = 49152
TEMPLATE_MAX_LEN = 256
MIN_TEMPLATE_LEN = 4

def _read_template_at(analyzer, anchor, ptr_offset) -> Optional[str]:
    try:
        raw = analyzer.read_bytes(anchor + ptr_offset, 2)
        if len(raw) < 2:
            return None
        ptr = raw[0] | raw[1] << 8
    except (OSError, AttributeError):
        return None
    if not TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH:
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b'\x00')
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode('ascii', errors='replace')
    if not text:
        return None
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum((1 for c in text if 32 <= ord(c) <= 126))
    if printable / len(text) < 0.9:
        return None
    return text

def read_active_template(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> Optional[str]:
    return _read_template_at(analyzer, anchor, ACTIVE_TEMPLATE_PTR_OFFSET)

def read_active_templates(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> list[str]:
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
    if not TEMPLATE_RANGE_LOW <= ptr < TEMPLATE_RANGE_HIGH:
        return None
    try:
        buf = analyzer.read_bytes(anchor + ptr, TEMPLATE_MAX_LEN)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b'\x00')
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode('ascii', errors='replace')
    if not text:
        return None
    if len(text.rstrip()) < MIN_TEMPLATE_LEN:
        return None
    printable = sum((1 for c in text if 32 <= ord(c) <= 126))
    if printable / len(text) < 0.9:
        return None
    return text

def read_current_text_pointer(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> Optional[int]:
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        if len(raw) < 2:
            return None
        return raw[0] | raw[1] << 8
    except (OSError, AttributeError):
        return None
DISPLAY_OCCURRENCE_OFFSET = 37366

def read_display_occurrence(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> Optional[int]:
    try:
        raw = analyzer.read_bytes(anchor + DISPLAY_OCCURRENCE_OFFSET, 4)
        if len(raw) < 4:
            return None
        return raw[0] | raw[1] << 8 | raw[2] << 16 | raw[3] << 24
    except (OSError, AttributeError):
        return None

def read_active_template_candidates(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> list[ActiveTemplateCandidate]:
    out: list[ActiveTemplateCandidate] = []
    seen_ptrs: set[int] = set()
    cur_ptr = read_current_text_pointer(analyzer, anchor)
    if cur_ptr is not None and (not is_response_buffer_pointer(cur_ptr)):
        text = _read_template_from_ptr(analyzer, anchor, cur_ptr)
        if text is not None:
            out.append(ActiveTemplateCandidate(source='current_ptr', ptr_slot=None, ptr=cur_ptr, text=text))
            seen_ptrs.add(cur_ptr)
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = analyzer.read_bytes(anchor + off, 2)
            if len(raw) < 2:
                continue
            ptr = raw[0] | raw[1] << 8
        except (OSError, AttributeError):
            continue
        if is_response_buffer_pointer(ptr):
            continue
        if ptr in seen_ptrs:
            continue
        text = _read_template_from_ptr(analyzer, anchor, ptr)
        if text is None:
            continue
        out.append(ActiveTemplateCandidate(source='active_slot', ptr_slot=off, ptr=ptr, text=text))
        seen_ptrs.add(ptr)
    return out

def candidate_signature(c: 'ActiveTemplateCandidate') -> tuple[str, Optional[int], int, str]:
    return (c.source, c.ptr_slot, c.ptr, c.text.rstrip())
_SCREEN_IMAGES: dict[str, tuple] = {'confirm': ('YESNO.IMG',), 'popup': ('NEWPOP.IMG', 'MENU_RT.IMG')}

@dataclass(frozen=True)
class TemplateTable:
    input_kind: dict
    surface_kind: dict
    img_input: dict
    img_surface: dict
    confirm_only: frozenset = field(default_factory=frozenset)

def build_template_table(*declaration_groups) -> TemplateTable:
    input_kind: dict[int, str] = {}
    surface_kind: dict[int, str] = {}
    img_input: dict[str, set] = {i: set() for imgs in _SCREEN_IMAGES.values() for i in imgs}
    img_surface: dict[str, set] = {i: set() for imgs in _SCREEN_IMAGES.values() for i in imgs}
    confirm_only: set[int] = set()
    for rows in declaration_groups:
        for ptr, ikind, skind, iimgs, simgs in rows:
            if skind and tuple(simgs) == ('confirm',):
                confirm_only.add(ptr)
            if ikind:
                input_kind[ptr] = ikind
                for img in (i for scr in iimgs for i in _SCREEN_IMAGES[scr]):
                    img_input[img].add(ikind)
            if skind:
                surface_kind[ptr] = skind
                for img in (i for scr in simgs for i in _SCREEN_IMAGES[scr]):
                    img_surface[img].add(skind)
    return TemplateTable(input_kind=input_kind, surface_kind=surface_kind, img_input={k: frozenset(v) for k, v in img_input.items()}, img_surface={k: frozenset(v) for k, v in img_surface.items()}, confirm_only=frozenset(confirm_only))
COUNTER_OFFER_DECLARATIONS: tuple = ((26058, 'counter_offer', 'negotiation_counter', ('popup',), ('popup',)),)
COUNTER_OFFER_TABLE: TemplateTable = build_template_table(COUNTER_OFFER_DECLARATIONS)

def declared_template_pointers(*declaration_groups) -> frozenset:
    return frozenset((ptr for rows in declaration_groups for ptr, ikind, skind, _iimgs, _simgs in rows if ikind or skind))

def template_table_pointers(table: TemplateTable) -> frozenset:
    return frozenset(table.input_kind) | frozenset(table.surface_kind)

def input_prompt_kind(c: 'ActiveTemplateCandidate', table: TemplateTable) -> str:
    return table.input_kind.get(c.ptr, '')

def template_surface_kind(c: 'ActiveTemplateCandidate', table: TemplateTable) -> str:
    return table.surface_kind.get(c.ptr, '')

def is_confirm_only_template(c: 'ActiveTemplateCandidate', table: TemplateTable) -> bool:
    return c.ptr in table.confirm_only

def surface_kind_of_pointer(ptr, table: TemplateTable) -> str:
    if ptr is None:
        return ''
    return table.surface_kind.get(ptr, '')

def select_facility_surface_candidate(candidates: list['ActiveTemplateCandidate'], accepted_surface_kinds: set, lookup_hit: callable, table: TemplateTable) -> tuple[Optional['ActiveTemplateCandidate'], list[tuple[str, str]]]:
    decisions: list[tuple[str, str]] = []
    selected: Optional['ActiveTemplateCandidate'] = None
    selected_priority = 999
    for c in candidates:
        kind = template_surface_kind(c, table)
        if kind not in accepted_surface_kinds:
            decisions.append(('rejected', 'surface_mismatch'))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(('rejected', 'no_lookup_hit'))
                continue
        except Exception:
            decisions.append(('rejected', 'lookup_error'))
            continue
        if c.source == 'current_ptr':
            prio = 0
        elif c.source == 'active_slot':
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(('selected', 'ok'))
        else:
            decisions.append(('rejected', 'priority_lower'))
    return (selected, decisions)

def select_facility_yesno_candidate(candidates: list['ActiveTemplateCandidate'], expected_prompt_kind: str, lookup_hit: callable, table: TemplateTable) -> tuple[Optional['ActiveTemplateCandidate'], list[tuple[str, str]]]:
    decisions: list[tuple[str, str]] = []
    selected: Optional['ActiveTemplateCandidate'] = None
    selected_priority = 999
    for c in candidates:
        kind = input_prompt_kind(c, table)
        if kind != expected_prompt_kind:
            decisions.append(('rejected', 'kind_mismatch'))
            continue
        try:
            if not lookup_hit(c.text):
                decisions.append(('rejected', 'no_lookup_hit'))
                continue
        except Exception:
            decisions.append(('rejected', 'lookup_error'))
            continue
        if c.source == 'current_ptr':
            prio = 0
        elif c.source == 'active_slot':
            prio = 1
        else:
            prio = 2
        if prio < selected_priority:
            selected = c
            selected_priority = prio
            decisions.append(('selected', 'ok'))
        else:
            decisions.append(('rejected', 'priority_lower'))
    return (selected, decisions)

def _allowed_input_kinds_for_img(img_name: str, table: TemplateTable) -> Optional[frozenset]:
    return table.img_input.get((img_name or '').upper())

def _allowed_surface_kinds_for_img(img_name: str, table: TemplateTable) -> Optional[frozenset]:
    return table.img_surface.get((img_name or '').upper())

def select_foreground_candidate(candidates: list['ActiveTemplateCandidate'], lookup_hit: callable) -> Optional['ActiveTemplateCandidate']:
    for c in candidates:
        if c.source != 'current_ptr':
            continue
        try:
            if lookup_hit(c.text):
                return c
        except Exception:
            continue
    return None

def select_active_template_candidate(candidates: list['ActiveTemplateCandidate'], table: TemplateTable, lookup_hit: callable, img_name: str='') -> Optional['ActiveTemplateCandidate']:
    _allowed_input_kinds = _allowed_input_kinds_for_img(img_name, table)
    _allowed_surface_kinds = _allowed_surface_kinds_for_img(img_name, table)
    _foreground = select_foreground_candidate(candidates, lookup_hit)
    if _foreground is not None:
        return _foreground
    for c in candidates:
        if c.source != 'active_slot':
            continue
        ikind = input_prompt_kind(c, table)
        if not ikind:
            continue
        if _allowed_input_kinds is not None:
            if ikind not in _allowed_input_kinds:
                continue
        try:
            if lookup_hit(c.text):
                return c
        except Exception:
            continue
    for c in candidates:
        if c.source != 'active_slot':
            continue
        kind = template_surface_kind(c, table)
        if not kind:
            continue
        if _allowed_surface_kinds is not None:
            if kind not in _allowed_surface_kinds:
                continue
        try:
            if lookup_hit(c.text):
                return c
        except Exception:
            continue
    return None
__all__ = ['ACTIVE_TEMPLATE_PTR_OFFSETS', 'ACTIVE_TEMPLATE_PTR_OFFSET', 'CURRENT_TEXT_PTR_OFFSET', 'DISPLAY_OCCURRENCE_OFFSET', 'TEMPLATE_RANGE_LOW', 'TEMPLATE_RANGE_HIGH', 'ActiveTemplateCandidate', 'COUNTER_OFFER_DECLARATIONS', 'COUNTER_OFFER_TABLE', 'TemplateTable', 'build_template_table', 'declared_template_pointers', 'template_table_pointers', 'surface_kind_of_pointer', 'candidate_signature', 'is_dialog_text_pointer', 'is_message_buffer_pointer', 'message_buffer_remaining', 'is_response_buffer_pointer', 'is_response_text_buffer_pointer', 'is_runtime_message_buffer_pointer', 'read_active_template', 'read_active_templates', 'read_active_template_candidates', 'read_current_text_pointer', 'read_dialog_text_foreground', 'read_display_occurrence', 'select_active_template_candidate', 'select_foreground_candidate']
