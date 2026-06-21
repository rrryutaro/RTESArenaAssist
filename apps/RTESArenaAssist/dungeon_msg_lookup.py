
from __future__ import annotations

import re

import i18n_helper as i18n

_entries: list[dict] = []
_loaded = False

_MONSTER_NAMES: dict[str, str] | None = None
_MONSTER_PHRASES: dict[str, str] | None = None
_ITEM_NAMES: dict[str, str] | None = None


def _iter_monsters():
    if i18n.v2_public_enabled("monsters"):
        for e in i18n.v2_category_entries("monsters"):
            eng = e.get("original") or ""
            ja = e.get("text")
            if eng and ja:
                yield eng, ja
    else:
        for _id, e in i18n.originals("monsters").items():
            eng = e.get("original", "") if isinstance(e, dict) else ""
            ja = i18n.text(_id)
            if eng and ja and ja != _id:
                yield eng, ja


def _monster_names() -> dict[str, str]:
    global _MONSTER_NAMES
    if _MONSTER_NAMES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            if eng[0].isupper() and not eng.startswith("You "):
                result[eng] = ja
        _MONSTER_NAMES = result
    return _MONSTER_NAMES


def _monster_phrases() -> dict[str, str]:
    global _MONSTER_PHRASES
    if _MONSTER_PHRASES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            if eng.startswith("You "):
                result[eng] = ja
        _MONSTER_PHRASES = result
    return _MONSTER_PHRASES


def _item_names() -> dict[str, str]:
    global _ITEM_NAMES
    if _ITEM_NAMES is None:
        by_sec: dict[str, list[tuple[str, dict]]] = {}
        for _id, e in i18n.originals("items").items():
            parts = _id.split(".")
            if len(parts) >= 2 and isinstance(e, dict):
                by_sec.setdefault(parts[1], []).append((_id, e))
        result: dict[str, str] = {}
        _SECS = ("weapons", "armor_slots", "shields", "accessories",
                 "potions", "quest_items", "lookup_aliases",
                 "spellcasting_items")
        for sec in _SECS:
            for _id, e in by_sec.get(sec, []):
                en = e.get("original", "")
                if not en:
                    continue
                ja = i18n.text(_id)
                if ja and ja != _id:
                    result[en] = ja
        for ent in i18n.v2_category_entries("items"):
            if (ent.get("context") or {}).get("section") not in _SECS:
                continue
            en, ja = ent.get("original"), ent.get("text")
            if en and ja:
                result.setdefault(en, ja)
        _ITEM_NAMES = result
    return _ITEM_NAMES

def lookup_spell(name: str) -> str:
    return i18n.value("spell_names", name) or ""


def _ensure_loaded() -> None:
    global _entries, _loaded
    if _loaded:
        return
    rebuilt: list[dict] = []
    for _id, e in i18n.originals("dungeon_messages").items():
        en = e.get("original", "") if isinstance(e, dict) else ""
        if not en:
            continue
        ja = i18n.value("dungeon_messages", en)
        ja_clean = ja if (ja and ja != en) else ""
        rebuilt.append({"key": {"en": en}, "translations": {"ja": ja_clean}})
    _entries = rebuilt
    _loaded = True


def lookup_item(name: str) -> str:
    if not name:
        return ""

    m = re.match(r"Bag of (\d+) gold pieces?", name, re.IGNORECASE)
    if m:
        return f"金貨 {m.group(1)} 枚入り袋"

    m_lr = re.match(r"^(.*?)\s*\(([LR])\)$", name)
    if m_lr:
        base_result = lookup_item(m_lr.group(1).strip())
        if base_result:
            suffix_ja = "（左）" if m_lr.group(2) == "L" else "（右）"
            return base_result + suffix_ja

    item_names = _item_names()
    if name in item_names:
        return item_names[name]

    m_ench = re.match(r"^(.+?) (of .+)$", name)
    if m_ench:
        ench_ja = i18n.value("item_enchantments", m_ench.group(2))
        if ench_ja:
            base_ja = lookup_item(m_ench.group(1).strip())
            if base_ja:
                return f"{ench_ja}の{base_ja}"

    for base_en, base_ja in item_names.items():
        if name.endswith(base_en):
            prefix = name[: len(name) - len(base_en)].strip()
            if not prefix:
                return base_ja
            prefix_parts = prefix.split()
            prefix_ja = "".join(
                (i18n.value("item_materials", p) or p) for p in prefix_parts
            )
            return f"{prefix_ja}{base_ja}"

    return ""


def lookup(text: str) -> str:
    if not text:
        return ""

    if text in _monster_phrases():
        return _monster_phrases()[text]

    m = re.match(r"^You see an? (.+?)\.", text)
    if m:
        name_en = m.group(1).strip()
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}が見える。"

    if text.startswith("The ") and text.endswith(" has no gold or usable items."):
        name_en = text[4:-len(" has no gold or usable items.")]
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}は金貨も使えるものも持っていない。"

    if text.startswith("The ") and text.endswith(" has nothing usable."):
        name_en = text[4:-len(" has nothing usable.")]
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}は使えるものを持っていない。"

    if text.startswith("The ") and " has " in text and " in their possession" in text:
        after_the = text[4:]
        has_pos = after_the.find(" has ")
        name_en = after_the[:has_pos]
        name_ja = _monster_names().get(name_en, name_en)
        item_part = after_the[has_pos + 5:].rstrip(".")
        item_part = item_part.replace(" in their possession", "").strip()
        return f"{name_ja}は {item_part} を持っている。"

    m = re.match(r"^You have found (\d+) gold pieces?!!", text)
    if m:
        return f"金貨 {m.group(1)} 枚を手に入れた！！"


    _ensure_loaded()

    for e in _entries:
        if e.get("key", {}).get("en", "") == text:
            return e.get("translations", {}).get("ja", "")

    best_len = 0
    best_jpn = ""
    for e in _entries:
        eng = e.get("key", {}).get("en", "")
        if eng and text.startswith(eng) and len(eng) > best_len:
            best_len = len(eng)
            best_jpn = e.get("translations", {}).get("ja", "")

    return best_jpn
