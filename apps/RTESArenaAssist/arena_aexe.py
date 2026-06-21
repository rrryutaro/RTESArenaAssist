from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("RTESArenaAssist")

GENERATOR_VERSION = "arena_aexe/1"


class GenerationCancelled(Exception):
    pass

AEXE_TABLES = {
    "races.singular": (0x3E290, 0x3E594, 8, "array"),
    "races.plural": (0x3E245, 0x3E549, 8, "array"),
    "classes.names": (0x3E15E, 0x3E462, 18, "array"),
    "classes.preferred_attributes": (0x35E34, 0x36034, 18, "array"),
    "calendar.month_names": (0x3E894, 0x3EB98, 12, "array"),
    "calendar.times_of_day": (0x40529, 0x4086D, 7, "array"),
    "calendar.weekday_names": (0x3E92A, 0x3EC2E, 7, "array"),
    "calendar.holiday_names": (0x3E95D, 0x3EC61, 15, "array"),
    "locations.province_names": (0x392F8, 0x394F8, 9, "array"),
    "locations.char_creation_province_names": (0x3E602, 0x3E906, 8, "array"),
    "locations.location_types": (0x3D0C3, 0x3D2F5, 5, "array"),
    "locations.ruler_titles": (0x3EAC7, 0x3EDCB, 14, "array"),
    "locations.start_dungeon_name": (0x402A1, 0x405DB, 1, "single"),
    "entities.attribute_names": (0x40C29, 0x3E500, 8, "array"),
    "entities.creature_names": (0x36BBE, 0x36DBE, 23, "array"),
    "entities.creature_sound_names": (0x3FA9D, 0x3FDD7, 26, "array"),
    "entities.creature_animation_filenames": (0x3E4FB, 0x3E7FF, 24, "array"),
    "entities.final_boss_name": (0x36D03, 0x36F03, 1, "single"),
    "entities.pronoun_names": (0x39CA5, 0x39CA5, 9, "array"),
    "entities.relation_names": (0x370C8, 0x370C8, 20, "array"),
    "menu.ask_about_places": (0x43FD3, 0x43FD3, 9, "array"),
    "menu.travel_places": (0x44035, 0x44035, 9, "array"),
    "entities.person_names": (0x39BBC, 0x39BBC, 8, "array"),
    "status.war_peace": (0x39B0C, 0x39B0C, 2, "array"),
    "entities.title_names": (0x39C01, 0x39C01, 12, "array"),
    "inn.room_types": (0x3E292, 0x3E292, 5, "array"),
    "inn.drinks_common": (0x3DB12, 0x3DB12, 12, "array"),
    "inn.drinks_special": (0x3DB60, 0x3DB60, 9, "array"),
    "entities.directions": (0x39CC6, 0x39CC6, 8, "array"),
    "character.status_effects": (0x36F90, 0x36F90, 7, "array"),
    "character.stat_labels": (0x40F61, 0x40F61, 3, "array"),
    "mages.effect_types": (0x40CC1, 0x40CC1, 25, "array"),
    "mages.effect_sub_cause": (0x40F20, 0x40F20, 4, "array"),
    "mages.damage_types": (0x41017, 0x41017, 5, "array"),
    "mages.attribute_kinds": (0x41052, 0x41052, 2, "array"),
    "mages.resist_types": (0x4106F, 0x4106F, 6, "array"),
    "mages.target_types": (0x41091, 0x41091, 5, "array"),
    "mages.spell_geometry": (0x40F90, 0x40F90, 3, "array"),
    "equipment.material_names": (0x3DD3B, 0x3E03F, 8, "array"),
    "equipment.item_condition_names": (0x4144D, 0x417F1, 8, "array"),
    "equipment.armor_names": (0x3DB20, 0x3DE24, 11, "array"),
    "equipment.plate_armor_names": (0x3DD8A, 0x3E08E, 11, "array"),
    "equipment.chain_armor_names": (0x3DE2C, 0x3E130, 11, "array"),
    "equipment.leather_armor_names": (0x3DECE, 0x3E1D2, 11, "array"),
    "equipment.armor_enchantment_names": (0x3DC49, 0x3DF4D, 14, "array"),
    "equipment.weapon_names": (0x3D900, 0x3DC04, 18, "array"),
    "equipment.weapon_enchantment_names": (0x3DA1B, 0x3DD1F, 14, "array"),
    "equipment.spellcasting_item_names": (0x3D4CD, 0x3D7D1, 4, "array"),
    "equipment.attack_spell_names": (0x3D4FF, 0x3D803, 15, "array"),
    "equipment.defensive_spell_names": (0x3D606, 0x3D90A, 9, "array"),
    "equipment.misc_spell_names": (0x3D69B, 0x3D99F, 8, "array"),
    "equipment.enhancement_item_names": (0x3D724, 0x3DA28, 4, "array"),
    "equipment.enhancement_attr_names": (0x3D74E, 0x3DA52, 8, "array"),
    "equipment.potion_names": (0x3DFC9, 0x3E2CD, 15, "array"),
    "equipment.body_part_names": (0x3DB8D, 0x3DE91, 11, "array"),
    "quests.main_quest_item_names": (0x402D8, 0x40612, 8, "array"),
    "status.effects_list": (0x41EB8, 0x42262, 23, "array"),
    "status.key_names": (0x3EB27, 0x3EE2B, 12, "array"),
    "city_generation.tavern_prefixes": (0x36216, 0x36416, 23, "array"),
    "city_generation.tavern_marine_suffixes": (0x362BD, 0x364BD, 23, "array"),
    "city_generation.tavern_suffixes": (0x36357, 0x36557, 23, "array"),
    "city_generation.temple_prefixes": (0x363E1, 0x365E1, 3, "array"),
    "city_generation.temple1_suffixes": (0x3640C, 0x3660C, 5, "array"),
    "city_generation.temple2_suffixes": (0x36449, 0x36649, 9, "array"),
    "city_generation.temple3_suffixes": (0x36488, 0x36688, 10, "array"),
    "city_generation.equipment_prefixes": (0x364D1, 0x366D1, 20, "array"),
    "city_generation.equipment_suffixes": (0x3659E, 0x3679E, 10, "array"),
    "city_generation.mages_guild_menu_name": (0x42567, 0x42911, 1, "single"),
    "items.gold_piece": (0x403FC, 0x40736, 1, "single"),
    "items.bag_of_gold_pieces": (0x4040A, 0x40744, 1, "single"),
    "char_creation.choose_class_creation": (0x35A80, 0x35C80, 37, "fixed"),
    "char_creation.class_questions_intro": (0x35AA7, 0x35CA7, 175, "fixed"),
    "char_creation.suggested_class": (0x35BB1, 0x35DB1, 75, "fixed"),
    "char_creation.choose_class_list": (0x3F61A, 0x3F956, 19, "fixed"),
    "char_creation.choose_name": (0x35B58, 0x35D58, 26, "fixed"),
    "char_creation.choose_gender": (0x35B74, 0x35D74, 20, "fixed"),
    "char_creation.choose_race": (0x35B8A, 0x35D8A, 37, "fixed"),
    "char_creation.confirm_race": (0x35BFF, 0x35DFF, 74, "fixed"),
    "char_creation.confirmed_race1": (0x35C4C, 0x35E4C, 84, "fixed"),
    "char_creation.confirmed_race2": (0x3F56E, 0x3F8AA, 18, "fixed"),
    "char_creation.confirmed_race3": (0x35CA2, 0x35EA2, 60, "fixed"),
    "char_creation.confirmed_race4": (0x35CE0, 0x35EE0, 67, "fixed"),
    "char_creation.distribute_class_points": (0x35D25, 0x35F25, 93, "fixed"),
    "char_creation.choose_attributes": (0x35FA3, 0x361A3, 23, "fixed"),
    "char_creation.choose_attributes_bonus_points_remaining": (0x3F5EF, 0x3F817, 1, "single"),
    "char_creation.choose_appearance": (0x35D84, 0x35F84, 174, "fixed"),
}

AKEY_ACD_OFFSETS = {
    "A001.0": 0x42EAF,
    "A002.0": 0x42D9E,
    "A002.1": 0x42D9E,
    "A100.0": 0x3FA1C,
    "A110.0": 0x40384,
    "A111.0": 0x403B1,
    "A112.0": 0x403C3,
    "A113.0": 0x403D3,
    "A114.0": 0x403E9,
    "A115.0": 0x40405,
    "A116.0": 0x40533,
    "A117.0": 0x40550,
    "A118.0": 0x402E3,
    "A119.0": 0x402F6,
    "A120.0": 0x40309,
    "A121.0": 0x4031E,
    "A130.0": 0x3DAFA,
    "A131.0": 0x42D79,
    "A132.0": 0x42DC6,
    "A133.0": 0x42DEA,
    "A134.0": 0x42E20,
    "A135.0": 0x42E34,
    "A136.0": 0x42E45,
    "A137.0": 0x42E69,
    "A138.0": 0x42E7A,
    "A139.0": 0x42EDF,
    "A150.0": 0x42BE3,
    "A151.0": 0x42C10,
    "A152.0": 0x42FA3,
    "A153.0": 0x42FBC,
    "A154.0": 0x42FD3,
    "A155.0": 0x42FF7,
    "A156.0": 0x43026,
    "A157.0": 0x4306C,
    "A158.0": 0x430A9,
    "A158.1": 0x430A9,
    "A170.0": 0x42BBF,
    "A171.0": 0x42BA6,
    "A172.0": 0x42B81,
    "A180.0": 0x431AD,
    "A181.0": 0x4322C,
    "A190.0": 0x43161,
    "A192.0": 0x43190,
    "A193.0": 0x431D2,
    "A194.0": 0x4320A,
    "A195.0": 0x43C7E,
    "A196.0": 0x43ED4,
    "A197.0": 0x44529,
    "A198.0": 0x44547,
    "A199.0": 0x4455E,
    "A210.0": 0x413E0,
    "A211.0": 0x4148A,
    "A212.0": 0x414AB,
    "A213.0": 0x414C6,
    "A214.0": 0x4155C,
    "A215.0": 0x43777,
    "A216.0": 0x4379D,
    "A217.0": 0x43935,
    "A218.0": 0x4394A,
    "A219.0": 0x43962,
    "A220.0": 0x43DB6,
    "A221.0": 0x42230,
    "A222.0": 0x42247,
    "A223.0": 0x36F7A,
    "A224.0": 0x4295C,
    "A225.0": 0x42B4F,
    "A230.0": 0x40670,
    "A231.0": 0x40692,
    "A232.0": 0x406A5,
    "A233.0": 0x406BC,
    "A234.0": 0x406D7,
    "A235.0": 0x406FA,
    "A236.0": 0x40744,
    "A237.0": 0x42128,
    "A300.0": 0x3FBE8,
    "A301.0": 0x4041E,
    "A302.0": 0x40925,
    "A303.0": 0x416D2,
    "A304.0": 0x416F8,
    "A305.0": 0x4170D,
    "A306.0": 0x4172A,
    "A307.0": 0x41756,
    "A308.0": 0x41843,
    "A309.0": 0x41861,
    "A310.0": 0x418D1,
    "A311.0": 0x4190F,
    "A312.0": 0x424D1,
    "A313.0": 0x4250B,
    "A314.0": 0x42864,
    "A400.0": 0x432DF,
    "A401.0": 0x432EF,
    "A402.0": 0x43308,
    "A403.0": 0x3F690,
    "A404.0": 0x433B3,
    "A405.0": 0x4351B,
    "A406.0": 0x435FA,
    "A407.0": 0x43605,
    "A408.0": 0x43610,
    "A409.0": 0x43623,
    "A410.0": 0x43637,
    "A411.0": 0x4364B,
    "A412.0": 0x436D3,
    "A413.0": 0x43AC9,
    "A414.0": 0x43E80,
    "A415.0": 0x43E9A,
    "A416.0": 0x43EB0,
    "A417.0": 0x43F08,
    "A418.0": 0x43F24,
    "A419.0": 0x43FA9,
    "A420.0": 0x44216,
    "A421.0": 0x44223,
    "A422.0": 0x44230,
    "A423.0": 0x44261,
    "A424.0": 0x44271,
    "A425.0": 0x44288,
    "A426.0": 0x442A1,
    "A427.0": 0x442D0,
    "A428.0": 0x442F4,
    "A429.0": 0x44103,
    "A430.0": 0x44311,
    "A431.0": 0x44325,
    "A432.0": 0x44338,
    "A600.0": 0x41FCA,
    "A600.1": 0x41FCA,
    "A619.0": 0x43176,
    "A191.0": 0x4297B,
    "A213_mages_spell_inscribed.0": 0x4141E,
    "A213_mages_spell_no_money.0": 0x4144F,
}

WILDERNESS_NORMAL = {"A.EXE": 0x3F02C, "ACD.EXE": 0x3F314}

_SENTINELS = ("races.singular", "calendar.month_names", "equipment.weapon_names", "status.key_names")


def _printable_ok(s: str) -> bool:
    return all(0x20 <= ord(c) <= 0x7E for c in s)


def _read_array(analyzer, addr: int, count: int) -> list[str]:
    raw = analyzer.read_bytes(addr, count * 80 + 80)
    parts = raw.split(b"\x00")
    out: list[str] = []
    for p in parts:
        if len(out) >= count:
            break
        out.append(p.decode("latin-1"))
    return out


def _read_single(analyzer, addr: int) -> str:
    raw = analyzer.read_bytes(addr, 160)
    return raw.split(b"\x00")[0].decode("latin-1")


def _read_fixed(analyzer, addr: int, length: int) -> str:
    raw = analyzer.read_bytes(addr, length)
    return raw.split(b"\x00")[0].decode("latin-1")


def _read_table(analyzer, image_base: int, off: int, count: int, kind: str):
    if kind == "single":
        return _read_single(analyzer, image_base + off)
    if kind == "fixed":
        return _read_fixed(analyzer, image_base + off, count)
    return _read_array(analyzer, image_base + off, count)


def _find_wilderness_hits(analyzer) -> list[int]:
    NORMAL, VILLAGE, DUNGEON, TAVERN = 24, 12, 12, 10
    TEMPLE_MIN, TEMPLE_MAX = 1, 30

    def plausible(buf, off, size):
        if off + 1 + size > len(buf):
            return False
        if buf[off] != size:
            return False
        return all(1 <= b <= 70 for b in buf[off + 1:off + 1 + size])

    hits: list[int] = []
    enum_func = getattr(analyzer, "_enum_readable_regions", None)
    if enum_func is None:
        return hits
    try:
        regions = enum_func(0x00000000, 0x7FFFFFFF)
    except Exception:  # noqa: BLE001
        logger.exception("arena_aexe: region enumeration failed")
        return hits
    for base, size in regions:
        if size <= 0 or size > 0x10000000:
            continue
        try:
            buf = analyzer.read_bytes(base, size)
        except OSError:
            continue
        n = len(buf)
        end = n - (1 + NORMAL + 1 + VILLAGE + 1 + DUNGEON + 1 + TAVERN + 1 + TEMPLE_MIN)
        for o in range(max(0, end)):
            if buf[o] != NORMAL:
                continue
            if not plausible(buf, o, NORMAL):
                continue
            p = o + 1 + NORMAL
            if not plausible(buf, p, VILLAGE):
                continue
            p += 1 + VILLAGE
            if not plausible(buf, p, DUNGEON):
                continue
            p += 1 + DUNGEON
            if not plausible(buf, p, TAVERN):
                continue
            p += 1 + TAVERN
            if p >= n:
                continue
            t = buf[p]
            if not (TEMPLE_MIN <= t <= TEMPLE_MAX):
                continue
            if not plausible(buf, p, t):
                continue
            hits.append(base + o)
    return hits


def _version_plausible(analyzer, image_base: int, version: str) -> bool:
    idx = 0 if version == "A.EXE" else 1
    good = 0
    for tn in _SENTINELS:
        rec = AEXE_TABLES[tn]
        off = rec[idx]
        count, kind = rec[2], rec[3]
        try:
            vals = _read_table(analyzer, image_base, off, count, kind)
        except OSError:
            return False
        seq = [vals] if kind == "single" else vals
        if not seq:
            return False
        if not all(_printable_ok(s) for s in seq):
            return False
        if seq[0] == "":
            return False
        good += 1
    return good == len(_SENTINELS)


def detect_image_base(analyzer) -> Optional[tuple[str, int]]:
    if analyzer is None:
        return None
    hits = _find_wilderness_hits(analyzer)
    if not hits:
        logger.info("arena_aexe: no wilderness anchor found")
        return None
    for h in hits:
        for version, woff in WILDERNESS_NORMAL.items():
            image_base = h - woff
            if image_base < 0:
                continue
            if _version_plausible(analyzer, image_base, version):
                logger.info("arena_aexe: version=%s image_base=0x%08X (anchor=0x%08X)",
                            version, image_base, h)
                return version, image_base
    logger.info("arena_aexe: anchor found but no version plausible (%d hits)", len(hits))
    return None


def harvest(analyzer, progress=None, cancel_check=None) -> Optional[tuple[str, dict]]:
    detected = detect_image_base(analyzer)
    if detected is None:
        return None
    version, image_base = detected
    idx = 0 if version == "A.EXE" else 1
    tables: dict[str, object] = {}
    items = list(AEXE_TABLES.items())
    total = len(items)
    for i, (tn, rec) in enumerate(items):
        if cancel_check is not None and cancel_check():
            raise GenerationCancelled()
        off = rec[idx]
        count, kind = rec[2], rec[3]
        try:
            tables[tn] = _read_table(analyzer, image_base, off, count, kind)
        except OSError as e:
            logger.warning("arena_aexe: read failed for %s: %s", tn, e)
            return None
        if progress is not None:
            try:
                progress(i + 1, total)
            except Exception:  # noqa: BLE001
                pass
    return version, tables


def _read_akey_record(analyzer, addr: int) -> str:
    raw = analyzer.read_bytes(addr, 240)
    return raw.split(b"\x00")[0].decode("latin-1")


def harvest_akey(analyzer) -> Optional[tuple[str, dict]]:
    detected = detect_image_base(analyzer)
    if detected is None:
        return None
    version, image_base = detected
    if version != "ACD.EXE":
        logger.info("arena_aexe: harvest_akey skipped (version=%s, ACD-only)", version)
        return None
    out: dict[str, str] = {}
    for akey, off in AKEY_ACD_OFFSETS.items():
        try:
            out[akey] = _read_akey_record(analyzer, image_base + off)
        except OSError as e:
            logger.warning("arena_aexe: akey read failed for %s: %s", akey, e)
            return None
    return version, out


def build_aexe_original_json(template: dict, tables: dict) -> dict:
    out: dict[str, dict] = {}
    for key, ent in template.items():
        st = ent.get("src_table")
        si = ent.get("src_index")
        if st is None or st not in tables:
            raise KeyError(f"src_table missing for {key}: {st}")
        val = tables[st]
        if isinstance(val, str):
            original = val
        else:
            if si is None or si < 0 or si >= len(val):
                raise IndexError(f"src_index out of range for {key}: {si}")
            original = val[si]
        if ent.get("strip_article") and isinstance(original, str):
            original = re.sub(r"^(?:a|an) (?=\S)", "", original)
        rest = {k: v for k, v in ent.items()
                if k not in ("src_table", "src_index", "strip_article")}
        out[key] = {"original": original, **rest}
    return out


CITY_GEN_OFFSETS = {
    "CoastalCityList": (0x3FEA8, 0x401E2),
    "CityTemplateFilenames": (0x3FEE2, 0x4021C),
    "StartingPositions": (0x3FF55, 0x4028F),
    "ReservedBlockLists": (0x3FF8E, 0x402C8),
}
_CITY_GEN_COASTAL_COUNT = 58
_CITY_GEN_TEMPLATE_COUNT = 6
_CITY_GEN_STARTING_COUNT = 22
_CITY_GEN_RESERVED_COUNT = 8


def harvest_city_generation(analyzer) -> Optional[tuple[str, dict]]:
    r = detect_image_base(analyzer)
    if r is None:
        return None
    version, image_base = r
    idx = 0 if version == "A.EXE" else 1

    def _off(name: str) -> int:
        return CITY_GEN_OFFSETS[name][idx]

    base = _off("CoastalCityList")
    try:
        blob = analyzer.read_bytes(image_base + base, 0x400)
    except (OSError, AttributeError):
        return None
    if not blob or len(blob) < 0x100:
        return None

    def _at(name: str) -> int:
        return _off(name) - base

    coastal = list(blob[_at("CoastalCityList"):
                        _at("CoastalCityList") + _CITY_GEN_COASTAL_COUNT])
    templates: list[str] = []
    p = _at("CityTemplateFilenames")
    for _ in range(_CITY_GEN_TEMPLATE_COUNT):
        e = blob.index(0, p)
        templates.append(blob[p:e].decode("latin-1"))
        p = e + 1
    sp_off = _at("StartingPositions")
    starting = [[blob[sp_off + i * 2], blob[sp_off + i * 2 + 1]]
                for i in range(_CITY_GEN_STARTING_COUNT)]
    reserved: list[list[int]] = []
    p = _at("ReservedBlockLists")
    for _ in range(_CITY_GEN_RESERVED_COUNT):
        lst: list[int] = []
        while blob[p] != 0:
            lst.append(blob[p])
            p += 1
        p += 1
        reserved.append(lst)
    data = {
        "coastal_city_list": coastal,
        "city_template_filenames": templates,
        "starting_positions": starting,
        "reserved_block_lists": reserved,
    }
    _name_keys = (
        "tavern_prefixes", "tavern_marine_suffixes", "tavern_suffixes",
        "temple_prefixes", "temple1_suffixes", "temple2_suffixes",
        "temple3_suffixes", "equipment_prefixes", "equipment_suffixes",
    )
    for k in _name_keys:
        rec = AEXE_TABLES.get(f"city_generation.{k}")
        if rec is None:
            continue
        try:
            data[k] = _read_table(analyzer, image_base, rec[idx], rec[2], rec[3])
        except OSError:
            pass
    return version, data


__all__ = [
    "GENERATOR_VERSION", "AEXE_TABLES", "AKEY_ACD_OFFSETS", "WILDERNESS_NORMAL",
    "CITY_GEN_OFFSETS",
    "detect_image_base", "harvest", "harvest_akey", "harvest_city_generation",
    "build_aexe_original_json",
]
