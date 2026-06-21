"""
spell_reader.py — スペルブック呪文リスト読み取り

NPCData+870 の knownSpellCount と +871 の knownSpellIDs から習得呪文 ID を読み、
SPELLSG.NN ファイルの SpellData 配列から呪文名を取得する。

SpellData 構造（85 bytes / spell）:
  +0x00: params[36]   (uint8_t[36])
  +0x24: targetType   (uint8_t)
  +0x25: unknown      (uint8_t)
  +0x26: element      (uint8_t)
  +0x27: flags        (uint16_t LE)
  +0x29: effects[3]   (uint8_t[3])
  +0x2C: subEffects[3](uint8_t[3])
  +0x2F: affectedAttrs(uint8_t[3])
  +0x32: cost         (uint16_t LE)
  +0x34: name[33]     (char[33])  ← 呪文名 null 終端 ASCII

live memory offsets:
  knownSpellCount: anchor+0x1A4+870 = anchor+0x50A
  knownSpellIDs:   anchor+0x1A4+871 = anchor+0x50B
"""

from __future__ import annotations
import os

from spell_effect_compose import (
    _lookup_pair,
    _active_effect_slot,
    _resolve_effect_name,
    _effect_details_from_arrays,
    _decode_spell_effect_segments,
    _normalize_spell_effect_text,
    _attach_effect_texts,
    _fill_missing_spellmaker_effect_texts,
    translate_effect_text,
)

# translate_effect_text は spell_effect_compose の公開名として利用可能。
# spell_reader 経由の参照を維持するため名前空間に保持する。
__all__ = [
    "load_spellsg",
    "read_spell_detail",
    "read_spellbook_items",
    "translate_effect_text",
]

NPCDATA_BASE       = 0x1A4
SPELL_COUNT_OFFSET = NPCDATA_BASE + 870   # = 0x50A
SPELL_IDS_OFFSET   = NPCDATA_BASE + 871   # = 0x50B

SPELL_DATA_SIZE    = 85
SPELL_NAME_OFFSET  = 0x34   # SpellData.name フィールド
SPELL_NAME_LEN     = 33
MAX_KNOWN_SPELLS   = 160    # 標準128 + 作成呪文。knownSpellIDs の上限に合わせる。


def load_spellsg(game_dir: str) -> dict[int, str]:
    """save_dir 内の SPELLSG.NN を探して spell_id → spell_name 辞書を返す。
    読み取れない場合は空辞書を返す。
    """
    if not game_dir:
        return {}
    for nn in ("00", "01", "02", "03", "04", "05", "06", "07", "08", "09"):
        path = os.path.join(game_dir, f"SPELLSG.{nn}")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
            result: dict[int, str] = {}
            max_records = min(MAX_KNOWN_SPELLS, len(data) // SPELL_DATA_SIZE)
            for i in range(max_records):
                base = i * SPELL_DATA_SIZE
                if base + SPELL_DATA_SIZE > len(data):
                    break
                name_bytes = data[base + SPELL_NAME_OFFSET:
                                  base + SPELL_NAME_OFFSET + SPELL_NAME_LEN]
                name = name_bytes.split(b"\x00")[0].decode("ascii", errors="replace").strip()
                if name:
                    result[i] = name
            return result
        except OSError:
            continue
    return {}


# ──────────────────────────────────────────────────────────────
# 呪文詳細画面（SPELLBOOK パーチメント）読み取り
# 観測（仮説、Fire Dart vs Light Heal の差分より）:
#   anchor+0x57E6 = 現在表示中の SpellData レコード（85 bytes）
#       - +0x32 (anchor+0x5818) = cost (u16 LE)
#       - +0x34 (anchor+0x581A) = name[33]
#   anchor+0x1044 = 効果テキストバッファ（"1 to 2 pts damage to health..."）
# ──────────────────────────────────────────────────────────────
SPELL_DETAIL_DATA_OFFSET = 0x57E6  # 現在表示中 SpellData レコード（仮説）
SPELL_DETAIL_NAME_OFFSET = SPELL_DETAIL_DATA_OFFSET + SPELL_NAME_OFFSET  # 0x581A
SPELL_DETAIL_COST_OFFSET = SPELL_DETAIL_DATA_OFFSET + 0x32  # 0x5818
# SpellData 構造内の他フィールド（観測ベース）:
SPELL_DETAIL_TARGET_OFFSET   = SPELL_DETAIL_DATA_OFFSET + 0x24  # 0x580A u8
SPELL_DETAIL_ELEMENT_OFFSET  = SPELL_DETAIL_DATA_OFFSET + 0x26  # 0x580C u8
SPELL_DETAIL_FLAGS_OFFSET    = SPELL_DETAIL_DATA_OFFSET + 0x27  # 0x580D u16 LE
SPELL_DETAIL_EFFECTS_OFFSET  = SPELL_DETAIL_DATA_OFFSET + 0x29  # 0x580F u8[3]
SPELL_DETAIL_SUB_EFFECTS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 0x2C  # 0x5812 u8[3]
SPELL_DETAIL_AFFECTED_ATTRS_OFFSET = SPELL_DETAIL_DATA_OFFSET + 0x2F  # 0x5815 u8[3]

SPELL_DETAIL_TEXT_OFFSET = 0x1044
SPELL_DETAIL_TEXT_LEN    = 512  # 効果テキスト（複数行、null 区切りの可能性あり）

# プレイヤー情報
PLAYER_NAME_OFFSET   = 0x1AD   # NPCData+9: 26B NUL 終端 ASCII
PLAYER_LEVEL_OFFSET  = 0x1AA   # u8 = Level - 1
PLAYER_GOLD_OFFSET   = 0x5C2   # u16 LE（attributes_panel OFF_GOLD と同等の運用）

# ──────────────────────────────────────────────────────────────
# Arena spell field 名前ルックアップ（観測ベース、要検証）
# 数値 → 表示名のマッピング。観測値: Fire Dart targetType=2, element=0, effects[0]=4
# Light Heal targetType=0, element=5, effects[0]=12
# ──────────────────────────────────────────────────────────────
TARGET_TYPE_NAMES = {
    # 0x5691 の実測 Target 名順に合わせる。
    0: ("Caster only",                 "自分のみ"),
    1: ("1 Target, Touch",             "対象1体・接触"),
    2: ("1 Target at Range",           "対象1体・遠隔"),
    3: ("Area - Centered on Caster",   "範囲・術者中心"),
    4: ("Area - at Range, Explosion",  "範囲・遠隔爆発"),
}

ELEMENT_NAMES = {
    # 実機バッファ 0x5620 付近の Save Vs. 名順に合わせる。
    0: ("Fire",       "火"),
    1: ("Cold",       "冷気"),
    2: ("Poison",     "毒"),
    3: ("Shock",      "電撃"),
    4: ("Magic",      "魔法"),
    5: ("None",       "なし"),
    6: ("Energy",     "エネルギー"),
}


def read_spell_detail(analyzer, anchor: int) -> dict:
    """呪文詳細画面で現在表示中の呪文情報を読み取る。

    Returns:
        辞書（読み取り失敗時はデフォルト値）:
            name           str  呪文名
            cost           int  Casting Cost (u16)
            target_id      int  targetType (u8)
            target_en/_ja  str  targetType ルックアップ
            element_id     int  element (u8)
            element_en/_ja str  element ルックアップ
            effect_id      int  有効効果スロットの effects[i] (u8)
            effect_en/_ja  str  effects/subEffects/affectedAttrs ルックアップ
            text_en        str  効果テキスト全体
            player_name    str  プレイヤー名
            player_level   int  プレイヤーレベル
            player_gold    int  所持金
    """
    def _u8(off: int) -> int:
        try:
            return analyzer.read_bytes(anchor + off, 1)[0]
        except (OSError, AttributeError):
            return 0

    def _u8_opt(off: int) -> int | None:
        try:
            return analyzer.read_bytes(anchor + off, 1)[0]
        except (OSError, AttributeError, IndexError):
            return None

    def _u16(off: int) -> int:
        try:
            b = analyzer.read_bytes(anchor + off, 2)
            return b[0] | (b[1] << 8)
        except (OSError, AttributeError):
            return 0

    def _u8_array(off: int, length: int, default: int = 0) -> list[int]:
        try:
            raw = analyzer.read_bytes(anchor + off, length)
            return [raw[i] if i < len(raw) else default for i in range(length)]
        except (OSError, AttributeError):
            return [default] * length

    def _str(off: int, length: int) -> str:
        try:
            raw = analyzer.read_bytes(anchor + off, length)
            return raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").strip()
        except (OSError, AttributeError):
            return ""

    name = _str(SPELL_DETAIL_NAME_OFFSET, SPELL_NAME_LEN)
    cost = _u16(SPELL_DETAIL_COST_OFFSET)
    spell_cost = cost * 2 if cost else 0
    casting_cost = spell_cost // 4 if spell_cost else 0
    target_id = _u8(SPELL_DETAIL_TARGET_OFFSET)
    element_id = _u8(SPELL_DETAIL_ELEMENT_OFFSET)
    effects = _u8_array(SPELL_DETAIL_EFFECTS_OFFSET, 3, 0xFF)
    sub_effects = _u8_array(SPELL_DETAIL_SUB_EFFECTS_OFFSET, 3, 0)
    affected_attrs = _u8_array(SPELL_DETAIL_AFFECTED_ATTRS_OFFSET, 3, 0)
    effect_details = _effect_details_from_arrays(
        effects, sub_effects, affected_attrs)
    effect_slot = _active_effect_slot(effects)
    effect_id = effects[effect_slot]
    sub_effect_id = sub_effects[effect_slot]
    affected_attr_id = affected_attrs[effect_slot]

    target_en, target_ja = _lookup_pair(TARGET_TYPE_NAMES, target_id)
    element_en, element_ja = _lookup_pair(ELEMENT_NAMES, element_id)
    effect_en, effect_ja = _resolve_effect_name(
        effect_id, sub_effect_id, affected_attr_id)

    # 効果テキスト: Arena は長文内にも単発 NUL を挟むため、連続 NUL までを採用する。
    text_en = ""
    text_segments: list[str] = []
    try:
        raw = analyzer.read_bytes(
            anchor + SPELL_DETAIL_TEXT_OFFSET, SPELL_DETAIL_TEXT_LEN)
        text_segments = _decode_spell_effect_segments(raw)
        text_en = " ".join(text_segments).strip()
    except (OSError, AttributeError):
        pass

    player_name = _str(PLAYER_NAME_OFFSET, 26)
    level_raw = _u8_opt(PLAYER_LEVEL_OFFSET)
    player_level = level_raw + 1 if level_raw is not None else 0
    player_gold = _u16(PLAYER_GOLD_OFFSET)

    # テンプレート一致で残留文字列を落とす。複数効果の本文は
    # 効果見出しごとに分割し、各 effect_details に割り当てる。
    effect_details = _attach_effect_texts(
        text_en, effect_details, text_segments)
    effect_details = _fill_missing_spellmaker_effect_texts(
        effect_details, analyzer, anchor)
    if effect_details:
        first_detail = effect_details[0]
        effect_en = first_detail.get("effect_en", effect_en)
        effect_ja = first_detail.get("effect_ja", effect_ja)
        text_en = first_detail.get("text_en", "") or ""
        text_ja = first_detail.get("text_ja", "") or ""
    else:
        text_en, text_ja = _normalize_spell_effect_text(text_en, effect_en)

    return {
        "name":         name,
        "cost":         cost,
        "spell_cost":   spell_cost,
        "casting_cost": casting_cost,
        "target_id":    target_id,
        "target_en":    target_en,
        "target_ja":    target_ja,
        "element_id":   element_id,
        "element_en":   element_en,
        "element_ja":   element_ja,
        "effect_slot":  effect_slot,
        "effect_id":    effect_id,
        "sub_effect_id": sub_effect_id,
        "affected_attr_id": affected_attr_id,
        "effects":      effects,
        "sub_effects":  sub_effects,
        "affected_attrs": affected_attrs,
        "effect_details": effect_details,
        "effect_en":    effect_en,
        "effect_ja":    effect_ja,
        "text_en":      text_en,
        "text_ja":      text_ja,
        "player_name":  player_name,
        "player_level": player_level,
        "player_gold":  player_gold,
    }


def read_spellbook_items(analyzer, anchor: int) -> list[dict]:
    """
    習得呪文リストを辞書リストで返す。

    Returns list of:
        {"en": str}  (spell name from SPELLSG file)
    """
    import assist_settings as settings
    game_dir = settings.get("save_dir", "")
    spell_table = load_spellsg(game_dir)

    try:
        count = analyzer.read_bytes(anchor + SPELL_COUNT_OFFSET, 1)[0]
    except OSError:
        return []

    if count == 0 or count > 160:
        return []

    try:
        ids_raw = analyzer.read_bytes(anchor + SPELL_IDS_OFFSET, count)
    except OSError:
        return []

    items: list[dict] = []
    for spell_id in ids_raw[:count]:
        name = spell_table.get(spell_id, f"Spell#{spell_id}")
        items.append({"en": name})
    return items
