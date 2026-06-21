# -*- coding: utf-8 -*-
"""mages_list_reader.py — 魔術師ギルド L4 専用の一覧バッファ読み取り（完全分離）。

観測結果のバッファマップに基づき、魔術師ギルドの各一覧をローカルに読む。
武具店 / 神殿 / 宿屋の list reader を呼ばず、本ファイルに閉じて実装する
（中立な低レベル analyzer.read_bytes のみ使用）。武具店リーダ
(equipment_shop_list_reader) と同じ「NUL 区切り + decode ascii errors=replace」方式を
ローカルコピーして使う。

一覧バッファ（anchor 相対 offset）と書式（実測）:
  - 購入ポーション : 0x9684（共用）  各エントリ ``<制御><座標3桁><価格> gp\n<名前>`` NUL区切り
  - 購入呪文       : 0x99F0           同上
  - 探知=所持品    : 0x9A6E           名前のみ NUL区切り
  - 作成 対象      : 0x5691           名前のみ（静的）
  - 作成 効果一覧  : 0x968C（共用）   名前のみ
  - 作成 効果サブ  : 0x5561           名前のみ
  - 効果選択(削除/修正): 0x1044       名前のみ

価格行の先頭3桁は描画X座標（テンプレ ``200%u gp`` / ``190%u gp`` のリテラル）で価格ではない。
各エントリ先頭には 0x88/0xC4/0x09 等の制御バイトが付くため、ascii errors=replace で読み、
制御・置換文字を除去してから解析する。
"""
from __future__ import annotations

import logging
import re

import i18n_helper as i18n

_log = logging.getLogger("RTESArenaAssist")

# 一覧バッファ offset（実測）
POTION_LIST_OFFSET = 0x9684
SPELL_LIST_OFFSET = 0x99F0
INVENTORY_LIST_OFFSET = 0x9A6E
SPELLMAKER_TARGET_OFFSET = 0x5691
SPELLMAKER_EFFECT_OFFSET = 0x9686
SPELLMAKER_SUBLIST_OFFSET = 0x5561
EFFECT_PICK_OFFSET = 0x1044

# アクティブ一覧ポインタ（実測）: いま描画中の一覧バッファの anchor 相対 offset を
# 保持する u16。同値が 0xA892 にもミラーされる。ポーション/呪文は固定 offset では
# 判別できない（呪文一覧表示中もポーション buffer に旧データが残るため）。本ポインタ
# が指す先を読めば、いま実際に画面へ出ている一覧を確実に取得できる。
ACTIVE_LIST_PTR_OFFSET = 0x5028

_READ_LEN = 0x400
_MAX_ITEMS = 64
# 価格直前にこの数以上の非復号バイト(U+FFFD)があれば別一覧の先頭(境界)とみなす。
# 通常エントリ区切りは制御 1〜3 バイトのみ。境界のコード片は高位バイトを多数含む。
_BOUNDARY_FFFD_MIN = 4

# 魔法アイテム一覧（POPUP7.IMG）: ポーション/呪文と書式が異なり、名前が先に来る。
#   1 エントリ = ``\t<名前列座標3桁><名前>\n\t<価格列座標3桁><価格> gp`` を NUL 区切り
# 観測: 名前列座標=031 / 価格列座標=235。バッファは anchor から遠い動的ヒープに置かれ
# offset が変動し得るため、名前行先頭の固定座標シグネチャ ``\t031`` を走査して特定する。
_MAGIC_NAME_SIG = b"\x09031"
# 走査窓（観測実測 anchor+0x2733A0 付近）。見つからなければ広域へ拡大する。
_MAGIC_SCAN_RANGES = (
    (0x200000, 0x300000),
    (0x000000, 0x800000),
)
# ``\t<名前列3桁><名前>\n<非数字>*<価格3桁+価格>gp`` を 1 エントリとして抽出
_MAGIC_RE = re.compile(r"\d{3}([^\n]+)\n\D*?(\d+)\s*gp", re.DOTALL)
# 直近に成功した anchor 相対 offset（再走査回避用キャッシュ）
_magic_offset_cache: int | None = None


# 価格行: 任意の前置文字 + 数字列 + " gp" + 改行 + 名前
_PRICE_RE = re.compile(r"(\d+)\s*gp\s*\n?(.*)", re.DOTALL)
# 名前として有効な文字（印字 ASCII + 空白）。制御・置換文字は除去。
_KEEP_RE = re.compile(r"[^\x20-\x7E]")

# Spellmaker の名前のみ一覧は、隣接バッファや直前の効果本文が残った領域を
# 読むことがある。既知カタログで種別を分類し、ゲーム画面に実在する行だけを採用する。
SPELLMAKER_TARGET_NAMES = frozenset({
    "None",
    "Caster only",
    "1 Target, Touch",
    "1 Target at Range",
    "Area - Centered on Caster",
    "Area - Centered On Caster",
    "Area - at Range, Explosion",
})
SPELLMAKER_EFFECT_CATEGORY_NAMES = frozenset({
    "Cause",
    "Continuous Damage",
    "Create",
    "Cure",
    "Damage",
    "Designate as Non-Target",
    "Destroy",
    "Drain Attribute",
    "Elemental Resistance",
    "Fortify Attribute",
    "Heal",
    "Transfer",
    "Invisibility",
    "Levitate",
    "Light",
    "Lock",
    "Open",
    "Regenerate",
    "Silence",
    "Spell Absorption",
    "Spell Reflection",
    "Spell Resistance",
})
SPELLMAKER_EFFECT_OPTION_NAMES = frozenset({
    "Disease",
    "Poison",
    "Paralyzation",
    "Curse",
    "Fear",
    "Death",
    "Health",
    "Fatigue",
    "Spell Points",
    "Shield",
    "Wall",
    "Floor",
    "Fire",
    "Cold",
    "Shock",
    "Magic",
    "Energy",
    "Attribute",
    "Figured Attribute",
    "Strength",
    "Intelligence",
    "Willpower",
    "Agility",
    "Speed",
    "Endurance",
    "Personality",
    "Luck",
    "Follows caster",
    "Projectile",
    "Yes",
    "No",
})
_FULL_EFFECT_SUFFIXES = {
    "Cause": ("Disease", "Poison", "Paralyzation", "Curse", "Fear", "Death"),
    "Continuous Damage": ("Health", "Fatigue", "Spell Points"),
    "Create": ("Shield", "Wall", "Floor"),
    "Cure": ("Disease", "Poison", "Paralyzation", "Curse", "Fear"),
    "Damage": ("Health", "Fatigue", "Spell Points"),
    "Destroy": ("Wall", "Floor"),
    "Heal": ("Fatigue", "Health", "Spell Points"),
    "Elemental Resistance": ("Fire", "Cold", "Shock", "Magic", "Poison"),
}
SPELLMAKER_EFFECT_FULL_NAMES = (
    frozenset({
        f"{prefix} {suffix}"
        for prefix, suffixes in _FULL_EFFECT_SUFFIXES.items()
        for suffix in suffixes
    })
    | frozenset({
        "Designate as Non-Target",
        "Drain Attribute",
        "Fortify Attribute",
        "Transfer Attribute",
        "Invisibility",
        "Levitate",
        "Light",
        "Lock",
        "Open",
        "Regenerate",
        "Silence",
        "Spell Absorption",
        "Spell Reflection",
        "Spell Resistance",
    })
)


def _read_raw(analyzer, anchor: int, offset: int, length: int = _READ_LEN) -> bytes:
    try:
        return analyzer.read_bytes(anchor + offset, length)
    except (OSError, AttributeError):
        return b""


def _clean(text: str) -> str:
    """制御文字・置換文字を除いた可読名を返す。"""
    return _KEEP_RE.sub("", text).strip()


def _is_name(s: str) -> bool:
    """名前らしい（英字を含み、印字可能率が高い）か。"""
    if not s or len(s) < 2:
        return False
    return any(c.isalpha() for c in s)


def _strip_coord(price_digits: str) -> str:
    """価格列 ``<座標3桁><価格>`` から座標3桁を除いて価格部を返す。"""
    return price_digits[3:] if len(price_digits) > 3 else price_digits


def _segments(raw: bytes) -> list[str]:
    """NUL 区切りで各エントリを ascii(errors=replace) 復号して返す。"""
    out: list[str] = []
    for seg in raw.split(b"\x00"):
        out.append(seg.decode("ascii", errors="replace"))
    return out


def read_priced_list(analyzer, anchor: int, offset: int) -> list[dict]:
    """価格付き一覧（ポーション/呪文）を読む → [{"en":名前, "ja":訳, "price_display":価格}]。"""
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    blanks = 0
    for seg in _segments(raw):
        m = _PRICE_RE.search(seg)
        if not m:
            # 価格行でない: 一覧開始後に空/ゴミが続いたら終端
            if items:
                blanks += 1
                if blanks >= 3:
                    break
            continue
        # リスト境界検出: ポーション一覧の直後に呪文一覧が同一バッファへ連結
        # されており、境界には一覧描画ルーチンのコード片（高位バイト多数）が
        # 挟まる。価格直前の非復号バイト（U+FFFD）が多いエントリは別一覧の
        # 先頭とみなして終端する（通常エントリの区切りは制御 1〜3 バイトのみ）。
        if items and seg[:m.start(1)].count("�") >= _BOUNDARY_FFFD_MIN:
            break
        blanks = 0
        name = _clean(m.group(2))
        if not _is_name(name):
            if items:
                break
            continue
        price = _strip_coord(m.group(1))
        items.append({"en": name, "ja": translate_name(name),
                      "price_display": f"{price} gp"})
        if len(items) >= _MAX_ITEMS:
            break
    return items


def read_active_list_offset(analyzer, anchor: int) -> int | None:
    """アクティブ一覧ポインタ（0x5028 の u16）を読み、妥当なら anchor 相対 offset を返す。"""
    try:
        off = analyzer.read_u16(anchor + ACTIVE_LIST_PTR_OFFSET)
    except (OSError, AttributeError):
        return None
    # near buffer 域（概ね 0x1000〜0xFE00）のみ有効とみなす
    if isinstance(off, int) and 0x1000 <= off <= 0xFE00:
        return off
    return None


def read_active_priced_list(analyzer, anchor: int) -> list[dict]:
    """アクティブ一覧ポインタが指す価格付き一覧（ポーション/呪文）を読む。

    ポーション/呪文は固定 offset では判別不能（非アクティブ buffer に旧データが
    残る）。本ポインタ経由なら、いま画面に出ている一覧を確実に取得できる。
    """
    off = read_active_list_offset(analyzer, anchor)
    if off is None:
        return []
    return read_priced_list(analyzer, anchor, off)


def looks_like_potion_list(items: list[dict]) -> bool:
    """先頭が ``Potion of`` なら潜在的にポーション一覧（呪文は決してこの接頭辞を持たない）。"""
    return bool(items) and items[0].get("en", "").startswith("Potion of")


def _parse_magic_entries(raw: bytes) -> list[dict]:
    """魔法アイテム一覧バッファを解析 → [{"en","ja","price_display"}]。"""
    items: list[dict] = []
    for seg in _segments(raw):
        m = _MAGIC_RE.search(seg)
        if not m:
            if items:
                break  # 一覧の終端（別データに到達）
            continue
        name = _clean(m.group(1))
        if not _is_name(name):
            if items:
                break
            continue
        price = _strip_coord(m.group(2))
        items.append({"en": name, "ja": translate_name(name),
                      "price_display": f"{price} gp"})
        if len(items) >= _MAX_ITEMS:
            break
    return items


def read_magic_item_list(analyzer, anchor: int) -> list[dict]:
    """魔法アイテム一覧（POPUP7.IMG）を読む → [{"en","ja","price_display"}]。

    名前が先・価格が後の書式で、バッファは遠隔ヒープに置かれ offset が変動し得る。
    名前行先頭の固定座標シグネチャ ``\\t031`` を走査して先頭エントリを特定する。
    直近成功 offset をキャッシュし、無効化された時のみ再走査する。
    """
    global _magic_offset_cache
    # 1) キャッシュ offset を検証して使う（高速パス）
    if _magic_offset_cache is not None:
        raw = _read_raw(analyzer, anchor, _magic_offset_cache, 0x800)
        items = _parse_magic_entries(raw)
        if items:
            return items
        _magic_offset_cache = None
    # 2) シグネチャ走査で先頭エントリを特定
    try:
        for rel_start, rel_end in _MAGIC_SCAN_RANGES:
            hits = analyzer.scan_bytes(
                _MAGIC_NAME_SIG, anchor + rel_start, anchor + rel_end)
            for h in hits:
                off = h.address - anchor
                raw = _read_raw(analyzer, anchor, off, 0x800)
                items = _parse_magic_entries(raw)
                if items:
                    _magic_offset_cache = off
                    return items
    except (OSError, AttributeError):
        pass
    return []


def read_name_list(analyzer, anchor: int, offset: int) -> list[dict]:
    """名前のみの一覧（所持品/効果/対象/効果選択）を読む → [{"en":名前, "ja":訳}]。"""
    raw = _read_raw(analyzer, anchor, offset)
    items: list[dict] = []
    blanks = 0
    for seg in _segments(raw):
        # 名前のみ一覧の直後に価格付き一覧（ポーション等）が連結されている
        # ことがある。価格行（``NNN gp``）に達したら別一覧の先頭とみなし終端する。
        if items and _PRICE_RE.search(seg):
            break
        name = _clean(seg)
        if not _is_name(name) or "\n" in name:
            if items:
                blanks += 1
                if blanks >= 3:
                    break
            continue
        blanks = 0
        items.append({"en": name, "ja": translate_name(name)})
        if len(items) >= _MAX_ITEMS:
            break
    return items


def filter_known_items(items: list[dict], allowed: set[str] | frozenset[str]
                       ) -> list[dict]:
    """既知カタログに含まれる連続項目だけを返す。

    名前のみ一覧は別リストや本文が後ろに続くことがあるため、先頭から既知項目が
    続く範囲を画面上の一覧とみなす。翻訳は最新辞書で引き直す。
    """
    allowed_set = set(allowed)
    out: list[dict] = []
    for item in items:
        name = (item.get("en") or "").strip()
        if name not in allowed_set:
            break
        copied = dict(item)
        copied["ja"] = translate_name(name)
        out.append(copied)
    return out


def classify_spellmaker_name_items(items: list[dict]
                                   ) -> tuple[str, str, list[dict]] | None:
    """Spellmaker の名前のみ一覧を内容から分類する。

    Returns:
        (title_en, title_ja, filtered_items)。不明なら None。
    """
    if not items:
        return None
    first = (items[0].get("en") or "").strip()
    if first in SPELLMAKER_TARGET_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_TARGET_NAMES)
        if filtered:
            return ("Targets", "対象一覧", filtered)
    if first in SPELLMAKER_EFFECT_CATEGORY_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_CATEGORY_NAMES)
        if filtered:
            return ("Effects", "効果一覧", filtered)
    if first in SPELLMAKER_EFFECT_OPTION_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_OPTION_NAMES)
        if filtered:
            return ("Effect Options", "効果オプション", filtered)
    if first in SPELLMAKER_EFFECT_FULL_NAMES:
        filtered = filter_known_items(items, SPELLMAKER_EFFECT_FULL_NAMES)
        if filtered:
            return ("Effects", "効果一覧", filtered)
    return None


def enrich_unidentified_by_index(analyzer, anchor: int,
                                 items: list[dict]) -> list[dict]:
    """所持品一覧（Detect Magic）の各行に未鑑定フラグ ``is_unidentified`` を付与する。

    所持品一覧の行順序はインベントリ構造体配列（非空スロット）の順序と一致する
    （実機確認）。中立なインベントリ構造体リーダ ``inventory_reader``（インベントリ
    解析の単一の真実）を順序対応で参照し、各行に未鑑定フラグを付ける。

    誤対応を避けるため、同一インデックスで原文名が一致した行だけに付与する
    （未鑑定品は選択一覧でもベース名で出るため必ず一致する）。件数や名前が
    食い違う行は付与せず無印のままにする（誤情報を出さない）。
    """
    if not items:
        return items
    try:
        import inventory_reader as inv
        structs = inv.read_equipment_items(analyzer, anchor)
    except Exception:  # noqa: BLE001
        return items
    out: list[dict] = []
    for i, it in enumerate(items):
        copied = dict(it)
        if i < len(structs):
            s = structs[i]
            if (s.get("en", "").strip() == (it.get("en", "") or "").strip()):
                copied["is_unidentified"] = bool(s.get("is_unidentified"))
        out.append(copied)
    return out


def translate_name(en: str) -> str:
    """項目名を翻訳する。mages カテゴリ → items カテゴリの順で引く。未登録は原文（英語）。

    鑑定済み魔法装備「<ベース> of <enchant>」(例: "Helm of Willpower") は直接訳が
    無いため、エンチャント名(item_enchantments)とベース名を合成して
    「意志力のヘルム」の形で返す（魔術師ギルド分離内のローカル合成）。
    """
    key = (en or "").strip()
    direct = i18n.value("mages", key) or i18n.value("items", key)
    if direct:
        return direct
    m = re.match(r"^(.+?) (of .+)$", key)
    if m:
        ench_ja = i18n.value("item_enchantments", m.group(2))
        if ench_ja:
            base = m.group(1).strip()
            base_ja = translate_name(base)
            if base_ja and base_ja != base:
                return f"{ench_ja}の{base_ja}"
    # 素材プレフィックス付き（例: "Mithril Torc" → ミスリル+トルク / "Steel Longsword"）
    parts = key.split()
    if len(parts) >= 2:
        base = parts[-1]
        base_ja = i18n.value("items", base) or i18n.value("mages", base)
        if base_ja:
            prefix_ja = "".join(
                (i18n.value("item_materials", p) or p) for p in parts[:-1])
            return f"{prefix_ja}{base_ja}"
    return key


__all__ = [
    "POTION_LIST_OFFSET", "SPELL_LIST_OFFSET", "INVENTORY_LIST_OFFSET",
    "SPELLMAKER_TARGET_OFFSET", "SPELLMAKER_EFFECT_OFFSET",
    "SPELLMAKER_SUBLIST_OFFSET", "EFFECT_PICK_OFFSET",
    "read_priced_list", "read_name_list", "read_magic_item_list",
    "read_active_priced_list", "read_active_list_offset",
    "looks_like_potion_list", "ACTIVE_LIST_PTR_OFFSET", "translate_name",
    "enrich_unidentified_by_index",
    "filter_known_items", "classify_spellmaker_name_items",
    "SPELLMAKER_TARGET_NAMES", "SPELLMAKER_EFFECT_CATEGORY_NAMES",
    "SPELLMAKER_EFFECT_OPTION_NAMES", "SPELLMAKER_EFFECT_FULL_NAMES",
]
