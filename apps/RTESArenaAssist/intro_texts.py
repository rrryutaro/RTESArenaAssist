"""
intro_texts.py — Arena 起動・メニュー・ニューゲーム画面テキストの ID 解決

表示文字列はコード内に持たず、context（IMG ファイル名・メニュー項目）→ 翻訳 ID の
対応のみを保持し、表示は i18n 辞書層から現在言語で解決する。

- Arena 画面由来テキスト（起動引用・オープニング・あらすじスライド・メニュー項目名）は
  `pregame_intro` カテゴリ（live_surface）の翻訳 ID。原文は単一静的 source に確定できない
  ため公開物へ静的同梱しない（_original は dev 専用アンカー・公開非同梱・原文は live 画面
  surface 由来として扱う）。
- メニュー項目の補足説明文は Assist 記述（Arena 資産でない）であり `ui_app`
  カテゴリ（assist_bundled）の翻訳 ID。
"""

from __future__ import annotations

import i18n_helper as i18n

# ── 起動イントロ（IMG → 翻訳 ID）──
#   QUOTE.IMG   → 起動引用画面
#   SCROLL01.IMG → オープニング ページ1
#   SCROLL02.IMG → オープニング ページ2
STARTUP_PAGE_IDS: dict[str, str] = {
    "QUOTE.IMG": "pregame_intro.startup_quote",
    "SCROLL01.IMG": "pregame_intro.startup_page1",
    "SCROLL02.IMG": "pregame_intro.startup_page2",
}
# レイアウトパネルの一括表示順（起動引用 → ページ1 → ページ2）
STARTUP_PAGE_ORDER: list[str] = [
    "pregame_intro.startup_quote",
    "pregame_intro.startup_page1",
    "pregame_intro.startup_page2",
]

# ── ニューゲーム あらすじ（INTRO01〜09.IMG → 翻訳 ID）──
NEWGAME_SLIDE_IDS: dict[str, str] = {
    f"INTRO0{i}": f"pregame_intro.slide_INTRO0{i}" for i in range(1, 10)
}
NEWGAME_SLIDE_ORDER: list[str] = [NEWGAME_SLIDE_IDS[k]
                                  for k in sorted(NEWGAME_SLIDE_IDS)]

# ── タイトルメニュー（表示順に (項目名 ID, 補足説明 ID)）──
#   項目名＝Arena 由来（pregame_intro）／補足説明＝Assist 記述（ui_app）。
MENU_ITEM_IDS: list[tuple[str, str]] = [
    ("pregame_intro.menu_load", "pregame.menu_load_desc"),
    ("pregame_intro.menu_newgame", "pregame.menu_newgame_desc"),
    ("pregame_intro.menu_exit", "pregame.menu_exit_desc"),
]


def source_text(id_str: str) -> str:
    """原文（英語ソース）列の文字列を返す（未解決は空文字）。

    `pregame_intro`（live_surface）は `_original` アンカー（dev 専用・公開では None＝
    live 画面 surface 由来扱いで degrade）、`ui_app` 説明文は en レイヤから取る。
    """
    if not id_str:
        return ""
    o = i18n.original(id_str)
    if o:
        return o
    en = i18n.lang_value_in(id_str, "en")
    return en or ""


def display_text(id_str: str) -> str:
    """現在言語の表示訳を返す（fallback 連鎖込み・未解決は空文字）。"""
    if not id_str:
        return ""
    return i18n.text_opt(id_str) or ""
