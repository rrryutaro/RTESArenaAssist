from __future__ import annotations
import logging
import struct
_log = logging.getLogger(__name__)
POPUP11_LIST_PTR_OFFSET = 20775

def _read_list_ptr(analyzer, anchor: int) -> int:
    raw = analyzer.read_bytes(anchor + POPUP11_LIST_PTR_OFFSET, 2)
    return struct.unpack('<H', raw)[0]

def _read_nul_strings(analyzer, addr: int, count: int) -> list[str]:
    if count <= 0:
        return []
    buf = analyzer.read_bytes(addr, count * 64 + 16)
    items: list[str] = []
    pos = 0
    while pos < len(buf) and len(items) < count:
        nul = buf.find(b'\x00', pos)
        if nul == -1:
            break
        chunk = buf[pos:nul]
        text = chunk.decode('ascii', errors='replace').strip()
        if not text:
            break
        items.append(text)
        pos = nul + 1
    return items

def parse_popup11_list(analyzer, anchor: int, item_count: int) -> list[str]:
    try:
        ptr = _read_list_ptr(analyzer, anchor)
        if ptr == 0:
            return []
        return _read_nul_strings(analyzer, anchor + ptr, item_count)
    except (OSError, struct.error):
        _log.exception('parse_popup11_list failed')
        return []
_LAST_REJECTED_HEAD: dict[str, str] = {}

def parse_where_is_list(analyzer, anchor: int, item_count: int) -> list[str]:
    items = parse_popup11_list(analyzer, anchor, item_count)
    if not items:
        return []
    try:
        from ask_about_menu_parser import is_known_place_name
    except Exception:
        return []
    if not is_known_place_name(items[0]):
        head = items[0][:40]
        if _LAST_REJECTED_HEAD.get('where_is') != head:
            _LAST_REJECTED_HEAD['where_is'] = head
            _log.info('場所一覧ではない（先頭 %r）ため出さない', head)
        return []
    _LAST_REJECTED_HEAD.pop('where_is', None)
    return items

def parse_dynamic_place_list(analyzer, anchor: int, item_count: int) -> list[str]:
    return parse_popup11_list(analyzer, anchor, item_count)
