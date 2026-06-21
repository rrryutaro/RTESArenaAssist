"""
dungeon_msg_lookup.py — オブジェクト対話ダイアログ・アイテム名翻訳ルックアップ

dungeon_messages.json をバックエンドとして使用し、ダンジョン中のダイアログ文字列を
日本語に変換する。

鍵入手・扉解錠は npc_dialog.json の A232 / A233 テンプレ経路 (placeholder %nk +
items.json/key_materials) に集約済み。本モジュールは残存ハードコードを順次撤去
予定。

lookup_item(name): NEWPOP アイテム名を日本語に変換する。
"""

from __future__ import annotations

import re

import i18n_helper as i18n

_entries: list[dict] = []
_loaded = False

# 翻訳切替コアから構築する各マップ（遅延ロード）。
# 注: モジュール import が i18n.init より先になり得るため、モジュール読込時には
#     構築せず初回参照時に構築する（早期構築すると originals が空で訳が落ちる）。
_MONSTER_NAMES: dict[str, str] | None = None
_MONSTER_PHRASES: dict[str, str] | None = None
_ITEM_NAMES: dict[str, str] | None = None


def _iter_monsters():
    """monsters カテゴリの (en, ja) を yield する。v2 公開 runtime 有効時は source_id 経路
    （v2_category_entries・legacy_id_map 非依存）。未有効は従来の originals＋text(id)。
    v2 は source_id を持たない entry（combat phrase 等・非テーブル源）を自然除外する。"""
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
    """monsters カテゴリから名詞エントリ（敵名）のみ抽出（遅延・キャッシュ）。"""
    global _MONSTER_NAMES
    if _MONSTER_NAMES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            # 動詞句・文（小文字始まり or "You" 始まり）は除外
            if eng[0].isupper() and not eng.startswith("You "):
                result[eng] = ja
        _MONSTER_NAMES = result
    return _MONSTER_NAMES


def _monster_phrases() -> dict[str, str]:
    """monsters カテゴリから combat log 用短文（"You..."）を抽出（遅延）。"""
    global _MONSTER_PHRASES
    if _MONSTER_PHRASES is None:
        result: dict[str, str] = {}
        for eng, ja in _iter_monsters():
            if eng.startswith("You "):
                result[eng] = ja
        _MONSTER_PHRASES = result
    return _MONSTER_PHRASES


def _item_names() -> dict[str, str]:
    """items カテゴリの所持品名マップ（遅延）。旧 dictionary のセクション順を
    保ち last-wins で構築する（spellcasting が Mark/Crystal を上書きする等を再現）。"""
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
        # dev は originals をセクション順 last-wins で構築（挙動不変）。
        for sec in _SECS:
            for _id, e in by_sec.get(sec, []):
                en = e.get("original", "")
                if not en:
                    continue
                ja = i18n.text(_id)
                if ja and ja != _id:
                    result[en] = ja  # セクション順 last-wins
        # 公開ビルド（originals 空）は v2_category_entries で補完＝`_original` 非依存。
        # 当該セクションのみ（context.section）に限定し既存 key は上書きしない（gap 補完）。
        for ent in i18n.v2_category_entries("items"):
            if (ent.get("context") or {}).get("section") not in _SECS:
                continue
            en, ja = ent.get("original"), ent.get("text")
            if en and ja:
                result.setdefault(en, ja)
        _ITEM_NAMES = result
    return _ITEM_NAMES

def lookup_spell(name: str) -> str:
    """Arena 呪文名を現在言語に変換して返す。対応なしは空文字。"""
    return i18n.value("spell_names", name) or ""


def _ensure_loaded() -> None:
    global _entries, _loaded
    if _loaded:
        return
    # dungeon_messages を翻訳切替コアから再構築（lookup は key.en / translations.ja のみ参照）。
    rebuilt: list[dict] = []
    for _id, e in i18n.originals("dungeon_messages").items():
        en = e.get("original", "") if isinstance(e, dict) else ""
        if not en:
            continue
        ja = i18n.value("dungeon_messages", en)
        # 未訳エントリ（ja が無く原文フォールバックで en と同値）は旧挙動に合わせ "" 扱い。
        ja_clean = ja if (ja and ja != en) else ""
        rebuilt.append({"key": {"en": en}, "translations": {"ja": ja_clean}})
    _entries = rebuilt
    _loaded = True


def lookup_item(name: str) -> str:
    """NEWPOP アイテム名を日本語に変換して返す。対応なしは空文字。

    パターン:
      "Bag of N gold pieces"   → "金貨 N 枚入り袋"
      "Foo (L)" / "Foo (R)"   → lookup_item("Foo") + "（左）"/"（右）"
      完全一致 → 末尾ベース名で分解（材質+ベース） → 空文字
    """
    if not name:
        return ""

    # "Bag of N gold pieces"（お金袋）
    m = re.match(r"Bag of (\d+) gold pieces?", name, re.IGNORECASE)
    if m:
        return f"金貨 {m.group(1)} 枚入り袋"

    # "(L)" / "(R)" サフィックス（Pauldron 等の左右ペア）
    m_lr = re.match(r"^(.*?)\s*\(([LR])\)$", name)
    if m_lr:
        base_result = lookup_item(m_lr.group(1).strip())
        if base_result:
            suffix_ja = "（左）" if m_lr.group(2) == "L" else "（右）"
            return base_result + suffix_ja

    item_names = _item_names()
    if name in item_names:
        return item_names[name]

    # 鑑定済み魔法装備のエンチャント接尾名「<ベース> of <enchant>」
    # 例: "Helm of Willpower" → 翻訳("of Willpower") + "の" + lookup_item("Helm")
    #     = "意志力のヘルム"。素材付き("Steel Helm of ...")もベース側再帰で対応。
    m_ench = re.match(r"^(.+?) (of .+)$", name)
    if m_ench:
        ench_ja = i18n.value("item_enchantments", m_ench.group(2))
        if ench_ja:
            base_ja = lookup_item(m_ench.group(1).strip())
            if base_ja:
                return f"{ench_ja}の{base_ja}"

    # 末尾のベース名を探して「材質+ベース名」に分解する
    # 例: "Plate Pauldron" → "プレート" + "ポールドロン"
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
    """ダイアログ文字列を日本語に変換して返す。対応なしは空文字。"""
    if not text:
        return ""

    if text in _monster_phrases():
        return _monster_phrases()[text]

    # "You see a [MonsterName]." / "You see an [MonsterName]."
    m = re.match(r"^You see an? (.+?)\.", text)
    if m:
        name_en = m.group(1).strip()
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}が見える。"

    # "The [MonsterName] has no gold or usable items."
    if text.startswith("The ") and text.endswith(" has no gold or usable items."):
        name_en = text[4:-len(" has no gold or usable items.")]
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}は金貨も使えるものも持っていない。"

    # "The [MonsterName] has nothing usable."
    if text.startswith("The ") and text.endswith(" has nothing usable."):
        name_en = text[4:-len(" has nothing usable.")]
        name_ja = _monster_names().get(name_en, name_en)
        return f"{name_ja}は使えるものを持っていない。"

    # "The [MonsterName] has [item] in their possession."  (敵が所持品を持つ場合)
    if text.startswith("The ") and " has " in text and " in their possession" in text:
        after_the = text[4:]
        has_pos = after_the.find(" has ")
        name_en = after_the[:has_pos]
        name_ja = _monster_names().get(name_en, name_en)
        item_part = after_the[has_pos + 5:].rstrip(".")
        # "in their possession" を除去
        item_part = item_part.replace(" in their possession", "").strip()
        return f"{name_ja}は {item_part} を持っている。"

    # "You have found N gold pieces!!" (金貨ドロップ、+0x929E バッファ経由)
    m = re.match(r"^You have found (\d+) gold pieces?!!", text)
    if m:
        return f"金貨 {m.group(1)} 枚を手に入れた！！"

    # 鍵入手・扉解錠の専用分岐は撤去。npc_dialog.json の鍵材質テンプレ経路
    # (placeholder %nk + items.json/key_materials) に集約。

    _ensure_loaded()

    # 完全一致
    for e in _entries:
        if e.get("key", {}).get("en", "") == text:
            return e.get("translations", {}).get("ja", "")

    # 前方一致（最長優先）
    best_len = 0
    best_jpn = ""
    for e in _entries:
        eng = e.get("key", {}).get("en", "")
        if eng and text.startswith(eng) and len(eng) > best_len:
            best_len = len(eng)
            best_jpn = e.get("translations", {}).get("ja", "")

    return best_jpn
