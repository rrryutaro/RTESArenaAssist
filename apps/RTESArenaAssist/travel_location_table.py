from __future__ import annotations
_TABLE_OFFSET = 5164
_RECORD_SIZE = 25
_NAME_LEN = 20
_HOVER_X = 36732
_HOVER_Y = 36734
_MAX_RECORDS = 80
_MAX_X = 400
_MAX_Y = 250

def read_location_table(analyzer, anchor: int):
    out = []
    try:
        blob = analyzer.read_bytes(anchor + _TABLE_OFFSET, _RECORD_SIZE * _MAX_RECORDS)
    except OSError:
        return out
    for i in range(_MAX_RECORDS):
        rec = blob[i * _RECORD_SIZE:(i + 1) * _RECORD_SIZE]
        if len(rec) < _RECORD_SIZE:
            break
        raw = rec[0:_NAME_LEN].split(b'\x00')[0]
        if not raw or not 65 <= raw[0] <= 90:
            if out:
                break
            continue
        try:
            name = raw.decode('latin-1')
        except (UnicodeDecodeError, ValueError):
            break
        x = rec[_NAME_LEN] | rec[_NAME_LEN + 1] << 8
        y = rec[_NAME_LEN + 2] | rec[_NAME_LEN + 3] << 8
        if x > _MAX_X or y > _MAX_Y:
            if out:
                break
            continue
        vis = rec[24]
        out.append((name, x, y, vis, len(out)))
    return out

def _is_visible(idx: int, vis: int, name: str) -> bool:
    if idx < 32:
        return bool(name)
    return bool(vis & 2)

def read_named_location(analyzer, anchor: int):
    table = read_location_table(analyzer, anchor)
    if not table:
        return None
    xy = read_hover_xy(analyzer, anchor)
    if xy is None:
        return None
    cx, cy = xy
    best = None
    best_d2 = None
    for name, x, y, vis, idx in table:
        if not _is_visible(idx, vis, name):
            continue
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        if best is None or d2 < best_d2:
            best, best_d2 = ((name, x, y, idx), d2)
    return best

def read_hover_xy(analyzer, anchor: int):
    try:
        x = int.from_bytes(analyzer.read_bytes(anchor + _HOVER_X, 2), 'little')
        y = int.from_bytes(analyzer.read_bytes(anchor + _HOVER_Y, 2), 'little')
    except OSError:
        return None
    return (x, y)
_ICON_ROW_Y_MIN = 175
_ICON_X_MIN = 35
_ICON_X_MAX = 92
_ICON_X_INPUT_MAX = 53
_ICON_X_EXECUTE_MAX = 72

def hovered_icon(analyzer, anchor: int):
    xy = read_hover_xy(analyzer, anchor)
    if xy is None:
        return None
    x, y = xy
    if y < _ICON_ROW_Y_MIN or x < _ICON_X_MIN or x > _ICON_X_MAX:
        return None
    if x < _ICON_X_INPUT_MAX:
        return 'input'
    if x < _ICON_X_EXECUTE_MAX:
        return 'execute'
    return 'exit'
_PROVINCE_NAME_TABLE = 12038
_PROVINCE_INDEX = 6430
_PROVINCE_COUNT = 9

def read_province_names(analyzer, anchor: int, count: int=_PROVINCE_COUNT):
    try:
        blob = analyzer.read_bytes(anchor + _PROVINCE_NAME_TABLE, 256)
    except OSError:
        return []
    out = []
    for part in blob.split(b'\x00'):
        if not part:
            continue
        try:
            out.append(part.decode('latin-1'))
        except (UnicodeDecodeError, ValueError):
            break
        if len(out) >= count:
            break
    return out

def read_displayed_province(analyzer, anchor: int):
    try:
        idx = analyzer.read_bytes(anchor + _PROVINCE_INDEX, 1)[0]
    except (OSError, AttributeError):
        return None
    names = read_province_names(analyzer, anchor)
    if 0 <= idx < len(names):
        return (idx, names[idx])
    return None

def location_type(idx: int):
    if idx < 8:
        return 'City-State'
    if idx < 16:
        return 'Town'
    if idx < 32:
        return 'Village'
    return None

def hovered_location(analyzer, anchor: int):
    xy = read_hover_xy(analyzer, anchor)
    if xy is None:
        return None
    x, y = xy
    table = read_location_table(analyzer, anchor)
    if not table:
        return None
    best_i = min(range(len(table)), key=lambda i: (table[i][1] - x) ** 2 + (table[i][2] - y) ** 2)
    name, bx, by = (table[best_i][0], table[best_i][1], table[best_i][2])
    dist = ((bx - x) ** 2 + (by - y) ** 2) ** 0.5
    return (name, x, y, dist, best_i)
__all__ = ['read_location_table', 'read_hover_xy', 'hovered_location', 'hovered_icon', 'location_type', 'read_named_location', 'read_province_names', 'read_displayed_province']
