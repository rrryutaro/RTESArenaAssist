from __future__ import annotations
import functools
import logging
import struct
from dataclasses import dataclass
_log = logging.getLogger('RTESArenaAssist')
FONT_NAME = 'ARENAFNT.DAT'
_GLYPH_COUNT = 96
_GLYPH_DATA_OFFSET = 95
SCREEN_COLS = 320
SPACE_ADVANCES = (4, 3, 5)
_CENTER_SLACK = 2
_MIN_BACKGROUND_UNLIT = 0.1

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

def row_masks(ink_by_row) -> tuple[int, ...]:
    out = []
    for row in ink_by_row:
        mask = 0
        for c in row:
            mask |= 1 << int(c)
        out.append(mask)
    return tuple(out)

@functools.lru_cache(maxsize=256)
def _line_template(font: ActionFont, text: str, space_advance: int) -> tuple[tuple[int, ...], int]:
    rows = [0] * font.height
    x = 0
    right = -1
    for ch in text:
        gi = ord(ch) - 32
        if not 0 <= gi < _GLYPH_COUNT:
            return ((), 0)
        if gi == 0:
            x += space_advance
            continue
        for r, v in enumerate(font.glyphs[gi]):
            for c in range(16):
                if v & 32768 >> c:
                    rows[r] |= 1 << x + c
                    right = max(right, x + c)
        x += font.widths[gi]
    return (tuple(rows), right + 1)

def _background_is_distinct(template, masks, x: int, width: int) -> bool:
    box = (1 << width) - 1 << x
    total = unlit = 0
    for t, m in zip(template, masks):
        background = box & ~(t << x)
        count = background.bit_count()
        total += count
        unlit += count - (m & background).bit_count()
    return total > 0 and unlit >= total * _MIN_BACKGROUND_UNLIT

def line_is_drawn(font: ActionFont, masks, text: str, *, center: int=SCREEN_COLS // 2) -> bool:
    if font is None or not text or len(masks) != font.height:
        return False
    for space_advance in SPACE_ADVANCES:
        template, width = _line_template(font, text, space_advance)
        if width <= 0 or not any(template):
            continue
        left = center - width // 2
        for x in range(left - _CENTER_SLACK, left + _CENTER_SLACK + 1):
            if x < 0 or x + width > SCREEN_COLS:
                continue
            if all((t << x & ~m == 0 for t, m in zip(template, masks))) and _background_is_distinct(template, masks, x, width):
                return True
    return False

def drawn_line_index(font: ActionFont, masks_list, texts) -> int | None:
    if font is None:
        return None
    found = None
    for i, text in enumerate(texts):
        if not text:
            continue
        if any((line_is_drawn(font, masks, text) for masks in masks_list)):
            if found is not None:
                return None
            found = i
    return found
__all__ = ['ActionFont', 'FONT_NAME', 'parse', 'load', 'decode_band', 'matches', 'SCREEN_COLS', 'SPACE_ADVANCES', 'row_masks', 'line_is_drawn', 'drawn_line_index']
