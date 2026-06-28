from __future__ import annotations
import logging
import re
from typing import NamedTuple
_log = logging.getLogger(__name__)
RESPONSE_OFFSETS: tuple[int, ...] = (37534, 4164, 39582)
RESPONSE_READ_LEN = 512
MIN_RESPONSE_LEN = 5
RESPONSE_SCAN_START = 4164
RESPONSE_SCAN_LEN = 768
RESPONSE_SCAN_WINDOW = 220
CURRENT_TEXT_PTR_OFFSET = 43076
_EMBEDDED_RESPONSE_MARKERS: tuple[str, ...] = ('Fixing that ', 'Sure I could fix that ', 'Fine. I can get it done in ', "Fine, I'll charge you ", 'I can cut down the time', 'I can cut the cost', "Then I'll get started", "Good, I'll get to it", 'I understand. You might consider', 'Well, if you change your mind')
_EMBEDDED_RESPONSE_TERMINATORS: tuple[str, ...] = ('Sound fair?', 'get started?', 'Is that okay?', 'How many days can you wait?', 'How much gold do you want to spend?', 'right away...', 'as soon as I can.', 'very fair prices...', "I'll be here.")
_RAW_C_PLACEHOLDER_RE = re.compile('%(?:lu|ld|u|d|s|mm|i|t|a)\\b')

class ResponseCandidate(NamedTuple):
    text: str
    lookup_hit: bool
    source_offset: int

def read_current_text_pointer(analyzer, anchor: int) -> int | None:
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | raw[1] << 8

def candidate_contains_pointer(candidate: ResponseCandidate, ptr: int | None) -> bool:
    if ptr is None:
        return False
    return candidate.source_offset <= ptr < candidate.source_offset + RESPONSE_READ_LEN

def _read_one(analyzer, anchor: int, offset: int) -> str:
    try:
        raw = analyzer.read_bytes(anchor + offset, RESPONSE_READ_LEN)
    except (OSError, AttributeError):
        return ''
    if not raw:
        return ''
    start = 0
    while start < len(raw) and (not 32 <= raw[start] <= 126):
        start += 1
    if start >= len(raw):
        return ''
    nul = raw.find(b'\x00', start)
    end = nul if nul != -1 else len(raw)
    text = raw[start:end].decode('ascii', errors='replace').strip()
    if len(text) < MIN_RESPONSE_LEN:
        return ''
    printable = sum((1 for c in text if 32 <= ord(c) <= 126))
    if printable / max(len(text), 1) < 0.85:
        return ''
    return text

def _lookup_embedded_response(text: str, ndl) -> str | None:
    if not text or ndl is None:
        return None
    for marker in _EMBEDDED_RESPONSE_MARKERS:
        start = text.find(marker)
        if start <= 0:
            continue
        candidate = text[start:].strip()
        try:
            if ndl.lookup(candidate) is not None:
                return candidate
        except Exception:
            continue
    return None

def _has_unrendered_c_placeholder(text: str) -> bool:
    return bool(_RAW_C_PLACEHOLDER_RE.search(text or ''))

def _normalize_printable_window(raw: bytes) -> str:
    chars = [chr(b) if 32 <= b <= 126 else ' ' for b in raw]
    return ' '.join(''.join(chars).split())

def _trim_embedded_response(text: str) -> str:
    best_end: int | None = None
    for terminator in _EMBEDDED_RESPONSE_TERMINATORS:
        pos = text.find(terminator)
        if pos == -1:
            continue
        end = pos + len(terminator)
        if best_end is None or end < best_end:
            best_end = end
    if best_end is not None:
        return text[:best_end].strip()
    return text.strip()

def _scan_embedded_response_region(analyzer, anchor: int, ndl) -> list[ResponseCandidate]:
    if ndl is None:
        return []
    try:
        raw = analyzer.read_bytes(anchor + RESPONSE_SCAN_START, RESPONSE_SCAN_LEN)
    except (OSError, AttributeError):
        return []
    if not raw:
        return []
    candidates: list[ResponseCandidate] = []
    seen: set[tuple[int, str]] = set()
    for marker in _EMBEDDED_RESPONSE_MARKERS:
        marker_b = marker.encode('ascii', errors='ignore')
        pos = raw.find(marker_b)
        while pos != -1:
            window = raw[pos:pos + RESPONSE_SCAN_WINDOW]
            text = _trim_embedded_response(_normalize_printable_window(window))
            if text and (not _has_unrendered_c_placeholder(text)):
                try:
                    hit = ndl.lookup(text) is not None
                except Exception:
                    hit = False
                if hit:
                    source_offset = RESPONSE_SCAN_START + pos
                    key = (source_offset, text)
                    if key not in seen:
                        candidates.append(ResponseCandidate(text=text, lookup_hit=True, source_offset=source_offset))
                        seen.add(key)
            pos = raw.find(marker_b, pos + 1)
    return candidates

def read_response_candidates_all(analyzer, anchor: int) -> list[ResponseCandidate]:
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        ndl = None
    candidates: list[ResponseCandidate] = []
    for off in RESPONSE_OFFSETS:
        text = _read_one(analyzer, anchor, off)
        if not text:
            continue
        hit = False
        if ndl is not None and (not _has_unrendered_c_placeholder(text)):
            try:
                hit = ndl.lookup(text) is not None
            except Exception:
                hit = False
            if not hit:
                embedded = _lookup_embedded_response(text, ndl)
                if embedded:
                    text = embedded
                    hit = True
        candidates.append(ResponseCandidate(text=text, lookup_hit=hit, source_offset=off))
    seen_candidates = {(c.source_offset, c.text) for c in candidates}
    for scanned in _scan_embedded_response_region(analyzer, anchor, ndl):
        key = (scanned.source_offset, scanned.text)
        if key in seen_candidates:
            continue
        candidates.append(scanned)
        seen_candidates.add(key)
    return candidates

def read_response_candidate(analyzer, anchor: int) -> ResponseCandidate | None:
    candidates = read_response_candidates_all(analyzer, anchor)
    if not candidates:
        return None
    ptr = read_current_text_pointer(analyzer, anchor)
    pointer_hits = [c for c in candidates if candidate_contains_pointer(c, ptr)]
    valid_pointer_hits = [c for c in pointer_hits if not _has_unrendered_c_placeholder(c.text)]
    if valid_pointer_hits:
        lookup_pointer_hits = [c for c in valid_pointer_hits if c.lookup_hit]
        selectable = lookup_pointer_hits or valid_pointer_hits
        if ptr is not None:
            return min(selectable, key=lambda c: (ptr - c.source_offset if c.source_offset <= ptr else RESPONSE_READ_LEN, -len(c.text)))
        return selectable[0]
    hits = [c for c in candidates if c.lookup_hit]
    if hits:
        return hits[0]
    return max(candidates, key=lambda c: len(c.text))
