from __future__ import annotations

import re

_COST_STR_OFFSET = 0x929C

_NPC_DIALOG_OFFSET = 0x1044
_PROMPT_EXTRA_SCAN_OFFSETS = (_COST_STR_OFFSET,)

_SPELLDETAIL_KEY = "_mages_spelldetail_key_prev"


def _translate_ui(en: str) -> str:
    try:
        from shop_menu_reader import translate_ui_text
        return translate_ui_text("mages_guild", en) or en
    except Exception:  # noqa: BLE001
        return en


def _read_cost_string(w):
    try:
        raw = w._analyzer.read_bytes(w._anchor + _COST_STR_OFFSET, 24)
    except (OSError, AttributeError):
        return None
    m = re.search(rb"C=(\d+)", raw)
    return int(m.group(1)) if m else None


def _casting_cost_divisor(player_level) -> int:
    try:
        level = int(player_level or 0)
    except (TypeError, ValueError):
        level = 0
    return max(1, level + 2) if level > 0 else 4


def _casting_cost_from_spell_cost(spell_cost: int, player_level) -> int:
    return int(spell_cost) // _casting_cost_divisor(player_level)


def _buy_price_for(w, name: str):
    try:
        from mages_list_reader import read_active_priced_list
        for it in read_active_priced_list(w._analyzer, w._anchor):
            if it.get("en") == name:
                digits = "".join(c for c in it.get("price_display", "")
                                 if c.isdigit())
                return int(digits) if digits else None
    except Exception:  # noqa: BLE001
        pass
    return None
