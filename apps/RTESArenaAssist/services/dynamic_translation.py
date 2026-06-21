"""dynamic_translation.py — Assist `dynamic_places.json` を流用した名称組立・翻訳。

分解合成翻訳スキーマ (form_decomposed v2) を読み、prefix/suffix
インデックスから英固有名と日本語訳を組み立てる。Assist 辞書がマスタで、
不足は Assist 側 dynamic_places.json に追加する。
"""
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
    """1 施設の原文 + 翻訳。"""
    en:           str          # 例: "Green Griffin" / "Order of the Red Rose"
    ja:           Optional[str]  # 例: "緑のグリフォン亭" — 翻訳できなければ None
    parts_missing: list[str]   # 翻訳できなかった部品 (例: ["Griffin"] など)


_data_cache: Optional[dict] = None
_aexe_city_gen_cache: Optional[dict] = None
_missing_parts: set[str] = set()


def _load() -> dict:
    """地名合成規則を i18n/<lang>/_rules.json の dynamic_places から得る（言語別規則）。"""
    global _data_cache
    if _data_cache is not None:
        return _data_cache
    if _ASSIST_DIR not in sys.path:
        sys.path.insert(0, _ASSIST_DIR)
    import i18n_helper as i18n
    _data_cache = i18n.rules().get("dynamic_places", {})
    return _data_cache


def _read_public_city_generation() -> Optional[dict]:
    """公開 v2 localpack の city_generation 生成資産（data）を読む（無ければ None）。

    公開版は aexe_strings.json を同梱しないため、建物名パーツ（prefix/suffix）は
    ユーザー環境で採取して localpack へ収録した city_generation.json から読む。
    """
    try:
        if _ASSIST_DIR not in sys.path:
            sys.path.insert(0, _ASSIST_DIR)
        import i18n_helper as i18n
        blob = i18n.v2_generated_asset("city_generation.json")
        if blob is None:
            return None
        data = json.loads(blob.decode("utf-8")).get("data")
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - 読込失敗は名称解決のみ諦める（地図描画は継続）
        return None


def _load_aexe_city_generation() -> dict:
    """建物名パーツ（tavern/temple/equipment の prefix/suffix）を得る。

    dev は aexe_strings.json（正本・Arena 原文含む）から、公開版はそれが非同梱のため
    v2 localpack の city_generation.json（生成資産・名称パーツ収録）から読む。どちらも
    得られなければ空 dict を返す（= 名称は未解決でも、施設検出・mif_name 解決・地図描画は
    巻き込まれずに継続させる＝表示と名称の分離）。
    """
    global _aexe_city_gen_cache
    if _aexe_city_gen_cache is not None:
        return _aexe_city_gen_cache
    out: dict = {}
    # dev: aexe_strings.json（正本）。公開版は非同梱で FileNotFoundError → 公開経路へ。
    try:
        with open(_AEXE_STRINGS_PATH, encoding="utf-8") as f:
            out = json.load(f).get("city_generation", {}) or {}
    except (OSError, ValueError):
        out = {}
    # 公開: localpack の city_generation 生成資産（名称パーツ収録）。
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
    """配列 [{en, value}, ...] から index 番目の (en, 現在言語訳) を取り出す。"""
    if not (0 <= index < len(arr)):
        return ("", None)
    entry = arr[index]
    return (entry.get("en", ""), entry.get("value"))


def translate_tavern(t: TavernName) -> BuildingTranslation:
    """Tavern 名を組み立て + 翻訳。"""
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
    """Temple 名を組み立て + 翻訳。model ごとに prefix と suffix セットが異なる。"""
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


# city type キー → 英表示ラベル (実機表示に合わせ小文字)。
_CITY_TYPE_EN = {
    "city_state": "city",
    "town":       "town",
    "village":    "village",
}

# city type キー → city_types カテゴリの構造 app_id (direct-id・公開版安全)。
# city_types は Assist 所有の構造ラベル 3 件 (city/town/village = OTA の
# localCityID 範囲→CityState/Town/Village 構造) で id は index 固定。
# en 逆引きではなく id 直引き (`i18n.text_opt`) で訳を解決する。id↔en の対応は
# tests/test_dynamic_translation_city_type の guard が ui.json 同様に固定する。
_CITY_TYPE_ID = {
    "city_state": "city_types.0.0",
    "town":       "city_types.1.0",
    "village":    "city_types.2.0",
}


def translate_equipment(e: EquipmentName,
                        city_type: Optional[str] = None
                        ) -> BuildingTranslation:
    """Equipment 名を組み立て + 翻訳。

    %ct (city type) は city_type から置換。
    %ef / %n は EquipmentName に座標由来の NPC 名が入っていれば置換する。
    """
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

    # Assist の分解翻訳は %ct を大文字の場所種別として受け取るため、
    # 表示英名は Arena 実機に合わせて小文字のまま、翻訳だけ正規化して照合する。
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
    """Mages Guild は固定名 1 件。"""
    data = _load().get("mages_guild", {})
    en = data.get("static_name_en", "Mages Guild")
    ja = data.get("static_name_value")
    return BuildingTranslation(en=en, ja=ja, parts_missing=([] if ja else [en]))


def get_missing_parts() -> list[str]:
    """Assist 辞書 dynamic_places.json で翻訳できなかった部品の一覧。"""
    return sorted(_missing_parts)


def clear_missing_parts() -> None:
    _missing_parts.clear()
