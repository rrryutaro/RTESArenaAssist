"""shop_menu_reader.py — 店内 MENU_RT.IMG 表示中の店主メニュー読取 + 翻訳。

memory layout (観測):
  各 menu item は anchor + 0x725F 付近に
    09 c0  <first_char>  09 d4  <rest...>  0D  00
  形式で連続。`09 c0 / 09 d4` は color/format escape (頭文字ハイライト)。

  **同一 buffer に複数 menu group が並列配置** (場面別):
    - group 1: 部屋未契約時 5 項目 (Buy Drinks / Get a Room / Sneak into a
               Room / Rumors / Exit)
    - group 2: 部屋契約済時 3 項目 (Buy Drinks / Rumors / Exit)
    - group 3: Yes / No control group (NEGOTBUT 確認画面)
    - 各 group 間に hotkey string ('BRE\\0' / 'YN\\0') + u16 LE item
      pointer table が挟まる

  **active group の特定**: `+0xA844` current_ptr が指す item span を含む
  group が画面に表示されている group。

API:
  parse_menu_groups(raw, *, base_offset) -> list[MenuGroup]
    全 menu group + 各 item span (anchor 相対) を抽出
  select_menu_group_by_ptr(groups, ptr) -> MenuGroup | None
    ptr が item span 内の group を返す。なければ None
  read_shop_menu_items(analyzer, anchor) -> list[str]
    互換: parse_menu_groups(...)[0] の text list を返す wrapper
  translate_shop_menu_items(items) -> list[tuple[str, str]]
    各 item を ui.json で翻訳
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import i18n_helper as i18n
from arena_bridge import ArenaMemoryAnalyzer


# Memory Analyzer 観測で確認した anchor 相対固定 offset。
# 0x725F から "09 c0 42 09 d4 75 79 ..." の "Buy Drinks" 構造が開始する。
# 宿屋の複数 group は 0x100 byte buffer 内に収まるが、神殿メニュー
# (Bless/Cure/Heal/Exit) は +0x7574 ~ +0x759C にあり 0x100 byte の外。
# MENU_RT.IMG を共有する施設群 (宿屋 / 神殿 / 装備店 / 魔術師ギルド) の menu
# group を 1 回のスキャンで全部取得するため、buffer を 0x400 byte に拡張する。
# 同 buffer 内の複数 group は select_menu_group_by_ptr で current_ptr に
# 該当する group を選ぶため、無関係 group の混入は実害なし。
SHOP_MENU_BUFFER_OFFSET = 0x725F
SHOP_MENU_BUFFER_MAXLEN = 0x400  # MENU_RT.IMG 共有施設対応

# メニューブロック間の最大 padding (このサイズを超えると別グループ)
_MENU_BLOCK_MAX_GAP = 8


_UI_DICT: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# context-aware UI 直引き (公開版 runtime 依存の解消)
# ---------------------------------------------------------------------------
# `ui` カテゴリの id はコンテキスト接頭辞付き非スラッグ (`ui.tavern_get_room.0`
# / `ui.equipment_buy_weapon.0` 等) で、同一英語 ("Exit" 等) が施設別に別 id を
# 持つ。`_load_ui_dict()` は `i18n.originals("ui")` を走査して英語→訳 map を
# 「先勝ち」で畳むため、(1) 文脈差を表現できず、(2) 公開ビルドは原文
# 非同梱で `originals("ui")` が空になり英語 fallback に落ちる。
#
# このため施設 (owner_kind) + 既知メニュー英語から `ui.<context>.<name>.0` を
# 直引きし `i18n.text_opt(id)` で解決する。id 直引きは原文を要さず公開版でも
# ja/ui.json から解決でき、訳もそのまま保つ。
#
# 表は各施設の店主メニュー署名 (`menu_signatures`) とメニュータイトル・Spellmaker
# 効果メニューを owner ごとに完備したもの。english は
# ライブメモリ一致用アンカー (menu_signatures と同カテゴリ)・id は ui.json の
# curated 構造 id。両者の対応は ui.json と一致することを
# `tests/test_shop_menu_reader.py` の guard が固定する (drift 防止)。未知 owner /
# 未登録項目は `_load_ui_dict()` へ fallback (公開では degraded)。
_OWNER_UI_IDS: dict[str, dict[str, str]] = {
    "tavern": {
        "Buy Drinks": "ui.tavern_buy_drinks.0",
        "Get a Room": "ui.tavern_get_room.0",
        "Sneak into a Room": "ui.tavern_sneak_room.0",
        "Rumors": "ui.tavern_rumors.0",
        "Exit": "ui.tavern_exit.0",
        "General": "ui.rumor_general.0",
        "Work": "ui.rumor_work.0",
        "MENU OPTIONS": "ui.menu_options.0",
        "Rumor Type": "ui.rumor_type_title.0",
    },
    "temple": {
        "Bless": "ui.bless.0",
        "Cure": "ui.cure.0",
        "Heal": "ui.heal.0",
        "Exit": "ui.exit.0",
        "MENU OPTIONS": "ui.menu_options.0",
    },
    "equipment": {
        "Buy": "ui.buy.0",
        "Sell": "ui.sell.0",
        "Repair": "ui.repair.0",
        "Steal": "ui.steal.0",
        "Exit": "ui.exit.0",
        "Weapon": "ui.equipment_buy_weapon.0",
        "Armor": "ui.equipment_buy_armor.0",
        "MENU OPTIONS": "ui.menu_options.0",
        "BUY OPTIONS": "ui.equipment_buy_options.0",
    },
    "mages_guild": {
        "Buy": "ui.buy.0",
        "Detect Magic": "ui.mages_detect_magic.0",
        "Spellmaker": "ui.mages_spellmaker_menu.0",
        "Steal": "ui.steal.0",
        "Exit": "ui.exit.0",
        "Potions": "ui.mages_potions.0",
        "Magic items": "ui.mages_magic_items.0",
        "Spells": "ui.mages_spells.0",
        "Potion": "ui.mages_potion.0",
        "Magic item": "ui.mages_magic_item.0",
        "MENU OPTIONS": "ui.menu_options.0",
        "PICK ITEM": "ui.mages_pick_item.0",
        # Spellmaker 効果メニュー (_render_effect_menu)
        "Edit Effects": "ui.mages_edit_effects.0",
        "Add": "ui.mages_add.0",
        "Modify": "ui.mages_modify.0",
        "Delete": "ui.mages_delete.0",
        # 効果名 (Spellmaker 詳細ヘッダ・translate_name 失敗時のフォールバック)
        "Damage Health": "ui.eff_damage_health.0",
        "Continuous Damage Health": "ui.eff_cont_damage_health.0",
        "Cause Curse": "ui.eff_cause_curse.0",
        "Cause Disease": "ui.eff_cause_disease.0",
        "Create Shield": "ui.eff_create_shield.0",
        "Create Wall": "ui.eff_create_wall.0",
        "Designate as Non-Target": "ui.eff_designate_nontarget.0",
        "Light": "ui.eff_light.0",
        "Levitate": "ui.eff_levitate.0",
        "Regenerate": "ui.eff_regenerate.0",
        "Drain Attribute Strength": "ui.eff_drain_attr_str.0",
        "Fortify Attribute Strength": "ui.eff_fortify_attr_str.0",
    },
}


def resolve_ui_id(owner_kind: str, en: str) -> Optional[str]:
    """owner_kind 文脈の既知メニュー英語 → `ui` app_id を直引きする。

    未知 owner / 未登録項目は None。`_OWNER_UI_IDS` (ui.json 検証済み) のみを引く
    純関数で、原文に依存しない (= 公開版安全)。
    """
    return _OWNER_UI_IDS.get(owner_kind or "", {}).get(en)


def translate_ui_text(owner_kind: str, en: str) -> Optional[str]:
    """owner_kind 文脈で `ui` 英語を現在言語訳へ解決する (公開版安全)。

    既知項目は `resolve_ui_id` の app_id を `i18n.text_opt` で直引き (原文
    非依存)。未知 owner / 未登録項目は `_load_ui_dict()` へ fallback する
    (英語→訳 map で解決・公開版では空= None = 英語 fallback degraded)。
    """
    _id = resolve_ui_id(owner_kind, en)
    if _id:
        t = i18n.text_opt(_id)
        if t:
            return t
    return _load_ui_dict().get(en)


@dataclass(frozen=True)
class MenuItem:
    """単一 menu item の text + anchor 相対 span + ショートカット文字."""
    text: str
    start: int  # 'start' = item の `09 c0` 開始 byte の anchor 相対 offset
    end: int    # 'end'   = item terminator (`0d 00`) 直後の anchor 相対 offset
    hotkey: str = ""  # 頭文字ハイライト文字 (`09 c0 <first> 09 d4 ...` の first)


@dataclass(frozen=True)
class MenuGroup:
    """連続 item の group + anchor 相対 span."""
    items: tuple[MenuItem, ...]
    start: int  # 最初の item の start
    end: int    # 最後の item の end


def _load_ui_dict() -> dict[str, str]:
    """ui カテゴリの 原文(en)→現在言語訳 マップを翻訳切替コアから構築する。

    旧 dictionary/ui.json 直読みを廃止。5 render module が本関数を共有するため
    シグネチャ(dict[str,str] 返却)は維持する。切替は再起動方式のため build once。
    """
    global _UI_DICT
    if _UI_DICT is not None:
        return _UI_DICT
    _UI_DICT = {}
    for _id, entry in i18n.originals("ui").items():
        en = entry.get("original") if isinstance(entry, dict) else None
        if not en:
            continue
        translated = i18n.text(_id)
        if translated and translated != _id and en not in _UI_DICT:
            _UI_DICT[en] = translated
    return _UI_DICT


def parse_menu_groups(raw: bytes, *,
                       base_offset: int = SHOP_MENU_BUFFER_OFFSET
                       ) -> list[MenuGroup]:
    """raw から全 menu group + 各 item の anchor 相対 span を抽出する。

    item 構造: `09 c0 <first> 09 d4 <rest> 0d 00`。
    item 間 gap が `_MENU_BLOCK_MAX_GAP` 以下なら同一 group、超えたら次 group
    として走査を継続する。

    Returns:
      group 開始順の MenuGroup list (空入力 / parser 失敗で空 list)。
    """
    n = len(raw)
    groups: list[MenuGroup] = []
    current_items: list[MenuItem] = []
    current_group_start: Optional[int] = None
    last_end: int = -1
    i = 0
    while i + 5 < n:
        if raw[i] == 0x09 and raw[i + 1] == 0xC0:
            # gap 判定: 同一 group か新規か
            if (current_items and last_end != -1
                    and (i - last_end) > _MENU_BLOCK_MAX_GAP):
                # gap 超過 → 現 group を確定して新規 group 開始
                groups.append(MenuGroup(
                    items=tuple(current_items),
                    start=current_group_start or current_items[0].start,
                    end=current_items[-1].end,
                ))
                current_items = []
                current_group_start = None
            # ハイライト文字 (`09 c0` 直後) が語頭でない項目への対応。
            # 既に同一 group に項目があり、直前項目の terminator から本 `09 c0`
            # までに printable 文字が挟まる場合、それは項目テキストの語頭側
            # (= 例: "Steal" はハイライトが 'T' で、'S' が `09 c0` の手前に置かれる)。
            # 末尾の printable 連続を prefix として取り込み、語頭の取りこぼしを防ぐ。
            # group 先頭項目 (current_items 空) は対象外 (= 先頭は通常ハイライト=語頭)。
            prefix = ""
            if current_items and last_end != -1 and last_end < i:
                run: list[str] = []
                for b in raw[last_end:i]:
                    if 0x20 <= b <= 0x7E:
                        run.append(chr(b))
                    else:
                        run = []  # 非 printable で区切り、末尾連続のみ残す
                prefix = "".join(run)
            first_b = raw[i + 2]
            first_char = (chr(first_b)
                          if 0x20 <= first_b <= 0x7E else "")
            j = i + 3
            # "09 d4" を skip (任意)
            if j + 1 < n and raw[j] == 0x09 and raw[j + 1] == 0xD4:
                j += 2
            # \r or \0 までを残り文字列として読む
            rest_chars: list[str] = []
            while j < n and raw[j] not in (0x00, 0x0D):
                if 0x20 <= raw[j] <= 0x7E:
                    rest_chars.append(chr(raw[j]))
                j += 1
            text = (prefix + first_char + "".join(rest_chars)).strip()
            # \r or \0 を skip (terminator)
            term_start = j
            while j < n and raw[j] in (0x00, 0x0D):
                j += 1
            term_end = j
            # item の anchor 相対 span (prefix を含めて開始位置を前へ伸ばす)
            item_start_abs = base_offset + i - len(prefix)
            item_end_abs = base_offset + term_end
            if text:
                current_items.append(MenuItem(
                    text=text,
                    start=item_start_abs,
                    end=item_end_abs,
                    hotkey=first_char,
                ))
                if current_group_start is None:
                    current_group_start = item_start_abs
            last_end = j
            i = j
        else:
            i += 1
    # 末尾 group の確定
    if current_items:
        groups.append(MenuGroup(
            items=tuple(current_items),
            start=current_group_start or current_items[0].start,
            end=current_items[-1].end,
        ))
    return groups


def select_menu_group_by_ptr(groups: list[MenuGroup],
                              ptr: Optional[int]) -> Optional[MenuGroup]:
    """ptr が item span 内に入る group を返す。なければ None。

    判定: `item.start <= ptr < item.end` を満たす item を含む group。
    item 間 (hotkey string / pointer table / padding) を指している場合は
    None を返す (= first group fallback はしない)。
    """
    if ptr is None:
        return None
    for g in groups:
        for it in g.items:
            if it.start <= ptr < it.end:
                return g
    return None


def parse_menu_first_group(raw: bytes) -> list[str]:
    """互換 API: parse_menu_groups(...)[0] の text list を返す。"""
    groups = parse_menu_groups(raw)
    if not groups:
        return []
    return [it.text for it in groups[0].items]


def read_shop_menu_items(analyzer: "ArenaMemoryAnalyzer",
                         anchor: int) -> list[str]:
    """店主メニュー全項目を抽出する (最初のグループのみ、互換 API)。

    parse_menu_groups / select_menu_group_by_ptr を使う方が確実。
    """
    try:
        raw = analyzer.read_bytes(
            anchor + SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_menu_first_group(raw)


def translate_shop_menu_items(items: list[str],
                              owner_kind: str = "",
                              ) -> list[tuple[str, Optional[str]]]:
    """各メニュー項目を ui.json 経由で翻訳。未登録は None。

    owner_kind 指定時は context-aware 直引き (`translate_ui_text`・公開版安全)。
    未指定 (後方互換) は従来どおり `_load_ui_dict()` の英語→訳 map を引く
    (= dev 専用・公開版では空 map で None)。
    """
    if owner_kind:
        return [(it, translate_ui_text(owner_kind, it)) for it in items]
    d = _load_ui_dict()
    return [(it, d.get(it)) for it in items]


__all__ = [
    "SHOP_MENU_BUFFER_OFFSET",
    "SHOP_MENU_BUFFER_MAXLEN",
    "MenuItem",
    "MenuGroup",
    "parse_menu_groups",
    "select_menu_group_by_ptr",
    "parse_menu_first_group",
    "read_shop_menu_items",
    "translate_shop_menu_items",
    "resolve_ui_id",
    "translate_ui_text",
]
