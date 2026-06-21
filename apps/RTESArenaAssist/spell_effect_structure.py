"""spell_effect_structure.py — spell_effect カテゴリの原文 surface 生成 provider。

数値構造（effect_id / sub_effect_id / affected_attr_id）を主キーに、Arena が画面・本文・
テンプレート上で使う英語原文 surface を決定論生成する。ここで持つ英語表は「表示翻訳」では
なく **生成規則 / 構造規則**（live 照合アンカーの素材）であり、表示用の訳は翻訳基盤側
（locale / mod）が別に持つ。

status:
  - "verified"            : 単一効果・完成名として surface が確定しているもの（互換のため維持）。
  - "verified_structure"  : 効果名 prefix・attribute/element が実測確認済みで合成規則は確定だが、
                            「単一 Arena surface」ではないもの（合成表示）。
  - "unverified_composite": prefix + sub/attribute を構造から合成したが、実測検証が未了のもの。

Spellmaker 効果名配列をライブメモリから採取（image_base+0x40CC7 から 24 効果名・null 終端配列）。
`Drain Attribute`（+0x40D20）・`Elemental Resistance`（+0x40D30）・`Fortify Attribute`（+0x40D45）
はいずれも単一 Arena surface として実在し（本モジュールの prefix と完全一致）、element は
"Resist Shock"（Electricity でなく Shock）を確認＝canonical=shock。よって effect 9/10/11 の合成名は
prefix・属性/元素ともに実測確認済み＝`verified_structure`（単一 surface でなく構成要素の合成）。

照合アンカーは実測 surface に従う（element の表示語が「電撃」でも surface は "Shock"）。
"""
from __future__ import annotations

NONE = 0xFF

# 効果カテゴリ prefix（effect_id → 構造英語 prefix）。
_EFFECT_PREFIX = {
    0: "Cause",
    1: "Continuous Damage",
    2: "Create",
    3: "Cure",
    4: "Damage",
    6: "Destroy",
    9: "Drain Attribute",
    10: "Elemental Resistance",
    11: "Fortify Attribute",
    12: "Heal",
    13: "Transfer Attribute",
}

# sub/attribute/element の構造名（番号 → 英語アンカー語）。
_DAMAGE_TARGET = {0: "Health", 1: "Fatigue", 2: "Spell Points"}
_HEAL_TARGET = {0: "Fatigue", 1: "Health", 2: "Spell Points"}
_ELEMENT_SUB = {0: "Fire", 1: "Cold", 2: "Shock", 3: "Magic", 4: "Poison"}
_ATTRIBUTE = {
    0: "Strength", 1: "Intelligence", 2: "Willpower", 3: "Agility",
    4: "Speed", 5: "Endurance", 6: "Personality", 7: "Luck",
}
_CAUSE_SUB = {0: "Disease", 1: "Poison", 2: "Paralyzation", 3: "Curse"}
_CURE_SUB = {0: "Disease", 1: "Poison", 2: "Paralyzation", 3: "Curse"}
_CREATE_SUB = {0: "Shield", 1: "Wall", 2: "Floor"}
_DESTROY_SUB = {0: "Wall", 1: "Floor"}

# 単一効果（effect_id → 完成名・sub 不要）。
_SIMPLE_EFFECT = {
    5: "Designate as Non-Target",
    15: "Invisibility",
    16: "Levitate",
    17: "Light",
    18: "Lock",
    19: "Open",
    20: "Regenerate",
    21: "Silence",
    22: "Spell Absorption",
    23: "Spell Reflection",
    24: "Spell Resistance",
}

# 完成名として surface が確定している合成効果（effect_id, sub → text）。
# これらは Arena 本文 / メニュー / SPELLMKR で完成形が確認できるもの＝verified。
_VERIFIED_COMPOSITE = {
    (0, 0): "Cause Disease",
    (0, 1): "Cause Poison",
    (0, 2): "Cause Paralyzation",
    (0, 3): "Cause Curse",
    (1, 0): "Continuous Damage Health",
    (1, 1): "Continuous Damage Fatigue",
    (1, 2): "Continuous Damage Spell Points",
    (2, 0): "Create Shield",
    (2, 1): "Create Wall",
    (2, 2): "Create Floor",
    (3, 0): "Cure Disease",
    (3, 1): "Cure Poison",
    (3, 2): "Cure Paralyzation",
    (3, 3): "Cure Curse",
    (4, 0): "Damage Health",
    (4, 1): "Damage Fatigue",
    (4, 2): "Damage Spell Points",
    (6, 0): "Destroy Wall",
    (6, 1): "Destroy Floor",
    (12, 0): "Heal Fatigue",
    (12, 1): "Heal Health",
    (12, 2): "Heal Spell Points",
}

# attribute/element を取る合成（effect_id）。prefix・属性/元素ともに実機採取で実測確認済み
# （上記採取記録）＝合成名は verified_structure（単一 surface でない構成要素の合成）。
_VERIFIED_STRUCTURE_EFFECTS = {9, 10, 11}


def surface_for(effect_id: int,
                sub_effect_id: int = 0,
                affected_attr_id: int = 0) -> tuple[str, str] | None:
    """効果構造から (英語原文 surface, status) を返す。未対応は None。"""
    if effect_id == NONE:
        return None

    # 単一効果（完成名・sub 不要）。
    if effect_id in _SIMPLE_EFFECT:
        return (_SIMPLE_EFFECT[effect_id], "verified")

    # 完成名が確定している合成。
    confirmed = _VERIFIED_COMPOSITE.get((effect_id, sub_effect_id))
    if confirmed is not None:
        return (confirmed, "verified")

    prefix = _EFFECT_PREFIX.get(effect_id)
    if prefix is None:
        return None

    # attribute / element を取る合成（prefix・構成要素ともに実機採取で実測確認済み）。
    # prefix 単独（属性/元素不明）は単一 Arena surface＝verified_surface、合成は verified_structure。
    if effect_id == 9:  # Drain Attribute
        attr = _ATTRIBUTE.get(sub_effect_id) or _ATTRIBUTE.get(affected_attr_id)
        return (f"{prefix} {attr}", "verified_structure") if attr else (prefix, "verified_surface")
    if effect_id == 11:  # Fortify Attribute
        attr = _ATTRIBUTE.get(sub_effect_id) or _ATTRIBUTE.get(affected_attr_id)
        return (f"{prefix} {attr}", "verified_structure") if attr else (prefix, "verified_surface")
    if effect_id == 10:  # Elemental Resistance
        elem = _ELEMENT_SUB.get(sub_effect_id)
        return (f"{prefix} {elem}", "verified_structure") if elem else (prefix, "verified_surface")
    if effect_id == 13:  # Transfer Attribute（単一・完成）
        return (prefix, "verified")

    # ここに来る (prefix あり・sub 表あり) は本来 _VERIFIED_COMPOSITE に載るが、
    # 未知 sub の場合は prefix のみを返す（未検証扱い）。
    return (prefix, "unverified_composite")


def build_originals(entries: list[dict]) -> dict[int, dict]:
    """bundle の spell_effect entries から localpack 用 originals を生成する。

    entries[*] = {"id": int, "source": {"effect_id":.., "sub_effect_id":.., "affected_attr_id":..}}
    戻り値: { id: {"text": str, "status": "verified"|"unverified_composite"} }
    （surface が作れない entry は除外＝localpack に original を持たない＝degraded）。
    """
    out: dict[int, dict] = {}
    for entry in entries:
        src = entry.get("source") or {}
        result = surface_for(
            int(src.get("effect_id", NONE)),
            int(src.get("sub_effect_id", 0)),
            int(src.get("affected_attr_id", 0)),
        )
        if result is None:
            continue
        text, status = result
        out[int(entry["id"])] = {"text": text, "status": status}
    return out


__all__ = ["surface_for", "build_originals", "NONE"]
