from __future__ import annotations
import struct
from typing import Any
PROVINCE_COUNT = 9
PROVINCE_DATA_SIZE = 1228
_NAME_SIZE = 20
_LOCATION_SIZE = 25
_CITY_STATES = 8
_TOWNS = 8
_VILLAGES = 16
_RANDOM_DUNGEONS = 14

def _read_name(raw: bytes, off: int) -> str:
    field = raw[off:off + _NAME_SIZE]
    nul = field.find(b'\x00')
    if nul >= 0:
        field = field[:nul]
    return field.decode('latin-1')

def _read_location(raw: bytes, off: int) -> tuple[dict[str, Any], int]:
    name = _read_name(raw, off)
    x, y = struct.unpack_from('<HH', raw, off + _NAME_SIZE)
    visibility = raw[off + _NAME_SIZE + 4]
    return ({'name': name, 'x': x, 'y': y, 'visibility': visibility}, off + _LOCATION_SIZE)

def parse_citydata(raw: bytes) -> dict[str, Any]:
    if len(raw) < PROVINCE_DATA_SIZE * PROVINCE_COUNT:
        raise ValueError(f'CITYDATA too small: {len(raw)} < {PROVINCE_DATA_SIZE * PROVINCE_COUNT}')
    provinces: list[dict[str, Any]] = []
    for i in range(PROVINCE_COUNT):
        base = PROVINCE_DATA_SIZE * i
        name = _read_name(raw, base)
        global_x, global_y, global_w, global_h = struct.unpack_from('<HHHH', raw, base + _NAME_SIZE)
        off = base + _NAME_SIZE + 8

        def _block(count: int, off: int) -> tuple[list[dict[str, Any]], int]:
            out: list[dict[str, Any]] = []
            for _ in range(count):
                loc, off = _read_location(raw, off)
                out.append(loc)
            return (out, off)
        city_states, off = _block(_CITY_STATES, off)
        towns, off = _block(_TOWNS, off)
        villages, off = _block(_VILLAGES, off)
        second_dungeon, off = _read_location(raw, off)
        first_dungeon, off = _read_location(raw, off)
        random_dungeons, off = _block(_RANDOM_DUNGEONS, off)
        provinces.append({'name': name, 'globalX': global_x, 'globalY': global_y, 'globalW': global_w, 'globalH': global_h, 'cityStates': city_states, 'towns': towns, 'villages': villages, 'secondDungeon': second_dungeon, 'firstDungeon': first_dungeon, 'randomDungeons': random_dungeons})
    return {'province_count': PROVINCE_COUNT, 'province_data_size': PROVINCE_DATA_SIZE, 'provinces': provinces}

def read_citydata_file(path: str) -> dict[str, Any]:
    with open(path, 'rb') as f:
        raw = f.read()
    return parse_citydata(raw)
WORLD_MAP_SOURCE = 'CITYDATA.65 (Arena DOS template)'

def build_world_map(raw: bytes) -> dict[str, Any]:
    out: dict[str, Any] = {'source': WORLD_MAP_SOURCE}
    out.update(parse_citydata(raw))
    return out

def build_location_originals(raw: bytes) -> dict[str, dict[str, Any]]:
    from location_lookup import _slug
    wm = parse_citydata(raw)
    out: dict[str, dict[str, Any]] = {}

    def _add(name: str, source_id: str) -> None:
        if not name:
            return
        app_id = f'location.{_slug(name)}.0'
        if app_id not in out:
            out[app_id] = {'original': name, 'src': source_id}
    for pi, p in enumerate(wm['provinces']):
        _add(p['name'], province_name_source_id(pi))
        location_id = 0
        for grp in ('cityStates', 'towns', 'villages'):
            for entry in p[grp]:
                _add(entry['name'], location_source_id(pi, location_id))
                location_id += 1
        _add(p['secondDungeon']['name'], location_source_id(pi, 32))
        _add(p['firstDungeon']['name'], location_source_id(pi, 33))
        for j, entry in enumerate(p['randomDungeons']):
            _add(entry['name'], location_source_id(pi, 34 + j))
    return out
CITYDATA_MANIFEST_VERSION = 'citydata/1'
WORLD_MAP_CATEGORY = 'world_map'
LOCATION_CATEGORY = 'location'

def _wrap_manifest(category: str, entries: dict[str, str], fingerprint: str) -> dict:
    import i18n_source_address as sa
    return {sa.MANIFEST_VERSION: CITYDATA_MANIFEST_VERSION, sa.MANIFEST_GENERATOR: f'citydata_reader/{CITYDATA_MANIFEST_VERSION}', sa.MANIFEST_FINGERPRINT: fingerprint, sa.MANIFEST_DIGEST: sa.manifest_digest(entries), 'category': category, sa.MANIFEST_ENTRIES: entries}

def build_world_map_manifest(raw: bytes, fingerprint: str) -> dict:
    import i18n_source_address as sa
    wm = parse_citydata(raw)
    entries: dict[str, str] = {}
    for pi, p in enumerate(wm['provinces']):
        if p['name']:
            entries[province_name_source_id(pi)] = sa.source_hash(p['name'])
        location_id = 0
        for grp in ('cityStates', 'towns', 'villages'):
            for e in p[grp]:
                if e['name']:
                    entries[location_source_id(pi, location_id)] = sa.source_hash(e['name'])
                location_id += 1
        if p['secondDungeon']['name']:
            entries[location_source_id(pi, 32)] = sa.source_hash(p['secondDungeon']['name'])
        if p['firstDungeon']['name']:
            entries[location_source_id(pi, 33)] = sa.source_hash(p['firstDungeon']['name'])
        for j, e in enumerate(p['randomDungeons']):
            if e['name']:
                entries[location_source_id(pi, 34 + j)] = sa.source_hash(e['name'])
    return _wrap_manifest(WORLD_MAP_CATEGORY, entries, fingerprint)
CITY_GENERATION_CATEGORY = 'city_generation'

def build_city_generation_manifest(city_gen_data: dict[str, Any], fingerprint: str) -> dict:
    import json as _json
    import i18n_source_address as sa
    entries = {f'aexe_citygen:{k}': sa.source_hash(_json.dumps(v, ensure_ascii=False, sort_keys=True)) for k, v in city_gen_data.items()}
    return _wrap_manifest(CITY_GENERATION_CATEGORY, entries, fingerprint)

def build_location_manifest(location_orig: dict[str, dict[str, Any]], fingerprint: str) -> dict:
    import i18n_source_address as sa
    entries = {v['src']: sa.source_hash(v['original']) for v in location_orig.values()}
    return _wrap_manifest(LOCATION_CATEGORY, entries, fingerprint)

def province_name_source_id(province_index: int) -> str:
    import i18n_source_address as sa
    return sa.citydata_province_name_id(province_index)

def location_source_id(province_index: int, location_id: int) -> str:
    import i18n_source_address as sa
    return sa.citydata_location_id(province_index, location_id)
__all__ = ['PROVINCE_COUNT', 'PROVINCE_DATA_SIZE', 'parse_citydata', 'read_citydata_file', 'build_world_map', 'WORLD_MAP_SOURCE', 'build_location_originals', 'province_name_source_id', 'location_source_id']
