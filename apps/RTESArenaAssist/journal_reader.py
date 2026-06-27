from __future__ import annotations
from typing import Optional
from arena_bridge import ArenaMemoryAnalyzer, JOURNAL_BUFFER_OFFSET, JOURNAL_BUFFER_MAXLEN

def _decode_ascii_chunks(raw: bytes) -> str:
    chunks: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        j = i
        while j < n and (32 <= raw[j] <= 126 or raw[j] in (10, 13)):
            j += 1
        if j > i:
            piece = raw[i:j].decode('ascii', errors='replace')
            if len(piece.strip()) >= 4:
                chunks.append(piece)
        while j < n and (not (32 <= raw[j] <= 126 or raw[j] in (10, 13))):
            j += 1
        i = j
    return '\n'.join(chunks)

def read_journal_raw(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> Optional[str]:
    try:
        raw = analyzer.read_bytes(anchor + JOURNAL_BUFFER_OFFSET, JOURNAL_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return None
    text = _decode_ascii_chunks(raw)
    if not text or len(text.strip()) < 5:
        return None
    return text
_DATE_LINE_PREFIX_RE = None

def _looks_like_date_line(line: str) -> bool:
    import re
    return bool(re.match('^[A-Z][a-z]+,\\s+\\d+', line.strip()))

def split_journal_lines(text: str) -> tuple[Optional[str], Optional[str]]:
    if not text:
        return (None, None)
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.strip() for ln in normalized.split('\n') if ln.strip()]
    if not lines:
        return (None, None)
    date_idx = -1
    for i, ln in enumerate(lines):
        if _looks_like_date_line(ln):
            date_idx = i
            break
    if date_idx == -1:
        date_line = lines[0]
        body_lines = lines[1:]
    else:
        date_line = lines[date_idx]
        body_lines = lines[date_idx + 1:]
    body_text = ' '.join(body_lines).strip()
    if body_text.endswith('*'):
        body_text = body_text[:-1].strip()
    return (date_line or None, body_text or None)

def translate_journal(date_en: Optional[str], body_en: Optional[str], lang: str='ja') -> tuple[Optional[str], Optional[str]]:
    import npc_dialog_lookup as ndl
    date_ja: Optional[str] = None
    body_ja: Optional[str] = None
    if date_en:
        try:
            date_ja = ndl._translate_date(date_en, lang)
        except Exception:
            date_ja = date_en
    if body_en:
        try:
            result = ndl.lookup(body_en)
            if result:
                ja_tmpl, ph = result
                body_ja = ndl.format_japanese(ja_tmpl, ph, lang)
            else:
                body_ja = None
        except Exception:
            body_ja = None
    return (date_ja, body_ja)
__all__ = ['read_journal_raw', 'split_journal_lines', 'translate_journal']
