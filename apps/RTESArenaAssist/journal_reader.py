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
    entries: list[tuple[Optional[str], Optional[str]]] = []
    for chunk in text.split('&'):
        normalized = chunk.replace('\r\n', '\n').replace('\r', '\n')
        lines: list[str] = []
        for raw_line in normalized.split('\n'):
            cleaned = _clean_journal_line(raw_line)
            if cleaned and cleaned not in {'Back', 'More', 'Exit'}:
                lines.append(cleaned)
        if not lines:
            continue
        date_line = lines[0]
        if not is_journal_date_header(date_line):
            continue
        body_text = _clean_body_text(lines[1:])
        entries.append((date_line or None, body_text or None))
    return entries

def is_journal_date_header(line: str) -> bool:
    if not (line or '').strip():
        return False
    from date_translator import DATE_PATTERN
    return DATE_PATTERN.match(line) is not None

def is_journal_drawn(analyzer: 'ArenaMemoryAnalyzer', anchor: int) -> bool:
    text = read_journal_raw(analyzer, anchor)
    if not text:
        return False
    return bool(parse_journal_entries(text))

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
__all__ = ['read_journal_raw', 'is_journal_date_header', 'is_journal_drawn', 'parse_journal_entries', 'split_journal_lines', 'translate_journal']
