from __future__ import annotations
import re
from typing import Optional, Tuple
DATE_PATTERN = re.compile('^\\s*(\\w+)\\s*,\\s*(\\d+)(?:st|nd|rd|th)?\\s+of\\s+(.+?)\\s+in\\s+the\\s+year\\s+(\\d+)E\\s+(\\d+)\\s*$', re.IGNORECASE)
_DAY_EN = ('Sundas', 'Morndas', 'Tirdas', 'Middas', 'Turdas', 'Fredas', 'Loredas')
_MONTH_EN = ('Morning Star', "Sun's Dawn", 'First Seed', "Rain's Hand", 'Second Seed', 'Mid Year', "Sun's Height", 'Last Seed', 'Hearthfire', 'Frostfall', "Sun's Dusk", 'Evening Star')
_PART_EN = ('morning', 'afternoon', 'evening', 'night')
_HEALTH_EN = ('healthy', 'diseased', 'poisoned', 'in critical condition', 'drunk', 'invisible', 'a non-target', 'resistant to fire', 'resistant to cold', 'resistant to shock', 'resistant to acid', 'resistant to poison', 'levitating', '', 'silenced', 'able to absorb spells', 'able to reflect spells', 'resistant to spells', 'shielded', 'regenerating', 'paralyzed', 'cursed', 'being drained')
_DISEASE_EN = ('Witch Pox', 'Plague', 'Yellow Fever', 'Stomach Rot', 'Consumption', 'Brain Fever', 'Swamp Rot', 'Calirons Curse', 'Cholera', 'Leprosy', 'Wound Rot', 'Red Death', 'Blood Rot', 'Typhoid Fever', 'Dementia', 'Chrondiasis', 'Wizard Fever')
_ATTRIBUTE_EN = ('Strength', 'Intelligence', 'Willpower', 'Agility', 'Speed', 'Endurance', 'Personality', 'Luck')

def _sbt_value(group: str, surface: str, en_list: tuple) -> Optional[str]:
    import i18n_helper as i18n
    v = i18n.value('status_buffer_text', surface)
    if v is not None:
        return v
    try:
        idx = en_list.index(surface)
    except ValueError:
        return None
    return i18n.text_opt(f'status_buffer_text.{group}.{idx}')

def parse_and_translate(text: str) -> Optional[Tuple[str, str]]:
    if not text:
        return None
    m = DATE_PATTERN.match(text)
    if not m:
        return None
    import i18n_helper as i18n
    day_en, day_num, month_en, era_num, year_num = m.groups()
    day_key = day_en.strip()
    day_ja = _sbt_value('day', day_key, _DAY_EN)
    if day_ja is None:
        return None
    month_key = re.sub('\\s+', ' ', month_en.strip())
    month_ja = _sbt_value('month', month_key, _MONTH_EN)
    if month_ja is None:
        return None
    era_ja = i18n.value('status_buffer_text', era_num) or i18n.text('status_buffer_text.era_fallback').replace('{era}', era_num)
    en = text.strip()
    ja = i18n.text('status_buffer_text.date_format').replace('{era}', era_ja).replace('{year}', year_num).replace('{month}', month_ja).replace('{day}', day_num).replace('{weekday}', day_ja)
    return (en, ja)
LOCATION_PATTERN = re.compile('^You are in\\s+(.+?)\\.?\\s*$')
TIME_PATTERN = re.compile('^It is\\s+(\\d+):(\\d+)\\s+in the\\s+(\\w+)\\.?\\s*$')
DATE_HEADER_PATTERN = re.compile('^The date is\\s+(.+?)\\s*$')
LOAD_PATTERN = re.compile('^You are currently carrying\\s+([\\d.]+)\\s*kg\\s+out of\\s+([\\d.]+)\\s*kg\\.?\\s*$')
DISEASE_PATTERN = re.compile('^You have\\s+(.+?)\\.?\\s*$')
FORTIFY_PATTERN = re.compile('^Your\\s+(.+?)\\s+is fortified\\.?\\s*$')
HEALTH_PATTERN = re.compile('^You are\\s+(.+?)\\.?\\s*$')

def is_status_state_line(line: str) -> bool:
    if not line:
        return False
    s = line.strip()
    return bool(DISEASE_PATTERN.match(s) or FORTIFY_PATTERN.match(s) or HEALTH_PATTERN.match(s))

def _translate_state_line(line: str) -> Optional[str]:
    import i18n_helper as i18n
    if not line:
        return None
    m = DISEASE_PATTERN.match(line)
    if m:
        name = m.group(1).strip()
        name_ja = _sbt_value('disease', name, _DISEASE_EN) or name
        return i18n.text('status_buffer_text.line_disease').replace('{disease}', name_ja)
    m = FORTIFY_PATTERN.match(line)
    if m:
        attr = m.group(1).strip()
        attr_ja = _sbt_value('attribute', attr, _ATTRIBUTE_EN) or attr
        return i18n.text('status_buffer_text.line_fortify').replace('{attribute}', attr_ja)
    m = HEALTH_PATTERN.match(line)
    if m:
        state = m.group(1).strip().lower()
        state_ja = _sbt_value('health', state, _HEALTH_EN) or state
        return i18n.text('status_buffer_text.line_state').replace('{state}', state_ja)
    return None

def _translate_status_line(line: str) -> Optional[str]:
    import i18n_helper as i18n
    if not line:
        return None
    m = LOCATION_PATTERN.match(line)
    if m:
        loc_en = m.group(1)
        try:
            import location_lookup
            loc_ja = location_lookup.lookup(loc_en) or loc_en
        except ImportError:
            loc_ja = loc_en
        return i18n.text('status_buffer_text.line_location').replace('{location}', loc_ja)
    m = TIME_PATTERN.match(line)
    if m:
        h, mn, part = m.groups()
        part_ja = _sbt_value('part', part.lower(), _PART_EN) or part
        return i18n.text('status_buffer_text.line_time').replace('{hour}', h).replace('{minute}', mn).replace('{part}', part_ja)
    m = DATE_HEADER_PATTERN.match(line)
    if m:
        date_part = m.group(1).rstrip('.').strip()
        result = parse_and_translate(date_part)
        if result is not None:
            _, ja = result
            return i18n.text('status_buffer_text.line_date').replace('{date}', ja)
        return None
    m = LOAD_PATTERN.match(line)
    if m:
        cur, mx = m.groups()
        return i18n.text('status_buffer_text.line_load').replace('{current}', cur).replace('{max}', mx)
    bare_date = parse_and_translate(line)
    if bare_date is not None:
        _, ja = bare_date
        return i18n.text('status_buffer_text.line_date').replace('{date}', ja)
    return _translate_state_line(line)
if __name__ == '__main__':
    samples = ['Tirdas, 1st of Hearthfire in the year 3E 389', "Loredas, 23rd of Sun's Dusk in the year 3E 401", "Morndas, 2nd of Rain's Hand in the year 3E 389", 'Hello world', '', '1st of Hearthfire']
    print('=== parse_and_translate (single date line) ===')
    for s in samples:
        result = parse_and_translate(s)
        print(f'  IN : {s!r}')
        print(f'  OUT: {result!r}')
    print()
    print('=== _translate_status_line (per line) ===')
    for line in ('You are in Imperial Dungeons.', 'It is 12:21 in the afternoon.', 'The date is Tirdas, 1st of Hearthfire in the year 3E 389', 'You are currently carrying 0 kg out of 82 kg.', 'You are healthy.'):
        print(f'  {line!r} -> {_translate_status_line(line)!r}')
        print('  --- 和訳 ---')
        for line in ja.split('\n'):
            print(f'    {line}')
