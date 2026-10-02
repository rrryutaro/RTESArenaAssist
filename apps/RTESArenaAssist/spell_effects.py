from __future__ import annotations
from dataclasses import dataclass
import math
import time
from player_condition import ConditionFields, read_fields
from combat_text_ja import text as combat_text
_TIMER_BASE = -3904
_TIMER_BYTES = 36
_TIMER_BIT_INDEX = {'fire': 2, 'levitate': 7, 'light': 8}
_MAX_TIMER = 10000
_GAME_TIME_OFFSET = 1484

@dataclass(frozen=True)
class SpellEffectSample:
    fields: ConditionFields
    strength_current: int
    strength_base: int
    timers: dict[str, int | None]
    game_time: int | None = None

@dataclass(frozen=True)
class SpellEffectRow:
    key: str
    name: str
    glyph: str
    color: str
    value: str
    ratio: float | None
_META = {'light': ('☀', '#f4ce78'), 'shield': ('◆', '#8dcbeb'), 'strength': ('↑', '#eaa09a'), 'fire': ('♨', '#ef9c67'), 'levitate': ('✧', '#bfa7eb')}

def read_sample(analyzer, anchor: int) -> SpellEffectSample | None:
    fields = read_fields(analyzer, anchor)
    if fields is None:
        return None
    try:
        attributes = analyzer.read_bytes(anchor + 461, 16)
        raw_timers = analyzer.read_bytes(anchor + _TIMER_BASE, _TIMER_BYTES)
    except (OSError, AttributeError):
        return None
    if not attributes or len(attributes) < 16 or (not raw_timers) or (len(raw_timers) < _TIMER_BYTES):
        return None
    timers: dict[str, int | None] = {}
    for key, index in _TIMER_BIT_INDEX.items():
        at = index * 4
        value = int.from_bytes(raw_timers[at:at + 2], 'little')
        timers[key] = value if 0 < value <= _MAX_TIMER else None
    try:
        raw_time = analyzer.read_bytes(anchor + _GAME_TIME_OFFSET, 4)
        game_time = int.from_bytes(raw_time, 'little') if len(raw_time) == 4 else None
    except (OSError, AttributeError):
        game_time = None
    return SpellEffectSample(fields=fields, strength_current=attributes[0], strength_base=attributes[8], timers=timers, game_time=game_time)

class _ObservedRoundClock:

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_wall: float | None = None
        self._active_seconds = 0.0
        self._game_time: int | None = None
        self._last_tick_active: float | None = None
        self._round_seconds: float | None = None
        self._last_measured_round_seconds: float | None = None

    def pause(self) -> None:
        self._last_wall = None
        self._last_tick_active = None
        self._round_seconds = None

    def observe(self, game_time: int | None, now: float) -> None:
        if self._last_wall is not None:
            self._active_seconds += max(0.0, now - self._last_wall)
        self._last_wall = now
        if game_time is None:
            self._game_time = None
            self._last_tick_active = None
            self._round_seconds = None
            return
        if self._game_time is None:
            self._game_time = game_time
            return
        delta = game_time - self._game_time & 4294967295
        if delta == 0:
            return
        if delta == 1 and self._last_tick_active is not None:
            interval = self._active_seconds - self._last_tick_active
            if interval >= 0.5:
                self._round_seconds = interval
                self._last_measured_round_seconds = interval
            else:
                self._round_seconds = None
        else:
            self._round_seconds = None
        self._last_tick_active = self._active_seconds
        self._game_time = game_time

    def remaining(self, rounds: int) -> tuple[int, float]:
        period = self._round_seconds or self._last_measured_round_seconds or 5.0
        tick = self._last_tick_active
        elapsed = min(math.floor(max(0.0, self._active_seconds - tick)), max(0.0, period - 0.001)) if tick is not None else 0
        remaining_rounds = max(0.001, rounds - elapsed / period)
        return (max(1, math.ceil(remaining_rounds * period)), remaining_rounds)

class SpellEffectTracker:

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._clock = _ObservedRoundClock()
        self._previous: dict[str, int | None] = {}
        self._maximum: dict[str, int] = {}
        self._order: list[str] = []
        self._strength_decay = False
        self._strength_baseline: int | None = None

    def pause(self) -> None:
        self._clock.pause()

    def update(self, sample: SpellEffectSample, *, time_unit: str='rounds', now: float | None=None) -> list[SpellEffectRow]:
        observed_at = time.monotonic() if now is None else now
        self._clock.observe(sample.game_time, observed_at)
        fields = sample.fields
        fortified = bool(fields.flags & 16 and fields.counters[4])
        if not fortified and (not self._strength_decay):
            self._strength_baseline = sample.strength_current
        baseline = self._strength_baseline
        strength_delta = max(0, sample.strength_current - baseline) if baseline is not None else None
        if fortified:
            self._strength_decay = baseline is not None
        elif baseline is None or sample.strength_current <= baseline:
            self._strength_decay = False
        active = {'light': bool(fields.effects & 256), 'shield': fields.shield > 0, 'strength': fortified or (self._strength_decay and bool(strength_delta)), 'fire': bool(fields.effects & 4), 'levitate': bool(fields.effects & 128)}
        amount = {'light': sample.timers.get('light'), 'shield': fields.shield, 'strength': strength_delta, 'fire': sample.timers.get('fire'), 'levitate': sample.timers.get('levitate')}
        for key in _META:
            now = amount[key] if active[key] else None
            before = self._previous.get(key)
            if not active[key]:
                self._maximum.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
            else:
                if key not in self._order:
                    self._order.append(key)
                if now is not None and (key in self._previous and before is None or (before is not None and now > before)):
                    self._maximum[key] = now
            self._previous[key] = now
        rows = []
        for key in self._order:
            glyph, color = _META[key]
            name = combat_text(f'spell_effect.name.{key}')
            value = amount[key]
            seconds = None
            if key == 'shield':
                label = combat_text('spell_effect.remaining_points', value=value)
            elif key == 'strength':
                if baseline is None:
                    label = combat_text('spell_effect.active')
                else:
                    display_current = round(sample.strength_current * 100 / 256)
                    display_base = round(baseline * 100 / 256)
                    label = f'+{display_current - display_base}'
            else:
                seconds = self._clock.remaining(value) if time_unit == 'seconds' and value is not None else None
                label = combat_text('spell_effect.remaining_seconds', value=seconds[0]) if seconds is not None else combat_text('spell_effect.remaining_rounds', value=value) if value is not None else combat_text('spell_effect.active')
            maximum = self._maximum.get(key)
            meter_value = seconds[1] if seconds is not None else value
            ratio = max(0.0, min(1.0, meter_value / maximum)) if value is not None and maximum else None
            rows.append(SpellEffectRow(key, name, glyph, color, label, ratio))
        return rows
__all__ = ['SpellEffectSample', 'SpellEffectRow', 'SpellEffectTracker', 'read_sample']
