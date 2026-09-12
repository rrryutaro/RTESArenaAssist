from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from screen_detector import ActionTextWatcher, band_mask_within, band_signature, note_band_signature
ABSENT_POLLS_TO_END = 10
EXPECT_POLLS_MAX = 40

@dataclass(frozen=True)
class BandObservation:
    seen: Optional[bool]
    live: bool
    rising: bool
    episode: int
    mask: int
    count: int
    settled: bool
    attribution: str
    buffer_text: str
IDLE = BandObservation(seen=None, live=False, rising=False, episode=0, mask=0, count=0, settled=False, attribution='none', buffer_text='')

def _watcher(w) -> ActionTextWatcher:
    watcher = getattr(w, '_band_watcher', None)
    if watcher is None:
        watcher = ActionTextWatcher()
        w._band_watcher = watcher
    return watcher

def _update_expectation(w, b30: dict) -> Optional[str]:
    text = b30.get('red_str') or ''
    if b30.get('red_changed') and text:
        w._band_expect = text
        w._band_expect_polls = 0
        return text
    expect = getattr(w, '_band_expect', None)
    if not expect:
        return None
    if b30.get('in_gameplay') and (not b30.get('dialog_active')):
        n = int(getattr(w, '_band_expect_polls', 0)) + 1
        w._band_expect_polls = n
        if n > EXPECT_POLLS_MAX:
            w._band_expect = None
            return None
    return expect

def _attribute(w, *, episode: int, mask: int, count: int, settled: bool, live: bool, expect: Optional[str], text: str) -> str:
    if count <= 0:
        return 'none'
    verdicts = getattr(w, '_band_verdicts', None)
    if verdicts is None:
        verdicts = {}
        w._band_verdicts = verdicts
    verdict = verdicts.get(episode)
    if verdict is not None:
        return verdict
    if not live or not settled:
        return 'pending'
    if expect:
        note_band_signature(w, expect, mask, count)
        w._band_expect = None
        w._band_learn = (expect, episode)
        verdict = 'buffer'
    else:
        ref = band_signature(w, text)
        verdict = 'buffer' if ref is not None and band_mask_within(mask, ref[0]) else 'other'
    verdicts.clear()
    verdicts[episode] = verdict
    return verdict

def _continue_learning(w, *, episode: int, mask: int, count: int) -> None:
    learn = getattr(w, '_band_learn', None)
    if not learn:
        return
    text, ep = learn
    if ep != episode:
        w._band_learn = None
        return
    ref = band_signature(w, text)
    if count > 0 and (ref is None or count > ref[1]):
        note_band_signature(w, text, mask, count)

def poll_action_text_band(w, *, b30: dict, active: bool, in_play: bool=True) -> BandObservation:
    if not in_play:
        release_band(w)
        return IDLE
    expect = _update_expectation(w, b30)
    want = bool(active) or bool(expect)
    watcher = _watcher(w)
    seen: Optional[bool] = None
    try:
        analyzer = getattr(w, '_analyzer', None)
        anchor = getattr(w, '_anchor', None)
        if analyzer is not None and anchor is not None:
            watcher.ensure(analyzer, anchor)
        watcher.set_active(want)
        if want:
            seen = watcher.consume()
    except (OSError, AttributeError, RuntimeError):
        seen = None
    live_prev = bool(getattr(w, '_band_live', False))
    live = live_prev
    if seen is True:
        w._band_absent = 0
        live = True
    elif seen is False:
        absent = int(getattr(w, '_band_absent', 0)) + 1
        w._band_absent = absent
        if absent >= ABSENT_POLLS_TO_END:
            live = False
    w._band_live = live
    rising = live and (not live_prev)
    if live_prev and (not live):
        try:
            watcher.reset_episode()
        except AttributeError:
            pass
        w._band_verdicts = {}
    try:
        episode, mask, count, settled = watcher.episode()
    except (AttributeError, TypeError, ValueError):
        episode, mask, count, settled = (0, 0, 0, False)
    text = b30.get('red_str') or ''
    _continue_learning(w, episode=episode, mask=mask, count=count)
    attribution = _attribute(w, episode=episode, mask=mask, count=count, settled=settled, live=live, expect=getattr(w, '_band_expect', None), text=text)
    obs = BandObservation(seen=seen, live=live, rising=rising, episode=episode, mask=mask, count=count, settled=settled, attribution=attribution, buffer_text=text)
    w._band_obs = obs
    return obs

def current_band(w) -> BandObservation:
    return getattr(w, '_band_obs', None) or IDLE

def release_band(w) -> None:
    watcher = getattr(w, '_band_watcher', None)
    if watcher is not None:
        try:
            watcher.set_active(False)
        except AttributeError:
            pass
    w._band_live = False
    w._band_absent = 0
    w._band_expect = None
    w._band_learn = None
    w._band_verdicts = {}
    w._band_obs = IDLE

def shutdown_band(w) -> None:
    watcher = getattr(w, '_band_watcher', None)
    if watcher is not None:
        try:
            watcher.stop()
        except Exception:
            pass
    release_band(w)
    w._band_watcher = None
__all__ = ['ABSENT_POLLS_TO_END', 'EXPECT_POLLS_MAX', 'BandObservation', 'IDLE', 'poll_action_text_band', 'current_band', 'release_band', 'shutdown_band']
