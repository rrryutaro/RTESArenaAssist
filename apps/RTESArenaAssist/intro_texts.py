
from __future__ import annotations

import i18n_helper as i18n

STARTUP_PAGE_IDS: dict[str, str] = {
    "QUOTE.IMG": "pregame_intro.startup_quote",
    "SCROLL01.IMG": "pregame_intro.startup_page1",
    "SCROLL02.IMG": "pregame_intro.startup_page2",
}
STARTUP_PAGE_ORDER: list[str] = [
    "pregame_intro.startup_quote",
    "pregame_intro.startup_page1",
    "pregame_intro.startup_page2",
]

NEWGAME_SLIDE_IDS: dict[str, str] = {
    f"INTRO0{i}": f"pregame_intro.slide_INTRO0{i}" for i in range(1, 10)
}
NEWGAME_SLIDE_ORDER: list[str] = [NEWGAME_SLIDE_IDS[k]
                                  for k in sorted(NEWGAME_SLIDE_IDS)]

MENU_ITEM_IDS: list[tuple[str, str]] = [
    ("pregame_intro.menu_load", "pregame.menu_load_desc"),
    ("pregame_intro.menu_newgame", "pregame.menu_newgame_desc"),
    ("pregame_intro.menu_exit", "pregame.menu_exit_desc"),
]


def source_text(id_str: str) -> str:
    if not id_str:
        return ""
    o = i18n.original(id_str)
    if o:
        return o
    en = i18n.lang_value_in(id_str, "en")
    return en or ""


def display_text(id_str: str) -> str:
    if not id_str:
        return ""
    return i18n.text_opt(id_str) or ""
