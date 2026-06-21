"""screen_detector.py — 画面状態検出 dispatcher

dispatcher は AssistWindow._top_level_state（"pregame" | "chargen" | "normal-play"）
を最初に参照し、その状態内のモジュールにのみ振り分ける。chargen 状態中に
play module を呼ぶことは絶対にない（階層構造を強制）。

モジュール構成:
- `screen_detector.py`: dispatcher + pregame 検出（本ファイル）
- `screen_detector_chargen.py`: chargen subscreen + INTRO*.IMG 検出
- `screen_detector_play.py`:    通常プレイの検出

公開 API（`detect_screen` / `get_chargen_subscreen` / `MENU_ACTIVE_OFFSET` 等）は
呼び出し側互換を維持する。
"""
from __future__ import annotations
from typing import Optional, Tuple

import i18n_helper as _i18n

# ──────────────────────────────────────────────────────────────
# 観測で確定したオフセット（observation ベースの仮説）
# ──────────────────────────────────────────────────────────────
FLAG_STATUS_POPUP_OFFSET    = 0x12BA  # u8: キャラクターポップアップ専用 (status/equipment/
                                       #     spellbook/spell_detail) 表示中=1
                                       #     system_menu / automap / logbook では 0
FLAG_EQUIPMENT_OPEN_OFFSET  = 0x129A  # u8: アイテム一覧サブページ表示中=1
                                       # 注意: equipment → status_page 等で残留する経路あり
                                       #       （観測）。flag_status と併用で判定。
FLAG_SPELL_DETAIL_OFFSET    = 0x1AEA  # u8: 旧 spellbook サブページ判別。極性が経路依存で
                                       #   逆転する (= 一覧 0x00/詳細 0xFF になる経路あり)
                                       #   ため主信号にしない。SPELL_VIEW_OFFSET を使う。
SPELL_VIEW_OFFSET           = 0x8F6E  # u8: 魔法一覧 / 魔法詳細 / 名称変更 の判別。
                                       #   絶対値はロード毎に変わるが、ロード内では
                                       #   一覧/詳細/名称変更が固定差のセットになる (観測):
                                       #     一覧 - 詳細     = 0x54
                                       #     一覧 - 名称変更 = 0x9F
                                       #   突入時 (=一覧) の値を base に捕捉し、base からの
                                       #   差で判別する (poll_controller + controllers/
                                       #   spell_view.py)。観測ベースの仮説。
MENU_ACTIVE_OFFSET          = 0x127C  # u16 LE: システムメニュー = 0x0000 で安定
                                       #         探索画面 idle = 0x0000 ↔ 0xa301 をバウンス
                                       #         判定には連続 2 ポーリング 0 を要求する
POPUP_OPEN_OFFSET           = 0x7924  # u8: 汎用 popup フラグ。キャラクターポップアップ +
                                       #     automap + logbook で 1。閉じると 0。
CITY_NPC_ACTIVE_OFFSET      = 0xA845  # u16 LE: 街 NPC ダイアログ中に非ゼロ（0x4385 観測）。
                                       #     OP.IMG + MENU_ACTIVE=0 でも system_menu に
                                       #     誤検出しないためのガード用（仮説: 1 観測）。

# 旧定数（攻撃態勢用、実装未使用）
ACTION_ACTIVE_OFFSET        = 0x79A9  # u8: 仮説のみ・現状は不使用（将来の調査用に残す）


# ──────────────────────────────────────────────────────────────
# 画面 ID セット（旧 SCREEN_NAMES dict の key 集合。所属確認に使用）
# ──────────────────────────────────────────────────────────────
SCREEN_IDS: frozenset = frozenset({
    # Phase 1: 起動
    "quote", "scroll01", "scroll02", "menu", "loadsave",
    # Phase 2: chargen
    "newgame_intro", "race_select", "race_confirm", "race_description",
    "status_proclamation", "class_select", "class_list", "class_accept",
    "ten_questions", "province_confirm", "class_advice", "goyenow",
    "distribute", "choose_attrs", "name_input", "sex_select",
    "appearance", "chargen_complete", "opening_cinematic",
    # Phase 3: 通常プレイ
    "game_screen", "status_page", "bonus_screen", "equipment",
    "spellbook", "spell_detail", "system_menu", "loadsave_in_play",
    # Phase 4: 既知だが未対応
    "automap", "logbook", "npc_dialog", "combat", "shop",
    "travel_map", "message_box",
    # フォールバック
    "loading", "unknown",
})


def _tr(sid: str, **kwargs) -> str:
    """screen ID を i18n キー "screen.<sid>" で翻訳して返す。"""
    return _i18n.tr(f"screen.{sid}", **kwargs)


# ──────────────────────────────────────────────────────────────
# 共有ヘルパー
# ──────────────────────────────────────────────────────────────
def _read_u8(analyzer, addr: int) -> int:
    try:
        return analyzer.read_bytes(addr, 1)[0]
    except (OSError, AttributeError):
        return 0


def _read_u16_le(analyzer, addr: int) -> int:
    try:
        b = analyzer.read_bytes(addr, 2)
        return b[0] | (b[1] << 8)
    except (OSError, AttributeError):
        return 0xFFFF  # 検出失敗時は「非アクティブ」相当を返してメニュー誤検出防止


# ──────────────────────────────────────────────────────────────
# pregame 専用検出（boot IMG / XMI のみ出現する状態）
# ──────────────────────────────────────────────────────────────
def _detect_pregame_screen(img_name: str) -> Optional[Tuple[str, str]]:
    """pregame 状態（起動〜タイトル）専用の画面検出。

    pregame 専用 IMG のみを返す。
    それ以外の IMG は None を返し、dispatcher が "loading" にフォールバックする。
    """
    img_upper = (img_name or "").upper()
    if img_upper.endswith(".XMI"):
        return ("loading", _tr("loading"))
    if img_upper == "QUOTE.IMG":
        return ("quote", _tr("quote"))
    if img_upper == "SCROLL01.IMG":
        return ("scroll01", _tr("scroll01"))
    if img_upper == "SCROLL02.IMG":
        return ("scroll02", _tr("scroll02"))
    if img_upper == "MENU.IMG":
        return ("menu", _tr("menu"))
    if img_upper == "LOADSAVE.IMG":
        return ("loadsave", _tr("loadsave"))
    return None


# ──────────────────────────────────────────────────────────────
# dispatcher
# ──────────────────────────────────────────────────────────────
def detect_screen(analyzer, anchor: Optional[int], img_name: str,
                  chargen_hint: Optional[str] = None,
                  menu_active_was_zero: bool = False,
                  top_level_state: str = "pregame",
                  last_chargen_subscreen: Optional[str] = None,
                  mif_name: str = "",
                  area: Optional[str] = None) -> Tuple[str, str]:
    """現在画面を検出する dispatcher。

    階層構造:
      1. analyzer / anchor が None → loading
      2. top_level_state == "pregame"    → _detect_pregame_screen()
      3. top_level_state == "chargen"    → detect_chargen_screen()（play module は絶対呼ばない）
      4. top_level_state == "normal-play"→ detect_play_screen()

    Args:
        analyzer:              アタッチ済み ArenaMemoryAnalyzer（None なら loading 扱い）
        anchor:                アンカーアドレス
        img_name:              現在の screen_img 値（大文字小文字どちらでも可）
        chargen_hint:          chargen 中のサブ画面 ID（`get_chargen_subscreen()` の戻り値）
        menu_active_was_zero:  直前 poll の menu_active も 0 だったか（system_menu 判定用）
        top_level_state:       現在の top-level 状態
        last_chargen_subscreen: chargen 中で最後に検出したサブ画面 ID（subscreen 間の隙間 fallback 用）

    Returns:
        (screen_id, display_name) のタプル
    """
    from screen_detector_chargen import detect_chargen_screen
    from screen_detector_play import detect_play_screen

    if analyzer is None or anchor is None:
        return ("loading", _tr("loading"))

    if top_level_state == "pregame":
        # ── 1. pregame: boot IMG / XMI のみ ──
        result = _detect_pregame_screen(img_name)
        return result if result is not None else ("loading", _tr("loading"))

    elif top_level_state == "chargen":
        # ── 2. chargen: play module は絶対に呼ばない（不変条件）──
        result = detect_chargen_screen(chargen_hint, img_name,
                                       last_subscreen=last_chargen_subscreen)
        if result is not None:
            return result
        # chargen 中の subscreen 間の隙間 → last known subscreen にフォールバック
        fallback = last_chargen_subscreen or "loading"
        return (fallback, _tr(fallback))

    else:
        # ── 3. normal-play ──
        return detect_play_screen(
            analyzer, anchor, img_name,
            mif_name=mif_name,
            menu_active_was_zero=menu_active_was_zero,
            area=area,
        )


# ──────────────────────────────────────────────────────────────
# chargen subscreen 識別
# ──────────────────────────────────────────────────────────────
def get_chargen_subscreen(window) -> Optional[str]:
    """AssistWindow の chargen 内部フラグから現在のサブ画面 ID を返す。

    判定優先順:
        1  opening_cinematic > 2  sex_select       > 3  name_input       >
        4  appearance        > 5  choose_attrs     > 6  distribute       >
        7  goyenow           > 8  class_advice     > 9  race_description  >
        10 status_proclamation > 11 race_select    > 12 class_accept     >
        13 ten_questions     > 14 class_list       > 15 class_select

    時系列の逆順で判定し「最も後に進入した subscreen が勝つ」原則を実現する。
    opening_cinematic は chargen の最終状態（post-chargen cinematic）のため
    priority 1（最優先）とする。
    chargen_done == 1 になるか chargen state リセットで各フラグはクリアされる
    想定なので、本関数は無条件にフラグを参照してよい（クリア済みなら None）。
    """
    # 判定優先順 1: post-chargen cinematic（chargen の最終状態 = 最優先）
    if getattr(window, "_chargen_opening_displayed", False):
        return "opening_cinematic"
    # 判定優先順 2〜3: chargen 後半
    if getattr(window, "_chargen_sex_select_displayed", False):
        return "sex_select"
    if getattr(window, "_in_chargen_name", False):
        return "name_input"
    # 判定優先順 4〜8: chargen 中盤（appearance 以降）
    if getattr(window, "_chargen_appearance_displayed", False):
        return "appearance"
    if getattr(window, "_chargen_choose_attrs_displayed", False):
        return "choose_attrs"
    if getattr(window, "_chargen_distribute_displayed", False):
        return "distribute"
    if getattr(window, "_chargen_goyenow_displayed", False):
        return "goyenow"
    if getattr(window, "_chargen_in_advice", False):
        return "class_advice"
    # 判定優先順 9: race_description（"Know ye this also..."）
    if getattr(window, "_chargen_race_desc_displayed", False):
        return "race_description"
    # 判定優先順 10: status_proclamation（"Then thou wilt be known as the..."）
    if getattr(window, "_chargen_complete_displayed", False):
        return "status_proclamation"
    # 判定優先順 11: race_select
    if getattr(window, "_chargen_race_select_displayed", False):
        return "race_select"
    # 判定優先順 12: class_accept（10Q 結果 / "Thou wouldst survive..."）
    if getattr(window, "_chargen_class_accept_displayed", False):
        return "class_accept"
    # 判定優先順 13: ten_questions
    if getattr(window, "_chargen_10q_displayed", False):
        return "ten_questions"
    # 判定優先順 14: class_list（手動経路、Choose thy class）
    if getattr(window, "_chargen_class_list_active", False):
        return "class_list"
    # 判定優先順 15: class_select（メソッド選択）
    if getattr(window, "_chargen_method_window", False):
        return "class_select"
    return None
