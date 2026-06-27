from __future__ import annotations
import re
_COMPILED: list[tuple[re.Pattern, str, str, str | None, list[str], int, str | None, int | None, str | None]] = []
_LITERAL: list[tuple[str, str, str, str | None, int, str | None, int | None, str | None]] = []
_HASH_TO_SIDS: dict[str, list[str]] = {}
_LOADED = False
_FUZZY_MIN_RATIO = 0.9
_PARTIAL_PREFIX_MIN = 80
_PARTIAL_TAIL_MIN = 24
_PLACEHOLDER_NAMES: frozenset[str] = frozenset({'nt', 'tem', 'en', 't', 'rf', 'cn', 'st', 'cn2', 'ct'})

def _template_to_regex(en_template: str) -> re.Pattern | None:
    seen: set[str] = set()
    parts: list[str] = []
    token_re = re.compile('%([a-z][a-z0-9]*)')
    last = 0
    for m in token_re.finditer(en_template):
        name = m.group(1)
        parts.append(re.escape(en_template[last:m.start()]))
        if name in _PLACEHOLDER_NAMES:
            if name not in seen:
                parts.append(f'(?P<{name}>.+?)')
                seen.add(name)
            else:
                parts.append(f'(?P={name})')
        else:
            parts.append('.+?')
        last = m.end()
    parts.append(re.escape(en_template[last:]))
    full_pattern = '^' + ''.join(parts) + '$'
    try:
        return re.compile(full_pattern, re.DOTALL)
    except re.error:
        return None
_CAT = 'template_dat_building_entry'
_PH_RE = re.compile('%([a-zA-Z][a-zA-Z0-9]*)')

def _placeholders_of(en: str) -> list[str]:
    seen: list[str] = []
    for m in _PH_RE.finditer(en):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen

def _derive_meta(source_id: str, en: str):
    import i18n_source_address as sa
    parts = source_id.split(':')
    block, copy, idx = (parts[1], int(parts[2]), int(parts[3]))
    if '_' in block:
        key, letter = block.rsplit('_', 1)
    else:
        key, letter = (block, None)
    return (key, letter, copy, idx, _placeholders_of(en), sa.source_hash(en))

def _iter_entries():
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_CAT):
        for e in i18n.v2_category_entries(_CAT):
            en = e.get('original')
            sid = e.get('source_id')
            if not en or not sid:
                continue
            key, letter, copy, idx, ph, sh = _derive_meta(sid, en)
            yield (en, e.get('text'), sid, key, letter, copy, idx, ph, sh)
    else:
        for id_, entry in i18n.originals(_CAT).items():
            if not isinstance(entry, dict):
                continue
            en = entry.get('original', '')
            if not en:
                continue
            try:
                idx = int(id_.split('.')[-1])
            except ValueError:
                idx = 0
            yield (en, i18n.text(id_), entry.get('source_id'), entry.get('key', ''), entry.get('letter'), entry.get('copy'), idx, entry.get('placeholders', []) or [], entry.get('source_hash'))

def _load() -> None:
    global _COMPILED, _LITERAL, _HASH_TO_SIDS, _LOADED
    if _LOADED:
        return
    compiled: list = []
    literal: list = []
    hash_to_sids: dict[str, list[str]] = {}
    for en, ja, source_id, key, letter, copy, idx, ph_list, source_hash in _iter_entries():
        if source_hash and source_id:
            hash_to_sids.setdefault(source_hash, []).append(source_id)
        if not ja:
            continue
        pattern = _template_to_regex(en)
        if pattern is None:
            continue
        compiled.append((pattern, ja, key, letter, ph_list, idx, source_id, copy, source_hash))
        if not ph_list:
            literal.append((' '.join(en.split()), ja, key, letter, idx, source_id, copy, source_hash))
    for sids in hash_to_sids.values():
        sids.sort()
    _COMPILED = compiled
    _LITERAL = literal
    _HASH_TO_SIDS = hash_to_sids
    _LOADED = True

def _meta(key: str, letter: str | None, source_id: str | None, copy: int | None, source_hash: str | None, **extra) -> dict:
    candidates = _HASH_TO_SIDS.get(source_hash or '', [])
    meta = {'matched_key': key, 'matched_letter': letter, 'source_id': source_id, 'copy': copy, 'source_id_candidates': list(candidates), 'placeholders': {}, 'placeholders_ja': {}}
    meta.update(extra)
    return meta

def _translate_facility(value: str, category: str) -> str:
    try:
        from dynamic_place_lookup import lookup as _place_lookup
    except ImportError:
        return value
    translated = _place_lookup(value, category=category)
    return translated if translated else value

def _translate_st(value: str) -> str:
    import i18n_helper as i18n
    return i18n.value('status_terms', value.lower()) or value

def _translate_placeholder(name: str, value: str) -> str:
    if not value:
        return value
    if name == 'nt':
        return _translate_facility(value, category='tavern')
    if name == 'tem':
        return _translate_facility(value, category='temple')
    if name == 'en':
        return _translate_facility(value, category='equipment_store')
    if name == 'st':
        return _translate_st(value)
    delegate_name = 'cn' if name == 'cn2' else name
    try:
        from npc_dialog_lookup import translate_placeholder as _npc_tp
        return _npc_tp(delegate_name, value, lang='ja')
    except ImportError:
        return value

def _format_ja(ja_template: str, placeholders: dict[str, str]) -> str:
    result = ja_template
    for name in sorted(placeholders, key=len, reverse=True):
        value = _translate_placeholder(name, placeholders[name])
        result = result.replace(f'%{name}', value)
    return result

def _common_prefix_len(a: str, b: str) -> int:
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i

def _best_contained_tail_len(needle: str, haystack: str) -> int:
    import difflib
    if not needle or not haystack:
        return 0
    match = difflib.SequenceMatcher(None, needle, haystack).find_longest_match(0, len(needle), 0, len(haystack))
    return match.size

def _partial_literal_match(normalized: str) -> tuple[str, str, str | None, str | None, int | None, str | None, int, int] | None:
    best_score: tuple[int, int] = (0, 0)
    best_group: list = []
    for en, ja, key, letter, _idx, source_id, copy, source_hash in _LITERAL:
        prefix_len = _common_prefix_len(normalized, en)
        if prefix_len < _PARTIAL_PREFIX_MIN:
            continue
        tail = normalized[prefix_len:].strip()
        tail_len = _best_contained_tail_len(tail, en[prefix_len:])
        if tail_len < _PARTIAL_TAIL_MIN:
            continue
        score = (prefix_len, tail_len)
        cand = (ja, key, letter, source_id, copy, source_hash, prefix_len, tail_len)
        if score > best_score:
            best_score = score
            best_group = [cand]
        elif score == best_score:
            best_group.append(cand)
    if not best_group:
        return None
    if len({(c[1], c[2]) for c in best_group}) > 1:
        return None
    best_group.sort(key=lambda c: c[4] if c[4] is not None else 0)
    return best_group[0]

def lookup(text: str) -> tuple[str, dict] | None:
    _load()
    normalized = ' '.join(text.split())
    if not normalized:
        return None
    for pattern, ja_template, key, letter, ph_list, _idx, source_id, copy, source_hash in _COMPILED:
        m = pattern.match(normalized)
        if m is None:
            continue
        placeholders_en = {name: m.group(name) for name in ph_list if name in m.groupdict()}
        placeholders_ja = {name: _translate_placeholder(name, value) for name, value in placeholders_en.items()}
        translated = _format_ja(ja_template, placeholders_en)
        meta = _meta(key, letter, source_id, copy, source_hash)
        meta['placeholders'] = placeholders_en
        meta['placeholders_ja'] = placeholders_ja
        return (translated, meta)
    import difflib
    best_ratio = 0.0
    best = None
    for en, ja, key, letter, idx, source_id, copy, source_hash in _LITERAL:
        ratio = difflib.SequenceMatcher(None, normalized, en).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = (ja, key, letter, source_id, copy, source_hash)
    if best is not None and best_ratio >= _FUZZY_MIN_RATIO:
        ja, key, letter, source_id, copy, source_hash = best
        return (ja, _meta(key, letter, source_id, copy, source_hash, fuzzy_ratio=round(best_ratio, 3)))
    partial = _partial_literal_match(normalized)
    if partial is not None:
        ja, key, letter, source_id, copy, source_hash, prefix_len, tail_len = partial
        return (ja, _meta(key, letter, source_id, copy, source_hash, partial_prefix_len=prefix_len, partial_tail_len=tail_len))
    return None

def is_building_entry_message(text: str) -> bool:
    return lookup(text) is not None
