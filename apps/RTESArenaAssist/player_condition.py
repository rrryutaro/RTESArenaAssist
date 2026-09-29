from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional
import assist_log
import date_translator
_log = logging.getLogger('RTESArenaAssist')
OFF_STATUS_FLAGS = 1457
OFF_STATUS_COUNTERS = 1459
OFF_ACTIVE_EFFECTS = 1470
OFF_SHIELD_VALUE = 1472
STATUS_COUNTER_COUNT = 10
_READ_SIZE = OFF_SHIELD_VALUE + 2 - OFF_STATUS_FLAGS
OFF_HP_CURR = 509
OFF_HP_MAX = 511
_FLAG_WORDS: tuple[tuple[int, int], ...] = ((1, 1), (2, 2), (32, 4), (128, 19), (64, 20), (4, 21), (512, 22))
_EFFECT_WORDS: tuple[tuple[int, int], ...] = ((1, 5), (2, 6), (4, 7), (8, 8), (16, 9), (32, 10), (64, 11), (128, 12), (512, 14), (1024, 15), (2048, 16), (4096, 17))
_BAD_WORDS = frozenset({1, 2, 4, 14, 20, 21, 22})
_HEALTHY_WORD = 0
_FLAG_NAMES = {1: 'diseased', 2: 'poisoned', 4: 'cursed', 8: 'blessed', 16: 'fortified', 32: 'drunk', 64: 'paralyzed', 128: 'regenerating', 256: 'dead', 512: 'being drained', 4096: 'creature', 16384: 'player?'}
_EFFECT_NAMES = {1: 'invisible', 2: 'non-target', 4: 'resist fire', 8: 'resist cold', 16: 'resist shock', 32: 'resist acid', 64: 'resist poison', 128: 'levitating', 256: 'light?', 512: 'silenced', 1024: 'absorb spells', 2048: 'reflect spells', 4096: 'resist spells'}

@dataclass(frozen=True)
class ConditionFields:
    flags: int
    counters: tuple[int, ...]
    effects: int
    shield: int

def read_fields(analyzer, anchor: int) -> Optional[ConditionFields]:
    if analyzer is None or not anchor:
        return None
    try:
        raw = analyzer.read_bytes(anchor + OFF_STATUS_FLAGS, _READ_SIZE)
    except (OSError, AttributeError):
        return None
    if not raw or len(raw) < _READ_SIZE:
        return None
    base = OFF_STATUS_FLAGS
    counters_at = OFF_STATUS_COUNTERS - base
    effects_at = OFF_ACTIVE_EFFECTS - base
    shield_at = OFF_SHIELD_VALUE - base
    return ConditionFields(flags=raw[0] | raw[1] << 8, counters=tuple(raw[counters_at:counters_at + STATUS_COUNTER_COUNT]), effects=raw[effects_at] | raw[effects_at + 1] << 8, shield=raw[shield_at] | raw[shield_at + 1] << 8)

def read_hp(analyzer, anchor: int) -> tuple[Optional[int], Optional[int]]:
    try:
        raw = analyzer.read_bytes(anchor + OFF_HP_CURR, 4)
    except (OSError, AttributeError):
        return (None, None)
    if not raw or len(raw) < 4:
        return (None, None)
    return (raw[0] | raw[1] << 8, raw[2] | raw[3] << 8)

def word_indices(fields: ConditionFields) -> list[int]:
    found = [index for bit, index in _FLAG_WORDS if fields.flags & bit]
    found += [index for bit, index in _EFFECT_WORDS if fields.effects & bit]
    return sorted(found)

def sheet_values(fields: ConditionFields, separator: str) -> dict[str, str]:
    indices = word_indices(fields)
    bad = [w for w in (date_translator.effect_word(i) for i in indices if i in _BAD_WORDS) if w]
    good = [w for w in (date_translator.effect_word(i) for i in indices if i not in _BAD_WORDS) if w]
    words = [w for w in (date_translator.effect_word(i) for i in indices) if w]
    out = {'condition': separator.join(words) if words else date_translator.effect_word(_HEALTHY_WORD) or ''}
    if bad:
        out['condition_bad'] = separator.join(bad)
    if good:
        out['condition_good'] = separator.join(good)
    return out

def _bit_names(value: int, names: dict[int, str]) -> str:
    parts = []
    bit = 1
    while bit <= 32768:
        if value & bit:
            parts.append(names.get(bit, f'0x{bit:04X}?'))
        bit <<= 1
    return ','.join(parts)

def describe(fields: ConditionFields) -> str:
    return '状態=0x%04X[%s] 魔法の効果=0x%04X[%s] カウンタ=%s ShieldValue=%d' % (fields.flags, _bit_names(fields.flags, _FLAG_NAMES), fields.effects, _bit_names(fields.effects, _EFFECT_NAMES), list(fields.counters), fields.shield)

class ConditionLog:

    def __init__(self) -> None:
        self._last_key: Optional[tuple] = None

    def reset(self) -> None:
        self._last_key = None

    def observe(self, fields: ConditionFields, *, hp: Optional[int]=None, hp_max: Optional[int]=None) -> bool:
        key = (fields.flags, fields.effects, fields.shield, tuple((value != 0 for value in fields.counters)))
        if key == self._last_key:
            return False
        first = self._last_key is None
        self._last_key = key
        assist_log.recog(_log, 'プレイヤーの状態の欄: %s%s 体力=%s/%s', '（接続時）' if first else '', describe(fields), '?' if hp is None else hp, '?' if hp_max is None else hp_max)
        return True

def log_status_window(state_lines, fields: Optional[ConditionFields], *, hp: Optional[int]=None, hp_max: Optional[int]=None) -> None:
    assist_log.recog(_log, 'ステータスの窓の状態の行: %s 欄: %s 体力=%s/%s', list(state_lines or ()), describe(fields) if fields is not None else '（読めない）', '?' if hp is None else hp, '?' if hp_max is None else hp_max)
__all__ = ['OFF_STATUS_FLAGS', 'OFF_STATUS_COUNTERS', 'OFF_ACTIVE_EFFECTS', 'OFF_SHIELD_VALUE', 'OFF_HP_CURR', 'OFF_HP_MAX', 'ConditionFields', 'ConditionLog', 'read_fields', 'read_hp', 'word_indices', 'sheet_values', 'describe', 'log_status_window']
