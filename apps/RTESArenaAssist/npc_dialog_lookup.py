
from __future__ import annotations

import json
import re

from npc_name_translator import translate_generated_name

_COMPILED: list[tuple[re.Pattern, str, int, bool, int]] = []
_LOADED = False

_CLOSED_PH_ALT: dict[str, str] = {}
_CLOSED_PH_LOADED = False
_CLOSED_PLACEHOLDERS: frozenset[str] = frozenset({"di"})

_PH_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PH_DIRECT_ID_NAMES: frozenset[str] = frozenset({"cn", "lp", "ct", "oc", "t", "di",
                                                 "g", "g2", "g3"})

_PV_VALUE_SUBGROUPS: frozenset[str] = frozenset({"ra", "t", "oc", "ct", "oth", "di",
                                                 "lp", "cn", "tem"})


def _ph_slug(en: str) -> str:
    s = en.strip().lower().replace("'", "")
    return _PH_SLUG_NON_ALNUM.sub("_", s).strip("_")


def _ph_direct_id(name: str, value: str) -> str | None:
    import i18n_helper as i18n
    return i18n.text_opt(f"placeholder_values.%{name}.{_ph_slug(value)}.0")


def _load_closed_ph() -> None:
    global _CLOSED_PH_LOADED
    if _CLOSED_PH_LOADED:
        return
    _CLOSED_PH_LOADED = True
    import i18n_helper as i18n
    words_by_name: dict[str, list[str]] = {}
    for id_, e in i18n.originals("placeholder_values").items():
        if not isinstance(e, dict):
            continue
        m = re.match(r"placeholder_values\.%([a-z0-9]+)\.", id_)
        if not m or m.group(1) not in _CLOSED_PLACEHOLDERS:
            continue
        en_val = (e.get("original", "") or "").strip()
        if en_val:
            words_by_name.setdefault(m.group(1), []).append(en_val)
    if not words_by_name:
        for sid in i18n.lang_ids("placeholder_values"):
            m = re.match(r"placeholder_values\.%([a-z0-9]+)\.(.+)\.[^.]+$", sid)
            if m and m.group(1) in _CLOSED_PLACEHOLDERS:
                words_by_name.setdefault(m.group(1), []).append(m.group(2))
    for name, words in words_by_name.items():
        words = sorted(set(words), key=lambda w: (-len(w), w))
        _CLOSED_PH_ALT[name] = "|".join(re.escape(w) for w in words)


def _literal_chars(en: str) -> int:
    return len(re.sub(r"%[a-z][a-z0-9]*", "", en))

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
    for id_, e in i18n.originals("items").items():
        parts = id_.split(".")
        if len(parts) < 2 or parts[1] != section or not isinstance(e, dict):
            continue
        en = e.get("original", "")
        ja = i18n.text(id_)
        if en and ja and ja != id_:
            out[en] = ja
    for ent in i18n.v2_category_entries("items"):
        if (ent.get("context") or {}).get("section") != section:
            continue
        en, ja = ent.get("original"), ent.get("text")
        if en and ja:
            out.setdefault(en, ja)
    return out


def _load_drinks() -> None:
    global _DRINKS_LOADED, _DRINKS_VALUES
    if _DRINKS_LOADED:
        return
    _DRINKS_LOADED = True
    _DRINKS_VALUES.update(_items_section_map("drinks"))


_ROOMS_VALUES: dict[str, str] = {}
_ROOMS_LOADED = False


def _load_rooms() -> None:
    global _ROOMS_LOADED, _ROOMS_VALUES
    if _ROOMS_LOADED:
        return
    _ROOMS_LOADED = True
    _ROOMS_VALUES.update(_items_section_map("rooms"))


_ITEMS_FLAT: dict[str, str] = {}
_ITEMS_FLAT_LOADED = False


def _load_items_flat() -> None:
    global _ITEMS_FLAT_LOADED, _ITEMS_FLAT
    if _ITEMS_FLAT_LOADED:
        return
    _ITEMS_FLAT_LOADED = True
    import i18n_helper as i18n
    for id_, e in i18n.originals("items").items():
        if not isinstance(e, dict):
            continue
        en = e.get("original", "")
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja
    for ent in i18n.v2_category_entries("items"):
        en = ent.get("original")
        ja = ent.get("text")
        if en and ja:
            _ITEMS_FLAT.setdefault(en, ja)
    for id_, e in i18n.originals("mages").items():
        en = e.get("original", "") if isinstance(e, dict) else ""
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja


_KEY_MATERIALS: dict[str, str] = {}
_KEY_MATERIALS_LOADED = False


def _load_key_materials() -> None:
    global _KEY_MATERIALS_LOADED, _KEY_MATERIALS
    if _KEY_MATERIALS_LOADED:
        return
    _KEY_MATERIALS_LOADED = True
    _KEY_MATERIALS.update(_items_section_map("key_materials"))


_PP_RULES: dict[str, dict[str, list[tuple[re.Pattern, str]]]] = {}


def _load_placeholder_preprocessing(lang: str) -> dict[str, list[tuple[re.Pattern, str]]]:
    if lang in _PP_RULES:
        return _PP_RULES[lang]
    import i18n_helper as i18n
    per_ph: dict[str, list[tuple[re.Pattern, str]]] = {}
    pp = i18n.rules(lang).get("placeholder_preprocessing", {})
    for ph_name, rules in pp.get("placeholders", {}).items():
        if not isinstance(rules, list):
            continue
        compiled_list = per_ph.setdefault(ph_name, [])
        for rule in rules:
            pattern = rule.get("pattern")
            replace = rule.get("replace", "")
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
    if not value or not lang or not name:
        return value
    rules = _load_placeholder_preprocessing(lang).get(name, [])
    if not rules:
        return value
    for compiled, replace in rules:
        value = compiled.sub(replace, value)
    return value

_DS_PATTERN = re.compile(r"^(.+?)\s+(\w+)\s+called\s+(\w+)\s+(.+)$")

_PLACEHOLDER_NAMES: frozenset[str] = frozenset([
    "a", "a2", "an", "ccs", "cll", "cn", "cn2", "cp", "ct", "da", "di",
    "doc", "ds", "en",
    "fn", "fq", "g", "g2", "g3", "hc", "hod", "jok", "lp", "mi",
    "mn", "mt", "n", "nc", "nc2", "nd", "ne", "nh", "nhd", "ni",
    "nk", "nr",
    "nt", "o", "oap", "oc", "omq", "oth", "pcf", "pcn", "qc", "qt", "r", "ra",
    "rcn", "rf", "sn", "st", "t", "tan", "tem", "tg", "tl", "tq", "tt",
])


def _template_to_regex(en_template: str) -> re.Pattern | None:
    seen: set[str] = set()
    pattern_parts: list[str] = []
    pos = 0
    text = en_template
    token_re = re.compile(r"%([a-z][a-z0-9]*)")

    last = 0
    for m in token_re.finditer(text):
        name = m.group(1)
        pattern_parts.append(re.escape(text[last:m.start()]))
        if name in _PLACEHOLDER_NAMES:
            if name not in seen:
                alt = _CLOSED_PH_ALT.get(name)
                if alt:
                    pattern_parts.append(
                        f"(?P<{name}>(?i:{alt}))(?![A-Za-z])")
                else:
                    pattern_parts.append(f"(?P<{name}>.+?)")
                seen.add(name)
            else:
                pattern_parts.append(f"(?P={name})")
        else:
            pattern_parts.append(r".+?")
        last = m.end()
    pattern_parts.append(re.escape(text[last:]))

    full_pattern = "^" + "".join(pattern_parts) + "$"
    try:
        return re.compile(full_pattern, re.DOTALL)
    except re.error:
        return None


_NPCD_CAT = "npc_dialog"
_PH_RE_NPCD = re.compile(r"%([a-zA-Z][a-zA-Z0-9]*)")


def _npcd_ph_of(en: str) -> list[str]:
    seen: list[str] = []
    for m in _PH_RE_NPCD.finditer(en):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def _npcd_key_int(source_id: str | None) -> int:
    if source_id and source_id.startswith("template:"):
        try:
            return int(source_id.split(":")[1])
        except (ValueError, IndexError):
            return -1
    return -1


def _resolve_npcd_ref(ref) -> str | None:
    import i18n_helper as i18n
    kind, val = ref
    if kind == "sid":
        return i18n.text_by_source_id(val, category=_NPCD_CAT)
    return i18n.text(val)


def _iter_npcd():
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_NPCD_CAT):
        for e in i18n.v2_category_entries(_NPCD_CAT):
            en_raw = e.get("original")
            if not en_raw:
                continue
            tmpl = e.get("text")
            if not tmpl:
                continue
            sid = e.get("source_id")
            yield en_raw, tmpl, _npcd_ph_of(en_raw), _npcd_key_int(sid), ("sid", sid)
    else:
        for id_, entry in i18n.originals(_NPCD_CAT).items():
            en_raw = entry.get("original", "") if isinstance(entry, dict) else ""
            if not en_raw:
                continue
            tmpl = i18n.text(id_)
            if not tmpl:
                continue
            parts = id_.split(".")
            try:
                key_int = int(parts[1]) if len(parts) >= 2 else -1
            except ValueError:
                key_int = -1
            yield (en_raw, tmpl, entry.get("placeholders", []) or [], key_int,
                   ("id", id_))


def _load() -> None:
    global _COMPILED, _LOADED, _DOC_VALUES, _DOC_COMPILED
    if _LOADED:
        return
    _load_closed_ph()
    entries: list[tuple[re.Pattern, str, int, bool, int]] = []
    doc_entries: list[tuple[re.Pattern, str, int]] = []
    for en_raw, tmpl, ph_list, key_int, ref in _iter_npcd():
        en = " ".join(en_raw.split())
        ph_count = len(ph_list)
        is_exact = (ph_count == 0)
        literal_len = _literal_chars(en)
        compiled = _template_to_regex(en)
        if compiled is None:
            continue
        entries.append((compiled, tmpl, ph_count, is_exact, literal_len))

        if 262 <= key_int <= 362:
            if not ph_list:
                _DOC_VALUES[en] = {"ref": ref}
            else:
                doc_entries.append((compiled, tmpl, ph_count))

    entries.sort(key=lambda x: (not x[3], -x[4], -x[2]))
    _COMPILED = entries
    doc_entries.sort(key=lambda x: -x[2])
    _DOC_COMPILED = doc_entries
    _LOADED = True


def _load_ph() -> None:
    global _PH_VALUES, _CLASS_VALUES, _PH_LOADED
    if _PH_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    for id_, e in i18n.originals("races").items():
        en_val = e.get("original", "") if isinstance(e, dict) else ""
        if en_val:
            ja = i18n.text(id_)
            if ja and ja != id_:
                _PH_VALUES[("ra", en_val)] = {lang: ja}
    for id_, e in i18n.originals("placeholder_values").items():
        if not isinstance(e, dict):
            continue
        m = re.match(r"placeholder_values\.%([a-z0-9]+)\.", id_)
        if not m:
            continue
        name = m.group(1)
        en_val = e.get("original", "")
        if not en_val:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _PH_VALUES[(name, en_val)] = {lang: ja}
    for id_, e in i18n.originals("classes").items():
        en_val = e.get("original", "") if isinstance(e, dict) else ""
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
    if i18n.v2_public_enabled("npc_traits"):
        for e in i18n.v2_category_entries("npc_traits"):
            en_val = (e.get("original") or "").strip()
            if en_val:
                _TRAIT_VALUES[en_val] = e.get("text") or ""
    else:
        for id_, e in i18n.originals("npc_traits").items():
            en_val = (e.get("original", "") if isinstance(e, dict) else "").strip()
            if en_val:
                ja = i18n.text(id_)
                _TRAIT_VALUES[en_val] = ja if (ja and ja != id_) else ""
    _TRAITS_LOADED = True


_CALENDAR_WEEKDAYS: dict[str, dict[str, str]] = {}
_CALENDAR_MONTHS: dict[str, dict[str, str]] = {}
_CALENDAR_LOADED = False


def _load_calendar() -> None:
    global _CALENDAR_LOADED
    if _CALENDAR_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    try:
        for id_, e in i18n.originals("calendar").items():
            if not isinstance(e, dict):
                continue
            cat = e.get("category", "")
            en = e.get("original", "")
            if not en:
                continue
            ja = i18n.text(id_)
            if not ja or ja == id_:
                continue
            if cat == "weekday":
                _CALENDAR_WEEKDAYS[en] = {lang: ja}
            elif cat == "month":
                _CALENDAR_MONTHS[en] = {lang: ja}
    except (OSError, json.JSONDecodeError):
        pass
    _CALENDAR_LOADED = True


_DATE_PATTERN_SHORT = re.compile(
    r"^([A-Z][a-z]+),\s+(\d+)(?:st|nd|rd|th)\s+of\s+([A-Z][A-Za-z'\s]+?)$")
_DATE_PATTERN_FULL = re.compile(
    r"^([A-Z][a-z]+),\s+(\d+)(?:st|nd|rd|th)\s+of\s+([A-Z][A-Za-z'\s]+?)"
    r"\s+in\s+the\s+year\s+([0-9]+E)\s+(\d+)$")

def _translate_date(value: str, lang: str) -> str:
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
        era_ja = i18n.value_in("eras", era_en, lang) or era_en
        return f"{weekday_ja}、{month_ja} {day_str} 日、{era_ja} {year_str} 年"

    m_short = _DATE_PATTERN_SHORT.match(text)
    if m_short:
        weekday_en = m_short.group(1)
        day_str = m_short.group(2)
        month_en = m_short.group(3).strip()
        weekday_ja = _CALENDAR_WEEKDAYS.get(weekday_en, {}).get(lang, weekday_en)
        month_ja = _CALENDAR_MONTHS.get(month_en, {}).get(lang, month_en)
        return f"{weekday_ja}、{month_ja} {day_str} 日"

    return value


def _translate_static_place(value: str, lang: str) -> str:
    if lang == "en":
        return value
    name = (value or "").strip()
    if not name:
        return value
    try:
        from location_lookup import lookup as _loc_lookup
        loc = _loc_lookup(name)
        if loc:
            return loc
    except Exception:  # noqa: BLE001
        pass
    _load_ph()
    cn = _PH_VALUES.get(("cn", name), {}).get(lang)
    if cn:
        return cn
    return value


def _translate_nt(value: str, lang: str) -> str:
    if lang == "en":
        return value
    from dynamic_place_lookup import lookup as _place_lookup
    translated = _place_lookup(value)
    return translated if translated else value


_DS_TAVERN_QUEST_PATTERN = re.compile(
    r"^(.+?)\s+called\s+(.+?)\s+of\s+(.+)$")

def _translate_ds(value: str, lang: str) -> str:
    if lang == "en":
        return value

    m = _DS_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        trait_en, occupation_en, title_en, name_en = (
            m.group(1), m.group(2), m.group(3), m.group(4))
        _load_traits()
        trait_ja = (
            _TRAIT_VALUES.get(trait_en)
            or i18n.text_opt(f"npc_traits.trait_{_ph_slug(trait_en)}.0")
            or trait_en)
        occupation_ja = translate_placeholder("oc", occupation_en, lang) or occupation_en
        title_ja = translate_placeholder("t", title_en, lang) or title_en
        name_ja = translate_generated_name(name_en, lang)
        return f"{trait_ja}{occupation_ja}の{title_ja}・{name_ja}"

    m = _DS_TAVERN_QUEST_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        descriptor_en = m.group(1).strip()
        named_en = m.group(2).strip()
        locale_en = m.group(3).strip()
        _load_traits()
        descriptor_ja = (
            i18n.value("descriptors", descriptor_en.lower()) or descriptor_en)

        named_ja = named_en
        parts = named_en.split(None, 1)
        if len(parts) == 2:
            maybe_trait, maybe_name = parts
            trait_ja_local = _TRAIT_VALUES.get(maybe_trait)
            if trait_ja_local:
                name_ja_local = translate_generated_name(maybe_name, lang)
                named_ja = f"{trait_ja_local}{name_ja_local}"
        if named_ja == named_en:
            translated_name = translate_generated_name(named_en, lang)
            if translated_name and translated_name != named_en:
                named_ja = translated_name

        locale_ja = locale_en
        _load_ph()
        for _ph_name in ("cn", "lp", "ct"):
            _result = _PH_VALUES.get((_ph_name, locale_en), {}).get(lang)
            if _result:
                locale_ja = _result
                break
        if locale_ja == locale_en:
            try:
                from dynamic_place_lookup import lookup as _place_lookup
                place_result = _place_lookup(locale_en)
                if place_result:
                    locale_ja = place_result
            except Exception:  # noqa: BLE001
                pass

        return f"{locale_ja} の {named_ja} という {descriptor_ja}"

    return value


def translate_placeholder(name: str, value: str, lang: str = "ja") -> str:
    if not value:
        return value
    value = _preprocess_placeholder_value(name, value, lang)
    if name in _PV_VALUE_SUBGROUPS or name in ("g", "g2", "g3"):
        import i18n_helper as i18n
        if i18n.v2_public_enabled("placeholder_values"):
            section = f"%{name}" if name in ("g", "g2", "g3") else None
            v2 = i18n.value_by_surface("placeholder_values", value,
                                       section=section, lang=lang)
            if v2 is not None:
                return v2
    if name in ("n", "fn", "rf"):
        if lang != "en":
            return translate_generated_name(value, lang)
        return value
    if name == "doc":
        _load()
        normalized = " ".join(value.split())
        doc_entry = _DOC_VALUES.get(normalized)
        if doc_entry is not None:
            resolved = _resolve_npcd_ref(doc_entry["ref"])
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
                        result = result.replace(f"%{ph_name}", translated_val)
                return result
        return value
    if name in ("ra", "t", "oc", "ct", "oth", "di", "lp", "cn", "tem"):
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        if name in _PH_DIRECT_ID_NAMES:
            direct = _ph_direct_id(name, value)
            if direct is not None:
                return direct
        if name == "oth":
            import i18n_helper as i18n
            nd = i18n.value("npc_dialog", value)
            if nd is not None:
                return nd
        if name == "oc":
            return _CLASS_VALUES.get(value, value)
        return value
    if name in ("cp", "cll", "ccs", "rcn"):
        return _translate_static_place(value, lang)
    if name == "nt":
        return _translate_nt(value, lang)
    if name == "ds":
        return _translate_ds(value, lang)
    if name in ("a", "a2"):
        return value
    if name == "da":
        if lang == "en":
            return value
        return _translate_date(value, lang)
    if name == "omq":
        return value
    if name == "r":
        import i18n_helper as i18n
        return i18n.value_in("relations", value.lower(), lang) or value
    if name in ("g", "g2", "g3"):
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        direct = _ph_direct_id(name, value)
        if direct is not None:
            return direct
        import i18n_helper as i18n
        return i18n.value_in("pronouns", value.lower(), lang) or value
    if name in ("fq", "ne"):
        if lang != "en":
            return translate_generated_name(value, lang)
        return value
    if name == "o":
        return value
    if name == "tl":
        if lang != "en":
            from dynamic_place_lookup import lookup as _place_lookup
            translated = _place_lookup(value)
            return translated if translated else value
        return value
    if name == "nd":
        if lang == "en":
            return value
        _load_drinks()
        return _DRINKS_VALUES.get(value, value)
    if name == "nr":
        if lang == "en":
            return value
        _load_rooms()
        return _ROOMS_VALUES.get(value, value)
    if name == "ni":
        if lang == "en":
            return value
        _load_items_flat()
        translated = _ITEMS_FLAT.get(value)
        if translated:
            return translated
        try:
            from equipment_shop_list_reader import translate_equipment_shop_name
            translated = translate_equipment_shop_name(value)
            return translated if translated else value
        except Exception:  # noqa: BLE001
            return value
    if name == "nk":
        if lang == "en":
            return value
        _load_key_materials()
        return _KEY_MATERIALS.get(value, value)
    if name == "nc2":
        return value
    return value


_ARRIVAL_RE = re.compile(
    r"^You have arrived in (?P<loc>.+?) in (?P<prov>.+?) Province\.\s*"
    r"The date is (?P<date>.+?)\s+It took (?P<days>\d+) days? to reach your goal\.\s*"
    r"(?P<flavor>.*)$",
    re.DOTALL)
_SETTLEMENT_RE = re.compile(
    r"^The (?P<type>Village|Town|City-State|City) of (?P<name>.+)$")
def _translate_settlement_location(loc: str, lang: str) -> str:
    if lang == "en":
        return loc
    import i18n_helper as i18n
    m = _SETTLEMENT_RE.match(loc.strip())
    if not m:
        return _translate_static_place(loc.strip(), lang)
    type_ja = i18n.value_in("settlement_types", m.group("type"), lang) or m.group("type")
    name_ja = _translate_static_place(m.group("name").strip(), lang)
    return f"{type_ja}「{name_ja}」"


def _translate_arrival(text: str, lang: str = "ja") -> str | None:
    if lang == "en":
        return None
    m = _ARRIVAL_RE.match(text)
    if not m:
        return None
    loc_ja = _translate_settlement_location(m.group("loc"), lang)
    prov_ja = _translate_static_place(m.group("prov"), lang)
    date_ja = _translate_date(m.group("date"), lang)
    days = m.group("days")
    flavor_ja = ""
    flavor = (m.group("flavor") or "").strip()
    if flavor:
        r = lookup(flavor)
        flavor_ja = format_japanese(r[0], r[1], lang) if r is not None else flavor
    result = (f"{prov_ja}地方の{loc_ja}に到着した。"
              f"日付は{date_ja}。目的地まで{days}日かかった。")
    if flavor_ja:
        result += " " + flavor_ja
    return result


def lookup(text: str) -> tuple[str, dict] | None:
    if not text:
        return None
    text = " ".join(text.split())
    _load()

    arrival = _translate_arrival(text, "ja")
    if arrival is not None:
        return (arrival, {})

    for compiled, ja, ph_count, is_exact, _literal_len in _COMPILED:
        m = compiled.match(text)
        if m:
            placeholders = m.groupdict()
            return (ja, placeholders)
    return None


def format_japanese(ja_template: str, placeholders: dict, lang: str = "ja") -> str:
    result = ja_template
    for name, value in sorted(
            placeholders.items(), key=lambda item: len(item[0]),
            reverse=True):
        if value:
            translated = translate_placeholder(name, value, lang)
            result = result.replace(f"%{name}", translated)
    from text_corrector import apply_text_corrections
    result = apply_text_corrections(result, lang)
    return result


if __name__ == "__main__":
    samples = [
        "Greetings, I am John, a Mage. I cast spells for a living.",
        "They call me Maria the Warrior. I fight for a living.",
        "I am called Tom, the Daggerfall Bard. You know, I play music for a living.",
        "Good day, sir. My name is Alice the skilled Healer. I heal the sick for a living.",
        "The boys call me Lily. I'm a whore.",
        "How would like to recover something for a friend of mine, a highly aggressive aristocrat called Lord Barbyrrya? You can find this person at the Blue Giants, you know the inn southwest of here? I'm sure you'll be paid nicely.",
    ]
    for s in samples:
        result = lookup(s)
        if result:
            ja_template, ph = result
            output = format_japanese(ja_template, ph)
            print(f"EN: {s}")
            print(f"PH: {ph}")
            print(f"JA: {output}")
        else:
            print(f"EN: {s}")
            print(f"JA: <no match>")
        print()
