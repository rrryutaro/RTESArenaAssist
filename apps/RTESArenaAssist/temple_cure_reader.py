from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from active_template_reader import ACTIVE_TEMPLATE_PTR_OFFSETS
_REGION_OFF = 4164
_REGION_SIZE = 1024
_TITLE_RE = re.compile('^Curing\\s+(.+?)\\.\\.\\.$')
_ROW_RE = re.compile('^\\t\\d{3}(\\d+) gp\\n(.+)$')
_CURE_EN = ('Diseased', 'Poisoned', 'Cursed')
_CURE_ALL_EN = 'Cure all'
_ACCEPTED_ROW_NAMES = frozenset(_CURE_EN) | {_CURE_ALL_EN}

@dataclass(frozen=True)
class CureRow:
    en: str
    price: int

@dataclass(frozen=True)
class CureView:
    title_en: str
    char_name: str
    rows: tuple
    row_offsets: tuple = ()

def _read_region(analyzer, anchor: int) -> bytes:
    try:
        return analyzer.read_bytes(anchor + _REGION_OFF, _REGION_SIZE) or b''
    except (OSError, AttributeError):
        return b''

def _cstr_at(raw: bytes, pos: int) -> str:
    end = raw.find(b'\x00', pos)
    if end < 0:
        end = len(raw)
    return raw[pos:end].decode('ascii', errors='replace')

def read_cure_view(analyzer, anchor: int) -> Optional[CureView]:
    if analyzer is None or not anchor:
        return None
    raw = _read_region(analyzer, anchor)
    if not raw:
        return None
    title = _cstr_at(raw, 0)
    m = _TITLE_RE.match(title)
    if m is None:
        return None
    char_name = m.group(1).strip()
    rows: list = []
    offsets: list = []
    seen: set = set()
    for row_en, price, off in _iter_rows(raw):
        if row_en in seen:
            continue
        seen.add(row_en)
        rows.append(CureRow(en=row_en, price=price))
        offsets.append(off)
    return CureView(title_en=title, char_name=char_name, rows=tuple(rows), row_offsets=tuple(offsets))

def _iter_rows(raw: bytes):
    pos = 0
    while pos < len(raw):
        s = _cstr_at(raw, pos)
        if s:
            m = _ROW_RE.match(s)
            if m is not None:
                name = m.group(2).strip()
                if name in _ACCEPTED_ROW_NAMES:
                    try:
                        yield (name, int(m.group(1)), _REGION_OFF + pos)
                    except ValueError:
                        pass
        pos += len(s.encode('ascii', errors='replace')) + 1

def read_active_slot_values(analyzer, anchor: int) -> tuple:
    if analyzer is None or not anchor:
        return ()
    vals = []
    for off in ACTIVE_TEMPLATE_PTR_OFFSETS:
        try:
            raw = analyzer.read_bytes(anchor + off, 2)
        except (OSError, AttributeError):
            return ()
        if not raw or len(raw) < 2:
            return ()
        vals.append(raw[0] | raw[1] << 8)
    return tuple(vals)
__all__ = ['read_cure_view', 'read_active_slot_values', 'CureView', 'CureRow', '_CURE_EN', '_CURE_ALL_EN']
