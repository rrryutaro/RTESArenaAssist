from __future__ import annotations
from typing import Iterable, Optional
_EMPTY_RUN_END = 4
_PRINTABLE_MIN = 0.7

def read_block(analyzer, address: int, *, sizes: Iterable[int], template_keys: Optional[frozenset]=None) -> str:
    data = b''
    for size in sizes:
        try:
            data = analyzer.read_bytes(address, size)
            if data:
                break
        except (OSError, AttributeError):
            continue
    if not data:
        return ''
    text_parts: list[str] = []
    empty_run = 0
    for raw in data.split(b'\x00'):
        if not raw:
            empty_run += 1
            if empty_run >= _EMPTY_RUN_END and text_parts:
                break
            continue
        empty_run = 0
        try:
            s = raw.decode('ascii', errors='replace').strip()
        except Exception:
            if text_parts:
                break
            continue
        if not s:
            continue
        printable = sum((1 for c in s if 32 <= ord(c) < 127))
        if printable / max(len(s), 1) < _PRINTABLE_MIN:
            if text_parts:
                break
            continue
        if len(s) < 3 and text_parts:
            continue
        text_parts.append(s)
    text = ' '.join(text_parts).strip()
    if not text or not template_keys:
        return text
    import npc_dialog_lookup as npcd
    trimmed = npcd.body_head_trim(text, keys=template_keys)
    return trimmed if trimmed is not None else text
__all__ = ['read_block']
