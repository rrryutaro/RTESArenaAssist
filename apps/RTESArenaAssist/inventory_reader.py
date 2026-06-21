
from __future__ import annotations
import struct

ITEM_SIZE  = 19
INV_SLOTS  = 40

INV_OFFSET            = 0x0212
WEAPON_NAMES_OFFSET       = 0x2204
PLATE_NAMES_OFFSET        = 0x268E
CHAIN_NAMES_OFFSET        = 0x2730
LEATHER_NAMES_OFFSET      = 0x27D2
JEWELRY_NAMES_OFFSET      = 0x2028
SPELLCASTING_NAMES_OFFSET = 0x1DD1
MATERIAL_NAMES_OFFSET     = 0x263F
BASE_ARMOR_NAMES_OFFSET   = 0x2424
ARMOR_ENCHANT_NAMES_OFFSET  = 0x254D
WEAPON_ENCHANT_NAMES_OFFSET = 0x231F

SPELL_ATTACK_NAMES_OFFSET  = 0x1E03
SPELL_DEFENSE_NAMES_OFFSET = 0x1F0A
SPELL_MISC_NAMES_OFFSET    = 0x1F9F
SPELL_ATTACK_COUNT  = 15
SPELL_DEFENSE_COUNT = 9
SPELL_MISC_COUNT    = 8

FLAG_MAGIC        = 0x01
FLAG_UNIDENTIFIED = 0x02

ENCHANT_COUNT = 14

ACCESSORY_MATERIAL_BASE = 3

SHIELD_SLOT_MIN = 7
SHIELD_SLOT_MAX = 10

ARMOR_PIECE_SLOT_MAX = 6

_CONDITION_NAMES_JA   = ["壊れている", "使用不可", "傷あり", "劣化",
                          "使用済み", "やや使用", "ほぼ新品", "新品"]
_CONDITION_THRESHOLDS = [1, 5, 15, 40, 60, 75, 91]


def _weight_str(weight_raw: int) -> str:
    if weight_raw == 0:
        return "—"
    kg = weight_raw / 256
    return f"{kg:.1f}kg" if kg != int(kg) else f"{int(kg)}.0kg"


def _condition_str(item: dict) -> str:
    if item["hands"] > 2:
        return f"残り {item['hands']} 回"
    hp, max_hp = item["health"], item["max_hp"]
    if max_hp <= 1:
        return ""
    pct = hp * 100 // max_hp
    for threshold, name in zip(reversed(_CONDITION_THRESHOLDS),
                                reversed(_CONDITION_NAMES_JA[1:])):
        if pct >= threshold:
            return name
    return _CONDITION_NAMES_JA[0]


def _effect_str(item: dict) -> str:
    if item["hands"] in (1, 2):
        return f"ダメージ {item['param1']}-{item['param2']}"
    ar = item["param1"] // 5
    return f"防御 -{ar}" if ar > 0 else ""


def _read_null_strings(data: bytes, max_count: int) -> list[str]:
    result: list[str] = []
    pos = 0
    for _ in range(max_count):
        end = data.find(b"\x00", pos)
        if end == -1:
            end = len(data)
        s = data[pos:end].decode("ascii", errors="replace").strip()
        result.append(s)
        pos = end + 1
        if pos >= len(data):
            break
    return result


def _parse_item(data: bytes, off: int) -> dict | None:
    if off + ITEM_SIZE > len(data):
        return None
    d = data[off:off + ITEM_SIZE]
    return dict(
        slot_id  = d[0],
        weight   = struct.unpack_from("<H", d, 1)[0],
        hands    = d[3],
        param1   = d[4],
        param2   = d[5],
        health   = struct.unpack_from("<H", d, 6)[0],
        max_hp   = struct.unpack_from("<H", d, 8)[0],
        price    = struct.unpack_from("<I", d, 10)[0],
        flags    = d[14],
        x        = d[15],
        material = d[16],
        y        = d[17],
        attr     = d[18],
    )


_ACCESSORY_SLOT_LABELS    = {0: "腕輪", 1: "帯", 2: "首飾", 3: "護符"}
_SPELLCASTING_SLOT_LABELS = {0: "印",   1: "水晶", 2: "腕輪", 3: "指輪"}
_ARMOR_SLOT_LABELS = {
    0: "胴部",
    1: "篭手",
    2: "脛当",
    3: "肩(左)",
    4: "肩(右)",
    5: "頭部",
    6: "靴",
}


def _slot_label(item: dict) -> str:
    hands = item["hands"]
    sid   = item["slot_id"]
    p1    = item["param1"]
    if hands in (1, 2):
        return "片手" if hands == 1 else "両手"
    if hands > 2:
        return _SPELLCASTING_SLOT_LABELS.get(sid, "呪具")
    if item["x"] == 0xFF and 0 <= sid <= 3:
        return _ACCESSORY_SLOT_LABELS.get(sid, "装身")
    if item["x"] == 0xFF and 4 <= sid <= 6:
        return _ARMOR_SLOT_LABELS.get(sid, "防具")
    if 18 <= p1 <= 50:
        return _ARMOR_SLOT_LABELS.get(sid, "防具")
    if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
        return "盾"
    return _ACCESSORY_SLOT_LABELS.get(sid, "装身")


def _classify_item(item: dict) -> tuple[str, int]:
    sid   = item["slot_id"]
    hands = item["hands"]
    p1    = item["param1"]
    if hands in (1, 2):
        return "weapon", -1
    if hands > 2:
        return "spellcasting", -1
    if item["x"] == 0xFF and 0 <= sid <= 3:
        return "accessory", -1
    if (item["x"] == 0xFF
            and 0 <= item["material"] <= 7
            and 4 <= sid <= 6):
        return "armor", 2
    if 40 <= p1 <= 50:
        return "armor", 2
    if 29 <= p1 <= 39:
        return "armor", 1
    if 18 <= p1 <= 28:
        return "armor", 0
    if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
        return "shield", -1
    return "accessory", -1


def _is_empty(item: dict) -> bool:
    return (item["price"] == 0 and item["health"] == 0
            and item["max_hp"] == 0 and item["param1"] == 0
            and item["slot_id"] == 0)


def _ench_index(item: dict) -> int | None:
    flags = item["flags"]
    if not (flags & FLAG_MAGIC):
        return None
    if flags & FLAG_UNIDENTIFIED:
        return None
    x = item["x"]
    if x == 0xFF or not (0 <= x < ENCHANT_COUNT):
        return None
    return x


def _get_item_name(item: dict,
                   weapon_names: list[str],
                   plate_names: list[str],
                   chain_names: list[str],
                   leather_names: list[str],
                   jewelry_names: list[str],
                   spellcasting_names: list[str],
                   material_names: list[str],
                   base_armor_names: list[str],
                   armor_enchant_names: list[str],
                   weapon_enchant_names: list[str],
                   spell_attack_names: list[str],
                   spell_defense_names: list[str],
                   spell_misc_names: list[str]) -> str:
    sid    = item["slot_id"]
    hands  = item["hands"]
    p1     = item["param1"]
    mat_id = item["material"]
    is_magic = bool(item["flags"] & FLAG_MAGIC)
    is_identified = not (item["flags"] & FLAG_UNIDENTIFIED)

    if hands in (1, 2):
        if 0 <= sid < len(weapon_names):
            base = weapon_names[sid]
        else:
            return f"Weapon#{p1}"
        if (item["x"] == 0xFF
                and 0 <= mat_id < len(material_names)):
            return f"{material_names[mat_id]} {base}"
        ei = _ench_index(item)
        if ei is not None and ei < len(weapon_enchant_names):
            return f"{base} {weapon_enchant_names[ei]}"
        return base

    if hands > 2:
        base = (spellcasting_names[sid]
                if 0 <= sid < len(spellcasting_names) else f"Spellcasting#{sid}")
        if is_magic and is_identified:
            table = {
                0: spell_attack_names,
                1: spell_defense_names,
                2: spell_misc_names,
            }.get(mat_id)
            x = item["x"]
            if table is not None and 0 <= x < len(table):
                return f"{base} {table[x]}"
        return base

    ei = _ench_index(item)
    if ei is not None and 0 <= sid < len(base_armor_names):
        base = base_armor_names[sid]
        if 0 <= mat_id < len(material_names):
            base = f"{material_names[mat_id]} {base}"
        if ei < len(armor_enchant_names):
            return f"{base} {armor_enchant_names[ei]}"

    if item["x"] == 0xFF and 0 <= sid <= 3:
        base = (jewelry_names[sid]
                if 0 <= sid < len(jewelry_names) else f"Jewelry#{sid}")
        if is_magic and is_identified:
            mi = mat_id + ACCESSORY_MATERIAL_BASE
            if 0 <= mi < len(material_names):
                return f"{material_names[mi]} {base}"
        return base

    if (item["x"] == 0xFF
            and 0 <= mat_id < len(material_names)
            and 4 <= sid <= ARMOR_PIECE_SLOT_MAX):
        base = base_armor_names[sid] if sid < len(base_armor_names) else f"Slot#{sid}"
        return f"{material_names[mat_id]} {base}"

    if 18 <= p1 <= 50:
        if 40 <= p1 <= 50:
            if 0 <= sid < len(plate_names):
                return plate_names[sid]
        elif 29 <= p1 <= 39:
            if 0 <= sid < len(chain_names):
                return chain_names[sid]
        elif 18 <= p1 <= 28:
            if 0 <= sid < len(leather_names):
                return leather_names[sid]
    else:
        if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
            if 0 <= sid < len(plate_names):
                return plate_names[sid]
        elif 0 <= sid < len(jewelry_names):
            return jewelry_names[sid]

    return f"Armor#{p1}"


def read_equipment_items(analyzer, anchor: int) -> list[dict]:
    def _safe_read_strings(offset: int, size: int, count: int) -> list[str]:
        try:
            return _read_null_strings(analyzer.read_bytes(anchor + offset, size), count)
        except OSError:
            return []

    weapon_names       = _safe_read_strings(WEAPON_NAMES_OFFSET,       400, 18)
    plate_names        = _safe_read_strings(PLATE_NAMES_OFFSET,        300, 11)
    chain_names        = _safe_read_strings(CHAIN_NAMES_OFFSET,        300, 11)
    leather_names      = _safe_read_strings(LEATHER_NAMES_OFFSET,      300, 11)
    jewelry_names      = _safe_read_strings(JEWELRY_NAMES_OFFSET,      100,  4)
    spellcasting_names = _safe_read_strings(SPELLCASTING_NAMES_OFFSET,  64,  4)
    material_names     = _safe_read_strings(MATERIAL_NAMES_OFFSET,     100,  8)
    base_armor_names   = _safe_read_strings(BASE_ARMOR_NAMES_OFFSET,   200, 11)
    armor_enchant_names  = _safe_read_strings(ARMOR_ENCHANT_NAMES_OFFSET,  300, ENCHANT_COUNT)
    weapon_enchant_names = _safe_read_strings(WEAPON_ENCHANT_NAMES_OFFSET, 300, ENCHANT_COUNT)
    spell_attack_names  = _safe_read_strings(SPELL_ATTACK_NAMES_OFFSET,  400, SPELL_ATTACK_COUNT)
    spell_defense_names = _safe_read_strings(SPELL_DEFENSE_NAMES_OFFSET, 300, SPELL_DEFENSE_COUNT)
    spell_misc_names    = _safe_read_strings(SPELL_MISC_NAMES_OFFSET,    300, SPELL_MISC_COUNT)

    try:
        inv_raw = analyzer.read_bytes(anchor + INV_OFFSET, ITEM_SIZE * INV_SLOTS)
    except OSError:
        return []

    items: list[dict] = []
    for i in range(INV_SLOTS):
        item = _parse_item(inv_raw, i * ITEM_SIZE)
        if item is None or _is_empty(item):
            continue
        en = _get_item_name(item, weapon_names, plate_names, chain_names,
                            leather_names, jewelry_names, spellcasting_names,
                            material_names, base_armor_names,
                            armor_enchant_names, weapon_enchant_names,
                            spell_attack_names, spell_defense_names,
                            spell_misc_names)
        item_type, armor_material_id = _classify_item(item)
        items.append({
            "en":               en,
            "slot_id":          item["slot_id"],
            "hands":            item["hands"],
            "health":           item["health"],
            "max_hp":           item["max_hp"],
            "price":            item["price"],
            "equipped":         bool(item["flags"] & 0x80),
            "is_unidentified":  bool(item["flags"] & 0x02),
            "item_type":        item_type,
            "armor_material_id": armor_material_id,
            "slot_label":       _slot_label(item),
            "weight":           _weight_str(item["weight"]),
            "condition":        _condition_str(item),
            "effect":           _effect_str(item),
        })
    return items
