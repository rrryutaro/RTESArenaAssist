from __future__ import annotations
import logging
import struct
from dataclasses import dataclass
_log = logging.getLogger('RTESArenaAssist')
FONT_NAME = 'ARENAFNT.DAT'
_GLYPH_COUNT = 96
_GLYPH_DATA_OFFSET = 95
SCREEN_COLS = 320

@dataclass(frozen=True)
class ActionFont:
    height: int
    widths: tuple[int, ...]
    glyphs: tuple[tuple[int, ...], ...]

def parse(raw: bytes) -> ActionFont | None:
    if not raw or len(raw) < _GLYPH_DATA_OFFSET + 2:
        return None
    height = raw[0]
    if height <= 0 or height > 32:
        return None
    need = _GLYPH_DATA_OFFSET + (_GLYPH_COUNT - 1) * height * 2
    if len(raw) < need:
        return None
    widths = [0] * _GLYPH_COUNT
    glyphs: list[tuple[int, ...]] = [()] * _GLYPH_COUNT
    idx = 0
    for i in range(1, _GLYPH_COUNT):
        rows: list[int] = []
        max_w = 0
        for _ in range(height):
            v = struct.unpack_from('<H', raw, _GLYPH_DATA_OFFSET + idx * 2)[0]
            idx += 1
            rows.append(v)
            for c in range(16):
                if v & 32768 >> c:
                    max_w = max(max_w, c + 1)
        widths[i] = max_w + 1
        glyphs[i] = tuple(rows)
    widths[0] = widths[1]
    glyphs[0] = tuple([0] * height)
    return ActionFont(height=height, widths=tuple(widths), glyphs=tuple(glyphs))

def load(vfs) -> ActionFont | None:
    if vfs is None:
        return None
    try:
        raw = vfs.read(FONT_NAME)
    except Exception:
        return None
    font = parse(raw) if raw else None
    if font is None:
        _log.info('%s が読めないため、帯の文の同定は行わない', FONT_NAME)
    return font

def _glyph_patterns(font: ActionFont) -> dict[int, tuple[tuple[int, ...], ...]]:
    pats: dict[int, tuple[tuple[int, ...], ...]] = {}
    for gi in range(_GLYPH_COUNT):
        w = font.widths[gi] - 1
        if w <= 0:
            continue
        pats[gi] = tuple((tuple((1 if v & 32768 >> c else 0 for c in range(w))) for v in font.glyphs[gi]))
    return pats

def decode_band(font: ActionFont, ink_by_row, *, space_gap: int=3) -> str:
    rows = [set(r) for r in ink_by_row]
    cols = sorted(set().union(*rows)) if rows else []
    if not cols:
        return ''
    runs: list[tuple[int, int, int]] = []
    start = prev = cols[0]
    for c in cols[1:]:
        if c - prev > 1:
            runs.append((start, prev, c - prev - 1))
            start = c
        prev = c
    runs.append((start, prev, 0))
    pats = _glyph_patterns(font)
    text: list[str] = []
    for left, right, gap in runs:
        width = right - left + 1
        obs = tuple((tuple((1 if left + c in rows[r] else 0 for c in range(width))) for r in range(len(rows))))
        found = ''
        for gi, pat in pats.items():
            if len(pat[0]) == width and len(pat) == len(obs) and (pat == obs):
                found = chr(32 + gi)
                break
        text.append(found or '?')
        if gap >= space_gap:
            text.append(' ')
    return ''.join(text)

def matches(decoded: str, expected: str) -> bool:
    if not decoded or not expected or len(decoded) != len(expected):
        return False
    for d, e in zip(decoded, expected):
        if d == '?':
            continue
        if d != e:
            return False
    return True
__all__ = ['ActionFont', 'FONT_NAME', 'parse', 'load', 'decode_band', 'matches', 'SCREEN_COLS']
