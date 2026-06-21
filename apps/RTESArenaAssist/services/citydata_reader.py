"""services/citydata_reader.py — CITYDATA.NN（都市データ）の決定論パーサ。

翻訳外 Arena 由来資産再構築の一部。
`services/data/world_map.json` は Arena の `CITYDATA.65`（個別ファイル・新規キャラ用テンプレート）
由来であり、公開物に同梱できない。本モジュールはユーザー環境の CITYDATA.NN を読み、
world_map.json と同一構造へ正規化する（→ ローカルデータパック生成 / location 名の出典）。

バイナリ構造（OpenTESArena `CityDataFile` 準拠・`Assets/CityDataFile.h/.cpp`）:
  - 9 province × 1228 byte。
  - province 先頭: name[20]（null 終端）＋ globalX/Y/W/H（各 uint16 LE）＝28 byte。
  - 続いて 48 location × 25 byte: cityStates[8] / towns[8] / villages[16] /
    secondDungeon(1) / firstDungeon(1) / randomDungeons[14]。
  - location: name[20]（null 終端）＋ x(uint16 LE) ＋ y(uint16 LE) ＋ visibility(uint8)。

出典ID（`citydata:*`）:
  - province 名: ``citydata:<province_index>:name``
  - location 名: ``citydata:<province_index>:<location_id>``（location_id は OTA getLocationData 順）
"""
from __future__ import annotations

import struct
from typing import Any

PROVINCE_COUNT = 9
PROVINCE_DATA_SIZE = 1228
_NAME_SIZE = 20
_LOCATION_SIZE = 25
# 各 province のロケーション内訳（OTA ArenaProvinceData の宣言順）。
_CITY_STATES = 8
_TOWNS = 8
_VILLAGES = 16
_RANDOM_DUNGEONS = 14


def _read_name(raw: bytes, off: int) -> str:
    """off から最大 20 byte の null 終端名を読む（Arena 名は 8bit・latin-1 で復号）。"""
    field = raw[off:off + _NAME_SIZE]
    nul = field.find(b"\x00")
    if nul >= 0:
        field = field[:nul]
    return field.decode("latin-1")


def _read_location(raw: bytes, off: int) -> tuple[dict[str, Any], int]:
    """1 ロケーション（25 byte）を読み (dict, 次 offset) を返す。"""
    name = _read_name(raw, off)
    x, y = struct.unpack_from("<HH", raw, off + _NAME_SIZE)
    visibility = raw[off + _NAME_SIZE + 4]
    return {"name": name, "x": x, "y": y, "visibility": visibility}, off + _LOCATION_SIZE


def parse_citydata(raw: bytes) -> dict[str, Any]:
    """CITYDATA.NN の生バイトを world_map.json 同一構造の dict へパースする。

    Returns:
      {"province_count", "province_data_size", "provinces": [...]}。
      provinces[i] = {name, globalX, globalY, globalW, globalH,
                      cityStates[], towns[], villages[],
                      secondDungeon, firstDungeon, randomDungeons[]}。
    """
    if len(raw) < PROVINCE_DATA_SIZE * PROVINCE_COUNT:
        raise ValueError(
            f"CITYDATA too small: {len(raw)} < "
            f"{PROVINCE_DATA_SIZE * PROVINCE_COUNT}")

    provinces: list[dict[str, Any]] = []
    for i in range(PROVINCE_COUNT):
        base = PROVINCE_DATA_SIZE * i
        name = _read_name(raw, base)
        global_x, global_y, global_w, global_h = struct.unpack_from(
            "<HHHH", raw, base + _NAME_SIZE)
        off = base + _NAME_SIZE + 8

        def _block(count: int, off: int) -> tuple[list[dict[str, Any]], int]:
            out: list[dict[str, Any]] = []
            for _ in range(count):
                loc, off = _read_location(raw, off)
                out.append(loc)
            return out, off

        city_states, off = _block(_CITY_STATES, off)
        towns, off = _block(_TOWNS, off)
        villages, off = _block(_VILLAGES, off)
        # ダンジョンは second（杖ダンジョン）が先、続いて first（杖マップ）。
        second_dungeon, off = _read_location(raw, off)
        first_dungeon, off = _read_location(raw, off)
        random_dungeons, off = _block(_RANDOM_DUNGEONS, off)

        provinces.append({
            "name": name,
            "globalX": global_x, "globalY": global_y,
            "globalW": global_w, "globalH": global_h,
            "cityStates": city_states,
            "towns": towns,
            "villages": villages,
            "secondDungeon": second_dungeon,
            "firstDungeon": first_dungeon,
            "randomDungeons": random_dungeons,
        })

    return {
        "province_count": PROVINCE_COUNT,
        "province_data_size": PROVINCE_DATA_SIZE,
        "provinces": provinces,
    }


def read_citydata_file(path: str) -> dict[str, Any]:
    """CITYDATA.NN ファイルを読み parse_citydata した結果を返す。"""
    with open(path, "rb") as f:
        raw = f.read()
    return parse_citydata(raw)


# world_map.json の "source" タグ（既存 dev 生成物と同形）。
WORLD_MAP_SOURCE = "CITYDATA.65 (Arena DOS template)"


def build_world_map(raw: bytes) -> dict[str, Any]:
    """CITYDATA.NN の生バイトを `services/data/world_map.json` 同形の dict へ生成する。

    ローカルデータパック収録 / provider 供給用（公開版で world_map.json を同梱しない）。
    parse_citydata の結果に "source" タグを付けて既存 dev 生成物と同じ最上位構造にする。
    """
    out: dict[str, Any] = {"source": WORLD_MAP_SOURCE}
    out.update(parse_citydata(raw))
    return out


def build_location_originals(raw: bytes) -> dict[str, dict[str, Any]]:
    """CITYDATA.NN から `location` カテゴリの原文エントリ（CITYDATA 由来分）を生成する。

    province 名＋全 location 名（空除く）を `location.<slug>.0` をキーに出典付きで返す
    （slug は `location_lookup._slug` と同一規則・重複名は先勝ち）。

    注意: `location` カテゴリは**混合**で、CITYDATA 由来（280件相当）に加え、建物種別
    （Alchemist/Inn/Mages Guild 等）・方角（North/NE 等）・lore（Emperor/Amulet of Kings 等）・
    'Cyrodiil' など **CITYDATA に無い 59 件は別出典**で本関数は生成しない。

    Returns: ``{app_id: {"original": name, "src": source_id}}``。
    """
    # location_lookup の slug 規則を単一ソースとして使う（drift 防止・lazy import で循環回避）。
    from location_lookup import _slug

    wm = parse_citydata(raw)
    out: dict[str, dict[str, Any]] = {}

    def _add(name: str, source_id: str) -> None:
        if not name:
            return
        app_id = f"location.{_slug(name)}.0"
        if app_id not in out:
            out[app_id] = {"original": name, "src": source_id}

    for pi, p in enumerate(wm["provinces"]):
        _add(p["name"], province_name_source_id(pi))
        location_id = 0
        for grp in ("cityStates", "towns", "villages"):
            for entry in p[grp]:
                _add(entry["name"], location_source_id(pi, location_id))
                location_id += 1
        _add(p["secondDungeon"]["name"], location_source_id(pi, 32))
        _add(p["firstDungeon"]["name"], location_source_id(pi, 33))
        for j, entry in enumerate(p["randomDungeons"]):
            _add(entry["name"], location_source_id(pi, 34 + j))
    return out


# 基準照合表（golden manifest）用の生成器バージョン（CITYDATA 由来カテゴリ共通）。
CITYDATA_MANIFEST_VERSION = "citydata/1"
WORLD_MAP_CATEGORY = "world_map"
LOCATION_CATEGORY = "location"


def _wrap_manifest(category: str, entries: dict[str, str], fingerprint: str) -> dict:
    """source_id→source_hash の entries を基準照合表 dict へ包む（原文なし）。"""
    import i18n_source_address as sa
    return {
        sa.MANIFEST_VERSION: CITYDATA_MANIFEST_VERSION,
        sa.MANIFEST_GENERATOR: f"citydata_reader/{CITYDATA_MANIFEST_VERSION}",
        sa.MANIFEST_FINGERPRINT: fingerprint,
        sa.MANIFEST_DIGEST: sa.manifest_digest(entries),
        "category": category,
        sa.MANIFEST_ENTRIES: entries,
    }


def build_world_map_manifest(raw: bytes, fingerprint: str) -> dict:
    """world_map の基準照合表（出典ID＋照合用ハッシュ・原文なし）。

    province 名＋全 location 名（空除く）を `citydata:*` 出典ID で hash 化する。
    """
    import i18n_source_address as sa
    wm = parse_citydata(raw)
    entries: dict[str, str] = {}
    for pi, p in enumerate(wm["provinces"]):
        if p["name"]:
            entries[province_name_source_id(pi)] = sa.source_hash(p["name"])
        location_id = 0
        for grp in ("cityStates", "towns", "villages"):
            for e in p[grp]:
                if e["name"]:
                    entries[location_source_id(pi, location_id)] = sa.source_hash(e["name"])
                location_id += 1
        if p["secondDungeon"]["name"]:
            entries[location_source_id(pi, 32)] = sa.source_hash(p["secondDungeon"]["name"])
        if p["firstDungeon"]["name"]:
            entries[location_source_id(pi, 33)] = sa.source_hash(p["firstDungeon"]["name"])
        for j, e in enumerate(p["randomDungeons"]):
            if e["name"]:
                entries[location_source_id(pi, 34 + j)] = sa.source_hash(e["name"])
    return _wrap_manifest(WORLD_MAP_CATEGORY, entries, fingerprint)


CITY_GENERATION_CATEGORY = "city_generation"


def build_city_generation_manifest(city_gen_data: dict[str, Any],
                                   fingerprint: str) -> dict:
    """city_generation（構造データ）の基準照合表。

    テキストでなく構造（coastal_city_list 等4フィールド）なので、各フィールドの
    決定論シリアライズ（sort_keys）の hash を出典ID `aexe_citygen:<field>` で持つ。
    """
    import json as _json
    import i18n_source_address as sa
    entries = {
        f"aexe_citygen:{k}": sa.source_hash(
            _json.dumps(v, ensure_ascii=False, sort_keys=True))
        for k, v in city_gen_data.items()
    }
    return _wrap_manifest(CITY_GENERATION_CATEGORY, entries, fingerprint)


def build_location_manifest(location_orig: dict[str, dict[str, Any]],
                            fingerprint: str) -> dict:
    """location（CITYDATA 由来 280件）の基準照合表（原文なし）。

    `build_location_originals` 出力（{app_id:{original,src}}）から
    {src(出典ID): source_hash(original)} を作る。
    """
    import i18n_source_address as sa
    entries = {v["src"]: sa.source_hash(v["original"])
               for v in location_orig.values()}
    return _wrap_manifest(LOCATION_CATEGORY, entries, fingerprint)


def province_name_source_id(province_index: int) -> str:
    """province 名の出典ID。住所定義は i18n_source_address に一元化。"""
    import i18n_source_address as sa
    return sa.citydata_province_name_id(province_index)


def location_source_id(province_index: int, location_id: int) -> str:
    """location 名の出典ID（location_id は OTA getLocationData 順）。

    0..7=cityStates / 8..15=towns / 16..31=villages / 32=secondDungeon /
    33=firstDungeon / 34..47=randomDungeons。住所定義は i18n_source_address に一元化。
    """
    import i18n_source_address as sa
    return sa.citydata_location_id(province_index, location_id)


__all__ = [
    "PROVINCE_COUNT",
    "PROVINCE_DATA_SIZE",
    "parse_citydata",
    "read_citydata_file",
    "build_world_map",
    "WORLD_MAP_SOURCE",
    "build_location_originals",
    "province_name_source_id",
    "location_source_id",
]
