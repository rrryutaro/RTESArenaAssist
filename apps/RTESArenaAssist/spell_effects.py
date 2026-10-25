from __future__ import annotations
from dataclasses import dataclass
import math
import time
from player_condition import FORTIFY_WINDOW_POSITION, SHIELD_WINDOW_POSITION, ConditionFields, effect_window_position, flag_window_position, read_fields
from combat_text_ja import text as combat_text
_TIMER_BASE = -3904
_TIMER_ENTRIES = 13
_TIMER_BYTES = _TIMER_ENTRIES * 4
_TIMER_MIN_BYTES = 36
_TIMER_BIT_INDEX = {'invisible': 0, 'fire': 2, 'cold': 3, 'shock': 4, 'magic': 5, 'poison': 6, 'levitate': 7, 'light': 8, 'silence': 9, 'absorb': 10, 'reflect': 11, 'spell_resist': 12}
_EFFECT_SPEC = {'light': (17, 0, 0), 'shield': (2, 0, 0), 'strength': (11, 255, 255), 'fire': (10, 0, 0), 'cold': (10, 1, 0), 'shock': (10, 2, 0), 'magic': (10, 3, 0), 'poison': (10, 4, 0), 'levitate': (16, 0, 0), 'invisible': (15, 0, 0), 'silence': (21, 0, 0), 'absorb': (22, 0, 0), 'reflect': (23, 0, 0), 'spell_resist': (24, 0, 0), 'regenerate': (20, 0, 0)}
_EFFECT_BIT = {'invisible': 1, 'fire': 4, 'cold': 8, 'shock': 16, 'magic': 32, 'poison': 64, 'levitate': 128, 'light': 256, 'silence': 512, 'absorb': 1024, 'reflect': 2048, 'spell_resist': 4096}
_MAX_TIMER = 10000
_GAME_TIME_OFFSET = 1484
_BUFFS_OFFSET = 1632
_BUFF_SIZE = 60
_BUFF_COUNT = 16
_BUFF_MODS_AT = 6
_BUFF_UNUSED_AT = 58

@dataclass(frozen=True)
class SpellEffectSample:
    fields: ConditionFields
    strength_current: int
    strength_base: int
    timers: dict[str, int | None]
    game_time: int | None = None
    attributes: tuple[int, ...] = ()
    fortify: tuple[int, int] | None = None

@dataclass(frozen=True)
class SpellEffectRow:
    key: str
    name: str
    glyph: str
    color: str
    value: str
    ratio: float | None
_META = {'light': ('☀', '#f4ce78'), 'shield': ('◆', '#8dcbeb'), 'strength': ('↑', '#eaa09a'), 'fire': ('♨', '#ef9c67'), 'cold': ('❄', '#9bd0f0'), 'shock': ('ϟ', '#f2e07a'), 'magic': ('✦', '#c7a6f0'), 'poison': ('☣', '#9fd88a'), 'levitate': ('✧', '#bfa7eb'), 'invisible': ('◌', '#b8c4d6'), 'silence': ('∅', '#d8a0a0'), 'absorb': ('◈', '#7fd1c4'), 'reflect': ('◇', '#a0c8f0'), 'spell_resist': ('◉', '#8fb8e8'), 'regenerate': ('✚', '#9fe0a8')}
_REGENERATE_FLAG = 128
_WINDOW_POSITION = {**{key: effect_window_position(bit) for key, bit in _EFFECT_BIT.items()}, 'shield': SHIELD_WINDOW_POSITION, 'regenerate': flag_window_position(_REGENERATE_FLAG), 'strength': FORTIFY_WINDOW_POSITION}
_ROUND_SAMPLES = 2
_fortified_attribute: int | None = None

def fortified_attribute() -> int | None:
    return _fortified_attribute

def effect_label(key: str, attribute: int | None=None) -> str:
    spec = _EFFECT_SPEC.get(key)
    if spec is None:
        return ''
    if key == 'strength' and attribute is not None:
        spec = (spec[0], attribute, attribute)
    from spell_effect_compose import effect_display_names
    names = effect_display_names([spec[0]], [spec[1]], [spec[2]], short=True)
    return names[0] if names else ''

def fortify_from_buffs(raw: bytes) -> tuple[int, int] | None:
    gains = [0] * 8
    for index in range(min(_BUFF_COUNT, len(raw) // _BUFF_SIZE)):
        buff = raw[index * _BUFF_SIZE:(index + 1) * _BUFF_SIZE]
        if buff[_BUFF_UNUSED_AT] == 255 and buff[_BUFF_UNUSED_AT + 1] == 255:
            continue
        for attr, value in enumerate(buff[_BUFF_MODS_AT:_BUFF_MODS_AT + 8]):
            if 0 < value < 128:
                gains[attr] += value
    best = max(gains)
    return (gains.index(best), best) if best > 0 else None

def read_sample(analyzer, anchor: int) -> SpellEffectSample | None:
    fields = read_fields(analyzer, anchor)
    if fields is None:
        return None
    try:
        attributes = analyzer.read_bytes(anchor + 461, 16)
        raw_timers = analyzer.read_bytes(anchor + _TIMER_BASE, _TIMER_BYTES)
    except (OSError, AttributeError):
        return None
    if not attributes or len(attributes) < 16 or (not raw_timers) or (len(raw_timers) < _TIMER_MIN_BYTES):
        return None
    if len(raw_timers) < _TIMER_BYTES:
        raw_timers = bytes(raw_timers) + bytes(_TIMER_BYTES - len(raw_timers))
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
    try:
        raw_buffs = analyzer.read_bytes(anchor + _BUFFS_OFFSET, _BUFF_SIZE * _BUFF_COUNT)
        fortify = fortify_from_buffs(raw_buffs) if raw_buffs else None
    except Exception:
        fortify = None
    return SpellEffectSample(fields=fields, strength_current=attributes[0], strength_base=attributes[8], timers=timers, game_time=game_time, attributes=tuple(attributes[0:8]), fortify=fortify)

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
        self._intervals: list[float] = []

    def pause(self) -> None:
        self._last_wall = None
        self._last_tick_active = None
        self._round_seconds = None
        self._intervals = []

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
                self._intervals = (self._intervals + [interval])[-_ROUND_SAMPLES:]
                period = min(self._intervals)
                self._round_seconds = period
                self._last_measured_round_seconds = period
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
        self._strength_baseline: tuple[int, ...] | None = None
        self._fortified_attribute: int | None = None
        self._publish_fortified()

    def _publish_fortified(self) -> None:
        global _fortified_attribute
        _fortified_attribute = self._fortified_attribute

    def pause(self) -> None:
        self._clock.pause()

    def update(self, sample: SpellEffectSample, *, time_unit: str='rounds', now: float | None=None) -> list[SpellEffectRow]:
        observed_at = time.monotonic() if now is None else now
        self._clock.observe(sample.game_time, observed_at)
        fields = sample.fields
        fortified = bool(fields.flags & 16 and fields.counters[4])
        current = sample.attributes or (sample.strength_current,)
        if not fortified and (not self._strength_decay) or (self._strength_baseline is not None and len(self._strength_baseline) != len(current)):
            self._strength_baseline = current
            if not fortified:
                self._fortified_attribute = None
        baseline = self._strength_baseline
        recorded = sample.fortify if fortified else None
        if recorded is not None and recorded[0] >= len(current):
            recorded = None
        deltas = [max(0, c - b) for c, b in zip(current, baseline)] if baseline is not None else None
        if recorded is not None:
            self._fortified_attribute = recorded[0]
        elif deltas is not None and max(deltas) > 0:
            self._fortified_attribute = deltas.index(max(deltas))
        attr = self._fortified_attribute
        self._publish_fortified()
        strength_delta = recorded[1] if recorded is not None else deltas[attr] if deltas is not None and attr is not None else 0 if deltas is not None else None
        if fortified:
            self._strength_decay = baseline is not None
        elif baseline is None or all((c <= b for c, b in zip(current, baseline))):
            self._strength_decay = False
        active = {key: bool(fields.effects & bit) for key, bit in _EFFECT_BIT.items()}
        active['shield'] = fields.shield > 0
        active['regenerate'] = bool(fields.flags & _REGENERATE_FLAG)
        active['strength'] = fortified or (self._strength_decay and bool(strength_delta))
        amount = {key: sample.timers.get(key) for key in _EFFECT_BIT}
        amount['shield'] = fields.shield
        amount['strength'] = strength_delta
        amount['regenerate'] = None
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
        for key in sorted(self._order, key=_WINDOW_POSITION.__getitem__):
            glyph, color = _META[key]
            name = effect_label(key, self._fortified_attribute) if key == 'strength' else effect_label(key)
            value = amount[key]
            seconds = None
            if key == 'shield':
                label = combat_text('spell_effect.remaining_points', value=value)
            elif key == 'strength':
                if recorded is not None:
                    display_current = round(current[attr] * 100 / 256)
                    display_before = round((current[attr] - recorded[1]) * 100 / 256)
                    label = f'+{display_current - display_before}'
                elif baseline is None:
                    label = combat_text('spell_effect.active')
                else:
                    at = attr if attr is not None else 0
                    display_current = round(current[at] * 100 / 256)
                    display_base = round(baseline[at] * 100 / 256)
                    label = f'+{display_current - display_base}'
            else:
                seconds = self._clock.remaining(value) if time_unit == 'seconds' and value is not None else None
                label = combat_text('spell_effect.remaining_seconds', value=seconds[0]) if seconds is not None else combat_text('spell_effect.remaining_rounds', value=value) if value is not None else combat_text('spell_effect.active')
            maximum = self._maximum.get(key)
            meter_value = seconds[1] if seconds is not None else value
            ratio = max(0.0, min(1.0, meter_value / maximum)) if value is not None and maximum else None
            rows.append(SpellEffectRow(key, name, glyph, color, label, ratio))
        return rows
__all__ = ['SpellEffectSample', 'SpellEffectRow', 'SpellEffectTracker', 'fortified_attribute', 'read_sample']
