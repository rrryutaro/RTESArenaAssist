from __future__ import annotations
import re
import i18n_helper as i18n
from inventory_reader import ITEM_SIZE, read_item_name_tables, name_from_item_bytes
REPAIR_STRUCT_OFFSET = 30435
REPAIR_JOB_SIZE = 24
REPAIR_JOB_COUNT = 5
_JOB_VALID_OFF = 0
_JOB_DUETO_OFF = 1
_JOB_ITEM_OFF = 5

def parse_repair_jobs(raw: bytes, tables: dict) -> list[dict]:
    jobs: list[dict] = []
    for j in range(REPAIR_JOB_COUNT):
        base = j * REPAIR_JOB_SIZE
        if base + REPAIR_JOB_SIZE > len(raw):
            break
        if raw[base + _JOB_VALID_OFF] == 0:
            continue
        due_to = int.from_bytes(raw[base + _JOB_DUETO_OFF:base + _JOB_DUETO_OFF + 4], 'little')
        item_bytes = raw[base + _JOB_ITEM_OFF:base + _JOB_ITEM_OFF + ITEM_SIZE]
        en = name_from_item_bytes(item_bytes, tables)
        if not en:
            continue
        d = item_bytes
        jobs.append({'en': en, 'job_index': j, 'due_to': due_to, 'slot_id': d[0], 'hands': d[3], 'health': d[6] | d[7] << 8, 'max_hp': d[8] | d[9] << 8})
    return jobs

def read_repair_jobs(analyzer, anchor: int) -> list[dict]:
    try:
        raw = analyzer.read_bytes(anchor + REPAIR_STRUCT_OFFSET, REPAIR_JOB_SIZE * REPAIR_JOB_COUNT)
    except (OSError, AttributeError):
        return []
    if not raw:
        return []
    tables = read_item_name_tables(analyzer, anchor)
    return parse_repair_jobs(raw, tables)
REPAIR_STATUS_SCAN_OFFSET = 37534
REPAIR_STATUS_SCAN_LEN = 1024
REPAIR_STATUS_RENDERED_OFFSET = 37834
_REPAIR_STATUS_TEMPLATES: tuple[tuple[str, str, str], ...] = (('not_ready', 'Your %s is not ready yet. I am almost done with it. Check back with me in %u hours.', 'npc_dialog.1421.0'), ('not_ready', 'Your %s is not ready yet. Check back with me in %u days.', 'npc_dialog.1420.0'), ('done', 'Your %s is ready.', 'npc_dialog.A181.0'))
_STATUS_RESOLVED_CACHE: list[tuple[str, re.Pattern, list[str], str]] | None = None

def _repair_status_matchers() -> list[tuple[str, re.Pattern, list[str], str]]:
    global _STATUS_RESOLVED_CACHE
    if _STATUS_RESOLVED_CACHE is not None:
        return _STATUS_RESOLVED_CACHE
    out: list[tuple[str, re.Pattern, list[str], str]] = []
    for kind, en, ja_id in sorted(_REPAIR_STATUS_TEMPLATES, key=lambda p: len(p[1]), reverse=True):
        ja = i18n.text_opt(ja_id) or ''
        if not ja:
            continue
        ja = ja.replace('%ni', '%s')
        rx, keys = ('', [])
        for part in re.split('(%[sud])', en):
            if part in ('%s', '%u', '%d'):
                keys.append(part)
                rx += '(.+?)' if part == '%s' else '(\\d+)'
            else:
                rx += re.escape(part)
        out.append((kind, re.compile(rx), keys, ja))
    _STATUS_RESOLVED_CACHE = out
    return out

def _match_status_segment(norm_seg: str):
    from equipment_shop_list_reader import translate_equipment_shop_name
    for kind, rx, keys, ja in _repair_status_matchers():
        m = rx.match(norm_seg)
        if not m:
            continue
        vals = list(m.groups())
        en_rendered = m.group(0)
        ja_out = ja
        for k, v in zip(keys, vals):
            if k == '%s':
                v = translate_equipment_shop_name(v) or v
            ja_out = ja_out.replace(k, str(v), 1)
        return (kind, en_rendered, ja_out)
    return None

def resolve_repair_status_reply(rendered_norm: str):
    idx = rendered_norm.find('Your ')
    while idx >= 0:
        r = _match_status_segment(rendered_norm[idx:idx + 160])
        if r is not None:
            return r
        idx = rendered_norm.find('Your ', idx + 1)
    return None

def scan_repair_status_reply(raw: bytes):
    idx = raw.find(b'Your ')
    while idx >= 0:
        seg = raw[idx:idx + 192]
        norm = ' '.join(''.join((chr(b) if 32 <= b <= 126 else ' ' for b in seg)).split())
        r = _match_status_segment(norm)
        if r is not None:
            return (r[0], r[1], r[2], idx)
        idx = raw.find(b'Your ', idx + 1)
    return None

def read_repair_status_reply(analyzer, anchor: int):
    try:
        raw = analyzer.read_bytes(anchor + REPAIR_STATUS_SCAN_OFFSET, REPAIR_STATUS_SCAN_LEN)
    except (OSError, AttributeError):
        return None
    if not raw:
        return None
    r = scan_repair_status_reply(bytes(raw))
    if r is None:
        return None
    kind, en, ja, idx = r
    return (kind, en, ja, REPAIR_STATUS_SCAN_OFFSET + idx)
__all__ = ['REPAIR_STRUCT_OFFSET', 'REPAIR_JOB_SIZE', 'REPAIR_JOB_COUNT', 'REPAIR_STATUS_SCAN_OFFSET', 'REPAIR_STATUS_SCAN_LEN', 'REPAIR_STATUS_RENDERED_OFFSET', 'parse_repair_jobs', 'read_repair_jobs', 'resolve_repair_status_reply', 'scan_repair_status_reply', 'read_repair_status_reply']
