"""pregame L1 状態の翻訳描画。

pregame (タイトル / ロード / オープニング演出 / ニューゲームスライド) の
IMG 別翻訳描画を pregame L1 node 所有としてここに集約する。従来は汎用
``controllers/img_screen_controller.py`` が描画を所有していた (描画所有の
node 化 = 分離化)。img_screen_controller の IMG 変化ハンドラは本モジュール
へ委譲する。

各関数は AssistWindow (``w``) を参照経由で UiRouter / 設定 / state vars に
アクセスする (img_screen_controller の従来メソッドと挙動同一・純移設)。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("pregame_render")


def show_startup_intro(w, img_name: str) -> None:
    """起動イントロ（QUOTE/SCROLL01/SCROLL02.IMG）の翻訳を表示する。

    実機観測シーケンス (2026-05-05):
        QUOTE.IMG   → Gaiden Shinji 引用
        SCROLL01.IMG → Opening Page 1（タムリエル〜アリーナの由来）
        SCROLL02.IMG → Opening Page 2（Uriel Septim VII / Elder Scrolls）
    """
    from intro_texts import (STARTUP_PAGE_IDS, STARTUP_PAGE_ORDER,
                             source_text, display_text)
    page_id = STARTUP_PAGE_IDS.get(img_name)
    slide_en = source_text(page_id)
    slide_ja = display_text(page_id)
    w._set_chargen_ui_state(True)
    # メインパネル: 現在ページのみ
    update_panel = (
        not w._startup_layout_pushed
        and w._layout_translate_panel is not None
    )
    # レイアウトパネル: 初回のみ全テキストを一括表示（ページ間は改行のみ）
    if update_panel:
        all_en = "\n".join(source_text(i) for i in STARTUP_PAGE_ORDER)
        all_ja = "\n".join(display_text(i) for i in STARTUP_PAGE_ORDER)
        w._ui_router.update_translation(
            "top_level_startup_intro", slide_en, slide_ja,
            panel_en=all_en, panel_ja=all_ja,
            speech_role="situation")
        w._startup_layout_pushed = True
    else:
        w._ui_router.update_translation(
            "top_level_startup_intro", slide_en, slide_ja,
            update_panel=False, speech_role="situation")


def show_menu_screen(w) -> None:
    """タイトルメニュー（MENU.IMG）の翻訳を表示する。

    タイトル画面進入時に chargen state を全リセットする。
    システムメニュー → New Game でタイトルに戻った場合の前回 chargen 状態
    残留（特に _chargen_complete_displayed）を防止。
    """
    from intro_texts import MENU_ITEM_IDS, source_text, display_text
    # chargen state を全リセット（タイトル進入は次の chargen の起点）
    try:
        w._chargen._reset_chargen_state_for_restart(
            reason="title screen entered (MENU.IMG)")
    except (AttributeError, RuntimeError) as exc:
        _log.debug("chargen reset on MENU.IMG skipped: %s", exc)
    # メインパネル: 項目名 + 補足説明
    main_en_parts = [
        f"{source_text(nid)}  — {source_text(did)}"
        for nid, did in MENU_ITEM_IDS
    ]
    main_ja_parts = [
        f"{display_text(nid)}  — {display_text(did)}"
        for nid, did in MENU_ITEM_IDS
    ]
    main_en = "\n".join(main_en_parts)
    main_ja = "\n".join(main_ja_parts)
    # レイアウトパネル: ゲーム内テキスト（項目名）のみ
    layout_en = "\n".join(source_text(nid) for nid, _did in MENU_ITEM_IDS)
    layout_ja = "\n".join(display_text(nid) for nid, _did in MENU_ITEM_IDS)
    w._set_chargen_ui_state(True)
    w._ui_router.update_translation(
        "top_level_menu", main_en, main_ja,
        panel_en=layout_en, panel_ja=layout_ja)


def show_load_screen(w) -> None:
    """ロード画面（LOADSAVE.IMG）のセーブスロット一覧を表示する。"""
    import save_manager as sm
    import save_reader as sr
    import assist_settings as settings
    game_dir = settings.get("save_dir", "")
    slot_data: list[dict] = []
    if game_dir:
        backup_dir = settings.get("backup_dir", "") or sm.default_backup_dir()
        try:
            notes = sm.load_slot_notes(backup_dir)
        except Exception:
            notes = {}
        for slot in sm.list_slots(game_dir):
            try:
                info = sr.read_slot_info(game_dir, slot)
            except Exception:
                info = {"slot": slot, "save_name": None, "modified": None}
            slot_data.append({
                "slot":       info.get("slot", slot),
                "save_name":  info.get("save_name") or "",
                "note_label": notes.get(str(slot), {}).get("name", ""),
                "modified":   info.get("modified") or "",
            })
    w._set_chargen_ui_state(True)
    try:
        w._ui_router.update_load_screen_slots(
            "load_screen", slot_data)
    except AttributeError:
        pass


def show_newgame_slide(w, img_name: str) -> None:
    """ニューゲームイントロ（INTRO*.IMG）の現在スライド翻訳を表示する。

    実機観測 (2026-05-05) によるIMGとテキストの対応:
        INTRO01: マップ画像（テキストなし）
        INTRO02〜09: 各スライド固有のテキスト（NEWGAME_SLIDE_TEXTS dict）
    """
    from intro_texts import (NEWGAME_SLIDE_IDS, NEWGAME_SLIDE_ORDER,
                             source_text, display_text)
    # img_name = "INTRO04.IMG" → キー = "INTRO04"
    key = img_name.replace(".IMG", "")
    slide_id = NEWGAME_SLIDE_IDS.get(key)
    slide_en = source_text(slide_id)
    slide_ja = display_text(slide_id)

    w._set_chargen_ui_state(True)

    # メインタブ: 現在スライドのみ
    update_panel = (
        not w._newgame_layout_pushed
        and w._layout_translate_panel is not None
    )

    # レイアウトパネル: 初回のみ全スライドを一括表示（テキストあるスライドのみ）
    if update_panel:
        all_en = "\n".join(s for i in NEWGAME_SLIDE_ORDER if (s := source_text(i)))
        all_ja = "\n".join(s for i in NEWGAME_SLIDE_ORDER if (s := display_text(i)))
        w._ui_router.update_translation(
            "top_level_newgame_slide", slide_en, slide_ja,
            panel_en=all_en, panel_ja=all_ja,
            speech_role="situation")
        w._newgame_layout_pushed = True
    else:
        w._ui_router.update_translation(
            "top_level_newgame_slide", slide_en, slide_ja,
            update_panel=False, speech_role="situation")


__all__ = [
    "show_startup_intro",
    "show_menu_screen",
    "show_load_screen",
    "show_newgame_slide",
]
