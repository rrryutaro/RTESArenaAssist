from __future__ import annotations
import re
from typing import Iterable, Mapping, Optional
import armor_rating
import i18n_helper as i18n
from attributes_panel import ATTR_KEYS as _ATTR_CODES, DERIVED_LABEL_KEYS, STAT_LABEL_KEYS, UNKNOWN, attr_label
ATTR_KEYS: tuple[str, ...] = tuple((code.lower() for code in _ATTR_CODES))
_GAUGES: tuple[tuple[str, str, str], ...] = (('hp_pct', 'hp_curr', 'hp_max'), ('fatigue_pct', 'fatigue_curr', 'fatigue_max'), ('spell_pts_pct', 'spell_pts_curr', 'spell_pts_max'))
DERIVED_KEYS: tuple[str, ...] = (*(name for key, _, _ in _GAUGES for name in (key, f'{key}_rest')), 'experience_pct', 'experience_pct_rest', 'experience_to_next')
CONDITION_KEYS: tuple[str, ...] = ('condition', 'condition_bad', 'condition_good')
ARMOR_KEYS: tuple[str, ...] = tuple((f'ar_{location}' for location in armor_rating.LOCATIONS))
VALUE_KEYS: tuple[str, ...] = ('name', 'race', 'race_en', 'class', 'class_en', *ATTR_KEYS, 'damage', 'max_kilos', 'magic_def', 'to_hit', 'to_defend', 'health', 'heal_mod', 'charisma', 'spell_pts', 'spell_pts_curr', 'spell_pts_max', 'bonus_pts', 'hp', 'hp_curr', 'hp_max', 'fatigue', 'fatigue_curr', 'fatigue_max', 'gold', 'level', 'experience', 'experience_next', *DERIVED_KEYS, *CONDITION_KEYS, *ARMOR_KEYS)
IMAGE_KEYS: tuple[str, ...] = ('face', 'body')
_LABEL_IDS: dict[str, str] = {'name': 'status.name', 'race': 'status.race', 'class': 'status.class', **DERIVED_LABEL_KEYS, **STAT_LABEL_KEYS, 'experience_next': 'charsheet.label.next_level', 'experience_to_next': 'charsheet.label.to_next_level', 'title': 'charsheet.title', 'section_attributes': 'charsheet.section.attributes', 'section_combat': 'charsheet.section.combat', 'section_vitals': 'charsheet.section.vitals', 'section_record': 'charsheet.section.record', 'col_value': 'charsheet.col.value', 'col_modifier': 'charsheet.col.modifier', 'condition': 'charsheet.label.condition', 'section_armor': 'charsheet.section.armor', 'armor_note': 'charsheet.armor.note', **{f'ar_{location}': f'charsheet.armor.{location}' for location in armor_rating.LOCATIONS}}
LABEL_KEYS: tuple[str, ...] = (*_LABEL_IDS, *ATTR_KEYS, *(f'{key}_code' for key in ATTR_KEYS))
_ATTR_LABEL_RE = re.compile('^(.*?)\\s*\\(([A-Z]{3})\\)\\s*$')

def split_attr_label(text: str, code: str) -> tuple[str, str]:
    match = _ATTR_LABEL_RE.match(text or '')
    if match and match.group(1):
        return (match.group(1), match.group(2))
    return (text or code, code)

def _number(text: Optional[str]) -> Optional[int]:
    try:
        return int(text) if text not in (None, '') else None
    except ValueError:
        return None

def _percent(part: Optional[int], whole: Optional[int]) -> Optional[int]:
    if part is None or whole is None or whole <= 0:
        return None
    return max(0, min(100, round(part * 100 / whole)))

def _put_gauge(out: dict[str, str], key: str, pct: Optional[int]) -> None:
    if pct is not None:
        out[key] = str(pct)
        out[f'{key}_rest'] = str(100 - pct)

def with_derived(values: Mapping[str, str]) -> dict[str, str]:
    out = dict(values)
    for key, curr_key, max_key in _GAUGES:
        _put_gauge(out, key, _percent(_number(values.get(curr_key)), _number(values.get(max_key))))
    experience = _number(values.get('experience'))
    next_level = _number(values.get('experience_next'))
    if experience is not None and next_level is not None:
        out['experience_to_next'] = str(max(0, next_level - experience))
        start = _number(values.get('experience_start'))
        if start is not None and next_level > start:
            _put_gauge(out, 'experience_pct', _percent(experience - start, next_level - start))
    return out

def with_armor(values: Mapping[str, str], equipped: Optional[Iterable[dict]]) -> dict[str, str]:
    out = dict(values)
    out.update(armor_rating.sheet_values(armor_rating.compute(equipped, armor_rating.parse_signed(values.get('to_defend')))))
    return out

def labels() -> dict[str, str]:
    out = {key: i18n.text(label_id) for key, label_id in _LABEL_IDS.items()}
    for key, code in zip(ATTR_KEYS, _ATTR_CODES):
        name, short = split_attr_label(attr_label(code), code)
        out[key] = name
        out[f'{key}_code'] = short
    return out
__all__ = ['ATTR_KEYS', 'DERIVED_KEYS', 'CONDITION_KEYS', 'ARMOR_KEYS', 'VALUE_KEYS', 'IMAGE_KEYS', 'LABEL_KEYS', 'UNKNOWN', 'labels', 'split_attr_label', 'with_derived', 'with_armor']
