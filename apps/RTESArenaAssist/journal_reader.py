from __future__ import annotations
import re
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

def _clean_journal_line(line: str) -> str:
    line = (line or '').strip()
    while line.startswith('&'):
        line = line[1:].strip()
    return line

def _clean_body_text(lines: list[str]) -> str:
    body_text = ' '.join((ln for ln in lines if ln)).strip()
    while body_text.endswith('*'):
        body_text = body_text[:-1].strip()
    return body_text

def parse_journal_entries(text: str) -> list[tuple[Optional[str], Optional[str]]]:
    if not text:
        return []
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [_clean_journal_line(ln) for ln in normalized.split('\n') if _clean_journal_line(ln)]
    if not lines:
        return []
    entries: list[tuple[Optional[str], Optional[str]]] = []
    date_line: Optional[str] = None
    body_lines: list[str] = []

    def flush() -> None:
        nonlocal date_line, body_lines
        if date_line is None:
            return
        body_text = _clean_body_text(body_lines)
        entries.append((date_line or None, body_text or None))
        date_line = None
        body_lines = []
    for line in lines:
        if _looks_like_date_line(line):
            flush()
            date_line = line
            body_lines = []
            continue
        if date_line is None:
            date_line = line
            body_lines = []
            continue
        if line in {'Back', 'More', 'Exit'}:
            continue
        body_lines.append(line)
    flush()
    return entries

def split_journal_lines(text: str) -> tuple[Optional[str], Optional[str]]:
    entries = parse_journal_entries(text)
    if not entries:
        return (None, None)
    return entries[0]
_ESCORT_JOURNAL_MISSING_COMMA_RE = re.compile("^(You have agreed to escort .+?'s .+?, .+?) to (.+ by .+\\.?)$")

def _journal_body_lookup_variants(body: str) -> list[str]:
    body = ' '.join((body or '').split())
    variants: list[str] = []
    m = _ESCORT_JOURNAL_MISSING_COMMA_RE.match(body)
    if m:
        variants.append(f'{m.group(1)}, to {m.group(2)}')
    variants.append(body)
    return variants

def _is_overbroad_journal_match(ja_tmpl: str, placeholders: dict) -> bool:
    if set(placeholders) != {'nc2'}:
        return False
    value = str(placeholders.get('nc2') or '')
    return len(value.split()) > 4 or ',' in value

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
            for variant in _journal_body_lookup_variants(body_en):
                result = ndl.lookup(variant)
                if not result:
                    continue
                ja_tmpl, ph = result
                if _is_overbroad_journal_match(ja_tmpl, ph):
                    continue
                body_ja = ndl.format_japanese(ja_tmpl, ph, lang)
                break
        except Exception:
            body_ja = None
    return (date_ja, body_ja)
__all__ = ['read_journal_raw', 'parse_journal_entries', 'split_journal_lines', 'translate_journal']
