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
    coastal_city_list:      list[int]
    city_template_filenames: list[str]
    starting_positions:     list[tuple[int, int]]
    reserved_block_lists:   list[list[int]]

    def is_coastal(self, global_city_id: int) -> bool:
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
    global _cached
    _cached = None


def load_city_generation_data(path: Optional[str] = None) -> CityGenerationData:
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
    if os.path.isfile(_DATA_FILE):
        return True
    return _read_pack_text("services/data/city_generation.json") is not None



@dataclass(frozen=True)
class LocationData:
    name:       str
    x:          int
    y:          int
    visibility: int

    def city_seed(self) -> int:
        return ((self.x & 0xFFFF) << 16) | (self.y & 0xFFFF)


@dataclass(frozen=True)
class ProvinceData:
    name:           str
    global_x:       int
    global_y:       int
    global_w:       int
    global_h:       int
    city_states:    list[LocationData]
    towns:          list[LocationData]
    villages:       list[LocationData]
    second_dungeon: LocationData
    first_dungeon:  LocationData
    random_dungeons: list[LocationData]

    def get_location(self, location_id: int) -> Optional[LocationData]:
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
    provinces: list[ProvinceData]

    def find_location_by_name(self, name: str
                              ) -> Optional[tuple[int, int, LocationData]]:
        for pid, prov in enumerate(self.provinces):
            for lid in range(48):
                loc = prov.get_location(lid)
                if loc is not None and loc.name == name:
                    return (pid, lid, loc)
        return None


_world_cached: Optional[WorldMapData] = None


def _read_pack_text(name: str) -> Optional[str]:
    try:
        import i18n_helper as i18n
        data = i18n.v2_generated_asset(os.path.basename(name))
    except Exception:  # noqa: BLE001
        return None
    return data.decode("utf-8") if data is not None else None


def _read_world_map_raw() -> Optional[dict]:
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
    global _world_cached
    _world_cached = None


def load_world_map_data(path: Optional[str] = None) -> WorldMapData:
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
    if os.path.isfile(_WORLD_FILE):
        return True
    return _read_pack_text("services/data/world_map.json") is not None
