from __future__ import annotations
import re
NPC_DIALOG_OFFSET = 4164
CURRENT_TEXT_PTR_OFFSET = 43076
PROMPT_EXTRA_SCAN_OFFSETS = (37532,)
MAGES_MENU_TEXT_OFFSET = 28508
MAGES_MENU_PTR_START = 28416
MAGES_MENU_PTR_END = 28736
DETECT_MAGIC_QUOTE_PREFIX = 'I can tell you if that is magical'
DETECT_MAGIC_ALREADY_KNOWN = 'You already know what that is!'
PROMPT_CACHE_ATTR = '_mages_prompt_resolve_cache'
_RESPONSE_END_RE = re.compile('[?!.]')
_PTR_UNSET = object()

def _printable(raw: bytes) -> str:
    return ''.join((c if 32 <= ord(c) <= 126 else ' ' for c in raw.decode('ascii', errors='replace')))

def resolve_response_prompt(analyzer, anchor: int, *, foreground_ptr=_PTR_UNSET, cache_on=None):
    try:
        raw = analyzer.read_bytes(anchor + NPC_DIALOG_OFFSET, 512)
    except (OSError, AttributeError):
        raw = b''
    if not isinstance(raw, (bytes, bytearray)):
        raw = b''
    extra_chunks: list[bytes] = []
    for off in PROMPT_EXTRA_SCAN_OFFSETS:
        try:
            chunk = analyzer.read_bytes(anchor + off, 160)
        except (OSError, AttributeError):
            chunk = b''
        extra_chunks.append(chunk if isinstance(chunk, (bytes, bytearray)) else b'')
    if foreground_ptr is _PTR_UNSET:
        try:
            raw_ptr = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
        except (OSError, AttributeError):
            raw_ptr = b''
        current_ptr = raw_ptr[0] | raw_ptr[1] << 8 if isinstance(raw_ptr, (bytes, bytearray)) and len(raw_ptr) >= 2 else None
    else:
        current_ptr = foreground_ptr
    cache_key = (bytes(raw), tuple((bytes(c) for c in extra_chunks)), current_ptr)
    if cache_on is not None:
        cache = getattr(cache_on, PROMPT_CACHE_ATTR, None)
        if cache is not None and cache[0] == cache_key:
            return cache[1]
    result = _resolve(analyzer, anchor, raw, extra_chunks, current_ptr)
    if cache_on is not None:
        setattr(cache_on, PROMPT_CACHE_ATTR, (cache_key, result))
    return result

def _resolve(analyzer, anchor: int, raw: bytes, extra_chunks: list[bytes], current_ptr):
    try:
        from npc_dialog_lookup import lookup as _nd_lookup
        from npc_dialog_lookup import format_japanese as _nd_format
        from normal_play.mages_spellmaker_render import _SPELLMAKER_PROMPT_LITERALS, _SPELLMAKER_PROMPT_FRAGMENT_LITERALS
    except Exception:
        return None

    def _translated(literal: str):
        res = _nd_lookup(literal)
        if not res:
            return None
        try:
            return (literal, _nd_format(res[0], res[1]))
        except Exception:
            return (literal, literal)
    text = _printable(raw)
    literal_text = text + ' ' + ' '.join((_printable(c) for c in extra_chunks))
    normalized_text = ' '.join(literal_text.split())
    if DETECT_MAGIC_QUOTE_PREFIX in normalized_text and isinstance(current_ptr, int) and (MAGES_MENU_PTR_START <= current_ptr < MAGES_MENU_PTR_END):
        try:
            raw_known = analyzer.read_bytes(anchor + MAGES_MENU_TEXT_OFFSET, 80)
        except (OSError, AttributeError):
            raw_known = b''
        known = bytes(raw_known).split(b'\x00', 1)[0].decode('ascii', errors='replace').strip()
        if known == DETECT_MAGIC_ALREADY_KNOWN:
            found = _translated(DETECT_MAGIC_ALREADY_KNOWN)
            if found:
                return found
    for literal in _SPELLMAKER_PROMPT_LITERALS:
        if literal in normalized_text:
            found = _translated(literal)
            if found:
                return found
    lowered_text = normalized_text.lower()
    for needles, literal in _SPELLMAKER_PROMPT_FRAGMENT_LITERALS:
        if all((needle in lowered_text for needle in needles)):
            found = _translated(literal)
            if found:
                return found
    seen: set[str] = set()
    for i, ch in enumerate(text):
        if not ch.isupper():
            continue
        seg = text[i:i + 160]
        end = _RESPONSE_END_RE.search(seg)
        if not end:
            continue
        cand = ' '.join(seg[:end.end()].split())
        if len(cand) < 10 or cand in seen:
            continue
        seen.add(cand)
        found = _translated(cand)
        if found:
            return found
    return None
__all__ = ['NPC_DIALOG_OFFSET', 'PROMPT_EXTRA_SCAN_OFFSETS', 'MAGES_MENU_TEXT_OFFSET', 'MAGES_MENU_PTR_START', 'MAGES_MENU_PTR_END', 'DETECT_MAGIC_QUOTE_PREFIX', 'DETECT_MAGIC_ALREADY_KNOWN', 'PROMPT_CACHE_ATTR', 'resolve_response_prompt']
