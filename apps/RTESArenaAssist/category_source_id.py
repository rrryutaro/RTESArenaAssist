"""category_source_id.py — カテゴリ別の legacy_id → source_id 決定論導出。

公開 bundle entry の `source.source_id`（原文非含の構造キー）を、現 `_original` の
legacy_id 構造から決定論導出する。カテゴリを増分対応する（未対応は None）。

source_id は原文・表示名・地名・旧 legacy_id を含まない（数値構造/資産位置のみ）。
"""
from __future__ import annotations

import json
import os
import re

import i18n_source_address as addr

_I18N_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n")
_AEXE_DIR = os.path.join(_I18N_DIR, "_aexe_template")
_LOCATION_CITYDATA_MAP = os.path.join(_I18N_DIR, "location_citydata_map.json")
# placeholder_values %oc（職業語彙）の TEMPLATE.DAT #0262 content 照合マップ（dev-only・slug 原文断片を
# legacy_id key に含むため公開DENY＝公開 spec 非同梱）。値は block/index のみ＝出力 source_id は原文非含。
_PH_OC_SOURCE_MAP = os.path.join(_I18N_DIR, "placeholder_values_oc_source.json")

_BE_PREFIX = "template_dat_building_entry."
_NNC_PREFIX = "npc_name_chunks.chunks."


def building_entry_source_id(legacy_id: str) -> str | None:
    """`template_dat_building_entry.<block>.copy<c>.<idx>` → `template:<block>:<c>:<idx>`。"""
    if not legacy_id.startswith(_BE_PREFIX):
        return None
    rest = legacy_id[len(_BE_PREFIX):]          # 例 "0000_a.copy0.2"
    if ".copy" not in rest:
        return None
    block, tail = rest.rsplit(".copy", 1)        # "0000_a", "0.2"
    parts = tail.split(".")
    if len(parts) != 2:
        return None
    try:
        copy_i, idx_i = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return addr.template_id(block, idx_i, copy=copy_i)


def npc_name_chunks_source_id(legacy_id: str) -> str | None:
    """`npc_name_chunks.chunks.<chunk>.<idx>` → `namechnk:<chunk>:<idx>`。

    `literals`（Assist curation・非 chunk）等は対象外で None。
    """
    if not legacy_id.startswith(_NNC_PREFIX):
        return None
    parts = legacy_id[len(_NNC_PREFIX):].split(".")
    if len(parts) != 2:
        return None
    try:
        chunk_i, idx_i = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return addr.namechnk_id(chunk_i, idx_i)


_INF_PREFIX = "inf_text."
_RIDDLE_SUBS = ("question", "correct", "wrong")


def inf_text_source_id(legacy_id: str) -> str | None:
    """INF @TEXT の legacy_id → source_id。

    `inf_text.<name>.INF_<idx>.0`            → `inf:<name>.INF:text:<idx>`
    `inf_text.<name>.INF_<idx>.question` 等  → `inf:<name>.INF:text:<idx>:<field>`（riddle）

    inf_text は混在源（INF @TEXT／_CHARGEN_（QUESTION/A.EXE）／TEMPLATE_DAT cinematic）。
    本 resolver は **INF @TEXT のみ**対応し、`_CHARGEN_`/`TEMPLATE_DAT` は別源として None
    （後段で question/aexe/curation 経路を追加）。
    """
    if not legacy_id.startswith(_INF_PREFIX):
        return None
    rest = legacy_id[len(_INF_PREFIX):]
    # _CHARGEN_Q_<n>（キャラ作成 40 問・QUESTION.TXT 由来）= question:<n>[:display]。
    m = re.match(r"^_CHARGEN_Q_(\d+)__0\.(0|display)$", rest)
    if m:
        base = addr.question_id(int(m.group(1)))
        return base if m.group(2) == "0" else base + ":display"
    # _CHARGEN_ UI/結果（A.EXE char creation）は aexe:char_creation:* へ（covered のみ・
    # 部分カバレッジの残は None）。_CHARGEN_Q は上で question 経路済み。
    # TEMPLATE_DAT cinematic は source_id なし（npc_dialog template と二重採番回避）。
    if rest.startswith("_CHARGEN_"):
        import arena_regen
        sid = arena_regen.chargen_ui_source_id(rest)
        if sid is not None:
            return sid
        # A.EXE 採取対象外の Assist 作 chargen UI（%s 実行時置換系=NAME/PROVINCE/
        # PROVINCE_CONFIRM・原文なし=CLASS_LIST/DISTRIBUTE_POINTS・cinematic=OPENING）。
        # Arena surface を持たない（localpack 非依存）が訳は公開 bundle に id 単位で
        # 存在する。構造 source_id（擬似 INF 名）を与え、id 経由で公開解決させる。
        m = re.match(r"^(_CHARGEN_\w*?)_(\d+)\.(0|display)$", rest)
        if m:
            base = addr.inf_id(m.group(1), int(m.group(2)))
            return base if m.group(3) == "0" else base + ":display"
        return None
    if rest.startswith("TEMPLATE_DAT"):
        return None
    if ".INF_" not in rest:
        return None
    name, tail = rest.split(".INF_", 1)          # "AGTEMPL", "8.question"
    parts = tail.split(".")
    if len(parts) != 2:
        return None
    idx_s, sub = parts
    try:
        idx_i = int(idx_s)
    except ValueError:
        return None
    base = addr.inf_id(name + ".INF", idx_i)      # inf:AGTEMPL.INF:text:8
    if sub == "0":
        return base
    if sub in _RIDDLE_SUBS:
        return base + ":" + sub
    return None


_NPCD_PREFIX = "npc_dialog."
_AKEY_RE = re.compile(r"^A\d")


def npc_dialog_source_id(legacy_id: str) -> str | None:
    """npc_dialog の legacy_id → source_id。

    TEMPLATE-scope: `npc_dialog.<block>.<variant>` → `template:<block>:<variant>`（2 セグ・
    building_entry は copy 次元あり 3 セグで衝突しない）。
    A-key（`npc_dialog.A###.*`＝A.EXE UI / trade / 修理屋 由来）は `arena_regen` の構造規則で
    `aexe:akey:*` / `tradetext:*` / `template:<block>:0:<variant>` へ振り分ける（curation 変種は None）。
    """
    if not legacy_id.startswith(_NPCD_PREFIX):
        return None
    rest = legacy_id[len(_NPCD_PREFIX):]          # "0100.0" / "A001.0" / "A604.9"
    if _AKEY_RE.match(rest):
        return _akey_source_id(rest)
    if "." not in rest:
        return None
    block, var = rest.rsplit(".", 1)
    try:
        var_i = int(var)
    except ValueError:
        return None
    return addr.template_id(block, var_i)          # template:<block>:<variant>


def _akey_source_id(akey: str) -> str | None:
    """npc_dialog A-key（prefix 無し）→ source_id。`arena_regen` の構造規則を単一住所として使う。"""
    import arena_regen
    return arena_regen.akey_structural_source_id(akey, set(_aexe_template("akey")))


# ACD 固定表カテゴリ（legacy_id → aexe:<group>:<table>:<src_index>）。
#   spells/equipment_suffixes/item_enchantments は equipment.*_spell_names /
#   *_enchantment_names を横断共有し、同一 source 位置が複数カテゴリの整数ID に対応する。
#   source_id_map schema v2（multi-target）でこれを許容（1 source_id→[整数ID...]・fan-out）。
_AEXE_CATEGORIES = frozenset({
    "calendar", "chargen_provinces", "classes", "location_types",
    "protect_locations", "races", "titles",
    "spells", "equipment_suffixes", "item_enchantments",
    "item_materials", "monsters",
    "equipment", "character", "mages", "dungeon", "items",
    # source-backed 再分類（live_surface→arena_generated）。
    "settlement_types", "chargen_race_descriptions",
    # ACD.EXE 固定テーブル由来の再分類（partial）。
    "pronouns", "relations", "ask_about_menu",
    # status_buffer_text の day/month を既存 calendar 表へ共有（19/35）。
    "status_buffer_text",
    # 小 resolver（partial）：descriptors man/woman・status_terms war/peace・
    # npc_traits Mad を ACD 表へ source-back。残は synthetic/D。
    "descriptors", "status_terms", "npc_traits",
})

_aexe_cache: dict[str, dict] = {}


def _owned_i18n_json(disk_path: str, seed_rel: str) -> dict:
    """Assist 所有 i18n データ（_aexe_template 等）を読む: disk 優先・無ければ exe 内 seed。

    公開 frozen では `_internal/i18n` を撤去（seed 集約）したため disk 直読みは失敗する。
    その場合は app_resources（exe 内 seed）から読む。どちらも無ければ空 dict。
    """
    try:
        with open(disk_path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        pass
    try:
        import app_resources
        txt = app_resources.read_text(seed_rel)
        if txt is not None:
            return json.loads(txt)
    except Exception:  # noqa: BLE001 - seed 不在/不正は空 dict
        pass
    return {}


def _aexe_template(category: str) -> dict:
    if category not in _aexe_cache:
        _aexe_cache[category] = _owned_i18n_json(
            os.path.join(_AEXE_DIR, category + ".json"),
            f"i18n/_aexe_template/{category}.json")
    return _aexe_cache[category]


# public_builtin_literal（極小一般 UI literal）。Arena 抽出 source でも
# Assist UI でもない公開安全 generic literal。**最小 allowlist（初期 Yes/No のみ）**。
# key → 注入 surface（生成時に注入＝Arena 資産/save 非依存）。
_PUBLIC_BUILTIN_SURFACES = {
    "generic.yes": "Yes",
    "generic.no": "No",
}
# legacy_id → public_builtin key（対象 entry のみ）。
_PUBLIC_BUILTIN_LEGACY = {
    "mages.Yes": "generic.yes",
    "mages.No": "generic.no",
}


def public_builtin_source_id(legacy_id: str) -> str | None:
    """public_builtin_literal 対象 legacy_id → `public_builtin:<key>`（allowlist 外は None）。"""
    key = _PUBLIC_BUILTIN_LEGACY.get(legacy_id)
    return addr.public_builtin_id(key) if key else None


def public_builtin_surfaces() -> dict:
    """{source_id: surface} の注入用 allowlist（生成器・reproduction が読む）。"""
    return {addr.public_builtin_id(k): v for k, v in _PUBLIC_BUILTIN_SURFACES.items()}


# mages 魔法アイテム名（composite item+enchantment）。
# A.EXE の spellcasting_item_names ＋ {attack,defensive,misc}_spell_names の合成。
# legacy_id → (item_idx, spell_kind, spell_idx)。JA はバンドル保持（語順反転含む）＝lossless。
_MAGES_MAGIC_ITEM = {
    "mages.Mark of Light": (0, "misc", 0),       # Mark + of Light
    "mages.Mark of Stamina": (0, "defensive", 0),  # Mark + of Stamina
    "mages.Crystal of Wizard's Fire": (1, "attack", 0),  # Crystal + of Wizard's Fire
}
_MAGIC_ITEM_TABLE = {
    "attack": "equipment.attack_spell_names",
    "defensive": "equipment.defensive_spell_names",
    "misc": "equipment.misc_spell_names",
}


def mages_magic_item_source_id(legacy_id: str) -> str | None:
    """mages 魔法アイテム名 → `magicitem:<item_idx>:<kind>:<spell_idx>`（他は None）。"""
    rec = _MAGES_MAGIC_ITEM.get(legacy_id)
    return addr.magic_item_id(*rec) if rec else None


# mages 素材+装身具名（material + accessory）。material_names ＋ enhancement_item_names。
_MAGES_MATERIAL_ITEM = {
    "mages.Mithril Belt": (5, 1),  # material_names[5]=Mithril + enhancement_item_names[1]=Belt
}


def mages_material_item_source_id(legacy_id: str) -> str | None:
    """mages 素材+装身具名 → `materialitem:<mat_idx>:<acc_idx>`（他は None）。"""
    rec = _MAGES_MATERIAL_ITEM.get(legacy_id)
    return addr.material_item_id(*rec) if rec else None


def compose_material_item(material_idx: int, acc_idx: int, tables: dict) -> str | None:
    """harvest table から素材+装身具名を合成（`<material> <accessory>`）。"""
    mats = tables.get("equipment.material_names")
    accs = tables.get("equipment.enhancement_item_names")
    if not mats or not accs:
        return None
    if 0 <= material_idx < len(mats) and 0 <= acc_idx < len(accs):
        m, a = mats[material_idx], accs[acc_idx]
        if isinstance(m, str) and isinstance(a, str) and m and a:
            return f"{m} {a}"
    return None


def material_item_surfaces(tables: dict) -> dict:
    """{source_id: surface} を harvest table から合成（reproduction 用）。"""
    out = {}
    for rec in set(_MAGES_MATERIAL_ITEM.values()):
        surf = compose_material_item(rec[0], rec[1], tables)
        if surf:
            out[addr.material_item_id(*rec)] = surf
    return out


def compose_magic_item(item_idx: int, spell_kind: str, spell_idx: int,
                       tables: dict) -> str | None:
    """harvest table から魔法アイテム名を合成（`<item> <of-spell>`）。導出不能は None。"""
    items = tables.get("equipment.spellcasting_item_names")
    spells = tables.get(_MAGIC_ITEM_TABLE.get(spell_kind, ""))
    if not items or not spells:
        return None
    if 0 <= item_idx < len(items) and 0 <= spell_idx < len(spells):
        item, spell = items[item_idx], spells[spell_idx]
        if isinstance(item, str) and isinstance(spell, str) and item and spell:
            return f"{item} {spell}"
    return None


def magic_item_surfaces(tables: dict) -> dict:
    """{source_id: surface} を harvest table から合成（reproduction 用）。"""
    out = {}
    for rec in set(_MAGES_MAGIC_ITEM.values()):
        surf = compose_magic_item(rec[0], rec[1], rec[2], tables)
        if surf:
            out[addr.magic_item_id(*rec)] = surf
    return out


# mages 合成効果名（FULL）→ spell effect 構造（effect_id, sub_effect_id）。
# `spell_effect_structure._VERIFIED_COMPOSITE`（verified 合成名）＋ Transfer Attribute(13,0) を
# 逆引きして mages.<name> → (eid, sub) を作る。surface は `surface_for` で構造から決定論再構成。
def _mages_spell_effect_struct() -> dict:
    if not hasattr(_mages_spell_effect_struct, "_cache"):
        import spell_effect_structure as ses
        m = {f"mages.{name}": struct for struct, name in ses._VERIFIED_COMPOSITE.items()}
        m["mages.Transfer Attribute"] = (13, 0)
        _mages_spell_effect_struct._cache = m
    return _mages_spell_effect_struct._cache


def mages_spell_effect_source_id(legacy_id: str) -> str | None:
    """mages 合成効果名 → `spelleffect:<eid>:<sub>`（verified surface のみ・他は None）。"""
    struct = _mages_spell_effect_struct().get(legacy_id)
    if struct is None:
        return None
    import spell_effect_structure as ses
    surf = ses.surface_for(struct[0], struct[1])
    # 構造から verified 系 surface（再構成可能）でない場合は source_id 化しない。
    if not surf or not surf[1].startswith("verified"):
        return None
    return addr.spell_effect_id(struct[0], struct[1])


def spell_effect_surfaces() -> dict:
    """{source_id: surface} を構造から決定論合成（reproduction 用・Arena 資産非依存）。"""
    import spell_effect_structure as ses
    out = {}
    for struct in set(_mages_spell_effect_struct().values()):
        surf = ses.surface_for(struct[0], struct[1])
        if surf and surf[1].startswith("verified"):
            out[addr.spell_effect_id(struct[0], struct[1])] = surf[0]
    return out


# mages 標準呪文名 → SPELLSG.65 index。
# SPELLSG.65 は OpenTESArena initStandardSpells が読む固定マスタ＝save slot 非依存・index 安定
# （`test_spellsg65_source.py` が実ファイルで lock）。legacy_id は `mages.<SpellName>`。
_MAGES_SPELLSG65_INDEX = {
    "Stamina": 0, "Sanctuary": 1, "Wanderlight": 3, "Wizard Lock": 4,
    "Orc Strength": 5, "Wizard's Fire": 6, "Strength Leech": 11, "Ice Bolt": 12,
    "Resist Fire": 14, "Resist Cold": 15, "Fireball": 16, "Earth Wall": 17,
    "Witch's Curse": 19, "Cure Poison": 21, "Resist Shock": 23, "Ice Storm": 26,
    "Heal True": 33, "Fire Storm": 35, "Spell Shield": 36, "Free Action": 37,
    "Troll's Blood": 41, "Cause Disease": 59, "Cure Disease": 60,
}


def mages_spellsg65_source_id(legacy_id: str) -> str | None:
    """mages 標準呪文 legacy_id（`mages.<SpellName>`）→ `spellsg65:standard:<index>`。

    SPELLSG.65 由来でない mages entry は None（呼出側で aexe 経路へフォールバック）。
    """
    if not legacy_id.startswith("mages."):
        return None
    name = legacy_id[len("mages."):]
    idx = _MAGES_SPELLSG65_INDEX.get(name)
    if idx is None:
        return None
    return addr.spellsg65_id(idx)


# item_materials の armor 防具クラス prefix（Leather/Chain/Plate）。
# composite armor name table（leather/chain/plate_armor_names）由来＝MaterialNames とは別系統。
# legacy_id `item_materials.{0,1,2}.0` → material（leather/chain/plate）。
_ITEM_MATERIALS_ARMOR_PREFIX = {
    "item_materials.0.0": "leather",
    "item_materials.1.0": "chain",
    "item_materials.2.0": "plate",
}


def item_materials_armor_prefix_source_id(legacy_id: str) -> str | None:
    """item_materials の Leather/Chain/Plate → `armor_prefix:<material>`（他は None）。"""
    material = _ITEM_MATERIALS_ARMOR_PREFIX.get(legacy_id)
    return addr.armor_prefix_id(material) if material else None


def derive_armor_prefix(material: str, comp_table: list, base_table: list) -> str | None:
    """composite armor name の index 0 と base armor name の差分で素材 prefix を導出する。

    例: leather_armor_names[0]="Leather Cuirass" − armor_names[0]="Cuirass" → "Leather"。
    全 index で同一 prefix のはずだが、index 0（Cuirass）で代表導出する。
    material は未使用（呼出側の対応付け明示用）。導出不能は None。
    """
    if not comp_table or not base_table:
        return None
    full, part = comp_table[0], base_table[0]
    if isinstance(full, str) and isinstance(part, str) and full.endswith(part):
        prefix = full[: len(full) - len(part)].strip()
        return prefix or None
    return None


def aexe_source_id(category: str, legacy_id: str) -> str | None:
    """ACD 固定表カテゴリの legacy_id → `aexe:<group>:<table>:<src_index>`。

    `_aexe_template/<cat>.json` の `src_table`（"<group>.<table>"）＋`src_index` を使う
    （原文非含・表示語 label を使わない）。
    """
    rec = _aexe_template(category).get(legacy_id)
    if not isinstance(rec, dict):
        return None
    src_table = rec.get("src_table")
    src_index = rec.get("src_index")
    if not src_table or src_index is None:
        return None
    if "." in src_table:
        group, table = src_table.split(".", 1)
    else:
        group, table = category, src_table
    return addr.aexe_table_id(group, table, src_index)


# カテゴリ → resolver（増分追加）。
_RESOLVERS = {
    "template_dat_building_entry": building_entry_source_id,
    "npc_name_chunks": npc_name_chunks_source_id,
    "inf_text": inf_text_source_id,
    "npc_dialog": npc_dialog_source_id,
}


_loc_cd_cache: dict | None = None


def _location_citydata_map() -> dict:
    global _loc_cd_cache
    if _loc_cd_cache is None:
        try:
            with open(_LOCATION_CITYDATA_MAP, encoding="utf-8") as fh:
                _loc_cd_cache = json.load(fh).get("map", {})
        except OSError:
            _loc_cd_cache = {}
    return _loc_cd_cache


def location_citydata_source_id(legacy_id: str) -> str | None:
    """CITYDATA 由来 location の app_id → `citydata:<...>`（dev マップから・slug は使わない）。"""
    return _location_citydata_map().get(legacy_id)


_ph_oc_cache: dict | None = None


def _ph_oc_source_map() -> dict:
    global _ph_oc_cache
    if _ph_oc_cache is None:
        try:
            with open(_PH_OC_SOURCE_MAP, encoding="utf-8") as fh:
                _ph_oc_cache = {k: v for k, v in json.load(fh).items()
                                if not k.startswith("_")}
        except OSError:
            _ph_oc_cache = {}
    return _ph_oc_cache


def placeholder_values_source_id(legacy_id: str) -> str | None:
    """placeholder_values `%oc`（職業語彙）の legacy_id → `template:<block>:<index>`。

    TEMPLATE.DAT #0262 への content 照合マップ（dev-only）から block/index を引く（slug は使わない＝
    出力 source_id は原文非含）。%oc 以外・未照合（case 変種/真の不在）は None＝derived/live_surface 側で扱う。
    """
    rec = _ph_oc_source_map().get(legacy_id)
    if not isinstance(rec, dict):
        return None
    block = rec.get("block")
    index = rec.get("index")
    if block is None or index is None:
        return None
    return addr.template_id(block, int(index))


def placeholder_values_oc_keys() -> set[str]:
    """%oc source-backed（arena_generated）の legacy_id 集合（resolution_kind 判定用）。"""
    return set(_ph_oc_source_map().keys())


_PH_DERIVED_MAP = os.path.join(_I18N_DIR, "placeholder_values_derived_map.json")
_ph_derived_cache: dict | None = None


def _ph_derived_map() -> dict:
    global _ph_derived_cache
    if _ph_derived_cache is None:
        try:
            with open(_PH_DERIVED_MAP, encoding="utf-8") as fh:
                _ph_derived_cache = {k: v for k, v in json.load(fh).items()
                                     if not k.startswith("_")}
        except OSError:
            _ph_derived_cache = {}
    return _ph_derived_cache


def placeholder_redirect_target(legacy_id: str):
    """derived placeholder（%cn/%oth/%ra 等で **訳一致**）の legacy_id → target 整数 ID。

    derived は target ID を canonical とし placeholder 側は redirect。target が別訳
    （文脈差）の entry は derived でなく own＝本 map に含めない（None）。map は dev-only（slug 原文断片）。
    """
    rec = _ph_derived_map().get(legacy_id)
    if isinstance(rec, dict):
        tid = rec.get("target_id")
        return int(tid) if tid is not None else None
    return None


def placeholder_derived_keys() -> set[str]:
    """derived redirect の legacy_id 集合（resolution_kind 判定用）。"""
    return set(_ph_derived_map().keys())


def location_citydata_keys() -> set[str]:
    """CITYDATA 由来 location の app_id 集合（location カテゴリの retire 判定用）。"""
    return set(_location_citydata_map().keys())


def source_id_for(category: str, legacy_id: str) -> str | None:
    """対応カテゴリの legacy_id から source_id を返す（未対応は None）。"""
    if category == "mages":
        # Yes/No は public_builtin_literal を最優先。
        sid = public_builtin_source_id(legacy_id)
        if sid:
            return sid
        # 標準呪文名は SPELLSG.65 を優先。
        sid = mages_spellsg65_source_id(legacy_id)
        if sid:
            return sid
        # 合成効果名（FULL）は spell effect 構造で再構成。
        sid = mages_spell_effect_source_id(legacy_id)
        if sid:
            return sid
        # 魔法アイテム名は composite item+enchantment で再構成。
        sid = mages_magic_item_source_id(legacy_id)
        if sid:
            return sid
        # 素材+装身具名（Mithril Belt 等）で再構成。
        sid = mages_material_item_source_id(legacy_id)
        if sid:
            return sid
        return aexe_source_id(category, legacy_id)
    if category == "item_materials":
        # Leather/Chain/Plate は composite armor 由来 prefix、metal 8 は aexe 表。
        sid = item_materials_armor_prefix_source_id(legacy_id)
        if sid:
            return sid
        return aexe_source_id(category, legacy_id)
    if category in _AEXE_CATEGORIES:
        return aexe_source_id(category, legacy_id)
    if category == "location_citydata":
        return location_citydata_source_id(legacy_id)
    if category == "placeholder_values":
        # %oc subgroup のみ source-backed（TEMPLATE.DAT #0262）。他 subgroup は None
        # （derived/live_surface）。
        return placeholder_values_source_id(legacy_id)
    fn = _RESOLVERS.get(category)
    return fn(legacy_id) if fn else None


def supported_categories() -> set[str]:
    return set(_RESOLVERS.keys()) | set(_AEXE_CATEGORIES) | {"location_citydata"}


__all__ = ["source_id_for", "building_entry_source_id", "supported_categories"]
