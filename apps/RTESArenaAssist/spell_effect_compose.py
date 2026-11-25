from __future__ import annotations
import re
_EFFECT_TARGET_JA = {'health': 'ヘルス', 'Health': 'ヘルス', 'spell pts': '呪文ポイント', 'Spell Pts': '呪文ポイント', 'fatigue': '疲労', 'Fatigue': '疲労'}
_TEMPLATES = [(re.compile('^(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+damage\\s+to\\s+(\\w+(?:\\s+\\w+)?)\\s*\\+\\s*(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+per\\s+(\\d+)\\s+level\\(s\\)\\.?$'), 'damage'), (re.compile('^\\+\\s*(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+to\\s+(\\w+(?:\\s+\\w+)?)\\s*\\+\\s*(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+per\\s+(\\d+)\\s+level\\(s\\)\\.?$'), 'heal'), (re.compile('^(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+drain\\s+to\\s+(\\w+(?:\\s+\\w+)?)\\s*\\+\\s*(\\d+)\\s+to\\s+(\\d+)\\s+pts\\s+per\\s+(\\d+)\\s+level\\(s\\)\\.?$'), 'drain')]

def _lookup_pair(table: dict, key: int) -> tuple[str, str]:
    pair = table.get(key)
    if pair is not None:
        return pair
    return ('—', '—')

def _active_effect_slot(effects: list[int]) -> int:
    for i, effect_id in enumerate(effects[:3]):
        if effect_id != 255:
            return i
    return 0

def _has_id(id_str: str) -> bool:
    import i18n_helper as i18n
    return i18n.text_opt(id_str) is not None

def _words_to_ids(words: list[str]) -> list[str]:
    for head in range(len(words), 0, -1):
        cid = 'mages.' + ' '.join(words[:head])
        if _has_id(cid):
            return [cid] + [f'mages.{w}' for w in words[head:]]
    return [f'mages.{w}' for w in words]

def _effect_display_ids(effect_id: int, sub_id: int, attr_id: int) -> list[str]:
    from spellmaker_tables import current
    tables = current()
    if tables is None:
        return []
    words = tables.name_words(effect_id, sub_id, attr_id)
    return _words_to_ids(words) if words else []

def _id_anchor(id_str: str) -> str:
    import i18n_helper as i18n
    o = i18n.original(id_str)
    return o if o else id_str.split('.', 1)[-1]

def _resolve_effect_name(effect_id: int, sub_id: int, attr_id: int) -> tuple[str, str]:
    if effect_id == 255:
        return ('(none)', '(なし)')
    ids = _effect_display_ids(effect_id, sub_id, attr_id)
    if not ids:
        return ('—', '—')
    import i18n_helper as i18n
    en_parts, ja_parts = ([], [])
    for id_str in ids:
        anchor = _id_anchor(id_str)
        ja = i18n.lang_value_in(id_str, 'ja')
        en_parts.append(anchor)
        ja_parts.append(ja if ja else anchor)
    return (' '.join(en_parts), ' '.join(ja_parts))

def _effect_details_from_arrays(effects: list[int], sub_effects: list[int], affected_attrs: list[int]) -> list[dict]:
    details: list[dict] = []
    for slot, effect_id in enumerate(effects[:3]):
        if effect_id == 255:
            continue
        sub_id = sub_effects[slot] if slot < len(sub_effects) else 0
        attr_id = affected_attrs[slot] if slot < len(affected_attrs) else 0
        effect_en, effect_ja = _resolve_effect_name(effect_id, sub_id, attr_id)
        display_ids = _effect_display_ids(effect_id, sub_id, attr_id)
        details.append({'slot': slot, 'effect_id': effect_id, 'sub_effect_id': sub_id, 'affected_attr_id': attr_id, 'effect_display_ids': display_ids, 'effect_anchor_id': display_ids[0] if len(display_ids) == 1 else None, 'effect_en': effect_en, 'effect_ja': effect_ja, 'text_en': '', 'text_ja': ''})
    return details
_SHORT_SIMPLE_KEYS = {15: 'invisible', 16: 'levitate', 17: 'light', 21: 'silence', 22: 'absorb', 23: 'reflect', 24: 'spell_resist'}
_SHORT_ELEMENT_KEYS = {0: 'fire', 1: 'cold', 2: 'shock', 3: 'magic', 4: 'poison'}
_SHORT_ATTRIBUTE_KEYS = {0: 'strength', 1: 'intelligence', 2: 'willpower', 3: 'agility', 4: 'speed', 5: 'endurance', 6: 'personality', 7: 'luck'}

def _short_name_key(effect_id: int, sub_id: int, attr_id: int) -> str | None:
    if effect_id == 2 and sub_id == 0:
        return 'shield'
    if effect_id == 10:
        return _SHORT_ELEMENT_KEYS.get(sub_id)
    if effect_id == 11:
        attr = _SHORT_ATTRIBUTE_KEYS.get(sub_id) or _SHORT_ATTRIBUTE_KEYS.get(attr_id)
        return f'fortify_{attr}' if attr else None
    return _SHORT_SIMPLE_KEYS.get(effect_id)

def effect_display_names(effects, sub_effects=(), affected_attrs=(), *, short: bool=False) -> list[str]:
    import i18n_helper as i18n
    names: list[str] = []
    for slot, effect_id in enumerate(list(effects)[:3]):
        if effect_id == 255:
            continue
        sub_id = sub_effects[slot] if slot < len(sub_effects) else 0
        attr_id = affected_attrs[slot] if slot < len(affected_attrs) else 0
        if short:
            key = _short_name_key(effect_id, sub_id, attr_id)
            shown = i18n.text_opt(f'spell_effect.name.{key}') if key else None
            if shown:
                names.append(shown)
                continue
        parts = []
        for id_str in _effect_display_ids(effect_id, sub_id, attr_id):
            anchor = _id_anchor(id_str)
            parts.append(i18n.value('mages', anchor) or anchor)
        if parts:
            names.append(' '.join(parts))
    return names

def _decode_spell_effect_segments(raw: bytes) -> list[str]:
    if not raw:
        return []
    m = re.search(b'\\x00{2,}', raw)
    end = m.start() if m else len(raw)
    segments: list[str] = []
    for seg in raw[:end].split(b'\x00'):
        chars: list[str] = []
        for b in seg:
            if 32 <= b <= 126:
                chars.append(chr(b))
            else:
                chars.append(' ')
        text = ' '.join(''.join(chars).split()).strip()
        if text:
            segments.append(text)
    return segments

def _decode_spell_effect_text(raw: bytes) -> str:
    return ' '.join(_decode_spell_effect_segments(raw)).strip()

def _effect_template_ids(effect_en: str) -> set[int]:
    from spellmaker_tables import current
    tables = current()
    if tables is None:
        return set()
    key = tables.full_names().get((effect_en or '').strip())
    if key is None:
        return set()
    template_id = tables.template_id(*key)
    return {template_id} if template_id is not None else set()

def _synthesis_template_id(effect_en: str) -> int | None:
    candidates = _effect_template_ids(effect_en)
    return next(iter(candidates)) if len(candidates) == 1 else None

def _normalize_spell_effect_text(text_en: str, effect_en: str, *, allow_mismatch_fallback: bool=False) -> tuple[str, str]:
    if not text_en:
        return ('', '')
    try:
        from spell_effect_text import match_template
        matched = match_template(text_en)
    except Exception:
        matched = None
    if matched:
        template_id, normalized_en, ja = matched
        expected = _effect_template_ids(effect_en)
        if expected and template_id not in expected:
            if allow_mismatch_fallback:
                return (text_en, translate_effect_text(text_en))
            return ('', '')
        return (normalized_en, ja)
    return (text_en, translate_effect_text(text_en))

def _is_effect_heading_text(text_en: str, effect_en: str) -> bool:
    text = (text_en or '').strip()
    effect = (effect_en or '').strip()
    return bool(effect and (text == effect or text.startswith(effect + ':')))

def _effect_heading_index(segment: str, indexes_by_effect: dict[str, list[int]]) -> int | None:
    text = (segment or '').strip()
    if not text:
        return None
    for effect, indexes in indexes_by_effect.items():
        if not indexes:
            continue
        if _is_effect_heading_text(text, effect):
            return indexes.pop(0)
    return None

def _attach_effect_texts_from_segments(segments: list[str], details: list[dict]) -> list[dict] | None:
    if not segments or not details:
        return None
    out = [dict(d) for d in details]
    indexes_by_effect: dict[str, list[int]] = {}
    for idx, detail in enumerate(out):
        effect = detail.get('effect_en', '')
        if effect and effect != '(none)':
            indexes_by_effect.setdefault(effect, []).append(idx)
    current_idx: int | None = None
    assigned: dict[int, list[str]] = {}
    saw_heading = False
    for segment in segments:
        heading_idx = _effect_heading_index(segment, indexes_by_effect)
        if heading_idx is not None:
            current_idx = heading_idx
            assigned.setdefault(current_idx, [])
            saw_heading = True
            continue
        if current_idx is not None:
            assigned.setdefault(current_idx, []).append(segment)
    if not saw_heading:
        return None
    for idx, parts in assigned.items():
        segment = ' '.join(parts).strip()
        effect = out[idx].get('effect_en', '')
        normalized_en, text_ja = _normalize_spell_effect_text(segment, effect, allow_mismatch_fallback=True)
        if not normalized_en and segment:
            normalized_en = segment
            text_ja = translate_effect_text(segment)
        out[idx]['text_en'] = normalized_en
        out[idx]['text_ja'] = text_ja
    return out

def _effect_text_start_pattern(effect_en: str) -> re.Pattern | None:
    effect = (effect_en or '').strip()
    table = {'Cause Disease': '\\d+%\\s+chance\\s+to\\s+inflict\\s+disease', 'Cause Poison': '\\d+%\\s+chance\\s+to\\s+inflict\\s+poison', 'Cause Paralyzation': '\\d+%\\s+chance\\s+to\\s+paralyze', 'Cause Curse': '\\d+%\\s+chance\\s+to\\s+curse\\s+target\\(s\\)', 'Damage Health': '\\d+\\s+to\\s+\\d+\\s+pts\\s+(?:of\\s+)?damage\\s+to\\s+health', 'Damage Fatigue': '\\d+\\s+to\\s+\\d+\\s+pts\\s+(?:of\\s+)?damage\\s+to\\s+fatigue', 'Damage Spell Points': '\\d+\\s+to\\s+\\d+\\s+pts\\s+(?:of\\s+)?damage\\s+to\\s+spell\\s+pts', 'Heal Health': '\\+\\s*\\d+\\s+to\\s+\\d+\\s+pts\\s+to\\s+Health', 'Heal Fatigue': '\\+\\s*\\d+\\s+to\\s+\\d+\\s+pts\\s+to\\s+Fatigue', 'Heal Spell Points': '\\+\\s*\\d+\\s+to\\s+\\d+\\s+pts\\s+to\\s+Spell\\s+Points', 'Create Shield': '\\d+\\s+hit\\s+pts\\s+shield\\s+created', 'Create Wall': '\\d+\\s+wall\\(s\\)\\s+permanently\\s+created', 'Regenerate': 'Regenerate\\s+\\d+\\s+health\\s+points', 'Levitate': 'Caster\\s+can\\s+float\\s+for\\s+\\d+\\s+rnd\\(s\\)', 'Light': 'Creates\\s+a\\s+globe\\s+of\\s+light'}
    pattern = table.get(effect)
    if pattern is None and effect.startswith('Continuous Damage '):
        target = effect.removeprefix('Continuous Damage ').lower()
        pattern = 'Cause\\s+\\d+\\s+to\\s+\\d+\\s+pts\\s+of\\s+damage\\s+to\\s+' + re.escape(target)
    if pattern is None and effect.startswith('Drain Attribute '):
        attr = effect.removeprefix('Drain Attribute ')
        pattern = '\\d+\\s+pts\\s+of\\s+' + re.escape(attr) + '\\s+drained\\s+from\\s+target\\(s\\)'
    if pattern is None:
        return None
    return re.compile(pattern, re.IGNORECASE)

def _attach_effect_texts_by_template_starts(text: str, details: list[dict]) -> list[dict] | None:
    if not text or len(details) <= 1:
        return None
    starts: list[tuple[int, int]] = []
    search_from = 0
    for idx, detail in enumerate(details):
        pattern = _effect_text_start_pattern(detail.get('effect_en', ''))
        if pattern is None:
            continue
        match = pattern.search(text, search_from)
        if match is None:
            continue
        starts.append((idx, match.start()))
        search_from = match.start() + 1
    if not starts:
        return None
    if starts[0][0] > 0 and starts[0][1] > 0:
        prefix = text[:starts[0][1]].strip()
        current_idx = starts[0][0]
        current_effect = details[current_idx].get('effect_en', '') if 0 <= current_idx < len(details) else ''
        is_heading = _is_effect_heading_text(prefix, current_effect)
        if not is_heading:
            is_heading = any((_is_effect_heading_text(prefix, d.get('effect_en', '')) for d in details))
        if not is_heading:
            starts.insert(0, (starts[0][0] - 1, 0))
    starts.sort(key=lambda item: item[1])
    out = [dict(d) for d in details]
    for order, (detail_idx, start) in enumerate(starts):
        end = starts[order + 1][1] if order + 1 < len(starts) else len(text)
        if detail_idx < 0 or detail_idx >= len(out):
            continue
        segment = text[start:end].strip()
        effect = out[detail_idx].get('effect_en', '')
        normalized_en, text_ja = _normalize_spell_effect_text(segment, effect, allow_mismatch_fallback=True)
        if not normalized_en and segment:
            normalized_en = segment
            text_ja = translate_effect_text(segment)
        out[detail_idx]['text_en'] = normalized_en
        out[detail_idx]['text_ja'] = text_ja
    return out

def _attach_effect_texts(text_en: str, details: list[dict], segments: list[str] | None=None) -> list[dict]:
    out = [dict(d) for d in details]
    segmented = _attach_effect_texts_from_segments(segments or [], out)
    if segmented is not None:
        text = (text_en or '').strip()
        if text and any((not d.get('text_en') for d in segmented)):
            by_template = _attach_effect_texts_by_template_starts(text, segmented)
            if by_template is not None:
                for idx, detail in enumerate(segmented):
                    if detail.get('text_en') or idx >= len(by_template):
                        continue
                    fallback = by_template[idx]
                    if fallback.get('text_en'):
                        detail['text_en'] = fallback.get('text_en', '')
                        detail['text_ja'] = fallback.get('text_ja', '')
        return segmented
    text = (text_en or '').strip()
    if not out:
        return out
    if not text:
        return out
    if len(out) == 1:
        effect = out[0].get('effect_en', '')
        normalized_en, text_ja = _normalize_spell_effect_text(text, effect)
        out[0]['text_en'] = normalized_en
        out[0]['text_ja'] = text_ja
        return out
    by_template = _attach_effect_texts_by_template_starts(text, out)
    if by_template is not None:
        return by_template
    return out
_COMPONENT_PREFIXES = ('Drain Attribute ', 'Fortify Attribute ', 'Transfer Attribute ', 'Transfer Figured Attribute ', 'Elemental Resistance ', 'Heal ')

def _component_word(effect_en: str) -> str:
    for prefix in _COMPONENT_PREFIXES:
        if effect_en.startswith(prefix):
            return effect_en[len(prefix):].strip()
    return ''
_B_WORD_BY_CHOICE = {0: '', 1: 'not'}

def _record_b_word(analyzer, anchor: int) -> str | None:
    try:
        from mages_spellmaker import FORM_CHOICES
        from spell_reader import read_spell_choice_index
        index = read_spell_choice_index(analyzer, anchor, FORM_CHOICES['FORM10']['flag_values'])
    except Exception:
        return None
    return _B_WORD_BY_CHOICE.get(index)

def _synthesize_spellmaker_effect_text(detail: dict, analyzer, anchor: int):
    effect = (detail.get('effect_en') or '').strip()
    template_id = _synthesis_template_id(effect)
    if template_id is None:
        return ('', '')
    slot = max(0, min(int(detail.get('slot', 0) or 0), 2))
    try:
        from spell_record_reader import read_record_values
        from spell_effect_text import render_en
        values = read_record_values(analyzer, anchor, slot)
        if not values:
            return ('', '')
        numbers = {str(grp): v for grp, v in values.items()}
        if 5 in values:
            numbers['a'] = values[5]
        word = _component_word(effect)
        words = {'c': word} if word else {}
        b_word = _record_b_word(analyzer, anchor)
        if b_word is not None:
            words['b'] = b_word
        text = render_en(template_id, numbers, words)
    except Exception:
        return ('', '')
    if not text:
        return ('', '')
    return _normalize_spell_effect_text(text, effect, allow_mismatch_fallback=True)

def _fill_missing_spellmaker_effect_texts(details: list[dict], analyzer, anchor: int) -> list[dict]:
    out = [dict(d) for d in details]
    for detail in out:
        if detail.get('text_en'):
            continue
        text_en, text_ja = _synthesize_spellmaker_effect_text(detail, analyzer, anchor)
        if text_en:
            detail['text_en'] = text_en
            detail['text_ja'] = text_ja
    return out

def _target_word_ja(word: str) -> str:
    return _EFFECT_TARGET_JA.get(word, _EFFECT_TARGET_JA.get(word.lower(), word))

def translate_effect_text(text_en: str) -> str:
    if not text_en:
        return ''
    try:
        from spell_effect_text import translate as _set
        ja = _set(text_en)
        if ja:
            return ja
    except Exception:
        pass
    s = text_en.strip()
    for regex, kind in _TEMPLATES:
        m = regex.match(s)
        if not m:
            continue
        x, y, target, a, b, n = m.groups()
        target_ja = _target_word_ja(target.strip())
        if kind == 'damage':
            return f'{target_ja}に{x}〜{y}ポイントのダメージ、{n}レベル毎に+{a}〜{b}ポイント'
        if kind == 'heal':
            return f'{target_ja}を{x}〜{y}ポイント回復、{n}レベル毎に+{a}〜{b}ポイント'
        if kind == 'drain':
            return f'{target_ja}を{x}〜{y}ポイント吸収、{n}レベル毎に+{a}〜{b}ポイント'
    return ''
