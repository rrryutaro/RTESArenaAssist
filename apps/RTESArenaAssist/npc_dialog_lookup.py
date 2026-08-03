from __future__ import annotations
import json
import re
from npc_name_translator import translate_generated_name
_COMPILED: list[tuple[re.Pattern, str, int, bool, int]] = []
_LOADED = False
_TRAVEL_EVENT_KEYS: frozenset[int] = frozenset({1274, 1275})
_TRAVEL_EVENT_COMPILED: list[tuple[re.Pattern, str, int, bool, int]] = []
_CLOSED_PH_ALT: dict[str, str] = {}
_CLOSED_PH_LOADED = False
_CLOSED_PLACEHOLDERS: frozenset[str] = frozenset({'di'})
_PH_SLUG_NON_ALNUM = re.compile('[^a-z0-9]+')
_PH_DIRECT_ID_NAMES: frozenset[str] = frozenset({'cn', 'lp', 'ct', 'oc', 't', 'di', 'g', 'g2', 'g3'})
_PV_VALUE_SUBGROUPS: frozenset[str] = frozenset({'ra', 't', 'oc', 'ct', 'oth', 'di', 'lp', 'cn', 'tem'})

def _ph_slug(en: str) -> str:
    s = en.strip().lower().replace("'", '')
    return _PH_SLUG_NON_ALNUM.sub('_', s).strip('_')

def _ph_direct_id(name: str, value: str) -> str | None:
    import i18n_helper as i18n
    return i18n.text_opt(f'placeholder_values.%{name}.{_ph_slug(value)}.0')

def _clean_placeholder_value(value: str) -> str:
    return (value or '').strip().rstrip(',.;:')

def _load_closed_ph() -> None:
    global _CLOSED_PH_LOADED
    if _CLOSED_PH_LOADED:
        return
    _CLOSED_PH_LOADED = True
    import i18n_helper as i18n
    words_by_name: dict[str, list[str]] = {}
    for id_, e in i18n.originals('placeholder_values').items():
        if not isinstance(e, dict):
            continue
        m = re.match('placeholder_values\\.%([a-z0-9]+)\\.', id_)
        if not m or m.group(1) not in _CLOSED_PLACEHOLDERS:
            continue
        en_val = (e.get('original', '') or '').strip()
        if en_val:
            words_by_name.setdefault(m.group(1), []).append(en_val)
    if not words_by_name:
        for sid in i18n.lang_ids('placeholder_values'):
            m = re.match('placeholder_values\\.%([a-z0-9]+)\\.(.+)\\.[^.]+$', sid)
            if m and m.group(1) in _CLOSED_PLACEHOLDERS:
                words_by_name.setdefault(m.group(1), []).append(m.group(2))
    for name, words in words_by_name.items():
        words = sorted(set(words), key=lambda w: (-len(w), w))
        _CLOSED_PH_ALT[name] = '|'.join((re.escape(w) for w in words))

def _literal_chars(en: str) -> int:
    return len(re.sub('%[a-z][a-z0-9]*', '', en))
_DOC_VALUES: dict[str, dict[str, str]] = {}
_DOC_COMPILED: list[tuple[re.Pattern, str, int]] = []
_PH_VALUES: dict[tuple[str, str], dict[str, str]] = {}
_CLASS_VALUES: dict[str, str] = {}
_PH_LOADED = False
_TRAIT_VALUES: dict[str, str] = {}
_TRAITS_LOADED = False
_DRINKS_VALUES: dict[str, str] = {}
_DRINKS_LOADED = False

def _items_section_map(section: str) -> dict[str, str]:
    import i18n_helper as i18n
    out: dict[str, str] = {}
    for id_, e in i18n.originals('items').items():
        parts = id_.split('.')
        if len(parts) < 2 or parts[1] != section or (not isinstance(e, dict)):
            continue
        en = e.get('original', '')
        ja = i18n.text(id_)
        if en and ja and (ja != id_):
            out[en] = ja
    for ent in i18n.v2_category_entries('items'):
        if (ent.get('context') or {}).get('section') != section:
            continue
        en, ja = (ent.get('original'), ent.get('text'))
        if en and ja:
            out.setdefault(en, ja)
    return out

def _load_drinks() -> None:
    global _DRINKS_LOADED, _DRINKS_VALUES
    if _DRINKS_LOADED:
        return
    _DRINKS_LOADED = True
    _DRINKS_VALUES.update(_items_section_map('drinks'))
_ROOMS_VALUES: dict[str, str] = {}
_ROOMS_LOADED = False

def _load_rooms() -> None:
    global _ROOMS_LOADED, _ROOMS_VALUES
    if _ROOMS_LOADED:
        return
    _ROOMS_LOADED = True
    _ROOMS_VALUES.update(_items_section_map('rooms'))
_ITEMS_FLAT: dict[str, str] = {}
_ITEMS_FLAT_LOADED = False

def _load_items_flat() -> None:
    global _ITEMS_FLAT_LOADED, _ITEMS_FLAT
    if _ITEMS_FLAT_LOADED:
        return
    _ITEMS_FLAT_LOADED = True
    import i18n_helper as i18n
    for id_, e in i18n.originals('items').items():
        if not isinstance(e, dict):
            continue
        en = e.get('original', '')
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja
    for ent in i18n.v2_category_entries('items'):
        en = ent.get('original')
        ja = ent.get('text')
        if en and ja:
            _ITEMS_FLAT.setdefault(en, ja)
    for id_, e in i18n.originals('mages').items():
        en = e.get('original', '') if isinstance(e, dict) else ''
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja
    for ent in i18n.v2_category_entries('mages'):
        en = ent.get('original')
        ja = ent.get('text')
        if en and ja:
            _ITEMS_FLAT.setdefault(en, ja)
_KEY_MATERIALS: dict[str, str] = {}
_KEY_MATERIALS_LOADED = False

def _load_key_materials() -> None:
    global _KEY_MATERIALS_LOADED, _KEY_MATERIALS
    if _KEY_MATERIALS_LOADED:
        return
    values = _items_section_map('key_materials')
    if not values:
        return
    _KEY_MATERIALS.update(values)
    _KEY_MATERIALS_LOADED = True

def _lookup_key_material(value: str) -> str | None:
    material = re.sub('^\\s*(?:an?|the)\\s+', '', value, flags=re.IGNORECASE).strip()
    candidates = (material, material.title(), value.strip(), value.strip().title())
    for candidate in candidates:
        translated = _KEY_MATERIALS.get(candidate)
        if translated is not None:
            return translated
    folded = {k.casefold(): v for k, v in _KEY_MATERIALS.items()}
    return folded.get(material.casefold()) or folded.get(value.strip().casefold())

def _translate_quest_item(value: str, lang: str) -> str | None:
    if lang == 'en':
        return value
    clean = _clean_placeholder_value(value)
    if not clean:
        return None
    import i18n_helper as i18n
    candidates = []
    for candidate in (clean, clean.title(), clean.capitalize()):
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        translated = i18n.value_by_surface('items', candidate, section='quest_items')
        if translated is not None:
            return translated
    return None
_PP_RULES: dict[str, dict[str, list[tuple[re.Pattern, str]]]] = {}
_I18N_RUNTIME_SIGNATURE: tuple | None = None

def _i18n_runtime_signature() -> tuple:
    try:
        import i18n_helper as i18n
    except Exception:
        return ()
    cats = getattr(i18n, '_V2_CATEGORIES_ENABLED', set())
    try:
        cats_sig = None if cats is None else tuple(sorted(cats))
    except TypeError:
        cats_sig = ()
    v2 = getattr(i18n, '_V2_PUBLIC', None)
    localpack = getattr(v2, 'localpack', None)
    obs = getattr(localpack, 'live_surface_obs', None)
    try:
        obs_len = len(obs) if obs is not None else 0
    except TypeError:
        obs_len = 0
    return (getattr(i18n, '_BASE_DIR', ''), getattr(i18n, '_I18N_DIR', ''), i18n.current_lang(), tuple(i18n.original_categories()), id(v2), id(localpack), cats_sig, obs_len)

def _reset_i18n_bound_caches() -> None:
    global _COMPILED, _LOADED, _CLOSED_PH_ALT, _CLOSED_PH_LOADED
    global _DOC_VALUES, _DOC_COMPILED, _PH_VALUES, _CLASS_VALUES, _PH_LOADED
    global _TRAIT_VALUES, _TRAITS_LOADED, _DRINKS_VALUES, _DRINKS_LOADED
    global _ROOMS_VALUES, _ROOMS_LOADED, _ITEMS_FLAT, _ITEMS_FLAT_LOADED
    global _KEY_MATERIALS, _KEY_MATERIALS_LOADED, _PP_RULES
    global _EXACT_ORIGINALS, _CALENDAR_WEEKDAYS, _CALENDAR_MONTHS
    global _CALENDAR_HOLIDAYS, _CALENDAR_LOADED
    global _TRAVEL_RE_CACHE, _TRAVEL_LOC_RE_CACHE
    global _TRAVEL_EVENT_COMPILED
    global _BODY_HEAD_ENTRIES, _BODY_HEAD_LOADED, _BODY_HEAD_PREFIX_RE
    global _BODY_HEAD_ANCHORS, _BODY_SPAN_ENTRIES, _BODY_SPAN_RE
    global _FIXED_SEG_ENTRIES, _FIXED_SEG_LOADED
    _COMPILED = []
    _LOADED = False
    _TRAVEL_EVENT_COMPILED = []
    _BODY_HEAD_ENTRIES = []
    _BODY_HEAD_LOADED = False
    _BODY_HEAD_PREFIX_RE = {}
    _BODY_HEAD_ANCHORS = {}
    _BODY_SPAN_ENTRIES = {}
    _BODY_SPAN_RE = {}
    _FIXED_SEG_ENTRIES = []
    _FIXED_SEG_LOADED = False
    _CLOSED_PH_ALT = {}
    _CLOSED_PH_LOADED = False
    _DOC_VALUES = {}
    _DOC_COMPILED = []
    _PH_VALUES = {}
    _CLASS_VALUES = {}
    _PH_LOADED = False
    _TRAIT_VALUES = {}
    _TRAITS_LOADED = False
    _DRINKS_VALUES = {}
    _DRINKS_LOADED = False
    _ROOMS_VALUES = {}
    _ROOMS_LOADED = False
    _ITEMS_FLAT = {}
    _ITEMS_FLAT_LOADED = False
    _KEY_MATERIALS = {}
    _KEY_MATERIALS_LOADED = False
    _PP_RULES = {}
    _EXACT_ORIGINALS = []
    _CALENDAR_WEEKDAYS = {}
    _CALENDAR_MONTHS = {}
    _CALENDAR_HOLIDAYS = {}
    _CALENDAR_LOADED = False
    _TRAVEL_RE_CACHE = {}
    _TRAVEL_LOC_RE_CACHE = {}

def _ensure_i18n_bound_caches_current() -> None:
    global _I18N_RUNTIME_SIGNATURE
    sig = _i18n_runtime_signature()
    if _I18N_RUNTIME_SIGNATURE is None:
        _I18N_RUNTIME_SIGNATURE = sig
        return
    if sig != _I18N_RUNTIME_SIGNATURE:
        _reset_i18n_bound_caches()
        _I18N_RUNTIME_SIGNATURE = sig

def _load_placeholder_preprocessing(lang: str) -> dict[str, list[tuple[re.Pattern, str]]]:
    if lang in _PP_RULES:
        return _PP_RULES[lang]
    import i18n_helper as i18n
    per_ph: dict[str, list[tuple[re.Pattern, str]]] = {}
    pp = i18n.rules(lang).get('placeholder_preprocessing', {})
    for ph_name, rules in pp.get('placeholders', {}).items():
        if not isinstance(rules, list):
            continue
        compiled_list = per_ph.setdefault(ph_name, [])
        for rule in rules:
            pattern = rule.get('pattern')
            replace = rule.get('replace', '')
            if not pattern:
                continue
            try:
                compiled = re.compile(pattern)
            except re.error:
                continue
            compiled_list.append((compiled, replace))
    _PP_RULES[lang] = per_ph
    return per_ph

def _preprocess_placeholder_value(name: str, value: str, lang: str) -> str:
    if not value or not lang or (not name):
        return value
    rules = _load_placeholder_preprocessing(lang).get(name, [])
    if not rules:
        return value
    for compiled, replace in rules:
        value = compiled.sub(replace, value)
    return value
_DS_PATTERN = re.compile('^(.+?)\\s+(\\w+)\\s+called\\s+(.+)$')
_PLACEHOLDER_NAMES: frozenset[str] = frozenset(['a', 'a2', 'adn', 'amn', 'an', 'apr', 'arc', 'art', 'ba', 'ccs', 'cll', 'cn', 'cn2', 'cp', 'ct', 'da', 'de', 'di', 'dit', 'doc', 'ds', 'du', 'en', 'fn', 'fq', 'g', 'g2', 'g3', 'hc', 'hod', 'i', 'jok', 'lp', 'mi', 'mn', 'mpr', 'mt', 'n', 'nap', 'nc', 'nc2', 'nd', 'ne', 'nh', 'nhd', 'ni', 'nk', 'nr', 'nt', 'o', 'oap', 'oc', 'omq', 'opp', 'oth', 'pcf', 'pcn', 'qc', 'qmn', 'qt', 'r', 'ra', 'rcn', 'rf', 's', 'sn', 'st', 't', 'ta', 'tan', 'tc', 'tem', 'tg', 'ti', 'tl', 'tq', 'tt', 'u'])

def _template_to_regex(en_template: str, *, anchor_end: bool=True) -> re.Pattern | None:
    seen: set[str] = set()
    pattern_parts: list[str] = []
    pos = 0
    text = en_template
    token_re = re.compile('%([a-z][a-z0-9]*)')
    last = 0
    for m in token_re.finditer(text):
        name = m.group(1)
        pattern_parts.append(re.escape(text[last:m.start()]))
        if name in _PLACEHOLDER_NAMES:
            if name not in seen:
                alt = _CLOSED_PH_ALT.get(name)
                if alt:
                    pattern_parts.append(f'(?P<{name}>(?i:{alt}))(?![A-Za-z])')
                else:
                    pattern_parts.append(f'(?P<{name}>.+?)')
                seen.add(name)
            else:
                pattern_parts.append(f'(?P={name})')
        else:
            pattern_parts.append('.+?')
        last = m.end()
    pattern_parts.append(re.escape(text[last:]))
    full_pattern = '^' + ''.join(pattern_parts) + ('$' if anchor_end else '')
    try:
        return re.compile(full_pattern, re.DOTALL)
    except re.error:
        return None
_NPCD_CAT = 'npc_dialog'
_PH_RE_NPCD = re.compile('%([a-zA-Z][a-zA-Z0-9]*)')

def _npcd_ph_of(en: str) -> list[str]:
    seen: list[str] = []
    for m in _PH_RE_NPCD.finditer(en):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen

def _npcd_key_int(source_id: str | None) -> int:
    if source_id and source_id.startswith('template:'):
        try:
            return int(source_id.split(':')[1])
        except (ValueError, IndexError):
            return -1
    return -1

def _resolve_npcd_ref(ref) -> str | None:
    import i18n_helper as i18n
    kind, val = ref
    if kind == 'sid':
        return i18n.text_by_source_id(val, category=_NPCD_CAT)
    return i18n.text(val)

def _iter_npcd(*, include_untranslated: bool=False):
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_NPCD_CAT):
        for e in i18n.v2_category_entries(_NPCD_CAT):
            en_raw = e.get('original')
            if not en_raw:
                continue
            tmpl = e.get('text')
            if not tmpl:
                if not include_untranslated:
                    continue
                tmpl = ''
            sid = e.get('source_id')
            yield (en_raw, tmpl, _npcd_ph_of(en_raw), _npcd_key_int(sid), ('sid', sid))
    else:
        for id_, entry in i18n.originals(_NPCD_CAT).items():
            en_raw = entry.get('original', '') if isinstance(entry, dict) else ''
            if not en_raw:
                continue
            tmpl = i18n.text(id_)
            if not tmpl:
                if not include_untranslated:
                    continue
                tmpl = ''
            parts = id_.split('.')
            try:
                key_int = int(parts[1]) if len(parts) >= 2 else -1
            except ValueError:
                key_int = -1
            yield (en_raw, tmpl, entry.get('placeholders', []) or [], key_int, ('id', id_))
_EXACT_ORIGINALS: list[tuple[str, str]] = []

def _load() -> None:
    global _COMPILED, _LOADED, _DOC_VALUES, _DOC_COMPILED, _EXACT_ORIGINALS
    global _TRAVEL_EVENT_COMPILED
    if _LOADED:
        return
    _load_closed_ph()
    entries: list[tuple[re.Pattern, str, int, bool, int]] = []
    doc_entries: list[tuple[re.Pattern, str, int]] = []
    travel_event_entries: list[tuple[re.Pattern, str, int, bool, int]] = []
    exact_originals: list[tuple[str, str]] = []
    for en_raw, tmpl, ph_list, key_int, ref in _iter_npcd():
        en = ' '.join(en_raw.split())
        ph_count = len(ph_list)
        is_exact = ph_count == 0
        literal_len = _literal_chars(en)
        compiled = _template_to_regex(en)
        if compiled is None:
            continue
        entries.append((compiled, tmpl, ph_count, is_exact, literal_len))
        if is_exact and en:
            exact_originals.append((en, tmpl))
        if key_int in _TRAVEL_EVENT_KEYS:
            travel_event_entries.append((compiled, tmpl, ph_count, is_exact, literal_len))
        if 262 <= key_int <= 362:
            if not ph_list:
                _DOC_VALUES[en] = {'ref': ref}
            else:
                doc_entries.append((compiled, tmpl, ph_count))
    entries.sort(key=lambda x: (not x[3], -x[4], -x[2]))
    _COMPILED = entries
    doc_entries.sort(key=lambda x: -x[2])
    _DOC_COMPILED = doc_entries
    travel_event_entries.sort(key=lambda x: (not x[3], -x[4], -x[2]))
    _TRAVEL_EVENT_COMPILED = travel_event_entries
    _EXACT_ORIGINALS = exact_originals
    _LOADED = True

def _match_exact_prefix_tolerant(q_norm: str) -> tuple[str, str] | None:
    if len(q_norm) < 12:
        return None
    _load()
    best: tuple[str, str] | None = None
    for en, tmpl in _EXACT_ORIGINALS:
        if en.endswith(q_norm) and 0 < len(en) - len(q_norm) <= 4:
            if best is None or len(en) < len(best[0]):
                best = (en, tmpl)
    return best

def lookup_prefix_tolerant(text: str) -> tuple[str, dict] | None:
    r = lookup(text)
    if r is not None:
        return r
    if not text:
        return None
    m = _match_exact_prefix_tolerant(' '.join(text.split()))
    return (m[1], {}) if m is not None else None

def lookup_prompt_prefix_tolerant(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    q = ' '.join(text.split())
    r = lookup(q)
    if r is not None:
        return (q, format_japanese(r[0], r[1]))
    m = _match_exact_prefix_tolerant(q)
    if m is None:
        return None
    clean_en, tmpl = m
    return (clean_en, format_japanese(tmpl, {}))

def _load_ph() -> None:
    global _PH_VALUES, _CLASS_VALUES, _PH_LOADED
    if _PH_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    for id_, e in i18n.originals('races').items():
        en_val = e.get('original', '') if isinstance(e, dict) else ''
        if en_val:
            ja = i18n.text(id_)
            if ja and ja != id_:
                _PH_VALUES['ra', en_val] = {lang: ja}
    for id_, e in i18n.originals('placeholder_values').items():
        if not isinstance(e, dict):
            continue
        m = re.match('placeholder_values\\.%([a-z0-9]+)\\.', id_)
        if not m:
            continue
        name = m.group(1)
        en_val = e.get('original', '')
        if not en_val:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _PH_VALUES[name, en_val] = {lang: ja}
    for id_, e in i18n.originals('classes').items():
        en_val = e.get('original', '') if isinstance(e, dict) else ''
        if en_val:
            ja = i18n.text(id_)
            if ja and ja != id_:
                _CLASS_VALUES[en_val] = ja
    _PH_LOADED = True

def _load_traits() -> None:
    global _TRAIT_VALUES, _TRAITS_LOADED
    if _TRAITS_LOADED:
        return
    import i18n_helper as i18n
    if i18n.v2_public_enabled('npc_traits'):
        for e in i18n.v2_category_entries('npc_traits'):
            en_val = (e.get('original') or '').strip()
            if en_val:
                _TRAIT_VALUES[en_val] = e.get('text') or ''
    else:
        for id_, e in i18n.originals('npc_traits').items():
            en_val = (e.get('original', '') if isinstance(e, dict) else '').strip()
            if en_val:
                ja = i18n.text(id_)
                _TRAIT_VALUES[en_val] = ja if ja and ja != id_ else ''
    _TRAITS_LOADED = True
_CALENDAR_WEEKDAYS: dict[str, dict[str, str]] = {}
_CALENDAR_MONTHS: dict[str, dict[str, str]] = {}
_CALENDAR_HOLIDAYS: dict[str, dict[str, str]] = {}
_CALENDAR_LOADED = False

def _load_calendar() -> None:
    global _CALENDAR_LOADED
    if _CALENDAR_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    try:
        entries: list[tuple[str, str, str, str | None]] = []
        if i18n.v2_public_enabled('calendar'):
            for entry in i18n.v2_category_entries('calendar'):
                en = (entry.get('original') or '').strip()
                ja = entry.get('text') or ''
                sid = entry.get('source_id') or ''
                if 'weekday_names' in sid:
                    entries.append(('weekday', en, ja, None))
                elif 'month_names' in sid:
                    entries.append(('month', en, ja, None))
                elif 'holiday_names' in sid:
                    entries.append(('holiday', en, ja, None))
        else:
            for id_, e in i18n.originals('calendar').items():
                if not isinstance(e, dict):
                    continue
                cat = e.get('category', '')
                en = e.get('original', '')
                ja = i18n.text(id_)
                entries.append((cat, en, ja, id_))
        for cat, en, ja, id_ in entries:
            if not en:
                continue
            if not ja or (id_ is not None and ja == id_):
                continue
            if cat == 'weekday':
                _CALENDAR_WEEKDAYS[en] = {lang: ja}
            elif cat == 'month':
                _CALENDAR_MONTHS[en] = {lang: ja}
            elif cat == 'holiday':
                _CALENDAR_HOLIDAYS[en] = {lang: ja}
    except (OSError, json.JSONDecodeError):
        pass
    _CALENDAR_LOADED = True
_DATE_PATTERN_SHORT = re.compile("^([A-Z][a-z]+),\\s+(\\d+)(?:st|nd|rd|th)\\s+of\\s+([A-Z][A-Za-z'\\s]+?)$")
_DATE_PATTERN_FULL = re.compile("^([A-Z][a-z]+),\\s+(\\d+)(?:st|nd|rd|th)\\s+of\\s+([A-Z][A-Za-z'\\s]+?)\\s+in\\s+the\\s+year\\s+([0-9]+E)\\s+(\\d+)$")

def _translate_date(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    import i18n_helper as i18n
    _load_calendar()
    text = value.strip()
    m_full = _DATE_PATTERN_FULL.match(text)
    if m_full:
        weekday_en = m_full.group(1)
        day_str = m_full.group(2)
        month_en = m_full.group(3).strip()
        era_en = m_full.group(4)
        year_str = m_full.group(5)
        weekday_ja = _CALENDAR_WEEKDAYS.get(weekday_en, {}).get(lang, weekday_en)
        month_ja = _CALENDAR_MONTHS.get(month_en, {}).get(lang, month_en)
        era_ja = i18n.value_in('eras', era_en, lang) or era_en
        return i18n.text('status_buffer_text.date_format_dialog_full').replace('{weekday}', weekday_ja).replace('{month}', month_ja).replace('{day}', day_str).replace('{era}', era_ja).replace('{year}', year_str)
    m_short = _DATE_PATTERN_SHORT.match(text)
    if m_short:
        weekday_en = m_short.group(1)
        day_str = m_short.group(2)
        month_en = m_short.group(3).strip()
        weekday_ja = _CALENDAR_WEEKDAYS.get(weekday_en, {}).get(lang, weekday_en)
        month_ja = _CALENDAR_MONTHS.get(month_en, {}).get(lang, month_en)
        return i18n.text('status_buffer_text.date_format_dialog_short').replace('{weekday}', weekday_ja).replace('{month}', month_ja).replace('{day}', day_str)
    return value

def _translate_calendar_label(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    _load_calendar()
    text = value.strip()
    return _CALENDAR_HOLIDAYS.get(text, {}).get(lang, value)

def _translate_nested_npc_dialog(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    normalized = ' '.join(value.split())
    result = lookup(normalized)
    if result is None:
        return value
    ja_template, placeholders = result
    return format_japanese(ja_template, placeholders, lang)

def _translate_static_place(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    name = (value or '').strip()
    if not name:
        return value
    try:
        from location_lookup import lookup as _loc_lookup
        loc = _loc_lookup(name)
        if loc:
            return loc
    except Exception:
        pass
    _load_ph()
    cn = _PH_VALUES.get(('cn', name), {}).get(lang)
    if cn:
        return cn
    cn = _ph_direct_id('cn', name)
    if cn:
        return cn
    return value

def _translate_nt(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    from dynamic_place_lookup import lookup as _place_lookup
    translated = _place_lookup(value)
    return translated if translated else value
_DS_TAVERN_QUEST_PATTERN = re.compile('^(.+?)\\s+called\\s+(.+?)\\s+of\\s+(.+)$')

def _npc_desc_lookup(rule_key: str, en: str, lang: str) -> Optional[str]:
    if lang == 'en' or not en:
        return None
    import i18n_helper as i18n
    key = en.strip().lower()
    for e in i18n.rules().get(rule_key, []):
        if isinstance(e, dict) and str(e.get('en', '')).lower() == key:
            v = e.get('value')
            return v if v else None
    return None

def _npc_desc_noun(en: str, lang: str) -> Optional[str]:
    return _npc_desc_lookup('npc_desc_nouns', en, lang)

def _npc_desc_title(en: str, lang: str) -> Optional[str]:
    return _npc_desc_lookup('npc_desc_titles', en, lang)

def _known_title_ja(token: str, lang: str) -> Optional[str]:
    if not token:
        return None
    t = _npc_desc_title(token, lang)
    if t:
        return t
    _load_ph()
    t = _PH_VALUES.get(('t', token), {}).get(lang)
    if t:
        return t
    return _ph_direct_id('t', token)

def _translate_trait_words(en: str, lang: str) -> Optional[str]:
    if lang == 'en' or not en:
        return None
    out: list[str] = []
    for w in en.split():
        t = _npc_desc_lookup('npc_desc_advs', w, lang) or _npc_desc_lookup('npc_desc_adjs', w, lang)
        if not t:
            return None
        out.append(t)
    return ''.join(out) if out else None

def _translate_ds(value: str, lang: str) -> str:
    if lang == 'en':
        return value
    m = _DS_TAVERN_QUEST_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        descriptor_en = m.group(1).strip()
        named_en = m.group(2).strip()
        locale_en = m.group(3).strip()
        _load_traits()
        descriptor_ja = i18n.value('descriptors', descriptor_en.lower()) or descriptor_en
        named_ja = named_en
        parts = named_en.split(None, 1)
        if len(parts) == 2:
            maybe_trait, maybe_name = parts
            trait_ja_local = _TRAIT_VALUES.get(maybe_trait) or _npc_desc_title(maybe_trait, lang)
            if trait_ja_local:
                name_ja_local = translate_generated_name(maybe_name, lang)
                named_ja = i18n.text('status_buffer_text.ds_format_trait_name').replace('{trait}', trait_ja_local).replace('{name}', name_ja_local)
        if named_ja == named_en:
            translated_name = translate_generated_name(named_en, lang)
            if translated_name and translated_name != named_en:
                named_ja = translated_name
        locale_ja = locale_en
        for _ph_name in ('cn', 'lp', 'ct'):
            _result = translate_placeholder(_ph_name, locale_en, lang)
            if _result != locale_en:
                locale_ja = _result
                break
        if locale_ja == locale_en:
            try:
                from dynamic_place_lookup import lookup as _place_lookup
                place_result = _place_lookup(locale_en)
                if place_result:
                    locale_ja = place_result
            except Exception:
                pass
        return i18n.text('status_buffer_text.ds_format_tavern_quest').replace('{locale}', locale_ja).replace('{named}', named_ja).replace('{descriptor}', descriptor_ja)
    m = _DS_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        trait_en, occupation_en, called_en = (m.group(1), m.group(2), m.group(3))
        _load_traits()
        trait_ja = _TRAIT_VALUES.get(trait_en) or i18n.text_opt(f'npc_traits.trait_{_ph_slug(trait_en)}.0') or _translate_trait_words(trait_en, lang) or trait_en
        occupation_ja = _npc_desc_noun(occupation_en, lang) or i18n.value('descriptors', occupation_en.lower()) or translate_placeholder('oc', occupation_en, lang) or occupation_en
        title_ja = None
        name_en = called_en
        parts = called_en.split(None, 1)
        if len(parts) == 2:
            maybe_title_ja = _known_title_ja(parts[0], lang)
            if maybe_title_ja is not None:
                title_ja, name_en = (maybe_title_ja, parts[1])
        name_ja = translate_generated_name(name_en, lang)
        if title_ja is None:
            fmt = i18n.text_opt('status_buffer_text.ds_format_ask_about_untitled')
            if not fmt:
                return value
            return fmt.replace('{trait}', trait_ja).replace('{occupation}', occupation_ja).replace('{name}', name_ja)
        return i18n.text('status_buffer_text.ds_format_ask_about').replace('{trait}', trait_ja).replace('{occupation}', occupation_ja).replace('{title}', title_ja).replace('{name}', name_ja)
    return value

def translate_placeholder(name: str, value: str, lang: str='ja') -> str:
    if not value:
        return value
    _ensure_i18n_bound_caches_current()
    value = _preprocess_placeholder_value(name, value, lang)
    if name in _PV_VALUE_SUBGROUPS or name in ('g', 'g2', 'g3'):
        import i18n_helper as i18n
        if i18n.v2_public_enabled('placeholder_values'):
            section = f'%{name}' if name in ('g', 'g2', 'g3') else None
            v2 = i18n.value_by_surface('placeholder_values', value, section=section, lang=lang)
            if v2 is not None:
                return v2
    if name in ('n', 'fn', 'rf', 'an', 'nc'):
        if lang != 'en':
            return translate_generated_name(value, lang)
        return value
    if name == 'doc':
        _load()
        normalized = ' '.join(value.split())
        doc_entry = _DOC_VALUES.get(normalized)
        if doc_entry is not None:
            resolved = _resolve_npcd_ref(doc_entry['ref'])
            if resolved:
                return resolved
        for compiled, ja_tmpl, _ in _DOC_COMPILED:
            m = compiled.match(normalized)
            if m:
                nested = m.groupdict()
                result = ja_tmpl
                for ph_name, ph_val in nested.items():
                    if ph_val:
                        translated_val = translate_placeholder(ph_name, ph_val, lang)
                        result = result.replace(f'%{ph_name}', translated_val)
                return result
        return value
    if name in ('mn', 'mt'):
        if lang == 'en':
            return value
        from dungeon_msg_lookup import lookup_monster_name
        return lookup_monster_name(value) or value
    if name in ('ra', 't', 'oc', 'ct', 'oth', 'di', 'lp', 'cn', 'tem'):
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        if name in _PH_DIRECT_ID_NAMES:
            direct = _ph_direct_id(name, value)
            if direct is not None:
                return direct
        if name == 'oth':
            import i18n_helper as i18n
            nd = i18n.value('npc_dialog', value)
            if nd is not None:
                return nd
        if name == 'oc':
            cls = _CLASS_VALUES.get(value)
            if cls is not None:
                return cls
            import i18n_helper as i18n
            cls_v2 = i18n.value_in('classes', value, lang)
            if cls_v2 is not None:
                return cls_v2
            return value
        if name == 'ra':
            import i18n_helper as i18n
            races_ja = i18n.value_in('races', value, lang)
            if races_ja is not None:
                return races_ja
        if name == 'ct' and lang != 'en':
            _st = _translate_settlement_type(value.strip().title(), lang)
            if _st:
                return _st
        if name in ('lp', 'tem'):
            if lang != 'en':
                from dynamic_place_lookup import lookup as _place_lookup
                translated = _place_lookup(value)
                if translated:
                    return translated
        if name == 'cn' and lang != 'en':
            _static = _translate_static_place(value, lang)
            if _static != value:
                return _static
        return value
    if name == 'tq':
        return translate_placeholder('t', value, lang)
    if name in ('cp', 'cll', 'ccs', 'rcn', 'cn2', 'hc', 'qc', 'tan'):
        return _translate_static_place(value, lang)
    if name == 'st':
        if lang == 'en':
            return value
        import i18n_helper as i18n
        return i18n.value_in('status_terms', value.lower(), lang) or i18n.value_in('status_terms', value, lang) or value
    if name == 'nh':
        return _translate_calendar_label(value, lang)
    if name == 'nhd':
        return _translate_date(value, lang)
    if name in ('hod', 'jok'):
        return _translate_nested_npc_dialog(value, lang)
    if name == 'nt':
        return _translate_nt(value, lang)
    if name == 'ds':
        return _translate_ds(value, lang)
    if name in ('a', 'a2', 'oap'):
        return value
    if name == 'da':
        return _translate_date(value, lang)
    if name in ('omq', 'mi'):
        translated = _translate_quest_item(value, lang)
        return translated if translated is not None else value
    if name == 'r':
        import i18n_helper as i18n
        key = _clean_placeholder_value(value).lower()
        direct = i18n.value_in('relations', key, lang)
        if direct is not None:
            return direct
        parts = key.split()
        if parts:
            base = i18n.value_in('relations', parts[-1], lang)
            if base is not None:
                return base
        return value
    if name in ('g', 'g2', 'g3'):
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        direct = _ph_direct_id(name, value)
        if direct is not None:
            return direct
        import i18n_helper as i18n
        return i18n.value_in('pronouns', value.lower(), lang) or value
    if name in ('fq', 'ne'):
        cleaned = _clean_placeholder_value(value).rstrip('-~')
        if lang != 'en':
            return translate_generated_name(cleaned, lang)
        return cleaned
    if name in ('o', 'pcn'):
        return value
    if name in ('tl', 'en'):
        if lang != 'en':
            from dynamic_place_lookup import lookup as _place_lookup
            translated = _place_lookup(value)
            return translated if translated else value
        return value
    if name == 'nd':
        if lang == 'en':
            return value
        _load_drinks()
        return _DRINKS_VALUES.get(value, value)
    if name == 'nr':
        if lang == 'en':
            return value
        _load_rooms()
        return _ROOMS_VALUES.get(value, value)
    if name in ('ni', 'i'):
        if lang == 'en':
            return value
        _load_items_flat()
        translated = _ITEMS_FLAT.get(value)
        if translated:
            return translated
        try:
            from equipment_shop_list_reader import translate_equipment_shop_name
            translated = translate_equipment_shop_name(value)
            return translated if translated else value
        except Exception:
            return value
    if name == 'nk':
        if lang == 'en':
            return value
        _load_key_materials()
        return _lookup_key_material(value) or value
    if name == 'nc2':
        return value
    return value
_ARRIVAL_RE = re.compile('^You have arrived in (?P<loc>.+?) in (?P<prov>.+?) Province\\.\\s*The date is (?P<date>.+?)\\s+It took (?P<days>\\d+) days? to reach your goal\\.\\s*(?P<flavor>.*)$', re.DOTALL)
_SETTLEMENT_RE = re.compile('^The (?P<type>Village|Town|City-State|City) of (?P<name>.+)$')
_SETTLEMENT_TYPE_IDS = {'Village': 'settlement_types.0.0', 'Town': 'settlement_types.1.0', 'City': 'settlement_types.2.0', 'City-State': 'settlement_types.3.0'}

def _translate_settlement_type(loc_type: str, lang: str) -> str | None:
    if not loc_type:
        return None
    import i18n_helper as i18n
    return i18n.value_in('location_types', loc_type, lang) or i18n.value_in('settlement_types', loc_type, lang) or i18n.lang_value_in(_SETTLEMENT_TYPE_IDS.get(loc_type, ''), lang)

def _translate_settlement_location(loc: str, lang: str) -> str:
    if lang == 'en':
        return loc
    import i18n_helper as i18n
    m = _SETTLEMENT_RE.match(loc.strip())
    if not m:
        return _translate_static_place(loc.strip(), lang)
    loc_type = m.group('type')
    type_ja = _translate_settlement_type(loc_type, lang) or loc_type
    name_ja = _translate_static_place(m.group('name').strip(), lang)
    return i18n.text('status_buffer_text.settlement_format').replace('{type}', type_ja).replace('{name}', name_ja)

def _translate_arrival(text: str, lang: str='ja') -> str | None:
    if lang == 'en':
        return None
    m = _ARRIVAL_RE.match(text)
    if not m:
        return None
    import i18n_helper as i18n
    loc_ja = _translate_settlement_location(m.group('loc'), lang)
    prov_ja = _translate_static_place(m.group('prov'), lang)
    date_ja = _translate_date(m.group('date'), lang)
    days = m.group('days')
    flavor_ja = ''
    flavor = (m.group('flavor') or '').strip()
    if flavor:
        r = lookup(flavor)
        flavor_ja = format_japanese(r[0], r[1], lang) if r is not None else flavor
    result = i18n.text('status_buffer_text.travel_arrival_format').replace('{province}', prov_ja).replace('{location}', loc_ja).replace('{date}', date_ja).replace('{days}', days)
    if flavor_ja:
        result += ' ' + flavor_ja
    return result
_TRAVEL_RE_CACHE: dict[str, object] = {}

def _frag_to_regex(norm_fmt: str, groups: list[str]) -> str:
    out: list[str] = []
    gi = 0
    for tok in re.split('(%[sd])', norm_fmt):
        if tok == '%s':
            out.append(f'(?P<{groups[gi]}>.+?)')
            gi += 1
        elif tok == '%d':
            out.append(f'(?P<{groups[gi]}>\\d+)')
            gi += 1
        elif tok:
            out.append(''.join(('\\s+' if ch == ' ' else re.escape(ch) for ch in tok)))
    return ''.join(out)

def _norm_fmt(s: str) -> str:
    return ' '.join(s.replace('\r', ' ').split())

def _load_travel_originals() -> dict:
    import i18n_helper as i18n
    if i18n.v2_public_enabled('travel'):
        out: dict[str, dict[str, str]] = {}
        prefix = 'aexe:travel:'
        for entry in i18n.v2_category_entries('travel'):
            sid = entry.get('source_id') or ''
            original = entry.get('original') or ''
            if not sid.startswith(prefix) or not original:
                continue
            parts = sid[len(prefix):].split(':')
            if len(parts) != 2 or not parts[1].isdigit():
                continue
            out[f'{parts[0]}.{parts[1]}'] = {'original': original}
        if out:
            return out
    return i18n.originals('travel')

def _build_travel_res() -> list[tuple]:
    orig = _load_travel_originals()
    if not orig:
        return []

    def _o(key: str) -> str | None:
        e = orig.get(key)
        return e.get('original') if isinstance(e, dict) else None
    loc0 = _o('location_format_texts.0')
    loc1 = _o('location_format_texts.1')
    loc2 = _o('location_format_texts.2')
    date_prefix = _o('arrival_popup_date.0')
    day0 = _o('day_prediction.0')
    day1 = _o('day_prediction.1')
    dist = _o('distance_prediction.0')
    arr_prefix = _o('arrival_date_prediction.0')
    if not all((date_prefix, day0, day1, dist, arr_prefix)):
        return []
    tail = _frag_to_regex(_norm_fmt(date_prefix), []) + '\\s+(?P<date1>.+?)\\s+' + _frag_to_regex(_norm_fmt(day0), []) + '\\s+' + _frag_to_regex(_norm_fmt(day1), ['days']) + '\\s+' + _frag_to_regex(_norm_fmt(dist), ['km']) + '\\s+' + _frag_to_regex(_norm_fmt(arr_prefix), []) + '\\s+(?P<date2>.+)$'
    res: list[tuple] = []
    if loc2:
        res.append(('city', re.compile('^' + _frag_to_regex(_norm_fmt(loc2), ['ltype', 'lname', 'prov']) + '\\s+' + tail)))
    if loc0:
        res.append(('dungeon', re.compile('^' + _frag_to_regex(_norm_fmt(loc0), ['lname', 'prov']) + '\\s+' + tail)))
    if loc1:
        res.append(('center', re.compile('^' + _frag_to_regex(_norm_fmt(loc1), ['lname', 'prov']) + '\\s+' + tail)))
    return res

def _translate_travel_estimate(text: str, lang: str='ja') -> str | None:
    _ensure_i18n_bound_caches_current()
    if lang == 'en':
        return None
    res = _TRAVEL_RE_CACHE.get('res')
    if res is None:
        res = _build_travel_res()
        _TRAVEL_RE_CACHE['res'] = res
    if not res:
        return None
    for kind, rx in res:
        m = rx.match(text)
        if not m:
            continue
        g = m.groupdict()
        prov_ja = _translate_static_place(g['prov'], lang)
        if kind == 'city':
            loc_ja = _translate_settlement_location(f"The {g['ltype']} of {g['lname']}", lang)
        else:
            loc_ja = _translate_static_place(g['lname'], lang)
        date1_ja = _translate_date(g['date1'], lang)
        date2_ja = _translate_date(g['date2'], lang)
        days = g['days']
        km = g['km']
        import i18n_helper as i18n
        return i18n.text('status_buffer_text.travel_estimate_format').replace('{province}', prov_ja).replace('{location}', loc_ja).replace('{date1}', date1_ja).replace('{days}', days).replace('{km}', km).replace('{date2}', date2_ja)
    return None
_TRAVEL_ESTIMATE_SHAPE_RE = re.compile('^\\s*(?:The\\s+.+?\\s+of\\s+.+?\\s+in\\s+.+?\\s+Province\\.|.+?\\s+in\\s+.+?\\s+Province\\.|The\\s+.+?\\s+in\\s+the\\s+.+?\\.)\\s+The\\s+date\\s+is\\s+.+?\\s+Based\\s+on\\s+the\\s+current\\s+weather,\\s+it\\s+will\\s+take\\s+\\d+\\s+days?\\s+to\\s+travel\\s+here\\.\\s+The\\s+total\\s+distance\\s+is\\s+[\\d,]+\\s*km\\.\\s+You\\s+should\\s+arrive\\s+by\\s+.+\\s*$', re.IGNORECASE)

def _looks_like_travel_estimate(text: str) -> bool:
    if not text:
        return False
    flat = ' '.join(text.replace('\r', ' ').split())
    return bool(_TRAVEL_ESTIMATE_SHAPE_RE.match(flat))

def is_travel_estimate(text: str) -> bool:
    if not text:
        return False
    flat = ' '.join(text.replace('\r', ' ').split())
    if _looks_like_travel_estimate(flat):
        return True
    return _translate_travel_estimate(flat, 'ja') is not None
_TRAVEL_LOC_RE_CACHE: dict[str, object] = {}

def _build_travel_loc_res() -> list[tuple]:
    orig = _load_travel_originals()
    if not orig:
        return []

    def _o(key: str) -> str | None:
        e = orig.get(key)
        return e.get('original') if isinstance(e, dict) else None
    loc0 = _o('location_format_texts.0')
    loc1 = _o('location_format_texts.1')
    loc2 = _o('location_format_texts.2')
    res: list[tuple] = []
    if loc2:
        res.append(('city', re.compile('^' + _frag_to_regex(_norm_fmt(loc2), ['ltype', 'lname', 'prov']))))
    if loc0:
        res.append(('dungeon', re.compile('^' + _frag_to_regex(_norm_fmt(loc0), ['lname', 'prov']))))
    if loc1:
        res.append(('center', re.compile('^' + _frag_to_regex(_norm_fmt(loc1), ['lname', 'prov']))))
    return res

def travel_location_name(text: str, lang: str='ja') -> tuple[str, str] | None:
    _ensure_i18n_bound_caches_current()
    if lang == 'en':
        return None
    res = _TRAVEL_LOC_RE_CACHE.get('res')
    if res is None:
        res = _build_travel_loc_res()
        _TRAVEL_LOC_RE_CACHE['res'] = res
    if not res:
        return None
    norm = ' '.join(text.split())
    for kind, rx in res:
        m = rx.match(norm)
        if not m:
            continue
        g = m.groupdict()
        prov_ja = _translate_static_place(g['prov'], lang)
        if kind == 'city':
            en = f"The {g['ltype']} of {g['lname']} in {g['prov']} Province."
            loc_ja = _translate_settlement_location(f"The {g['ltype']} of {g['lname']}", lang)
        elif kind == 'dungeon':
            en = f"{g['lname']} in {g['prov']} Province."
            loc_ja = _translate_static_place(g['lname'], lang)
        else:
            en = f"The {g['lname']} in the {g['prov']}."
            loc_ja = _translate_static_place(g['lname'], lang)
        import i18n_helper as i18n
        return (en, i18n.text('status_buffer_text.travel_location_format').replace('{province}', prov_ja).replace('{location}', loc_ja))
    return None
_ALREADY_IN_RE = re.compile('^You are already in (.+?)\\.?\\s*$')

def _translate_already_in(text: str, lang: str='ja') -> str | None:
    if lang == 'en':
        return None
    m = _ALREADY_IN_RE.match(' '.join(text.split()))
    if not m:
        return None
    place = m.group(1).strip()
    place_ja = _translate_static_place(place, lang) or place
    import i18n_helper as i18n
    return i18n.text('status_buffer_text.already_in_format').replace('{place}', place_ja)
_CONDITION_WARNING_RE = re.compile('Considering your condition.*attempt the journey', re.S)

def _translate_condition_warning(text: str, lang: str='ja') -> str | None:
    if lang == 'en':
        return None
    if not _CONDITION_WARNING_RE.search(' '.join(text.split())):
        return None
    import i18n_helper as i18n
    return i18n.text('status_buffer_text.travel_condition_warning') or None

def lookup(text: str) -> tuple[str, dict] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    text = ' '.join(text.split())
    _load()
    arrival = _translate_arrival(text, 'ja')
    if arrival is not None:
        return (arrival, {})
    already = _translate_already_in(text, 'ja')
    if already is not None:
        return (already, {})
    condition = _translate_condition_warning(text, 'ja')
    if condition is not None:
        return (condition, {})
    travel = _translate_travel_estimate(text, 'ja')
    if travel is not None:
        return (travel, {})
    compiled = _lookup_compiled_full(text)
    if compiled is not None:
        return compiled
    composite = lookup_composite(text)
    if composite is not None:
        return (composite[1], {})
    return None

def _lookup_compiled_full(text: str) -> tuple[str, dict] | None:
    closed_invalid_score = None
    closed_invalid_checked = False
    for compiled, ja, ph_count, is_exact, _literal_len in _COMPILED:
        m = compiled.match(text)
        if m:
            placeholders = m.groupdict()
            has_closed_group = any((name in _CLOSED_PH_ALT for name in placeholders))
            if not is_exact and (not has_closed_group):
                if not closed_invalid_checked:
                    closed_invalid_score = _closed_invalid_specificity(text)
                    closed_invalid_checked = True
                if closed_invalid_score is not None and closed_invalid_score[0] >= _literal_len:
                    continue
            return (ja, placeholders)
    return None

def lookup_exact(text: str) -> tuple[str, dict] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    normalized = ' '.join(text.split())
    _load()
    return _lookup_compiled_full(normalized)
_COMPOSITE_SPLIT_RE = re.compile('(?=`)')

def lookup_composite(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    norm = ' '.join(text.split())
    frags = [f.strip() for f in _COMPOSITE_SPLIT_RE.split(norm) if f.strip()]
    if len(frags) < 2 or not all((f.startswith('`') for f in frags)):
        return None
    en_lines: list[str] = []
    ja_lines: list[str] = []
    for frag in frags:
        result = lookup(frag)
        if result is None:
            return None
        ja_tmpl, placeholders = result
        ja_lines.append(format_japanese(ja_tmpl, placeholders))
        en_lines.append(frag.lstrip('`').strip())
    return ('\n'.join(en_lines), '\n'.join(ja_lines))

def lookup_travel_event(text: str) -> tuple[str, dict] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    text = ' '.join(text.split())
    _load()
    for compiled, ja, _ph_count, _is_exact, _literal_len in _TRAVEL_EVENT_COMPILED:
        m = compiled.match(text)
        if m:
            return (ja, m.groupdict())
    return None
_BODY_HEAD_ENTRIES: list[tuple[str, str, str, int]] = []
_BODY_HEAD_LOADED = False
_BODY_HEAD_PREFIX_RE: dict[str, re.Pattern] = {}
_BODY_HEAD_ANCHORS: dict[frozenset, tuple[str, ...]] = {}
_BODY_HEAD_ANCHOR_MAX = 50
_BODY_HEAD_ANCHOR_MIN = 16

def _body_head_anchor_of(en_norm: str) -> str:
    m = _PH_RE_NPCD.search(en_norm)
    lit = en_norm[:m.start()] if m else en_norm
    anchor = lit[:_BODY_HEAD_ANCHOR_MAX].rstrip()
    if len(anchor) < _BODY_HEAD_ANCHOR_MIN:
        return ''
    return anchor

def _load_body_head() -> None:
    global _BODY_HEAD_LOADED
    if _BODY_HEAD_LOADED:
        return
    _BODY_HEAD_LOADED = True
    _load_closed_ph()
    for en_raw, tmpl, _ph_list, key_int, _ref in _iter_npcd():
        en = ' '.join(en_raw.split())
        anchor = _body_head_anchor_of(en)
        if not anchor:
            continue
        _BODY_HEAD_ENTRIES.append((anchor.upper(), en, tmpl, key_int))

def body_head_anchors(keys: frozenset) -> tuple[str, ...]:
    _ensure_i18n_bound_caches_current()
    cached = _BODY_HEAD_ANCHORS.get(keys)
    if cached is not None:
        return cached
    anchors: list[str] = []
    for en_raw, _tmpl, _ph_list, key_int, _ref in _iter_npcd(include_untranslated=True):
        if key_int not in keys:
            continue
        anchor = _body_head_anchor_of(' '.join(en_raw.split()))
        if anchor:
            anchors.append(anchor)
    out = tuple(dict.fromkeys(anchors))
    _BODY_HEAD_ANCHORS[keys] = out
    return out

def lookup_body_head(text: str, *, keys: frozenset | None=None) -> tuple[str, dict] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    body = ' '.join(text.split())
    if not body:
        return None
    _load_body_head()
    body_upper = body.upper()
    best: tuple[int, str, str] | None = None
    ambiguous = False
    for anchor_u, en, tmpl, key_int in _BODY_HEAD_ENTRIES:
        if keys is not None and key_int not in keys:
            continue
        if not body_upper.startswith(anchor_u):
            continue
        if best is None or len(anchor_u) > best[0]:
            best = (len(anchor_u), en, tmpl)
            ambiguous = False
        elif len(anchor_u) == best[0] and (en, tmpl) != (best[1], best[2]):
            ambiguous = True
    if best is None or ambiguous:
        return None
    _anchor_len, en, tmpl = best
    compiled = _BODY_HEAD_PREFIX_RE.get(en)
    if compiled is None:
        compiled = _template_to_regex(en, anchor_end=False)
        if compiled is not None:
            _BODY_HEAD_PREFIX_RE[en] = compiled
    placeholders: dict = {}
    if compiled is not None:
        m = compiled.match(body)
        if m:
            placeholders = {k: v for k, v in m.groupdict().items() if v}
    return (tmpl, placeholders)
_BODY_SPAN_ENTRIES: dict[frozenset | None, tuple[tuple[str, str], ...]] = {}
_BODY_SPAN_RE: dict[str, re.Pattern | None] = {}

def _squeeze_ws(s: str) -> str:
    return ''.join(s.split())

def _body_span_regex(en_norm: str) -> re.Pattern | None:
    if en_norm in _BODY_SPAN_RE:
        return _BODY_SPAN_RE[en_norm]
    parts: list[str] = []
    last = 0
    for m in _PH_RE_NPCD.finditer(en_norm):
        parts.append(re.escape(_squeeze_ws(en_norm[last:m.start()])))
        parts.append('.+?')
        last = m.end()
    tail = _squeeze_ws(en_norm[last:])
    compiled: re.Pattern | None = None
    if tail:
        parts.append(re.escape(tail))
        try:
            compiled = re.compile('^' + ''.join(parts), re.DOTALL | re.IGNORECASE)
        except re.error:
            compiled = None
    _BODY_SPAN_RE[en_norm] = compiled
    return compiled

def _body_span_entries(keys: frozenset | None) -> tuple[tuple[str, str], ...]:
    cached = _BODY_SPAN_ENTRIES.get(keys)
    if cached is not None:
        return cached
    entries: list[tuple[str, str]] = []
    for en_raw, _tmpl, _ph_list, key_int, _ref in _iter_npcd(include_untranslated=True):
        if keys is not None and key_int not in keys:
            continue
        en = ' '.join(en_raw.split())
        anchor = _body_head_anchor_of(en)
        if not anchor:
            continue
        entries.append((anchor.upper(), en))
    out = tuple(entries)
    _BODY_SPAN_ENTRIES[keys] = out
    return out

def body_head_trim(text: str, *, keys: frozenset | None=None) -> str | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    body = ' '.join(text.split())
    if not body:
        return None
    body_upper = body.upper()
    best: tuple[int, str] | None = None
    ambiguous = False
    for anchor_u, en in _body_span_entries(keys):
        if not body_upper.startswith(anchor_u):
            continue
        if best is None or len(anchor_u) > best[0]:
            best = (len(anchor_u), en)
            ambiguous = False
        elif len(anchor_u) == best[0] and en != best[1]:
            ambiguous = True
    if best is None or ambiguous:
        return None
    compiled = _body_span_regex(best[1])
    if compiled is None:
        return None
    m = compiled.match(_squeeze_ws(body))
    if m is None:
        return None
    remaining = m.end()
    for i, ch in enumerate(body):
        if not ch.isspace():
            remaining -= 1
            if remaining == 0:
                return body[:i + 1]
    return None
_FIXED_SEG_ENTRIES: list[tuple[tuple, list, str, int]] = []
_FIXED_SEG_LOADED = False

def _split_segments(en_norm: str) -> tuple[tuple, list]:
    segs: list[tuple[str, str]] = []
    names: list[str] = []
    pos = 0
    for m in _PH_RE_NPCD.finditer(en_norm):
        lit = en_norm[pos:m.start()]
        if lit:
            segs.append(('lit', lit))
        segs.append(('ph', m.group(1)))
        names.append(m.group(1))
        pos = m.end()
    tail = en_norm[pos:]
    if tail:
        segs.append(('lit', tail))
    return (tuple(segs), names)

def _load_fixed_segments() -> None:
    global _FIXED_SEG_LOADED
    if _FIXED_SEG_LOADED:
        return
    _FIXED_SEG_LOADED = True
    _load_closed_ph()
    for en_raw, tmpl, _ph_list, key_int, _ref in _iter_npcd():
        if not tmpl:
            continue
        segs, names = _split_segments(' '.join(en_raw.split()))
        if not segs:
            continue
        _FIXED_SEG_ENTRIES.append((segs, names, tmpl, key_int))

def _walk_segments(segs: tuple, body_up: str, body: str, *, allow_partial: bool=False) -> tuple | None:
    pos = 0
    matched_parts = 0
    matched_chars = 0
    values: dict[str, str] = {}
    pending_ph: str | None = None
    first = True
    walked_all = True
    for kind, val in segs:
        if kind == 'ph':
            pending_ph = val
            continue
        up = val.upper()
        if first:
            if pending_ph is None:
                if not body_up.startswith(up):
                    return None
                idx = 0
            else:
                idx = body_up.find(up, pos)
                if idx <= pos:
                    return None
        else:
            idx = body_up.find(up, pos)
            if idx == -1:
                if not allow_partial:
                    return None
                remainder = body_up[pos:]
                if pending_ph is None and (not up.startswith(remainder)):
                    return None
                walked_all = False
                break
        if pending_ph is not None:
            captured = body[pos:idx].strip()
            if not captured:
                return None
            previous = values.get(pending_ph)
            if previous is not None and previous != captured:
                return None
            values[pending_ph] = captured
            pending_ph = None
        pos = idx + len(val)
        matched_parts += 1
        matched_chars += len(val)
        first = False
    if matched_parts == 0:
        return None
    span_end = pos if walked_all and pending_ph is None else None
    return (matched_parts, matched_chars, values, span_end)

def _closed_invalid_specificity(text: str) -> tuple[int, int] | None:
    if not text:
        return None
    _load_fixed_segments()
    body = ' '.join(text.split())
    body_up = body.upper()
    best: tuple[int, int] | None = None
    for segs, names, _tmpl, _key_int in _FIXED_SEG_ENTRIES:
        if not any((name in _CLOSED_PH_ALT for name in names)):
            continue
        got = _walk_segments(segs, body_up, body)
        if got is None or got[3] != len(body):
            continue
        invalid = any(((alt := _CLOSED_PH_ALT.get(name)) is not None and re.fullmatch(f'(?:{alt})', value, flags=re.IGNORECASE) is None for name, value in got[2].items()))
        if not invalid:
            continue
        score = (got[1], got[0])
        if best is None or score > best:
            best = score
    return best

def _identify_by_fixed_parts(text: str, *, allow_partial: bool=False, require_span: bool=False) -> tuple[str, dict, int | None] | None:
    if not text:
        return None
    _ensure_i18n_bound_caches_current()
    _load_fixed_segments()
    body = ' '.join(text.split())
    body_up = body.upper()
    best = None
    best_score = (0, 0)
    invalid_best_score = (0, 0)
    tied = False
    for segs, _names, tmpl, _key_int in _FIXED_SEG_ENTRIES:
        got = _walk_segments(segs, body_up, body, allow_partial=allow_partial)
        if got is None:
            continue
        score = (got[1], got[0])
        closed_invalid = False
        for name, value in got[2].items():
            alt = _CLOSED_PH_ALT.get(name)
            if alt and re.fullmatch(f'(?:{alt})', value, flags=re.IGNORECASE) is None:
                closed_invalid = True
                break
        if closed_invalid:
            if score > invalid_best_score:
                invalid_best_score = score
            continue
        if require_span and got[3] is None:
            continue
        if score > best_score:
            best_score = score
            best = (tmpl, got[2], got[3])
            tied = False
        elif score == best_score and best is not None:
            tied = True
    if best is None or tied or (invalid_best_score != (0, 0) and invalid_best_score >= best_score):
        return None
    return best

def lookup_by_fixed_parts(text: str) -> tuple[str, dict] | None:
    found = _identify_by_fixed_parts(text)
    if found is None:
        return None
    return (found[0], found[1])

def lookup_partial_by_fixed_parts(text: str) -> tuple[str, dict] | None:
    found = _identify_by_fixed_parts(text, allow_partial=True)
    if found is None:
        return None
    return (found[0], found[1])

def lookup_span_by_fixed_parts(text: str) -> tuple[str, dict, str] | None:
    found = _identify_by_fixed_parts(text, require_span=True)
    if found is None:
        return None
    body = ' '.join(text.split())
    return (found[0], found[1], body[:found[2]])

def lookup_span_at_chunk_boundaries(chunks: list[str] | tuple[str, ...]) -> tuple[str, dict, str] | None:
    prefix: list[str] = []
    matches: list[tuple[str, dict, str]] = []
    for chunk in chunks:
        normalized = ' '.join((chunk or '').split())
        if not normalized:
            return None
        prefix.append(normalized)
        span = ' '.join(prefix)
        found = lookup_exact(span)
        if found is not None:
            matches.append((found[0], found[1], span))
    return matches[0] if len(matches) == 1 else None

def format_japanese(ja_template: str, placeholders: dict, lang: str='ja') -> str:
    result = ja_template
    for name, value in sorted(placeholders.items(), key=lambda item: len(item[0]), reverse=True):
        if value:
            translated = translate_placeholder(name, value, lang)
            result = result.replace(f'%{name}', translated)
    from text_corrector import apply_text_corrections
    result = apply_text_corrections(result, lang)
    return result
if __name__ == '__main__':
    samples = ['Greetings, I am John, a Mage. I cast spells for a living.', 'They call me Maria the Warrior. I fight for a living.', 'I am called Tom, the Daggerfall Bard. You know, I play music for a living.', 'Good day, sir. My name is Alice the skilled Healer. I heal the sick for a living.', "The boys call me Lily. I'm a whore.", "How would like to recover something for a friend of mine, a highly aggressive aristocrat called Lord Barbyrrya? You can find this person at the Blue Giants, you know the inn southwest of here? I'm sure you'll be paid nicely."]
    for s in samples:
        result = lookup(s)
        if result:
            ja_template, ph = result
            output = format_japanese(ja_template, ph)
            print(f'EN: {s}')
            print(f'PH: {ph}')
            print(f'JA: {output}')
        else:
            print(f'EN: {s}')
            print(f'JA: <no match>')
        print()
