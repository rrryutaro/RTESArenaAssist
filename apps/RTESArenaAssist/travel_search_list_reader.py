from __future__ import annotations
import logging
import struct
_log = logging.getLogger('RTESArenaAssist')
TRAVEL_LIST_PTR_OFFSET = 20520
_MAX_ITEMS = 128
_READ_LEN = 2048

def read_active_list_ptr(analyzer, anchor: int) -> int:
    try:
        return struct.unpack('<H', analyzer.read_bytes(anchor + TRAVEL_LIST_PTR_OFFSET, 2))[0]
    except (OSError, struct.error, AttributeError):
        return 0

def read_travel_city_list(analyzer, anchor: int) -> list[str]:
    ptr = read_active_list_ptr(analyzer, anchor)
    if ptr == 0:
        return []
    try:
        buf = analyzer.read_bytes(anchor + ptr, _READ_LEN)
    except (OSError, AttributeError):
        return []
    items: list[str] = []
    pos = 0
    while pos < len(buf) and len(items) < _MAX_ITEMS:
        nul = buf.find(b'\x00', pos)
        if nul == -1:
            break
        chunk = buf[pos:nul]
        if chunk == b'':
            break
        text = chunk.decode('ascii', errors='replace').strip()
        if not text:
            break
        items.append(text)
        pos = nul + 1
    return items
