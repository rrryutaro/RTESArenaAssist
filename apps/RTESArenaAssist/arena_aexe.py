from __future__ import annotations
import logging
import re
from typing import Optional
logger = logging.getLogger('RTESArenaAssist')
GENERATOR_VERSION = 'arena_aexe/1'

class GenerationCancelled(Exception):
    pass
AEXE_TABLES = {'races.singular': (254608, 255380, 8, 'array'), 'races.plural': (254533, 255305, 8, 'array'), 'classes.names': (254302, 255074, 18, 'array'), 'classes.preferred_attributes': (220724, 221236, 18, 'array'), 'calendar.month_names': (256148, 256920, 12, 'array'), 'calendar.times_of_day': (263465, 264301, 7, 'array'), 'calendar.weekday_names': (256298, 257070, 7, 'array'), 'calendar.holiday_names': (256349, 257121, 15, 'array'), 'locations.province_names': (234232, 234744, 9, 'array'), 'locations.char_creation_province_names': (255490, 256262, 8, 'array'), 'locations.location_types': (250051, 250613, 5, 'array'), 'locations.ruler_titles': (256711, 257483, 14, 'array'), 'locations.start_dungeon_name': (262817, 263643, 1, 'single'), 'entities.attribute_names': (265257, 255232, 8, 'array'), 'entities.creature_names': (224190, 224702, 23, 'array'), 'entities.creature_sound_names': (260765, 261591, 26, 'array'), 'entities.creature_animation_filenames': (255227, 255999, 24, 'array'), 'entities.final_boss_name': (224515, 225027, 1, 'single'), 'entities.pronoun_names': (236709, 236709, 9, 'array'), 'entities.relation_names': (225480, 225480, 20, 'array'), 'quests.delivery_quest_item_names': (225697, 225697, 45, 'array'), 'menu.ask_about_places': (278483, 278483, 9, 'array'), 'menu.travel_places': (278581, 278581, 9, 'array'), 'entities.person_names': (236476, 236476, 8, 'array'), 'status.war_peace': (236300, 236300, 2, 'array'), 'entities.title_names': (236545, 236545, 12, 'array'), 'inn.room_types': (254610, 254610, 5, 'array'), 'inn.drinks_common': (252690, 252690, 12, 'array'), 'inn.drinks_special': (252768, 252768, 9, 'array'), 'entities.directions': (236742, 236742, 8, 'array'), 'character.status_effects': (225168, 225168, 7, 'array'), 'character.stat_labels': (266081, 266081, 3, 'array'), 'mages.effect_types': (265409, 265409, 25, 'array'), 'mages.effect_sub_cause': (266016, 266016, 4, 'array'), 'mages.damage_types': (266263, 266263, 5, 'array'), 'mages.attribute_kinds': (266322, 266322, 2, 'array'), 'mages.resist_types': (266351, 266351, 6, 'array'), 'mages.target_types': (266385, 266385, 5, 'array'), 'mages.spell_geometry': (266128, 266128, 3, 'array'), 'equipment.material_names': (253243, 254015, 8, 'array'), 'equipment.item_condition_names': (267341, 268273, 8, 'array'), 'equipment.armor_names': (252704, 253476, 11, 'array'), 'equipment.plate_armor_names': (253322, 254094, 11, 'array'), 'equipment.chain_armor_names': (253484, 254256, 11, 'array'), 'equipment.leather_armor_names': (253646, 254418, 11, 'array'), 'equipment.armor_enchantment_names': (253001, 253773, 14, 'array'), 'equipment.weapon_names': (252160, 252932, 18, 'array'), 'equipment.weapon_enchantment_names': (252443, 253215, 14, 'array'), 'equipment.spellcasting_item_names': (251085, 251857, 4, 'array'), 'equipment.attack_spell_names': (251135, 251907, 15, 'array'), 'equipment.defensive_spell_names': (251398, 252170, 9, 'array'), 'equipment.misc_spell_names': (251547, 252319, 8, 'array'), 'equipment.enhancement_item_names': (251684, 252456, 4, 'array'), 'equipment.enhancement_attr_names': (251726, 252498, 8, 'array'), 'equipment.potion_names': (253897, 254669, 15, 'array'), 'equipment.body_part_names': (252813, 253585, 11, 'array'), 'quests.main_quest_item_names': (262872, 263698, 8, 'array'), 'status.effects_list': (270008, 270946, 23, 'array'), 'status.key_names': (256807, 257579, 12, 'array'), 'city_generation.tavern_prefixes': (221718, 222230, 23, 'array'), 'city_generation.tavern_marine_suffixes': (221885, 222397, 23, 'array'), 'city_generation.tavern_suffixes': (222039, 222551, 23, 'array'), 'city_generation.temple_prefixes': (222177, 222689, 3, 'array'), 'city_generation.temple1_suffixes': (222220, 222732, 5, 'array'), 'city_generation.temple2_suffixes': (222281, 222793, 9, 'array'), 'city_generation.temple3_suffixes': (222344, 222856, 10, 'array'), 'city_generation.equipment_prefixes': (222417, 222929, 20, 'array'), 'city_generation.equipment_suffixes': (222622, 223134, 10, 'array'), 'city_generation.mages_guild_menu_name': (271719, 272657, 1, 'single'), 'items.gold_piece': (263164, 263990, 1, 'single'), 'items.bag_of_gold_pieces': (263178, 264004, 1, 'single'), 'travel.location_format_texts': (226477, 226989, 3, 'array'), 'travel.day_prediction': (226547, 227059, 2, 'array'), 'travel.distance_prediction': (226616, 227128, 1, 'single'), 'travel.arrival_date_prediction': (226646, 227158, 1, 'single'), 'travel.arrival_popup_date': (226426, 226938, 1, 'single'), 'char_creation.choose_class_creation': (219776, 220288, 37, 'fixed'), 'char_creation.class_questions_intro': (219815, 220327, 175, 'fixed'), 'char_creation.suggested_class': (220081, 220593, 75, 'fixed'), 'char_creation.choose_class_list': (259610, 260438, 19, 'fixed'), 'char_creation.choose_name': (219992, 220504, 26, 'fixed'), 'char_creation.choose_gender': (220020, 220532, 20, 'fixed'), 'char_creation.choose_race': (220042, 220554, 37, 'fixed'), 'char_creation.confirm_race': (220159, 220671, 74, 'fixed'), 'char_creation.confirmed_race1': (220236, 220748, 84, 'fixed'), 'char_creation.confirmed_race2': (259438, 260266, 18, 'fixed'), 'char_creation.confirmed_race3': (220322, 220834, 60, 'fixed'), 'char_creation.confirmed_race4': (220384, 220896, 67, 'fixed'), 'char_creation.distribute_class_points': (220453, 220965, 93, 'fixed'), 'char_creation.choose_attributes': (221091, 221603, 23, 'fixed'), 'char_creation.choose_attributes_bonus_points_remaining': (259567, 260119, 1, 'single'), 'char_creation.choose_appearance': (220548, 221060, 174, 'fixed')}
AKEY_ACD_OFFSETS = {'A001.0': 274095, 'A002.0': 273822, 'A002.1': 273822, 'A100.0': 260636, 'A110.0': 263044, 'A111.0': 263089, 'A112.0': 263107, 'A113.0': 263123, 'A114.0': 263145, 'A115.0': 263173, 'A116.0': 263475, 'A117.0': 263504, 'A118.0': 262883, 'A119.0': 262902, 'A120.0': 262921, 'A121.0': 262942, 'A130.0': 252666, 'A131.0': 273785, 'A132.0': 273862, 'A133.0': 273898, 'A134.0': 273952, 'A135.0': 273972, 'A136.0': 273989, 'A137.0': 274025, 'A138.0': 274042, 'A139.0': 274143, 'A150.0': 273379, 'A151.0': 273424, 'A152.0': 274339, 'A153.0': 274364, 'A154.0': 274387, 'A155.0': 274423, 'A156.0': 274470, 'A157.0': 274540, 'A158.0': 274601, 'A158.1': 274601, 'A170.0': 273343, 'A171.0': 273318, 'A172.0': 273281, 'A180.0': 274861, 'A181.0': 274988, 'A190.0': 274785, 'A192.0': 274832, 'A193.0': 274898, 'A194.0': 274954, 'A195.0': 277630, 'A196.0': 278228, 'A197.0': 279849, 'A198.0': 279879, 'A199.0': 279902, 'A210.0': 267232, 'A211.0': 267402, 'A212.0': 267435, 'A213.0': 267462, 'A214.0': 267612, 'A215.0': 276343, 'A216.0': 276381, 'A217.0': 276789, 'A218.0': 276810, 'A219.0': 276834, 'A220.0': 277942, 'A221.0': 270896, 'A222.0': 270919, 'A223.0': 225146, 'A224.0': 272732, 'A225.0': 273231, 'A230.0': 263792, 'A231.0': 263826, 'A232.0': 263845, 'A233.0': 263868, 'A234.0': 263895, 'A235.0': 263930, 'A236.0': 264004, 'A237.0': 270632, 'A300.0': 261096, 'A301.0': 263198, 'A302.0': 264485, 'A303.0': 267986, 'A304.0': 268024, 'A305.0': 268045, 'A306.0': 268074, 'A307.0': 268118, 'A308.0': 268355, 'A309.0': 268385, 'A310.0': 268497, 'A311.0': 268559, 'A312.0': 271569, 'A313.0': 271627, 'A314.0': 272484, 'A400.0': 275167, 'A401.0': 275183, 'A402.0': 275208, 'A403.0': 259728, 'A404.0': 275379, 'A405.0': 275739, 'A406.0': 275962, 'A407.0': 275973, 'A408.0': 275984, 'A409.0': 276003, 'A410.0': 276023, 'A411.0': 276043, 'A412.0': 276179, 'A413.0': 277193, 'A414.0': 278144, 'A415.0': 278170, 'A416.0': 278192, 'A417.0': 278280, 'A418.0': 278308, 'A419.0': 278441, 'A420.0': 279062, 'A421.0': 279075, 'A422.0': 279088, 'A423.0': 279137, 'A424.0': 279153, 'A425.0': 279176, 'A426.0': 279201, 'A427.0': 279248, 'A428.0': 279284, 'A429.0': 278787, 'A430.0': 279313, 'A431.0': 279333, 'A432.0': 279352, 'A600.0': 270282, 'A600.1': 270282, 'A619.0': 274806, 'A191.0': 272763, 'A213_mages_spell_inscribed.0': 267294, 'A213_mages_spell_no_money.0': 267343}
WILDERNESS_NORMAL = {'A.EXE': 258092, 'ACD.EXE': 258836}
_SENTINELS = ('races.singular', 'calendar.month_names', 'equipment.weapon_names', 'status.key_names')

def _printable_ok(s: str) -> bool:
    return all((32 <= ord(c) <= 126 for c in s))

def _read_array(analyzer, addr: int, count: int) -> list[str]:
    raw = analyzer.read_bytes(addr, count * 80 + 80)
    parts = raw.split(b'\x00')
    out: list[str] = []
    for p in parts:
        if len(out) >= count:
            break
        out.append(p.decode('latin-1'))
    return out

def _read_single(analyzer, addr: int) -> str:
    raw = analyzer.read_bytes(addr, 160)
    return raw.split(b'\x00')[0].decode('latin-1')

def _read_fixed(analyzer, addr: int, length: int) -> str:
    raw = analyzer.read_bytes(addr, length)
    return raw.split(b'\x00')[0].decode('latin-1')

def _read_table(analyzer, image_base: int, off: int, count: int, kind: str):
    if kind == 'single':
        return _read_single(analyzer, image_base + off)
    if kind == 'fixed':
        return _read_fixed(analyzer, image_base + off, count)
    return _read_array(analyzer, image_base + off, count)

def _find_wilderness_hits(analyzer) -> list[int]:
    NORMAL, VILLAGE, DUNGEON, TAVERN = (24, 12, 12, 10)
    TEMPLE_MIN, TEMPLE_MAX = (1, 30)

    def plausible(buf, off, size):
        if off + 1 + size > len(buf):
            return False
        if buf[off] != size:
            return False
        return all((1 <= b <= 70 for b in buf[off + 1:off + 1 + size]))
    hits: list[int] = []
    enum_func = getattr(analyzer, '_enum_readable_regions', None)
    if enum_func is None:
        return hits
    try:
        regions = enum_func(0, 2147483647)
    except Exception:
        logger.exception('arena_aexe: region enumeration failed')
        return hits
    for base, size in regions:
        if size <= 0 or size > 268435456:
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
            if not TEMPLE_MIN <= t <= TEMPLE_MAX:
                continue
            if not plausible(buf, p, t):
                continue
            hits.append(base + o)
    return hits

def _version_plausible(analyzer, image_base: int, version: str) -> bool:
    idx = 0 if version == 'A.EXE' else 1
    good = 0
    for tn in _SENTINELS:
        rec = AEXE_TABLES[tn]
        off = rec[idx]
        count, kind = (rec[2], rec[3])
        try:
            vals = _read_table(analyzer, image_base, off, count, kind)
        except OSError:
            return False
        seq = [vals] if kind == 'single' else vals
        if not seq:
            return False
        if not all((_printable_ok(s) for s in seq)):
            return False
        if seq[0] == '':
            return False
        good += 1
    return good == len(_SENTINELS)

def detect_image_base(analyzer) -> Optional[tuple[str, int]]:
    if analyzer is None:
        return None
    hits = _find_wilderness_hits(analyzer)
    if not hits:
        logger.info('arena_aexe: no wilderness anchor found')
        return None
    for h in hits:
        for version, woff in WILDERNESS_NORMAL.items():
            image_base = h - woff
            if image_base < 0:
                continue
            if _version_plausible(analyzer, image_base, version):
                logger.info('arena_aexe: version=%s image_base=0x%08X (anchor=0x%08X)', version, image_base, h)
                return (version, image_base)
    logger.info('arena_aexe: anchor found but no version plausible (%d hits)', len(hits))
    return None

def harvest(analyzer, progress=None, cancel_check=None) -> Optional[tuple[str, dict]]:
    detected = detect_image_base(analyzer)
    if detected is None:
        return None
    version, image_base = detected
    idx = 0 if version == 'A.EXE' else 1
    tables: dict[str, object] = {}
    items = list(AEXE_TABLES.items())
    total = len(items)
    for i, (tn, rec) in enumerate(items):
        if cancel_check is not None and cancel_check():
            raise GenerationCancelled()
        off = rec[idx]
        count, kind = (rec[2], rec[3])
        try:
            tables[tn] = _read_table(analyzer, image_base, off, count, kind)
        except OSError as e:
            logger.warning('arena_aexe: read failed for %s: %s', tn, e)
            return None
        if progress is not None:
            try:
                progress(i + 1, total)
            except Exception:
                pass
    return (version, tables)

def _read_akey_record(analyzer, addr: int) -> str:
    raw = analyzer.read_bytes(addr, 240)
    return raw.split(b'\x00')[0].decode('latin-1')

def harvest_akey(analyzer) -> Optional[tuple[str, dict]]:
    detected = detect_image_base(analyzer)
    if detected is None:
        return None
    version, image_base = detected
    if version != 'ACD.EXE':
        logger.info('arena_aexe: harvest_akey skipped (version=%s, ACD-only)', version)
        return None
    out: dict[str, str] = {}
    for akey, off in AKEY_ACD_OFFSETS.items():
        try:
            out[akey] = _read_akey_record(analyzer, image_base + off)
        except OSError as e:
            logger.warning('arena_aexe: akey read failed for %s: %s', akey, e)
            return None
    return (version, out)

def build_aexe_original_json(template: dict, tables: dict) -> dict:
    out: dict[str, dict] = {}
    for key, ent in template.items():
        st = ent.get('src_table')
        si = ent.get('src_index')
        if st is None or st not in tables:
            raise KeyError(f'src_table missing for {key}: {st}')
        val = tables[st]
        if isinstance(val, str):
            original = val
        else:
            if si is None or si < 0 or si >= len(val):
                raise IndexError(f'src_index out of range for {key}: {si}')
            original = val[si]
        if ent.get('strip_article') and isinstance(original, str):
            original = re.sub('^(?:a|an) (?=\\S)', '', original)
        rest = {k: v for k, v in ent.items() if k not in ('src_table', 'src_index', 'strip_article')}
        out[key] = {'original': original, **rest}
    return out
CITY_GEN_OFFSETS = {'CoastalCityList': (261800, 262626), 'CityTemplateFilenames': (261858, 262684), 'StartingPositions': (261973, 262799), 'ReservedBlockLists': (262030, 262856)}
_CITY_GEN_COASTAL_COUNT = 58
_CITY_GEN_TEMPLATE_COUNT = 6
_CITY_GEN_STARTING_COUNT = 22
_CITY_GEN_RESERVED_COUNT = 8

def harvest_city_generation(analyzer) -> Optional[tuple[str, dict]]:
    r = detect_image_base(analyzer)
    if r is None:
        return None
    version, image_base = r
    idx = 0 if version == 'A.EXE' else 1

    def _off(name: str) -> int:
        return CITY_GEN_OFFSETS[name][idx]
    base = _off('CoastalCityList')
    try:
        blob = analyzer.read_bytes(image_base + base, 1024)
    except (OSError, AttributeError):
        return None
    if not blob or len(blob) < 256:
        return None

    def _at(name: str) -> int:
        return _off(name) - base
    coastal = list(blob[_at('CoastalCityList'):_at('CoastalCityList') + _CITY_GEN_COASTAL_COUNT])
    templates: list[str] = []
    p = _at('CityTemplateFilenames')
    for _ in range(_CITY_GEN_TEMPLATE_COUNT):
        e = blob.index(0, p)
        templates.append(blob[p:e].decode('latin-1'))
        p = e + 1
    sp_off = _at('StartingPositions')
    starting = [[blob[sp_off + i * 2], blob[sp_off + i * 2 + 1]] for i in range(_CITY_GEN_STARTING_COUNT)]
    reserved: list[list[int]] = []
    p = _at('ReservedBlockLists')
    for _ in range(_CITY_GEN_RESERVED_COUNT):
        lst: list[int] = []
        while blob[p] != 0:
            lst.append(blob[p])
            p += 1
        p += 1
        reserved.append(lst)
    data = {'coastal_city_list': coastal, 'city_template_filenames': templates, 'starting_positions': starting, 'reserved_block_lists': reserved}
    _name_keys = ('tavern_prefixes', 'tavern_marine_suffixes', 'tavern_suffixes', 'temple_prefixes', 'temple1_suffixes', 'temple2_suffixes', 'temple3_suffixes', 'equipment_prefixes', 'equipment_suffixes')
    for k in _name_keys:
        rec = AEXE_TABLES.get(f'city_generation.{k}')
        if rec is None:
            continue
        try:
            data[k] = _read_table(analyzer, image_base, rec[idx], rec[2], rec[3])
        except OSError:
            pass
    return (version, data)
__all__ = ['GENERATOR_VERSION', 'AEXE_TABLES', 'AKEY_ACD_OFFSETS', 'WILDERNESS_NORMAL', 'CITY_GEN_OFFSETS', 'detect_image_base', 'harvest', 'harvest_akey', 'harvest_city_generation', 'build_aexe_original_json']
