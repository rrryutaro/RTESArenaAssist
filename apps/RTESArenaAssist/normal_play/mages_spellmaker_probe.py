from __future__ import annotations
import logging
from assist_log import recog
_log = logging.getLogger('RTESArenaAssist')
_RECORD_ATTR = '_mages_spellmaker_probe_record'
_LIST_ATTR = '_mages_spellmaker_probe_list'
_LIST_READ_LEN = 288
_LIST_MAX_SEGMENTS = 24

def note_record(w, data: dict) -> None:
    try:
        key = (tuple(data.get('effects') or ()), tuple(data.get('sub_effects') or ()), tuple(data.get('affected_attrs') or ()), data.get('target_id'), data.get('element_id'), _read_flags(w))
    except Exception:
        return
    if key == getattr(w, _RECORD_ATTR, None):
        return
    setattr(w, _RECORD_ATTR, key)
    effects, subs, attrs, target, element, flags = key
    details = [d for d in data.get('effect_details') or [] if isinstance(d, dict)]
    names = [d.get('effect_en', '') for d in details]
    shown = [(d.get('effect_ja', ''), d.get('text_en', ''), d.get('text_ja', '')) for d in details]
    recog(_log, 'spellmaker record changed: effects=%s sub=%s attrs=%s flags=%s target=%s element=%s names=%r shown=%r', list(effects), list(subs), list(attrs), f'{flags:#06x}' if isinstance(flags, int) else flags, target, element, names, shown)

def note_name_list(w, offset: int, title: str, shown: int) -> None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + offset, _LIST_READ_LEN)
    except (OSError, AttributeError):
        return
    segments = [seg.decode('ascii', errors='replace') for seg in raw.split(b'\x00')[:_LIST_MAX_SEGMENTS]]
    key = (offset, tuple(segments))
    if key == getattr(w, _LIST_ATTR, None):
        return
    setattr(w, _LIST_ATTR, key)
    recog(_log, 'spellmaker list place changed: off=%#06x title=%r shown=%d segments=%r', offset, title, shown, segments)
_FORM_ATTR = '_mages_spellmaker_probe_form'
_FORM_SCAN_START = 0
_FORM_SCAN_LEN = 65536
_FORM_MAX_RUNS = 32
_FORM_RUN_SHOWN = 8

def _record_columns(w):
    from spell_record_reader import GRP_OFFS
    cols = []
    for base in GRP_OFFS:
        raw = w._analyzer.read_bytes(w._anchor + base, 6)
        if len(raw) < 6:
            return None
        cols.append(tuple((raw[i] | raw[i + 1] << 8 for i in (0, 2, 4))))
    return tuple(cols)

def _changed_runs(old: bytes, new: bytes):
    runs = []
    i, n = (0, min(len(old), len(new)))
    while i < n and len(runs) < _FORM_MAX_RUNS:
        if old[i] == new[i]:
            i += 1
            continue
        j = i
        while j < n and old[j] != new[j]:
            j += 1
        runs.append((i, old[i:j], new[i:j]))
        i = j
    return runs

def note_form_values(w, form_img: str) -> None:
    try:
        cols = _record_columns(w)
        cost = w._analyzer.read_bytes(w._anchor + 37532, 12).split(b'\x00')[0]
        region = w._analyzer.read_bytes(w._anchor + _FORM_SCAN_START, _FORM_SCAN_LEN)
    except (OSError, AttributeError):
        return
    if cols is None or len(region) < _FORM_SCAN_LEN:
        return
    prev = getattr(w, _FORM_ATTR, None)
    key = (form_img, cols, cost)
    if prev is not None and prev[0] == key:
        setattr(w, _FORM_ATTR, (key, region))
        return
    setattr(w, _FORM_ATTR, (key, region))
    opened = prev is None or prev[0][0] != form_img
    runs = [] if opened else _changed_runs(prev[1], region)
    shown = ['%#06x:%s>%s' % (_FORM_SCAN_START + off, a[:_FORM_RUN_SHOWN].hex(), b[:_FORM_RUN_SHOWN].hex()) for off, a, b in runs]
    recog(_log, 'spellmaker form values: img=%r %s cost=%r columns=%r changed=%d %s', form_img, 'opened' if opened else 'changed', cost.decode('ascii', errors='replace'), [list(c) for c in cols], len(runs), shown)

def forget_form_values(w) -> None:
    if getattr(w, _FORM_ATTR, None) is not None:
        setattr(w, _FORM_ATTR, None)
_LIST_SIGNALS_ATTR = '_mages_spellmaker_probe_list_signals'
_ACTIVE_LIST_PTR_OFFSET = 20520
_EFFECT_COPY_OFFSET = 38534

def note_list_signals(w, sig: dict, img: str, view_kind: str) -> None:
    try:
        raw_ptr = w._analyzer.read_bytes(w._anchor + _ACTIVE_LIST_PTR_OFFSET, 2)
        raw_copy = w._analyzer.read_bytes(w._anchor + _EFFECT_COPY_OFFSET, 40)
    except (OSError, AttributeError):
        return
    if len(raw_ptr) < 2:
        return
    list_ptr = raw_ptr[0] | raw_ptr[1] << 8
    copy_head = raw_copy.split(b'\x00')[0].decode('ascii', errors='replace')
    desc = sig.get('view_desc')
    key = (img, view_kind, sig.get('frame'), sig.get('list_flag'), desc, list_ptr, copy_head)
    if key == getattr(w, _LIST_SIGNALS_ATTR, None):
        return
    setattr(w, _LIST_SIGNALS_ATTR, key)
    recog(_log, 'spellmaker list signals: img=%r kind=%s frame=%s list=%s desc=%s screen=%s list_ptr=%#06x copy_head=%r', img, view_kind or '-', _hex(sig.get('frame')), _hex(sig.get('list_flag')), '%#06x' % desc if isinstance(desc, int) else None, sig.get('spellmaker_screen'), list_ptr, copy_head)

def _hex(value):
    return '%#04x' % value if isinstance(value, int) else None

def _read_flags(w):
    try:
        from spell_reader import SPELL_DETAIL_FLAGS_OFFSET
        raw = w._analyzer.read_bytes(w._anchor + SPELL_DETAIL_FLAGS_OFFSET, 2)
    except Exception:
        return None
    if not raw or len(raw) < 2:
        return None
    return raw[0] | raw[1] << 8
__all__ = ['note_record', 'note_name_list', 'note_list_signals', 'note_form_values', 'forget_form_values']
