"""city_data.py — A.EXE / CITYDATA.65 抽出済データの読込モジュール。

- city_generation.json: A.EXE の [CityGeneration] セクション
  (CoastalCityList / CityTemplateFilenames / StartingPositions / ReservedBlockLists)
- world_map.json: CITYDATA.65 の 9 province × 48 location

extract_city_data.py / extract_world_data.py で生成された JSON を読み、
各テーブルへのアクセサを提供する。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Optional


def _resolve_data_dir() -> str:
    module_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(
            getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable))),
            "services", "data",
        ))
    candidates.append(os.path.join(module_dir, "data"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return candidates[0]


_DATA_DIR  = _resolve_data_dir()
_DATA_FILE = os.path.join(_DATA_DIR, "city_generation.json")
_WORLD_FILE = os.path.join(_DATA_DIR, "world_map.json")


@dataclass(frozen=True)
class CityGenerationData:
    """A.EXE から抽出された city generation 用テーブル。"""
    coastal_city_list:      list[int]
    city_template_filenames: list[str]
    starting_positions:     list[tuple[int, int]]
    reserved_block_lists:   list[list[int]]

    def is_coastal(self, global_city_id: int) -> bool:
        """global_city_id (= (provinceID << 5) + localCityID) が海岸都市か?"""
        return global_city_id in self.coastal_city_list

    def get_starting_position(self, index: int) -> Optional[tuple[int, int]]:
        if 0 <= index < len(self.starting_positions):
            return self.starting_positions[index]
        return None

    def get_reserved_block_list(self, index: int) -> Optional[list[int]]:
        if 0 <= index < len(self.reserved_block_lists):
            return self.reserved_block_lists[index]
        return None

    def get_template_filename(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.city_template_filenames):
            return self.city_template_filenames[index]
        return None


_cached: Optional[CityGenerationData] = None


def _read_city_generation_raw() -> Optional[dict]:
    """city_generation を provider 経由で読む: ローカルパック優先 → bundled disk fallback。"""
    txt = _read_pack_text("services/data/city_generation.json")
    if txt:
        try:
            return json.loads(txt)
        except ValueError:
            pass
    if os.path.isfile(_DATA_FILE):
        with open(_DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def reset_city_generation_cache() -> None:
    """city_generation キャッシュを破棄する（pack 切替/テスト用）。"""
    global _cached
    _cached = None


def load_city_generation_data(path: Optional[str] = None) -> CityGenerationData:
    """CityGenerationData を構築する (キャッシュ)。

    path 明示時はそのファイル（後方互換）。未指定は provider 経由
    （ローカルパック → bundled disk fallback）。
    """
    global _cached
    if _cached is not None:
        return _cached
    if path is not None:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = _read_city_generation_raw()
        if raw is None:
            raise FileNotFoundError(
                "city_generation data unavailable (pack/bundled both absent)")
    d = raw["data"]
    _cached = CityGenerationData(
        coastal_city_list       = list(d["coastal_city_list"]),
        city_template_filenames = list(d["city_template_filenames"]),
        starting_positions      = [tuple(p) for p in d["starting_positions"]],
        reserved_block_lists    = [list(arr) for arr in d["reserved_block_lists"]],
    )
    return _cached


def is_data_available() -> bool:
    """city_generation が provider（ローカルパック）または bundled disk から得られるか。"""
    if os.path.isfile(_DATA_FILE):
        return True
    return _read_pack_text("services/data/city_generation.json") is not None


# ══════════════════════════════════════════════════════════════
# World map (CITYDATA.65) 読込
# ══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LocationData:
    """1 location (city / town / village / dungeon)。"""
    name:       str
    x:          int       # province local 座標
    y:          int
    visibility: int

    def city_seed(self) -> int:
        """citySeed = (local.x << 16) | local.y"""
        return ((self.x & 0xFFFF) << 16) | (self.y & 0xFFFF)


@dataclass(frozen=True)
class ProvinceData:
    name:           str
    global_x:       int
    global_y:       int
    global_w:       int
    global_h:       int
    city_states:    list[LocationData]   # 8 件
    towns:          list[LocationData]   # 8 件
    villages:       list[LocationData]   # 16 件
    second_dungeon: LocationData
    first_dungeon:  LocationData
    random_dungeons: list[LocationData]  # 14 件

    def get_location(self, location_id: int) -> Optional[LocationData]:
        """locationID (0-47) → LocationData。
            0-7  = cityStates
            8-15 = towns
           16-31 = villages
           32+   = dungeons (32 = secondDungeon, 33 = firstDungeon, 34-47 = random)
        """
        if 0 <= location_id < 8:
            return self.city_states[location_id]
        if 8 <= location_id < 16:
            return self.towns[location_id - 8]
        if 16 <= location_id < 32:
            return self.villages[location_id - 16]
        if location_id == 32:
            return self.second_dungeon
        if location_id == 33:
            return self.first_dungeon
        if 34 <= location_id < 48:
            return self.random_dungeons[location_id - 34]
        return None


@dataclass(frozen=True)
class WorldMapData:
    provinces: list[ProvinceData]   # 9 件

    def find_location_by_name(self, name: str
                              ) -> Optional[tuple[int, int, LocationData]]:
        """全 province 横断で name 一致する location を探す。
        Returns:
            (province_id, location_id, location) または None
        """
        for pid, prov in enumerate(self.provinces):
            for lid in range(48):
                loc = prov.get_location(lid)
                if loc is not None and loc.name == name:
                    return (pid, lid, loc)
        return None


_world_cached: Optional[WorldMapData] = None


def _read_pack_text(name: str) -> Optional[str]:
    """翻訳外 Arena 生成資産を v2 localpack の `generated_assets/<basename>` から読む（無ければ None）。

    Read generated Arena assets only from the v2 localpack (`RTESArenaAssist.localpack`),
    which is the single Arena-derived provider for the public build.
    未ロード/未収録は None（呼び側が bundled disk(dev) へ fallback、それも無ければ degraded）。
    """
    try:
        import i18n_helper as i18n
        data = i18n.v2_generated_asset(os.path.basename(name))
    except Exception:  # noqa: BLE001
        return None
    return data.decode("utf-8") if data is not None else None


def _read_world_map_raw() -> Optional[dict]:
    """world_map を読む: v2 localpack の generated_assets 優先 → bundled disk（dev）fallback。"""
    txt = _read_pack_text("services/data/world_map.json")
    if txt:
        try:
            return json.loads(txt)
        except ValueError:
            pass
    if os.path.isfile(_WORLD_FILE):
        with open(_WORLD_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def reset_world_map_cache() -> None:
    """world_map キャッシュを破棄する（pack 切替/テスト用）。"""
    global _world_cached
    _world_cached = None


def load_world_map_data(path: Optional[str] = None) -> WorldMapData:
    """WorldMapData を構築する (キャッシュ)。

    path 明示時はそのファイルを読む（後方互換）。未指定は provider 経由
    （ローカルパック → bundled disk fallback）。
    """
    global _world_cached
    if _world_cached is not None:
        return _world_cached
    if path is not None:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = _read_world_map_raw()
        if raw is None:
            raise FileNotFoundError(
                "world_map data unavailable (pack/bundled both absent)")

    def _loc(d: dict) -> LocationData:
        return LocationData(name=d["name"], x=d["x"], y=d["y"],
                            visibility=d["visibility"])

    provinces = []
    for p in raw["provinces"]:
        provinces.append(ProvinceData(
            name           = p["name"],
            global_x       = p["globalX"],
            global_y       = p["globalY"],
            global_w       = p["globalW"],
            global_h       = p["globalH"],
            city_states    = [_loc(c) for c in p["cityStates"]],
            towns          = [_loc(t) for t in p["towns"]],
            villages       = [_loc(v) for v in p["villages"]],
            second_dungeon = _loc(p["secondDungeon"]),
            first_dungeon  = _loc(p["firstDungeon"]),
            random_dungeons = [_loc(d) for d in p["randomDungeons"]],
        ))
    _world_cached = WorldMapData(provinces=provinces)
    return _world_cached


def is_world_map_available() -> bool:
    """world_map が provider（ローカルパック）または bundled disk から得られるか。"""
    if os.path.isfile(_WORLD_FILE):
        return True
    return _read_pack_text("services/data/world_map.json") is not None
