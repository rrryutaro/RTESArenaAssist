from __future__ import annotations
import logging
from dataclasses import dataclass
from assist_log import recog as _recog
from screen_detector import SCREEN_BUFFER_OFFSET, display_buffer_matches, find_display_copy, read_display_key
_log = logging.getLogger('RTESArenaAssist')
_SCANS_PER_CONNECTION = 2
_EXTRA_COPIES = 3

@dataclass(frozen=True)
class DisplayCopies:
    main: int | None
    extras: tuple = ()
    resolved: bool = False

    @property
    def bases(self) -> tuple[int, ...]:
        out: list[int] = [] if self.main is None else [int(self.main)]
        for extra in self.extras:
            if extra not in out:
                out.append(int(extra))
        return tuple(out)
UNRESOLVED = DisplayCopies(main=None)

def _comp(anchor: int) -> int:
    return anchor + SCREEN_BUFFER_OFFSET

def _reset(w, anchor) -> None:
    w._display_copy_anchor = anchor
    w._display_copy_base = None
    w._display_copy_extras = ()
    w._display_copy_scans = 0
    w._display_copy_mismatch_noted = False

def _connection(w):
    analyzer = getattr(w, '_analyzer', None)
    anchor = getattr(w, '_anchor', None)
    if analyzer is None or not anchor:
        return (None, None)
    if getattr(w, '_display_copy_anchor', None) != anchor:
        _reset(w, anchor)
    return (analyzer, anchor)

def display_copies(w) -> DisplayCopies:
    anchor = getattr(w, '_anchor', None)
    if anchor is None or getattr(w, '_display_copy_anchor', None) != anchor:
        return UNRESOLVED
    comp = _comp(anchor)
    base = getattr(w, '_display_copy_base', None)
    extras = tuple((int(b) for b in getattr(w, '_display_copy_extras', ()) if b != comp and b != base))
    if base is None:
        return DisplayCopies(main=None, extras=extras, resolved=False)
    if base == comp:
        return DisplayCopies(main=None, extras=extras, resolved=True)
    return DisplayCopies(main=int(base), extras=extras, resolved=True)

def _can_scan(w) -> bool:
    return int(getattr(w, '_display_copy_scans', 0)) < _SCANS_PER_CONNECTION

def _search(w, analyzer, anchor: int) -> tuple[bool, int | None]:
    key = read_display_key(analyzer, anchor)
    if key is None:
        return (False, None)
    w._display_copy_scans = int(getattr(w, '_display_copy_scans', 0)) + 1
    return (True, find_display_copy(analyzer, anchor, key))

def _hex_list(bases) -> str:
    return '[' + ', '.join(('0x%X' % b for b in bases)) + ']'

def _switch(w, anchor: int, new_base: int, *, keep_old: bool=True) -> None:
    old = getattr(w, '_display_copy_base', None)
    extras = [b for b in getattr(w, '_display_copy_extras', ()) if b not in (new_base, old)]
    if keep_old and old is not None and (old != new_base) and (old != _comp(anchor)):
        extras.insert(0, old)
    w._display_copy_extras = tuple(extras[:_EXTRA_COPIES])
    w._display_copy_base = new_base

def poll_display_copy(w, *, gameplay: bool) -> None:
    if not gameplay:
        return
    analyzer, anchor = _connection(w)
    if analyzer is None:
        return
    if getattr(w, '_display_copy_base', None) is not None:
        return
    searched, found = _search(w, analyzer, anchor)
    if not searched:
        return
    comp = _comp(anchor)
    if found is None:
        w._display_copy_base = comp
        _recog(_log, '表示側の写し: 見つからないため合成側を読む')
        return
    w._display_copy_base = found
    _recog(_log, '表示側の写し: 0x%X（合成側 0x%X）', found, comp)

def _lost(w, analyzer, anchor: int, *, keep: bool) -> None:
    if _can_scan(w):
        _searched, found = _search(w, analyzer, anchor)
        if found is not None:
            _switch(w, anchor, found, keep_old=keep)
            _recog(_log, '表示側の写し: 探し直した 0x%X（一緒に読む写し %s）', found, _hex_list(getattr(w, '_display_copy_extras', ())))
            return
    if not keep:
        _switch(w, anchor, _comp(anchor), keep_old=False)
        _recog(_log, '表示側の写し: 読めないため合成側を読む')
    elif not getattr(w, '_display_copy_mismatch_noted', False):
        w._display_copy_mismatch_noted = True
        _recog(_log, '表示側の写し: 鍵が画面と違うが、代わりが見つからないため同じ写しを読む')

def verify_on_request(w) -> None:
    analyzer, anchor = _connection(w)
    if analyzer is None:
        return
    base = getattr(w, '_display_copy_base', None)
    if base is None:
        return
    if base == _comp(anchor):
        if _can_scan(w):
            _searched, found = _search(w, analyzer, anchor)
            if found is not None:
                _switch(w, anchor, found)
                _recog(_log, '表示側の写し: 0x%X（探し直して見つけた）', found)
        return
    if display_buffer_matches(analyzer, anchor, base) is False:
        _lost(w, analyzer, anchor, keep=True)

def main_copy_unreadable(w) -> None:
    analyzer, anchor = _connection(w)
    if analyzer is None:
        return
    base = getattr(w, '_display_copy_base', None)
    if base is None or base == _comp(anchor):
        return
    _lost(w, analyzer, anchor, keep=False)

def drop_extra(w, base: int) -> None:
    extras = tuple(getattr(w, '_display_copy_extras', ()))
    kept = tuple((b for b in extras if b != base))
    if len(kept) == len(extras):
        return
    w._display_copy_extras = kept
    _recog(_log, '表示側の写し: 前の写し 0x%X が読めないため読むのをやめる', base)

def forget(w) -> None:
    _reset(w, None)
__all__ = ['DisplayCopies', 'UNRESOLVED', 'display_copies', 'poll_display_copy', 'verify_on_request', 'main_copy_unreadable', 'drop_extra', 'forget']
