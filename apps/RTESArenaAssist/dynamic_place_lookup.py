
from __future__ import annotations

import logging
import re

_log = logging.getLogger(__name__)

_DATA: dict = {}
_LOC_TYPES: dict[str, str] = {}
_LOADED = False


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    try:
        import i18n_helper as i18n
        _DATA.update(i18n.rules().get("dynamic_places", {}))
        for id_, e in i18n.originals("location_types").items():
            en = e.get("original", "") if isinstance(e, dict) else ""
            if en:
                _LOC_TYPES[en] = i18n.lang_only(id_) or ""
    except Exception as exc:
        _log.warning("dynamic_places/location_types load failed: %s", exc)
    _LOADED = True


def _translate_name_part(name: str) -> str:
    try:
        from npc_name_translator import translate_generated_name
        result = translate_generated_name(name)
        return result if result else name
    except Exception:
        return name


def _translate_ct(ct_en: str) -> str:
    _load()
    return _LOC_TYPES.get(ct_en, ct_en)



def _lookup_tavern(en_text: str) -> str:
    data = _DATA.get("tavern", {})
    rule = data.get("combination_rule", "{prefix}{suffix}亭")
    prefixes = data.get("prefixes", [])
    suffixes = data.get("suffixes", [])
    marine_sfxs = data.get("marine_suffixes", [])

    sorted_prefixes = sorted(prefixes, key=lambda p: len(p["en"]), reverse=True)

    matched_prefix_ja = None
    remainder = None
    for p in sorted_prefixes:
        pref_en = p["en"] + " "
        if en_text.startswith(pref_en):
            matched_prefix_ja = p["value"]
            remainder = en_text[len(pref_en):]
            break

    if matched_prefix_ja is None:
        _log.debug("dynamic_place_unmatched: category=tavern en=%r (no prefix)", en_text)
        return ""

    for s in suffixes:
        if remainder == s["en"]:
            return rule.format(prefix=matched_prefix_ja, suffix=s["value"])

    for s in marine_sfxs:
        if remainder == s["en"]:
            return rule.format(prefix=matched_prefix_ja, suffix=s["value"])

    _log.debug("dynamic_place_unmatched: category=tavern en=%r (no suffix)", en_text)
    return matched_prefix_ja


def _lookup_temple(en_text: str) -> str:
    models = _DATA.get("temple", {}).get("models", [])
    for model in models:
        prefix_en = model.get("prefix_en", "")
        if en_text.startswith(prefix_en):
            remainder = en_text[len(prefix_en):]
            rule = model.get("combination_rule", "{suffix}")
            for s in model.get("suffixes", []):
                if remainder == s["en"]:
                    return rule.format(suffix=s["value"])
            _log.debug("dynamic_place_unmatched: category=temple en=%r (no suffix)", en_text)
            return ""
    _log.debug("dynamic_place_unmatched: category=temple en=%r (no prefix)", en_text)
    return ""


def _build_eq_prefix_regex(prefix_en: str) -> tuple[re.Pattern, list[str]]:
    variables: list[str] = []
    parts = re.split(r"(%ef|%n|%ct)", prefix_en)
    regex_parts: list[str] = []
    for part in parts:
        if part == "%ef":
            regex_parts.append("(.+?)")
            variables.append("ef")
        elif part == "%n":
            regex_parts.append("(.+?)")
            variables.append("n")
        elif part == "%ct":
            regex_parts.append("(City-State|Town|Village|Dungeon)")
            variables.append("ct")
        else:
            regex_parts.append(re.escape(part))
    pattern = re.compile("^" + "".join(regex_parts) + r"\s(.+)$")
    return pattern, variables


def _lookup_equipment_store(en_text: str) -> str:
    data = _DATA.get("equipment_store", {})
    rule = data.get("combination_rule", "{prefix}{suffix}")
    prefixes = data.get("prefixes", [])
    suffixes = data.get("suffixes", [])

    sorted_sfx = sorted(suffixes, key=lambda s: len(s["en"]), reverse=True)

    def _find_suffix(tail: str) -> str | None:
        for s in sorted_sfx:
            if tail == s["en"]:
                return s["value"]
        return None

    literal_prefixes = [p for p in prefixes if not p.get("variables")]
    variable_prefixes = [p for p in prefixes if p.get("variables")]

    sorted_lit = sorted(literal_prefixes, key=lambda p: len(p["en"]), reverse=True)
    for p in sorted_lit:
        if en_text.startswith(p["en"] + " "):
            tail = en_text[len(p["en"]) + 1:]
            sja = _find_suffix(tail)
            if sja is not None:
                return rule.format(prefix=p["value"], suffix=sja)
        elif en_text == p["en"]:
            pass

    sorted_var = sorted(variable_prefixes, key=lambda p: len(p["en"]), reverse=True)
    for p in sorted_var:
        pat, var_names = _build_eq_prefix_regex(p["en"])
        m = pat.match(en_text)
        if m:
            groups = m.groups()
            tail = groups[-1]
            sja = _find_suffix(tail)
            if sja is None:
                continue
            prefix_ja_template = p["value"]
            var_values = dict(zip(var_names, groups[:-1]))
            ef_val = var_values.get("ef", "")
            n_val = var_values.get("n", "")
            ct_val = var_values.get("ct", "")
            prefix_ja = prefix_ja_template
            if ef_val:
                prefix_ja = prefix_ja.replace("{ef}", _translate_name_part(ef_val))
            if n_val:
                prefix_ja = prefix_ja.replace("{n}", _translate_name_part(n_val))
            if ct_val:
                prefix_ja = prefix_ja.replace("{ct}", _translate_ct(ct_val))
            return rule.format(prefix=prefix_ja, suffix=sja)

    _log.debug("dynamic_place_unmatched: category=equipment_store en=%r", en_text)
    return ""


def _lookup_mages_guild(en_text: str) -> str:
    mg = _DATA.get("mages_guild", {})
    if en_text == mg.get("static_name_en", ""):
        return mg.get("static_name_value", "")
    _log.debug("dynamic_place_unmatched: category=mages_guild en=%r", en_text)
    return ""



_EQ_SUFFIX_SET: set[str] | None = None


def _get_eq_suffix_set() -> set[str]:
    global _EQ_SUFFIX_SET
    if _EQ_SUFFIX_SET is None:
        _load()
        _EQ_SUFFIX_SET = {
            s["en"] for s in _DATA.get("equipment_store", {}).get("suffixes", [])
        }
    return _EQ_SUFFIX_SET


def detect_category(en_text: str) -> str | None:
    _load()
    text = (en_text or "").strip()
    if not text:
        return None

    mg = _DATA.get("mages_guild", {})
    if text == mg.get("static_name_en", ""):
        return "mages_guild"

    for model in _DATA.get("temple", {}).get("models", []):
        if text.startswith(model.get("prefix_en", "")):
            return "temple"

    eq_sfx = _get_eq_suffix_set()
    for sfx in eq_sfx:
        if text.endswith(" " + sfx) or text == sfx:
            return "equipment_store"

    return "tavern"



def lookup(en_text: str, category: str | None = None) -> str:
    _load()
    text = (en_text or "").strip()
    if not text:
        return ""

    cat = category or detect_category(text)

    if cat == "tavern":
        return _lookup_tavern(text)
    if cat == "temple":
        return _lookup_temple(text)
    if cat == "equipment_store":
        return _lookup_equipment_store(text)
    if cat == "mages_guild":
        return _lookup_mages_guild(text)

    _log.debug("dynamic_place_unmatched: category=%r en=%r (unknown category)", cat, text)
    return ""
