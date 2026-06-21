from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import i18n_helper as i18n
from arena_bridge import ArenaMemoryAnalyzer


SHOP_MENU_BUFFER_OFFSET = 0x725F
SHOP_MENU_BUFFER_MAXLEN = 0x400

_MENU_BLOCK_MAX_GAP = 8


_UI_DICT: dict[str, str] | None = None


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
        "Edit Effects": "ui.mages_edit_effects.0",
        "Add": "ui.mages_add.0",
        "Modify": "ui.mages_modify.0",
        "Delete": "ui.mages_delete.0",
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
    return _OWNER_UI_IDS.get(owner_kind or "", {}).get(en)


def translate_ui_text(owner_kind: str, en: str) -> Optional[str]:
    _id = resolve_ui_id(owner_kind, en)
    if _id:
        t = i18n.text_opt(_id)
        if t:
            return t
    return _load_ui_dict().get(en)


@dataclass(frozen=True)
class MenuItem:
    text: str
    start: int
    end: int
    hotkey: str = ""


@dataclass(frozen=True)
class MenuGroup:
    items: tuple[MenuItem, ...]
    start: int
    end: int


def _load_ui_dict() -> dict[str, str]:
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
    n = len(raw)
    groups: list[MenuGroup] = []
    current_items: list[MenuItem] = []
    current_group_start: Optional[int] = None
    last_end: int = -1
    i = 0
    while i + 5 < n:
        if raw[i] == 0x09 and raw[i + 1] == 0xC0:
            if (current_items and last_end != -1
                    and (i - last_end) > _MENU_BLOCK_MAX_GAP):
                groups.append(MenuGroup(
                    items=tuple(current_items),
                    start=current_group_start or current_items[0].start,
                    end=current_items[-1].end,
                ))
                current_items = []
                current_group_start = None
            prefix = ""
            if current_items and last_end != -1 and last_end < i:
                run: list[str] = []
                for b in raw[last_end:i]:
                    if 0x20 <= b <= 0x7E:
                        run.append(chr(b))
                    else:
                        run = []
                prefix = "".join(run)
            first_b = raw[i + 2]
            first_char = (chr(first_b)
                          if 0x20 <= first_b <= 0x7E else "")
            j = i + 3
            if j + 1 < n and raw[j] == 0x09 and raw[j + 1] == 0xD4:
                j += 2
            rest_chars: list[str] = []
            while j < n and raw[j] not in (0x00, 0x0D):
                if 0x20 <= raw[j] <= 0x7E:
                    rest_chars.append(chr(raw[j]))
                j += 1
            text = (prefix + first_char + "".join(rest_chars)).strip()
            term_start = j
            while j < n and raw[j] in (0x00, 0x0D):
                j += 1
            term_end = j
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
    if current_items:
        groups.append(MenuGroup(
            items=tuple(current_items),
            start=current_group_start or current_items[0].start,
            end=current_items[-1].end,
        ))
    return groups


def select_menu_group_by_ptr(groups: list[MenuGroup],
                              ptr: Optional[int]) -> Optional[MenuGroup]:
    if ptr is None:
        return None
    for g in groups:
        for it in g.items:
            if it.start <= ptr < it.end:
                return g
    return None


def parse_menu_first_group(raw: bytes) -> list[str]:
    groups = parse_menu_groups(raw)
    if not groups:
        return []
    return [it.text for it in groups[0].items]


def read_shop_menu_items(analyzer: "ArenaMemoryAnalyzer",
                         anchor: int) -> list[str]:
    try:
        raw = analyzer.read_bytes(
            anchor + SHOP_MENU_BUFFER_OFFSET, SHOP_MENU_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return []
    return parse_menu_first_group(raw)


def translate_shop_menu_items(items: list[str],
                              owner_kind: str = "",
                              ) -> list[tuple[str, Optional[str]]]:
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
