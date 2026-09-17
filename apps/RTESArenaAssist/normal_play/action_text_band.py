from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import arena_font
from assist_log import recog as _recog
from screen_detector import SCREEN_BUFFER_OFFSET, action_text_full_band_addr, action_text_ink_rows, display_buffer_matches, resolve_action_text_color_index, resolve_display_buffer
_log = logging.getLogger('RTESArenaAssist')
_DISPLAY_SCANS_PER_CONNECTION = 2
_EXTRA_COPIES = 3

@dataclass(frozen=True)
class BandObservation:
    seen: Optional[bool]
    live: bool
    rising: bool
    episode: int
    count: int
    text: str
    buffer_text: str
    masks: tuple = ()
    font: Optional[arena_font.ActionFont] = None

    def drawn_line(self, texts) -> Optional[int]:
        if not self.masks or self.font is None:
            return None
        return arena_font.drawn_line_index(self.font, self.masks, texts)
IDLE = BandObservation(seen=None, live=False, rising=False, episode=0, count=0, text='', buffer_text='')

def _font(w) -> arena_font.ActionFont | None:
    if getattr(w, '_band_font_tried', False):
        return getattr(w, '_band_font', None)
    w._band_font_tried = True
    font = None
    try:
        from runtime_paths import install_vfs
        font = arena_font.load(install_vfs())
    except Exception:
        font = None
    w._band_font = font
    if font is None:
        _recog(_log, '帯の文の同定: フォントが読めないため行わない')
    return font

def _scan_display(w, analyzer, anchor: int) -> int | None:
    w._band_screen_scans = int(getattr(w, '_band_screen_scans', 0)) + 1
    return resolve_display_buffer(analyzer, anchor)

def _can_scan(w) -> bool:
    return int(getattr(w, '_band_screen_scans', 0)) < _DISPLAY_SCANS_PER_CONNECTION

def _switch_display_base(w, anchor: int, new_base: int, *, keep_old: bool=True) -> None:
    old = getattr(w, '_band_screen_base', None)
    extras = [b for b in getattr(w, '_band_screen_extras', ()) if b not in (new_base, old)]
    if keep_old and old is not None and (old != new_base) and (old != anchor + SCREEN_BUFFER_OFFSET):
        extras.insert(0, old)
    w._band_screen_extras = tuple(extras[:_EXTRA_COPIES])
    w._band_screen_base = new_base

def _display_base(w, analyzer, anchor: int) -> int:
    if getattr(w, '_band_screen_anchor', None) != anchor:
        w._band_screen_anchor = anchor
        w._band_screen_base = None
        w._band_screen_extras = ()
        w._band_screen_scans = 0
        w._band_screen_mismatch_noted = False
    cached = getattr(w, '_band_screen_base', None)
    if cached is not None:
        return cached
    comp = anchor + SCREEN_BUFFER_OFFSET
    base = _scan_display(w, analyzer, anchor)
    if base is None:
        base = comp
        _recog(_log, '帯の読取: 表示バッファが見つからないため合成側を読む')
    else:
        _recog(_log, '帯の読取: 表示バッファ 0x%X（合成側 0x%X）', base, comp)
    w._band_screen_base = base
    return base

def _hex_list(bases) -> str:
    return '[' + ', '.join(('0x%X' % b for b in bases)) + ']'

def _forget_extra(w, base) -> None:
    extras = tuple((b for b in getattr(w, '_band_screen_extras', ()) if b != base))
    w._band_screen_extras = extras

def _read_extra_inks(w, analyzer, color: int) -> tuple:
    inks = []
    for base in tuple(getattr(w, '_band_screen_extras', ())):
        addr, size = action_text_full_band_addr(base)
        try:
            block = analyzer.read_bytes(addr, size)
        except (OSError, AttributeError, RuntimeError):
            block = None
        if not block or len(block) < size:
            _forget_extra(w, base)
            _recog(_log, '帯の読取: 前の写し 0x%X が読めないため読むのをやめる', base)
            continue
        inks.append(action_text_ink_rows(block, color))
    return tuple(inks)

def _display_copy_lost(w, analyzer, anchor: int, *, keep: bool) -> None:
    if _can_scan(w):
        found = _scan_display(w, analyzer, anchor)
        if found is not None:
            _switch_display_base(w, anchor, found, keep_old=keep)
            _recog(_log, '帯の読取: 表示バッファを探し直した 0x%X（一緒に読む写し %s）', found, _hex_list(getattr(w, '_band_screen_extras', ())))
            return
    if not keep:
        _switch_display_base(w, anchor, anchor + SCREEN_BUFFER_OFFSET, keep_old=False)
        _recog(_log, '帯の読取: 表示バッファが読めないため合成側を読む')
    elif not getattr(w, '_band_screen_mismatch_noted', False):
        w._band_screen_mismatch_noted = True
        _recog(_log, '帯の読取: 表示バッファの鍵が画面と違うが、代わりが見つからないため同じ写しを読む')

def _verify_display_copy(w, analyzer, anchor) -> None:
    if analyzer is None or not anchor:
        return
    base = getattr(w, '_band_screen_base', None)
    if base is None or getattr(w, '_band_screen_anchor', None) != anchor:
        return
    if base == anchor + SCREEN_BUFFER_OFFSET:
        if _can_scan(w):
            found = _scan_display(w, analyzer, anchor)
            if found is not None:
                _switch_display_base(w, anchor, found)
                _recog(_log, '帯の読取: 表示バッファ 0x%X（探し直して見つけた）', found)
        return
    if display_buffer_matches(analyzer, anchor, base) is False:
        _display_copy_lost(w, analyzer, anchor, keep=True)

def _read_ink(w, b30: dict):
    analyzer = getattr(w, '_analyzer', None)
    anchor = getattr(w, '_anchor', None)
    if analyzer is None or not anchor:
        return None
    color = resolve_action_text_color_index(analyzer, anchor)
    if color is None:
        return None
    base = _display_base(w, analyzer, anchor)
    addr, size = action_text_full_band_addr(base)
    try:
        block = analyzer.read_bytes(addr, size)
    except (OSError, AttributeError, RuntimeError):
        block = None
    if not block or len(block) < size:
        if base != anchor + SCREEN_BUFFER_OFFSET:
            _display_copy_lost(w, analyzer, anchor, keep=False)
        return None
    return (action_text_ink_rows(block, color), _read_extra_inks(w, analyzer, color))

def poll_action_text_band(w, *, b30: dict, active: bool, in_play: bool=True) -> BandObservation:
    buffer_text = b30.get('red_str') or ''
    if not in_play:
        release_band(w)
        return IDLE
    requested_before = bool(getattr(w, '_band_requested', False))
    w._band_requested = bool(active)
    if not active:
        obs = BandObservation(seen=None, live=bool(getattr(w, '_band_live', False)), rising=False, episode=int(getattr(w, '_band_episode', 0)), count=int(getattr(w, '_band_count', 0)), text=str(getattr(w, '_band_text', '')), buffer_text=buffer_text)
        w._band_obs = obs
        return obs
    if not requested_before:
        _verify_display_copy(w, getattr(w, '_analyzer', None), getattr(w, '_anchor', None))
    read = _read_ink(w, b30)
    if read is None:
        obs = BandObservation(seen=None, live=bool(getattr(w, '_band_live', False)), rising=False, episode=int(getattr(w, '_band_episode', 0)), count=int(getattr(w, '_band_count', 0)), text=str(getattr(w, '_band_text', '')), buffer_text=buffer_text)
        w._band_obs = obs
        return obs
    ink, extra_inks = read
    masks = tuple((arena_font.row_masks(rows) for rows in (ink, *extra_inks)))
    count = sum((len(r) for r in ink))
    live = count > 0
    live_prev = bool(getattr(w, '_band_live', False))
    rising = live and (not live_prev)
    episode = int(getattr(w, '_band_episode', 0))
    text = str(getattr(w, '_band_text', ''))
    key_prev = getattr(w, '_band_ink_key', None)
    if live:
        if ink != key_prev:
            w._band_ink_key = ink
            font = _font(w)
            text = arena_font.decode_band(font, ink) if font is not None else ''
            if rising or not live_prev:
                episode += 1
            elif text != str(getattr(w, '_band_text', '')):
                episode += 1
            w._band_text = text
    else:
        w._band_ink_key = None
        w._band_text = ''
        text = ''
    w._band_live = live
    w._band_count = count
    w._band_episode = episode
    obs = BandObservation(seen=True, live=live, rising=rising, episode=episode, count=count, text=text, buffer_text=buffer_text, masks=masks, font=_font(w))
    w._band_obs = obs
    return obs

def current_band(w) -> BandObservation:
    return getattr(w, '_band_obs', None) or IDLE

def release_band(w) -> None:
    w._band_live = False
    w._band_count = 0
    w._band_ink_key = None
    w._band_text = ''
    w._band_requested = False
    w._band_obs = IDLE

def shutdown_band(w) -> None:
    release_band(w)
    w._band_screen_base = None
    w._band_screen_extras = ()
    w._band_screen_anchor = None
    w._band_screen_scans = 0
    w._band_screen_mismatch_noted = False
    w._band_font = None
    w._band_font_tried = False
    w._band_episode = 0
__all__ = ['BandObservation', 'IDLE', 'poll_action_text_band', 'current_band', 'release_band', 'shutdown_band']
