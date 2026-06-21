from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

from .building_name_generator import TavernName, TempleName, EquipmentName


_AEXE_STRINGS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "aexe_strings.json",
))
_ASSIST_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
))


@dataclass
class BuildingTranslation:
    en:           str
    ja:           Optional[str]
    parts_missing: list[str]


_data_cache: Optional[dict] = None
_aexe_city_gen_cache: Optional[dict] = None
_missing_parts: set[str] = set()


def _load() -> dict:
    global _data_cache
    if _data_cache is not None:
        return _data_cache
    if _ASSIST_DIR not in sys.path:
        sys.path.insert(0, _ASSIST_DIR)
    import i18n_helper as i18n
    _data_cache = i18n.rules().get("dynamic_places", {})
    return _data_cache


def _read_public_city_generation() -> Optional[dict]:
    try:
        if _ASSIST_DIR not in sys.path:
            sys.path.insert(0, _ASSIST_DIR)
        import i18n_helper as i18n
        blob = i18n.v2_generated_asset("city_generation.json")
        if blob is None:
            return None
        data = json.loads(blob.decode("utf-8")).get("data")
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _load_aexe_city_generation() -> dict:
    global _aexe_city_gen_cache
    if _aexe_city_gen_cache is not None:
        return _aexe_city_gen_cache
    out: dict = {}
    try:
        with open(_AEXE_STRINGS_PATH, encoding="utf-8") as f:
            out = json.load(f).get("city_generation", {}) or {}
    except (OSError, ValueError):
        out = {}
    if not out.get("tavern_prefixes"):
        pub = _read_public_city_generation()
        if pub:
            out = pub
    _aexe_city_gen_cache = out
    return _aexe_city_gen_cache


def _aexe_part(key: str, index: int) -> str:
    arr = _load_aexe_city_generation().get(key, [])
    if not (0 <= index < len(arr)):
        return ""
    return arr[index]


def _lookup_place_ja(en: str, category: str) -> Optional[str]:
    try:
        if _ASSIST_DIR not in sys.path:
            sys.path.insert(0, _ASSIST_DIR)
        from dynamic_place_lookup import lookup
        result = lookup(en, category)
        return result or None
    except Exception:
        return None


def _lookup_array_part(arr: list[dict], index: int) -> tuple[str, Optional[str]]:
    if not (0 <= index < len(arr)):
        return ("", None)
    entry = arr[index]
    return (entry.get("en", ""), entry.get("value"))


def translate_tavern(t: TavernName) -> BuildingTranslation:
    data = _load().get("tavern", {})
    pre_en = _aexe_part("tavern_prefixes", t.prefix_index)
    suffix_key = "tavern_marine_suffixes" if t.coastal else "tavern_suffixes"
    suf_en = _aexe_part(suffix_key, t.suffix_index)
    en = f"{pre_en} {suf_en}".strip()
    ja = _lookup_place_ja(en, "tavern")

    missing = []
    if not ja:
        prefixes = data.get("prefixes", [])
        suffixes = (data.get("marine_suffixes") if t.coastal
                    else data.get("suffixes")) or []
        _pre, pre_ja = _lookup_array_part(prefixes, t.prefix_index)
        _suf, suf_ja = _lookup_array_part(suffixes, t.suffix_index)
        missing.append(pre_en)
        missing.append(suf_en)
        if pre_ja and suf_ja:
            combination_rule = data.get("combination_rule", "{prefix}{suffix}亭")
            ja = combination_rule.replace("{prefix}", pre_ja).replace("{suffix}", suf_ja)
            missing = []
        for m in missing:
            if m:
                _missing_parts.add(f"tavern.prefixes/suffixes: {m}")

    return BuildingTranslation(en=en, ja=ja, parts_missing=missing)


def translate_temple(t: TempleName) -> BuildingTranslation:
    data = _load().get("temple", {})
    models = data.get("models", [])
    if not (0 <= t.model < len(models)):
        return BuildingTranslation(en="", ja=None,
                                   parts_missing=[f"temple.model[{t.model}]"])
    model = models[t.model]
    prefix_en = _aexe_part("temple_prefixes", t.model)
    suffix_key = ["temple1_suffixes", "temple2_suffixes", "temple3_suffixes"][t.model]
    suf_en = _aexe_part(suffix_key, t.suffix_index)
    en = f"{prefix_en}{suf_en}"
    ja = _lookup_place_ja(en, "temple")

    missing = []
    if not ja:
        combination_rule = model.get("combination_rule", "{suffix}")
        suffixes = model.get("suffixes", [])
        _suf, suf_ja = _lookup_array_part(suffixes, t.suffix_index)
        missing.append(suf_en)
        _missing_parts.add(
            f"temple.models[{t.model}].suffixes: {suf_en}")
        if suf_ja:
            ja = combination_rule.replace("{suffix}", suf_ja)
            missing = []

    return BuildingTranslation(en=en, ja=ja, parts_missing=missing)


_CITY_TYPE_EN = {
    "city_state": "city",
    "town":       "town",
    "village":    "village",
}

_CITY_TYPE_ID = {
    "city_state": "city_types.0.0",
    "town":       "city_types.1.0",
    "village":    "city_types.2.0",
}


def translate_equipment(e: EquipmentName,
                        city_type: Optional[str] = None
                        ) -> BuildingTranslation:
    data = _load().get("equipment_store", {})
    pre_en = _aexe_part("equipment_prefixes", e.prefix_index)
    suf_en = _aexe_part("equipment_suffixes", e.suffix_index)
    en = f"{pre_en} {suf_en}".strip()

    if _ASSIST_DIR not in sys.path:
        sys.path.insert(0, _ASSIST_DIR)
    import i18n_helper as i18n
    ct_en = _CITY_TYPE_EN.get(city_type or "", "")
    _ct_id = _CITY_TYPE_ID.get(city_type or "", "")
    ct_ja = (i18n.text_opt(_ct_id) if _ct_id else None)
    if "%ct" in en and ct_en:
        en = en.replace("%ct", ct_en)
    if "%ef" in en and e.ef_name:
        en = en.replace("%ef", e.ef_name)
    if "%n" in en and e.n_name:
        en = en.replace("%n", e.n_name)

    lookup_en = en
    if ct_en:
        lookup_en = lookup_en.replace(f"The {ct_en} ", f"The {ct_en.title()} ")
    ja = _lookup_place_ja(lookup_en, "equipment_store")

    missing = []
    if not ja:
        prefixes = data.get("prefixes", [])
        suffixes = data.get("suffixes", [])
        combination_rule = data.get("combination_rule", "{prefix}{suffix}")
        prefix_by_en = {p.get("en", ""): p for p in prefixes}
        suffix_by_en = {s.get("en", ""): s for s in suffixes}
        prefix_entry = prefix_by_en.get(pre_en)
        suffix_entry = suffix_by_en.get(suf_en)
        if prefix_entry is None:
            missing.append(pre_en)
            _missing_parts.add(f"equipment_store.prefixes: {pre_en}")
        if suffix_entry is None:
            missing.append(suf_en)
            _missing_parts.add(f"equipment_store.suffixes: {suf_en}")
        if prefix_entry is not None and suffix_entry is not None:
            prefix_ja = prefix_entry.get("value")
            suffix_ja = suffix_entry.get("value")
            if prefix_ja and e.ef_name:
                prefix_ja = prefix_ja.replace("{ef}", e.ef_name)
            if prefix_ja and e.n_name:
                prefix_ja = prefix_ja.replace("{n}", e.n_name)
            if prefix_ja and ct_ja:
                prefix_ja = prefix_ja.replace("{ct}", ct_ja)
            if prefix_ja and suffix_ja:
                ja = combination_rule.replace("{prefix}", prefix_ja).replace("{suffix}", suffix_ja)
                missing = []

    return BuildingTranslation(en=en, ja=ja, parts_missing=missing)


def translate_mages_guild() -> BuildingTranslation:
    data = _load().get("mages_guild", {})
    en = data.get("static_name_en", "Mages Guild")
    ja = data.get("static_name_value")
    return BuildingTranslation(en=en, ja=ja, parts_missing=([] if ja else [en]))


def get_missing_parts() -> list[str]:
    return sorted(_missing_parts)


def clear_missing_parts() -> None:
    _missing_parts.clear()
