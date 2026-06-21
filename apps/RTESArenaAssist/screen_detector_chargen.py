"""screen_detector_chargen.py — chargen 画面検出

責任範囲（normal-play 階層に従属）:
- chargen subscreen（class_select / ten_questions / race_select /
  class_advice / goyenow / distribute / choose_attrs / appearance /
  opening_cinematic）
- ニューゲームイントロ（INTRO01〜09.IMG）
- XMI 音楽期間（VISION.XMI 等）の chargen subscreen 維持

boot シーケンス（QUOTE / SCROLL01 / SCROLL02 / MENU / LOADSAVE）の
検出は pregame path（screen_detector._detect_pregame_screen）が担当する。
本モジュールは top_level_state == "chargen" 時のみ呼ばれる。

popup フラグ群（flag_status / popup_open / flag_equipment / flag_spell_detail /
menu_active）は **判定に使わない**。chargen フェーズの memory 状態は未観測の
ため、内部追跡フラグ（`_chargen_*_displayed`）と IMG 名で確定的に判定する。
"""
from __future__ import annotations
from typing import Optional, Tuple

from screen_detector import SCREEN_IDS, _tr


def detect_chargen_screen(
    chargen_hint: Optional[str],
    img_name: str,
    last_subscreen: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """chargen フェーズの画面を検出する。

    top_level_state == "chargen" のときのみ呼ばれる。boot IMG
    （QUOTE/SCROLL/MENU/LOADSAVE）は _detect_pregame_screen() が担当するため
    ここでは返さない。

    Args:
        chargen_hint:   `get_chargen_subscreen()` の戻り値。chargen subscreen ID
                        または None（subscreen 間の隙間）
        img_name:       現在の screen_img 値（大文字小文字どちらでも可）
        last_subscreen: 直近に検出した chargen subscreen ID（隙間の fallback 用）

    Returns:
        (screen_id, display_name) のタプル。検出できない場合は None
        （dispatcher が last_chargen_subscreen または "loading" にフォールバック）
    """
    img_upper = (img_name or "").upper()

    # XMI 音楽期間（VISION.XMI 等）: chargen subscreen を維持する
    # VISION.XMI = chargen 完了後の旅立ち専用 XMI。
    # chargen_hint → last_subscreen の順で優先してヘッダー消失を防ぐ。
    if img_upper.endswith(".XMI"):
        hint = chargen_hint or last_subscreen
        if hint and hint in SCREEN_IDS:
            return (hint, _tr(hint))
        return ("loading", _tr("loading"))

    # ── 1. ニューゲームイントロ INTRO01〜09 ──
    if img_upper.startswith("INTRO") and img_upper.endswith(".IMG"):
        try:
            num = int(img_upper.replace("INTRO", "").replace(".IMG", ""))
            return ("newgame_intro", _tr("newgame_intro", n=num))
        except ValueError:
            pass

    # post-chargen opening is a state-confirmed final chargen phase.  Arena may
    # leave the previous FACES*.CIF name in SCREEN_IMG during the handoff to the
    # status page, so the opening hint must win over the stale appearance IMG.
    if (chargen_hint == "opening_cinematic"
            or (last_subscreen == "opening_cinematic"
                and img_upper.startswith("FACES")
                and img_upper.endswith(".CIF"))):
        return ("opening_cinematic", _tr("opening_cinematic"))

    # ── 1.5 FACES*.CIF: 外見選択画面の確定信号 ──
    # appearance flag に依存せず、画面 IMG が FACES なら外見選択とみなす。
    # 能力値選択の Save/Reroll 確認画面 (MRSHIRT.IMG) と確実に区別する。
    if img_upper.startswith("FACES") and img_upper.endswith(".CIF"):
        return ("appearance", _tr("appearance"))

    # ── 2. chargen subscreen（NPC テキストフラグで確定）──
    if chargen_hint and chargen_hint in SCREEN_IDS:
        return (chargen_hint, _tr(chargen_hint))

    # ── 3. IMG 信号による subscreen 推定（chargen_hint が None の隙間で使用）──
    # 観測根拠: 複数回の再現確認
    #
    # PARCH.CIF: class_select 専用信号（クラス選択方法画面）
    # 旧仕様では 7 サブ状態共有と誤認識していたが実観測で class_select 数秒間のみ。
    if img_upper == "PARCH.CIF":
        return ("class_select", _tr("class_select"))

    # SCROLL02.DFA: 10Q phase の排他信号（30 秒継続、class_select 直後から）
    if img_upper == "SCROLL02.DFA":
        sub = last_subscreen if last_subscreen in (
            "ten_questions", "class_select",
        ) else "ten_questions"
        return (sub, _tr(sub))

    # NOEXIT.IMG: name_input / sex_select / race_select / race_confirm が共有する信号
    if img_upper == "NOEXIT.IMG":
        if last_subscreen in ("name_input", "sex_select", "race_select", "race_confirm"):
            return (last_subscreen, _tr(last_subscreen))
        return ("name_input", _tr("name_input"))

    # TERRAIN.IMG: status_proclamation 以降（race_description / class_advice）の信号
    # race_select ではない（旧仕様の誤り）
    if img_upper == "TERRAIN.IMG":
        if last_subscreen in ("status_proclamation", "race_description", "class_advice"):
            return (last_subscreen, _tr(last_subscreen))
        return ("status_proclamation", _tr("status_proclamation"))

    # ── 4. subscreen 間の隙間: last_subscreen にフォールバック ──
    # top_level_state == "chargen" が保証されているので play module は呼ばれない
    if last_subscreen and last_subscreen in SCREEN_IDS:
        return (last_subscreen, _tr(last_subscreen))

    return None
