from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import arena_font
from assist_log import recog as _recog
from screen_detector import SCREEN_BUFFER_OFFSET, action_text_full_band_addr, action_text_ink_rows, resolve_action_text_color_index
from screen_display_copy import display_copies as _display_copies, drop_extra as _drop_extra, main_copy_unreadable as _main_copy_unreadable, verify_on_request as _verify_on_request
_log = logging.getLogger('RTESArenaAssist')

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

def _read_extra_inks(w, analyzer, color: int, extras) -> tuple:
    inks = []
    for base in tuple(extras):
        addr, size = action_text_full_band_addr(base)
        try:
            block = analyzer.read_bytes(addr, size)
        except (OSError, AttributeError, RuntimeError):
            block = None
        if not block or len(block) < size:
            _drop_extra(w, base)
            continue
        inks.append(action_text_ink_rows(block, color))
    return tuple(inks)

def _read_ink(w, b30: dict):
    analyzer = getattr(w, '_analyzer', None)
    anchor = getattr(w, '_anchor', None)
    if analyzer is None or not anchor:
        return None
    color = resolve_action_text_color_index(analyzer, anchor)
    if color is None:
        return None
    copies = _display_copies(w)
    base = copies.main if copies.main is not None else anchor + SCREEN_BUFFER_OFFSET
    addr, size = action_text_full_band_addr(base)
    try:
        block = analyzer.read_bytes(addr, size)
    except (OSError, AttributeError, RuntimeError):
        block = None
    if not block or len(block) < size:
        if copies.main is not None:
            _main_copy_unreadable(w)
        return None
    return (action_text_ink_rows(block, color), _read_extra_inks(w, analyzer, color, copies.extras))

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
        _verify_on_request(w)
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
    w._band_font = None
    w._band_font_tried = False
    w._band_episode = 0
__all__ = ['BandObservation', 'IDLE', 'poll_action_text_band', 'current_band', 'release_band', 'shutdown_band']
