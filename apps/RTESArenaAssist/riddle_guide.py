from __future__ import annotations
import html
import i18n_helper as i18n
REVEAL_SCHEME = 'riddle-answer'
PLACE_SCHEME = 'riddle-place'

def parse_place(url: str) -> int | None:
    prefix = PLACE_SCHEME + ':'
    if not (url or '').startswith(prefix):
        return None
    rest = url[len(prefix):]
    if not rest:
        return -1
    try:
        return int(rest)
    except ValueError:
        return None

def _translate_place(en: str) -> str:
    try:
        import location_lookup
        return location_lookup.lookup(en) or en
    except Exception:
        return en

def _place_label(inf: str, place: str) -> str:
    unknown = i18n.tr('manual.guide.place_unknown')
    name = _translate_place((place or '').strip()) or unknown
    level = _level_label(inf)
    if level:
        return '%s %s' % (name, level)
    return name if name != unknown else inf

def _level_label(inf: str) -> str:
    stem = (inf or '').rsplit('.', 1)[0]
    digits = ''
    while stem and stem[-1].isdigit():
        digits = stem[-1] + digits
        stem = stem[:-1]
    return i18n.tr('manual.guide.floor', n=int(digits)) if digits else ''

def collect_entries(seen: list[dict]) -> list[dict]:
    import inf_text_lookup as itl
    itl._ensure_loaded()
    out: list[dict] = []
    for rec in seen or []:
        inf, idx = (rec.get('inf'), rec.get('idx'))
        entry = itl._index.get((inf, idx))
        if not entry or entry.get('type') != 'riddle':
            continue
        question = entry.get('question') or ''
        if not question:
            continue
        trans = itl.get_translation(entry)
        q_ja = trans.get('question', '') if isinstance(trans, dict) else ''
        out.append({'key': '%s#%s' % (inf, idx), 'place': _place_label(inf, rec.get('place', '')), 'question': question, 'question_ja': q_ja, 'answers': _answers_for(entry, inf, idx, rec)})
    return out

def _log_answer_miss(entry: dict, inf, idx) -> None:
    try:
        import logging
        import i18n_helper as i18n
        logging.getLogger('RTESArenaAssist').warning('riddle_guide: answers empty inf=%r idx=%r entry_keys=%s v2_cat=%s v2_any=%s originals=%d', inf, idx, sorted(entry.keys()), i18n.v2_public_enabled('inf_text'), i18n.v2_public_enabled(None), len(i18n.originals('inf_text') or {}))
    except Exception:
        pass

def _answers_for(entry: dict, inf, idx, rec: dict | None=None) -> list[str]:
    rec_ans = [str(a) for a in (rec or {}).get('answers') or [] if str(a).strip()]
    if rec_ans:
        return rec_ans
    answers = [str(a) for a in entry.get('answers') or [] if str(a).strip()]
    if answers:
        return answers
    try:
        import i18n_helper as i18n
        for e in (i18n.originals('inf_text') or {}).values():
            if not isinstance(e, dict):
                continue
            if str(e.get('inf', '')).upper() == str(inf).upper() and e.get('idx') == idx:
                got = [str(a) for a in e.get('answers') or [] if str(a).strip()]
                if got:
                    return got
    except Exception:
        pass
    got = answers_from_original(entry.get('original') or '')
    if got:
        return got
    _log_answer_miss(entry, inf, idx)
    return []

def answers_from_original(raw: str) -> list[str]:
    out: list[str] = []
    for line in (raw or '').replace('\r', '\n').split('\n'):
        s = line.strip()
        if s.startswith(':'):
            v = s[1:].strip()
            if v:
                out.append(v)
    return out

def group_entries(entries: list[dict]) -> list[tuple[str, list[dict]]]:
    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for e in entries or []:
        place = e.get('place') or ''
        if place not in groups:
            groups[place] = []
            order.append(place)
        groups[place].append(e)
    return [(p, groups[p]) for p in order]

def _answers_html(entry: dict) -> str:
    answers = [a for a in entry.get('answers') or [] if str(a).strip()]
    if not answers:
        return '<p>%s</p>' % html.escape(i18n.tr('manual.guide.answer_missing'))
    return ''.join(('<p>%s</p>' % html.escape(i18n.tr('manual.guide.answer_item', answer=str(a))) for a in answers))

def build_index_html(groups: list[tuple[str, list[dict]]]) -> str:
    parts = ['<h1>%s</h1>' % html.escape(i18n.tr('manual.guide.title'))]
    if not groups:
        parts.append('<p>%s</p>' % html.escape(i18n.tr('manual.guide.empty')))
        return '\n'.join(parts)
    parts.append('<p>%s</p>' % html.escape(i18n.tr('manual.guide.intro')))
    for i, (place, entries) in enumerate(groups):
        parts.append('<p><a href="%s:%d">%s</a>%s</p>' % (PLACE_SCHEME, i, html.escape(place), html.escape(i18n.tr('manual.guide.place_count', n=len(entries)))))
    return '\n'.join(parts)

def build_html(entries: list[dict], revealed: set[str] | None=None, heading: str | None=None, with_back: bool=False) -> str:
    revealed = revealed or set()
    if heading is None:
        heading = i18n.tr('manual.guide.title')
    parts = ['<h1>%s</h1>' % html.escape(heading)]
    if with_back:
        parts.append('<p><a href="%s:">%s</a></p>' % (PLACE_SCHEME, html.escape(i18n.tr('manual.guide.back'))))
    if not entries:
        parts.append('<p>%s</p>' % html.escape(i18n.tr('manual.guide.empty')))
        return '\n'.join(parts)
    for e in entries:
        parts.append('<hr>')
        if e.get('question_ja'):
            parts.append('<p><b>%s</b></p>' % html.escape(i18n.tr('manual.guide.question')))
            parts.append('<p style="margin-left:12px">%s</p>' % html.escape(e['question_ja']).replace('\n', '<br>'))
        parts.append('<p><b>%s</b></p>' % html.escape(i18n.tr('manual.guide.original')))
        parts.append('<p style="margin-left:12px; color:#888"><i>%s</i></p>' % html.escape(e['question']).replace('\n', '<br>'))
        if e['key'] in revealed:
            parts.append('<p><b>%s</b></p>' % html.escape(i18n.tr('manual.guide.answer_heading')))
            parts.append(_answers_html(e))
        else:
            parts.append('<p><a href="%s:%s">%s</a></p>' % (REVEAL_SCHEME, html.escape(e['key']), html.escape(i18n.tr('manual.guide.reveal'))))
    return '\n'.join(parts)

def parse_reveal(url: str) -> str | None:
    prefix = REVEAL_SCHEME + ':'
    return url[len(prefix):] if (url or '').startswith(prefix) else None
