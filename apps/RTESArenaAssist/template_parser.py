from __future__ import annotations
import re
from typing import Optional, Dict, Tuple
TEMPLATE_ADDR = 275779531
FILLED_ADDR = 275794030
TEMPLATE_ANCHOR_DELTA = 23419
FILLED_ANCHOR_DELTA = 37918
FILLED_DELTA = 14499
EXPECTED_TEMPLATE_PREFIX = b'You are in %s.'
_TEMPLATE_ADDR_CACHE: Optional[int] = None
_FILLED_ADDR_CACHE: Optional[int] = None
STATUS_PATTERN = re.compile('You are in (?P<location>.+?)\\.\\rIt is (?P<time>.+?)\\.\\rThe date is (?P<date>.+?)\\rYou are currently carrying (?P<weight>\\d+) kg out of (?P<weight_max>\\d+) kg\\.\\r(?:You are (?P<health>.+?)\\.\\r)?')
_SCAN_BELOW = 4194304
_SCAN_ABOVE = 6291456
_SCAN_CHUNK = 65536

def _read_string(analyzer, addr: int, length: int=512) -> str:
    if analyzer is None:
        return ''
    try:
        b = analyzer.read_bytes(addr, length)
    except (OSError, AttributeError):
        return ''
    if b'\x00' in b:
        b = b[:b.index(b'\x00')]
    return b.decode('ascii', errors='replace')

def _check_addr(analyzer, template_addr: int) -> bool:
    try:
        prefix = analyzer.read_bytes(template_addr, len(EXPECTED_TEMPLATE_PREFIX))
        return prefix == EXPECTED_TEMPLATE_PREFIX
    except (OSError, AttributeError):
        return False

def _scan_for_template(analyzer, anchor: int) -> Optional[Tuple[int, int]]:
    target = EXPECTED_TEMPLATE_PREFIX
    scan_start = max(268435456, anchor - _SCAN_BELOW)
    scan_end = anchor + _SCAN_ABOVE
    addr = scan_start
    while addr < scan_end:
        try:
            data = analyzer.read_bytes(addr, _SCAN_CHUNK)
            idx = data.find(target)
            if idx >= 0:
                t_addr = addr + idx
                f_addr = t_addr + FILLED_DELTA
                return (t_addr, f_addr)
        except (OSError, AttributeError):
            pass
        addr += _SCAN_CHUNK
    return None

def _resolve_addrs(analyzer, anchor: Optional[int]) -> Optional[Tuple[int, int]]:
    global _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE
    if _TEMPLATE_ADDR_CACHE is not None:
        if _check_addr(analyzer, _TEMPLATE_ADDR_CACHE):
            return (_TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE)
        _TEMPLATE_ADDR_CACHE = None
        _FILLED_ADDR_CACHE = None
    if anchor is not None:
        t_addr = anchor + TEMPLATE_ANCHOR_DELTA
        if _check_addr(analyzer, t_addr):
            _TEMPLATE_ADDR_CACHE = t_addr
            _FILLED_ADDR_CACHE = t_addr + FILLED_DELTA
            return (_TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE)
    if _check_addr(analyzer, TEMPLATE_ADDR):
        _TEMPLATE_ADDR_CACHE = TEMPLATE_ADDR
        _FILLED_ADDR_CACHE = FILLED_ADDR
        return (TEMPLATE_ADDR, FILLED_ADDR)
    if anchor is None:
        return None
    result = _scan_for_template(analyzer, anchor)
    if result is None:
        return None
    _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE = result
    return result

def parse_filled(analyzer, anchor: int=None) -> Optional[Dict[str, str]]:
    if analyzer is None:
        return None
    addrs = _resolve_addrs(analyzer, anchor)
    if addrs is None:
        return None
    _, filled_addr = addrs
    text = _read_string(analyzer, filled_addr, 512)
    if not text:
        return None
    m = STATUS_PATTERN.search(text)
    if m is None:
        return None
    parsed = {k: v if v is not None else '' for k, v in m.groupdict().items()}
    return parsed

def reset_cache() -> None:
    global _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE
    _TEMPLATE_ADDR_CACHE = None
    _FILLED_ADDR_CACHE = None

def render_status(parsed: Dict[str, str]) -> Tuple[str, str, str]:
    from date_translator import _translate_status_line
    location = parsed.get('location', '')
    time_str = parsed.get('time', '')
    date_str = parsed.get('date', '')
    weight = parsed.get('weight', '')
    weight_max = parsed.get('weight_max', '')
    health = parsed.get('health', '')
    en_lines: list = []
    ja_lines: list = []

    def _add(en: str) -> None:
        ja = _translate_status_line(en)
        en_lines.append(en)
        ja_lines.append(ja if ja is not None else en)
    if location:
        _add(f'You are in {location}.')
    if time_str:
        _add(f'It is {time_str}.')
    if date_str:
        _add(f'The date is {date_str}')
    if weight and weight_max:
        _add(f'You are currently carrying {weight} kg out of {weight_max} kg.')
    if health:
        _add(f'You are {health}.')
    return ('\n'.join(en_lines), '\n'.join(ja_lines), '')
