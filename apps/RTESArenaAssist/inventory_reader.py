"""
inventory_reader.py — Arena インベントリメモリ読み取り

【確定知見】
- anchor+0x212 = NPCData+110 = inventory[0] 先頭 (InventoryItem×40, 各 19 bytes)
- hands=1 or 2 → 武器 → weaponNames[slotID]
    x=0xFF + mat 0-7 → 素材名 + weaponNames[slotID]（Elven Longsword 等）
    x=0（mat=0xFF等）→ legacy 素材無し武器（Dagger, Katana 等）
- hands>2      → スペルキャスティングアイテム（トリンケット）→ spellcastingNames[slotID]
    hands フィールドはチャージ数を格納（観測: Mark=14チャージ）
    slotID: 0=Mark / 1=Crystal / 2=Bracers / 3=Ring（DOSBox ライブメモリ確認済み）
- hands=0    → 防具・盾・アクセサリ:
    【アクセサリ判別: d[15]=x フィールド 0xFF かつ slotID 0-3 → アクセサリ】
      観測例: Bracelet(slot=0,x=0xFF,mat=4,p1=25), Torc(slot=2,x=0xFF,mat=2,p1=15)
      d[15]=0xFF は「d[16]=metal_id を素材として使用」の意味であり、アクセサリ確定マーカーではない。
      slot 4-6 (Pauldron R/Helm/Boots) で x=0xFF + mat=metal_id は金属防具（Steel Helm 等）。
      slotID 0-3 → jewelryNames[slotID]
        0=Bracelet / 1=Belt / 2=Torc / 3=Amulet
    x=0xFF かつ d[16]=material 0-7 かつ slotID 4-6 → 素材名+部位名
      例: Steel Helm(slot=5,x=0xFF,mat=1), Iron Boots(slot=6,x=0xFF,mat=0)
    x=0（または x != 0xFF）→ legacy Plate/Chain/Leather（プレフィックスなし、p1 範囲で命名）
      例: Plate Boots(slot=6,p1=45,x=0,mat=0) → plateArmorNames[6]
      material: 0=Iron / 1=Steel / 2=Silver / 3=Elven / 4=Dwarven
                5=Mithril / 6=Adamantium / 7=Ebony
      slotID:   0=Cuirass / 1=Gauntlets / 2=Greaves / 3=Pauldron (L)
                4=Pauldron (R) / 5=Helm / 6=Boots
    上記以外は param1 範囲で判定（Plate/Chain/Leather）
      40-50 → プレート → plateArmorNames[slotID]
      29-39 → チェイン → chainArmorNames[slotID]
      18-28 → レザー  → leatherArmorNames[slotID]
    上記範囲外かつ slotID 7-10 → シールド → plateArmorNames[slotID]
      7=Buckler / 8=Round Shield / 9=Kite shield / 10=Tower shield

- 各文字列テーブルのオフセット（確定）:
    weaponNames        anchor+0x2204  (18 エントリ)
    plateArmorNames    anchor+0x268E  (11 エントリ: Cuirass〜Boots + 4 シールド)
    chainArmorNames    anchor+0x2730  (11 エントリ)
    leatherArmorNames  anchor+0x27D2  (11 エントリ)
    jewelryNames       anchor+0x2028  ( 4 エントリ: Bracelet/Belt/Torc/Amulet)
    spellcastingNames  anchor+0x1DD1  ( 4 エントリ: Mark/Crystal/Bracers/Ring)
    materialNames      anchor+0x2640  ( 8 エントリ: Iron〜Ebony・観測確定)
    baseArmorNames     anchor+0x2424  (11 エントリ: Cuirass〜Tower shield・観測確定)

命名規則の要点:
- シールド (slotID 7-10) とアクセサリ (slotID 0-3) は専用テーブルから名前取得する。
- スペルキャスティングアイテム (hands>2) は hands がチャージ数のため武器と区別する。
- material フィールド (d[16]) 0-7 に対応する Iron/Steel/Silver 等のプレフィックスを構築する。
- x フィールド (d[15]=0xFF) のアクセサリ判定は slot 0-3 に限定する。slot 4-6 で x=0xFF は
  金属防具（Steel Helm 等）にフォールスルーする。
- 素材ベース命名は x=0xFF 条件を伴う。武器も x=0xFF + mat 0-7 で素材プレフィックスを付与する。
- 金属防具命名（x=0xFF + mat 0-7 + slot 4-6）は p1 範囲外でも適用する。高 tier 金属
  （Dwarven/Mithril/Adamantium/Ebony）は p1 > 50 になるため、命名は (slot, material) の
  組合せで決まり p1 値に依存しない。
"""

from __future__ import annotations
import struct

ITEM_SIZE  = 19
INV_SLOTS  = 40

INV_OFFSET            = 0x0212   # anchor + this = inventory[0]
WEAPON_NAMES_OFFSET       = 0x2204   # null-terminated strings ×18
PLATE_NAMES_OFFSET        = 0x268E   # null-terminated strings ×11
CHAIN_NAMES_OFFSET        = 0x2730   # null-terminated strings ×11
LEATHER_NAMES_OFFSET      = 0x27D2   # null-terminated strings ×11
JEWELRY_NAMES_OFFSET      = 0x2028   # null-terminated strings ×4 (観測確定)
SPELLCASTING_NAMES_OFFSET = 0x1DD1   # null-terminated strings ×4 (観測: Mark/Crystal/Bracers/Ring)
MATERIAL_NAMES_OFFSET     = 0x263F   # null-terminated strings ×8: Iron/Steel/Silver/Elven/Dwarven/Mithril/Adamantium/Ebony
BASE_ARMOR_NAMES_OFFSET   = 0x2424   # null-terminated strings ×11: Cuirass/Gauntlets/Greaves/Pauldron(L)/Pauldron(R)/Helm/Boots/...
ARMOR_ENCHANT_NAMES_OFFSET  = 0x254D   # null-terminated strings ×14: of Strength/of Intelligence/...（鑑定済み魔法防具の接尾名）
WEAPON_ENCHANT_NAMES_OFFSET = 0x231F   # null-terminated strings ×14: of Strength/of Shock Resistance/...（鑑定済み魔法武器の接尾名）

# 呪具(スペルキャスティングアイテム)の呪文接尾名テーブル（鑑定後に付く "of <呪文>"）。
# 呪具は material フィールドが呪文カテゴリ(0=攻撃/1=防御/2=その他)、x がカテゴリ内
# インデックスを表す（鑑定前後 diff + 表示名 一致で確定）。
SPELL_ATTACK_NAMES_OFFSET  = 0x1E03   # ×15: of Wizard's Fire/of Shocking/...
SPELL_DEFENSE_NAMES_OFFSET = 0x1F0A   # ×9 : of Stamina/of Sanctuary/...
SPELL_MISC_NAMES_OFFSET    = 0x1F9F   # ×8 : of Light/of Wanderlight/...
SPELL_ATTACK_COUNT  = 15
SPELL_DEFENSE_COUNT = 9
SPELL_MISC_COUNT    = 8

# flags バイト（オフセット14）: bit0=魔法アイテム, bit1=未鑑定, bit7=装備中
FLAG_MAGIC        = 0x01
FLAG_UNIDENTIFIED = 0x02

# エンチャント番号テーブルのエントリ数（armor/weapon とも 14）
ENCHANT_COUNT = 14

# 装身具(ジュエリー)の鑑定後素材は materialNames の高位5素材
# (Elven/Dwarven/Mithril/Adamantium/Ebony = index 3-7)。material フィールド 0-4 に
# この base を加える（Torc mat=2 → materialNames[5]=Mithril を実機確認）。
ACCESSORY_MATERIAL_BASE = 3

# シールドが plateArmorNames の何番目から始まるか
SHIELD_SLOT_MIN = 7   # Buckler
SHIELD_SLOT_MAX = 10  # Tower shield

# 防具部位スロット ID の上限（0-6 = Cuirass〜Boots、これを超えるとシールド）
ARMOR_PIECE_SLOT_MAX = 6

# コンディション（観測確定値: anchor+0x5DE8 / anchor+0x5E00）
_CONDITION_NAMES_JA   = ["壊れている", "使用不可", "傷あり", "劣化",
                          "使用済み", "やや使用", "ほぼ新品", "新品"]
_CONDITION_THRESHOLDS = [1, 5, 15, 40, 60, 75, 91]


def _weight_str(weight_raw: int) -> str:
    if weight_raw == 0:
        return "—"
    kg = weight_raw / 256
    return f"{kg:.1f}kg" if kg != int(kg) else f"{int(kg)}.0kg"


def _condition_str(item: dict) -> str:
    # スペルキャスティングアイテム（hands>2）は hands フィールドにチャージ残数。
    # ゲーム内表示「N charge(s) left」と一致する。鑑定済み未判明時に魔法効果の
    # 内容は出せないため、回数のみ「状態」列に表示する。
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
    """null 終端文字列の連続を最大 max_count 個読む。"""
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
# 防具 slot_id 0-6 → 装着部位（素材種別ではなく装着部位ラベルで表す）
# slot_id は素材に依らず共通（Plate/Chain/Leather で同じ ID が同じ部位を示す）
_ARMOR_SLOT_LABELS = {
    0: "胴部",    # Cuirass
    1: "篭手",    # Gauntlets
    2: "脛当",    # Greaves
    3: "肩(左)",  # Pauldron L
    4: "肩(右)",  # Pauldron R
    5: "頭部",    # Helm
    6: "靴",      # Boots
}


def _slot_label(item: dict) -> str:
    """アイテム種別から装着部位ラベルを返す。"""
    hands = item["hands"]
    sid   = item["slot_id"]
    p1    = item["param1"]
    if hands in (1, 2):
        return "片手" if hands == 1 else "両手"
    if hands > 2:
        return _SPELLCASTING_SLOT_LABELS.get(sid, "呪具")
    # x=0xFF はジュエリー slot 0-3 (Bracelet/Belt/Torc/Amulet) のみアクセサリ確定。
    # slot 4-6 (Pauldron R/Helm/Boots) は金属ベース防具 (Iron/Steel/etc.) で x=0xFF を取るため
    # アクセサリ判定を slot 0-3 に限定する（Steel Helm 等の誤認識を避ける）。
    if item["x"] == 0xFF and 0 <= sid <= 3:
        return _ACCESSORY_SLOT_LABELS.get(sid, "装身")
    # 金属防具（x=0xFF + slot 4-6）は p1 値に依存せず armor 部位ラベル。
    # 高 tier 金属（Dwarven/Mithril/Adamantium/Ebony）は p1 が 50 を超えうる。
    if item["x"] == 0xFF and 4 <= sid <= 6:
        return _ARMOR_SLOT_LABELS.get(sid, "防具")
    if 18 <= p1 <= 50:
        return _ARMOR_SLOT_LABELS.get(sid, "防具")
    if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
        return "盾"
    return _ACCESSORY_SLOT_LABELS.get(sid, "装身")


def _classify_item(item: dict) -> tuple[str, int]:
    """アイテム種別と防具素材IDを返す。
    item_type: "weapon" | "armor" | "shield" | "accessory" | "spellcasting"
    armor_material_id: 0=Leather, 1=Chain, 2=Plate, -1=該当なし
    """
    sid   = item["slot_id"]
    hands = item["hands"]
    p1    = item["param1"]
    if hands in (1, 2):
        return "weapon", -1
    if hands > 2:
        return "spellcasting", -1
    # x=0xFF はジュエリー slot 0-3 のみアクセサリ確定。
    # slot 4-6 で x=0xFF は金属ベース防具のため fall-through（p1 範囲で armor 判定）。
    if item["x"] == 0xFF and 0 <= sid <= 3:
        return "accessory", -1
    # 金属防具（x=0xFF + mat 0-7 + slot 4-6）は p1 値に依存せず armor 確定。
    # 高 tier 金属で p1 > 50 の場合に旧コードはフォールスルーして "Armor#p1" になっていた。
    # 金属防具は重装相当のため armor_material_id=2 (Plate 同等) として扱う。
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
    """鑑定済み魔法アイテムのエンチャント番号 (x フィールド) を返す。

    flags bit0=魔法アイテム / bit1=未鑑定。鑑定済み (bit1=0) の魔法品で
    x が素材マーカー 0xFF でなくエンチャント番号範囲 (0-13) のときのみ番号を返す。
    未鑑定・非魔法・素材ベース品 (x=0xFF) は None（接尾エンチャント名を出さない）。

    実機確認 (鑑定前後 diff): 鑑定では flags bit1 のみ解除され x/material/attr は不変。
    x はエンチャント番号で、armor/weaponEnchantmentNames[x] が表示名の接尾になる。
    """
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

    # 武器（hands=1 または 2）
    if hands in (1, 2):
        if 0 <= sid < len(weapon_names):
            base = weapon_names[sid]
        else:
            return f"Weapon#{p1}"
        # 武器も x=0xFF + mat 0-7 で素材プレフィックス付与（Elven Longsword 等）
        # x=0xFF は「d[16]=metal_id を素材として使用」のマーカー。
        # x=0 + mat=0xFF は legacy の素材無し武器（Dagger, Katana 等）→ プレフィックス無し。
        if (item["x"] == 0xFF
                and 0 <= mat_id < len(material_names)):
            return f"{material_names[mat_id]} {base}"
        # 鑑定済み魔法武器: ベース名 + エンチャント接尾名（例: Longsword of Fire Resistance）。
        ei = _ench_index(item)
        if ei is not None and ei < len(weapon_enchant_names):
            return f"{base} {weapon_enchant_names[ei]}"
        return base

    # スペルキャスティングアイテム（hands>2 → hands はチャージ数）
    # slotID: 0=Mark / 1=Crystal / 2=Bracers / 3=Ring
    if hands > 2:
        base = (spellcasting_names[sid]
                if 0 <= sid < len(spellcasting_names) else f"Spellcasting#{sid}")
        # 鑑定済み呪具: material=呪文カテゴリ(0=攻撃/1=防御/2=その他)・x=インデックス
        # で呪文接尾名を付ける（例: Mark of Wizard's Fire / Crystal of Healing）。
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

    # 鑑定済み魔法防具/盾: 汎用ベース名 + (任意の素材) + エンチャント接尾名。
    # 実機確認: 未鑑定の "Plate Helm" は鑑定後 "Helm of Willpower" となり、
    # plate/chain/leather 段名ではなく汎用ベース名 (baseArmorNames) + エンチャント名で
    # 表示される。x=エンチャント番号 (!=0xFF) のため素材ベース品 (x=0xFF) や
    # ジュエリー (x=0xFF) とは衝突しない。
    ei = _ench_index(item)
    if ei is not None and 0 <= sid < len(base_armor_names):
        base = base_armor_names[sid]
        if 0 <= mat_id < len(material_names):
            base = f"{material_names[mat_id]} {base}"
        if ei < len(armor_enchant_names):
            return f"{base} {armor_enchant_names[ei]}"

    # x=0xFF はジュエリー slot 0-3 のみアクセサリ命名。
    # x=0xFF は「d[16]=metal_id を素材として使用」を意味するだけで、
    # アクセサリ確定マーカーではない。slot 4-6 (Pauldron R/Helm/Boots) で
    # x=0xFF + mat=metal_id は Steel Helm / Iron Boots 等の金属防具。
    # 観測例: Bracelet(slot=0,x=0xFF,mat=4), Torc(slot=2,x=0xFF,mat=2),
    # Steel Helm(slot=5,x=0xFF,mat=1) はアクセサリでなく金属防具。
    if item["x"] == 0xFF and 0 <= sid <= 3:
        base = (jewelry_names[sid]
                if 0 <= sid < len(jewelry_names) else f"Jewelry#{sid}")
        # 鑑定済み魔法装身具: 高位5素材(materialNames[mat+3])を前置（例: Mithril Torc）。
        if is_magic and is_identified:
            mi = mat_id + ACCESSORY_MATERIAL_BASE
            if 0 <= mi < len(material_names):
                return f"{material_names[mi]} {base}"
        return base

    # 金属防具命名（x=0xFF + mat 0-7 + slot 4-6）は p1 範囲チェックの外に置く。
    # 高 tier 金属（Dwarven/Mithril/Adamantium/Ebony）は p1 > 50 になりうるため、
    # `18 <= p1 <= 50` ブロック内の判定では捕捉できない。
    # 観測例: Dwarven Helm(slot=5,p1=55,x=0xFF,mat=4)。
    # 命名は (slot, material) の組合せで決まり p1 値に依存しない。
    if (item["x"] == 0xFF
            and 0 <= mat_id < len(material_names)
            and 4 <= sid <= ARMOR_PIECE_SLOT_MAX):
        base = base_armor_names[sid] if sid < len(base_armor_names) else f"Slot#{sid}"
        return f"{material_names[mat_id]} {base}"

    # 防具（hands=0、p1 が素材範囲 18-50）
    if 18 <= p1 <= 50:
        # Plate/Chain/Leather: param1 範囲テーブルを使用（legacy 経路、x != 0xFF）
        # 注: x=0xFF + slot 4-6 は上の金属防具命名で先に捕捉済み。slot 0-3 は jewelry。
        # ここに到達するのは x=0 (mat=0) または x=Plate(2)/Chain(1)/Leather(0) 系の legacy。
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
        # 素材範囲外 — シールドまたはアクセサリを slotID で判別
        # シールド (slotID 7-10): 全素材テーブルで共通の名前を持つので plateNames を使用
        if SHIELD_SLOT_MIN <= sid <= SHIELD_SLOT_MAX:
            if 0 <= sid < len(plate_names):
                return plate_names[sid]
        # アクセサリ/ジュエリー (slotID 0-3): jewelryNames を参照
        elif 0 <= sid < len(jewelry_names):
            return jewelry_names[sid]

    return f"Armor#{p1}"


def read_equipment_items(analyzer, anchor: int) -> list[dict]:
    """
    非空のインベントリスロットを辞書リストで返す。

    Returns list of:
        {"en": str, "slot_id": int, "hands": int,
         "health": int, "max_hp": int, "price": int,
         "equipped": bool, "weight": str, "condition": str, "effect": str}
    """
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
            "is_unidentified":  bool(item["flags"] & 0x02),   # flags bit1=未鑑定（未鑑定品は bit0+bit1 同時セット。bit0=1/bit1=0 は識別済み魔法品 → bit1 が真の未鑑定フラグ）
            "item_type":        item_type,
            "armor_material_id": armor_material_id,
            "slot_label":       _slot_label(item),
            "weight":           _weight_str(item["weight"]),
            "condition":        _condition_str(item),
            "effect":           _effect_str(item),
        })
    return items
