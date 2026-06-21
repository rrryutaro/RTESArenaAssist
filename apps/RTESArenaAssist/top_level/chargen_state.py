"""chargen 状態 (キャラクター作成中) の描画所有。

advice_capture_age 追跡 / chargen_state 安定性判定 / 各種 chargen 検出
(10Q intro / GoYeNow fallback / appearance 等) / cinematic 表示更新を
集約する。

window 側状態 (_chargen_*, _advice_capture_age 等) は従来通り window が
保持し、本モジュールは window 参照経由でアクセスする。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import assist_settings as settings
import inf_text_lookup as itl
from arena_bridge import (
    CHARGEN_STATE_OFFSET,
    CHARGEN_Q_SEQ_OFFSET,
    CHARGEN_Q_ARRAY_OFFSET,
    CHARGEN_DONE_OFFSET,
    SCREEN_IMG_OFFSET,
    SCREEN_IMG_MAXLEN,
)
from controllers.chargen_helpers import (
    _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN,
    _CHARGEN_GOYENOW_PREFIX,
    _CHARGEN_GOYENOW_SCAN_START, _CHARGEN_GOYENOW_SCAN_END,
    _is_garbage_npc_buffer,
)
from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("poll_controller")

# キャラクター作成中のメモリ観測対象。
# メモリ調査ワークフローに基づく仮説検証ループ用に、各画面で
# 値変化時に診断ログへ dump して安定性を蓄積する。
# 主用途: 能力値分配以降の状態判定 + 将来の 10Q / GoYeNow 判定改善検討
OFF_DIALOG_FLAG       = 0xB7C4   # ダイアログフラグ (0x01=表示中, 0x00=なし、文脈で別意味)
OFF_NPC_PHASE         = 0xA845   # NPC phase (能力値以降 0xA845/0xA846/0xA847 が外見ダイアログ判定候補)
OFF_NPC_PHASE_LEN     = 3
OFF_AUX_OBS_1         = 0x8F6E   # 補助観測 (能力値中の transient 変化候補)
OFF_AUX_OBS_2         = 0x8F74   # 補助観測 (ボーナスエラー検出候補)
OFF_AUX_OBS_3         = 0x8F7A   # 補助観測 (ボーナスエラー検出候補)
OFF_AUX_OBS_FAEA      = 0xFAEA   # 補助観測 (transient で安定 dismiss シグナルには不向き)
OFF_BONUS_PTS         = 0x129C
OFF_BONUS_WARN_BUF    = 0x929E   # ボーナス警告メッセージバッファ
OFF_RACE_CHARGEN      = 0x214    # chargen race buffer (前回 chargen 残留有、不採用)
OFF_RACE_PLAY         = 0x1A8    # player race (実機観測で chargen 中も最新選択を保持)
OFF_FACE_CLICK        = 0x129A   # face click counter

# 外見選択ダイアログ判定の観測値 (観測 2 回、要安定性検証)
APPEARANCE_DLG_BYTES  = (0x38, 0x19, 0x34)


# chargen 前景 panel_mode 提案の優先度。chargen は classify_chargen_view
# → render_chargen_view が単一権威。背景翻訳 push (priority=0) に勝たせ、normal-play
# 画面駆動 (poll_controller._SCREEN_PANEL_PRIORITY) と同一ティアで確定する。
_CHARGEN_PANEL_PRIORITY = 30


def _set_panel_mode(w, mode: str, *, priority: int = 0) -> None:
    """chargen surface の panel_mode 更新を UiRouter 経由に集約する。"""
    w._ui_router.set_panel_mode(mode, priority=priority)


def _post_chargen_opening_active(w) -> bool:
    """Return True once the post-chargen opening owns chargen display."""
    return (
        bool(getattr(w, "_chargen_opening_displayed", False))
        or bool(getattr(w, "_chargen_opening_text_prev", ""))
    )


def _appearance_detection_allowed(w) -> bool:
    """Guard FACES-based appearance detection from post-opening residues."""
    return (
        _current_top_level(w) == "chargen"
        and not getattr(w, "_chargen_appearance_displayed", False)
        and not _post_chargen_opening_active(w)
    )


def _chargen_text_translation_reason(w) -> str:
    """Return a reason when the current chargen state is text-only."""
    checks = (
        ("method", "_chargen_method_window"),
        ("ten_questions", "_chargen_10q_displayed"),
        ("class_accept", "_chargen_class_accept_displayed"),
        ("class_advice", "_chargen_in_advice"),
        ("goyenow", "_chargen_goyenow_displayed"),
        ("name_input", "_in_chargen_name"),
        ("sex_select", "_chargen_sex_select_displayed"),
    )
    for reason, attr in checks:
        if getattr(w, attr, False):
            return reason
    return ""


def _chargen_target_panel_mode(
        w, *, panel_visible: bool) -> tuple[str | None, str]:
    """Select the chargen tab panel mode for the current sub-state."""
    if getattr(w, "_chargen_opening_displayed", False):
        return ("translate", "opening")

    # クラス手動選択フェーズ
    if getattr(w, "_chargen_class_list_active", False):
        return ("class_list", "class_list")

    # 外見説明ダイアログ中は顔一覧ではなく説明翻訳を表示する。
    # 顔一覧はダイアログ閉幕後の外見選択本画面に限定する。
    if getattr(w, "_chargen_explanation_active", None) == "appearance":
        return ("translate", "appearance_explanation")

    # 外見フェーズ
    if getattr(w, "_chargen_appearance_displayed", False):
        return ("appearance_faces", "appearance_main")

    # complete (種族確定後の宣言)
    if getattr(w, "_chargen_complete_displayed", False):
        return ("translate", "complete")

    # 能力値分配フェーズ (説明ポップアップ / メイン / モーダル)
    if (getattr(w, "_chargen_choose_attrs_displayed", False)
            or getattr(w, "_chargen_distribute_displayed", False)
            or getattr(w, "_chargen_explanation_active", None) == "distribute"
            or getattr(w, "_chargen_attrs_modal_kind", None) in (
                "bonus_required", "stat_save_confirm")):
        # 説明ポップアップ (能力値配分説明) / 確認モーダル (bonus_required /
        # stat_save_confirm) 表示中は、画面どおりの説明翻訳を最優先で出す
        # (翻訳パネル可視でも translate)。Arena ではこれらは能力値画面に
        # かぶさるモーダルで、ユーザーは説明文を読むため。閉幕後 (explanation/
        # modal クリア) に能力値パネル (choose_attributes) へ戻す。
        # 観測: panel 可視時に choose_attributes を無条件優先していたため、
        # DistributePoints 発火 (検出は正常) 直後に説明翻訳がパネルへ上書きされ
        # 表示されなかった。renderer 優先順に整合させる。
        if (getattr(w, "_chargen_explanation_active", None) == "distribute"
                or getattr(w, "_chargen_attrs_modal_kind", None) in (
                    "bonus_required", "stat_save_confirm")):
            return ("translate", "attrs_popup_or_modal")
        if panel_visible:
            return ("choose_attributes", "attrs_phase(panel_shown)")
        return ("choose_attributes", "attrs_main(panel_hidden)")

    # 種族選択フェーズ (説明ポップアップ / マップ / 確認ダイアログ)
    if getattr(w, "_chargen_race_select_displayed", False):
        if panel_visible:
            return ("race_list", "race_select(panel_shown)")
        # 観測により判明: 種族選択フェーズでは
        # ダイアログフラグ +0xB7C4 の意味が他フェーズと逆転する。
        # - 他フェーズ: 0x01=ダイアログ表示中 / 0x00=なし
        # - 種族選択: 0x00=ポップアップ・確認ダイアログ表示中 /
        #             0x00 以外=マップ画面 (popup 閉幕後)
        # (観測値 +0xA845=0x72/+0xA847=0x02 は閉幕瞬間の transient 値であり
        #  steady state では検出できなかったため、ダイアログフラグ方式で極性を反転)
        try:
            dlg_r = w._analyzer.read_bytes(
                w._anchor + OFF_DIALOG_FLAG, 1)[0]
        except (OSError, AttributeError):
            dlg_r = 0xFF
        if dlg_r != 0x00:
            return ("race_list",
                    "race_select_map(panel_hidden, dlg=0x%02X)" % dlg_r)
        return ("translate", "race_select_popup(panel_hidden, dlg=0x00)")

    # 種族説明 "Know ye this also..."
    if getattr(w, "_chargen_race_desc_displayed", False):
        return ("translate", "race_desc")

    reason = _chargen_text_translation_reason(w)
    if reason:
        return ("translate", reason)

    return (None, "")


# chargen サブ状態 (1軸化の軸)。優先順は _chargen_target_panel_mode と同一。
# panel 可視/ダイアログ極性等の描画都合の分岐を含まない coarse な状態名。
CHARGEN_SUBSTATES = (
    "opening", "class_list", "appearance", "complete", "attrs",
    "race_select", "race_desc",
    # _chargen_text_translation_reason 由来 (テキスト主体フェーズ):
    "method", "ten_questions", "class_accept", "class_advice",
    "goyenow", "name_input", "sex_select",
)


def chargen_substate(w) -> str:
    """現在の chargen サブ状態を 1 つ返す純粋分類器 (1軸化の軸)。

    副作用なし。既存ラッチフラグから「いま chargen のどのサブ状態か」を
    優先順位で 1 つに確定する。``_chargen_target_panel_mode`` と同じ優先順で
    coarse な状態名 (CHARGEN_SUBSTATES のいずれか) を返す。該当なしは ""。

    将来の検出側 1軸化 (現サブ状態 1 本＋離脱判定で遷移) の dispatch 軸となる
    seam。本関数自体は判定 (classify) のみで描画・状態更新を行わない。
    """
    if getattr(w, "_chargen_opening_displayed", False):
        return "opening"
    if getattr(w, "_chargen_class_list_active", False):
        return "class_list"
    if getattr(w, "_chargen_explanation_active", None) == "appearance":
        return "appearance"
    if getattr(w, "_chargen_appearance_displayed", False):
        return "appearance"
    if getattr(w, "_chargen_complete_displayed", False):
        return "complete"
    if (getattr(w, "_chargen_choose_attrs_displayed", False)
            or getattr(w, "_chargen_distribute_displayed", False)
            or getattr(w, "_chargen_explanation_active", None) == "distribute"
            or getattr(w, "_chargen_attrs_modal_kind", None) in (
                "bonus_required", "stat_save_confirm")):
        return "attrs"
    if getattr(w, "_chargen_race_select_displayed", False):
        return "race_select"
    if getattr(w, "_chargen_race_desc_displayed", False):
        return "race_desc"
    return _chargen_text_translation_reason(w)


def _fire_distribute_points(w, chargen_state: int, *, source: str) -> None:
    """能力値配分説明画面 (DistributePoints) 検出時の共通処理。

    検出経路:
    - chargen_state+0x1C ルール (主)
    - 汎用バッファが GoYeNow スナップショットから変化した安全措置

    検出時に以下を実施:
    - _CHARGEN_DISTRIBUTE_POINTS_ の翻訳を翻訳タブ・翻訳パネルに表示
    - ステータスタブの表示 latch を arm (能力値画面突入の起点)
    - 能力値分配 phase 進入として attrs_phase_seen を立てる
      (modal 判定 / Appearance 判定の guard 用)
    - 説明ダイアログ表示中フラグ explanation_active="distribute" を立て、
      汎用バッファのスナップショットを取得 (翻訳タブにも説明翻訳
      を表示するため。renderer が translate モードを選ぶ)
    - 説明閉幕の判定は別 poll の処理で汎用バッファ変化時に行う。
    - panel_mode 切替は chargen renderer に委譲 (直接 _activate_choose_attributes_panel
      は呼ばない)。
    """
    if w._chargen_distribute_displayed:
        return
    entry = itl.lookup("_CHARGEN_DISTRIBUTE_POINTS_", 0)
    if entry is not None:
        w._update_translate_tab(entry)
    w._chargen_distribute_displayed = True
    # 能力値分配 phase 進入として attrs_phase_seen 確立
    if not w._chargen_attrs_phase_seen:
        w._chargen_attrs_state_anchor = chargen_state
        w._chargen_attrs_phase_seen = True
        _log.info(
            "chargen_latch: attrs_anchor=None->0x%02X source=DistributePoints (%s)",
            chargen_state, source)
    # 能力値分配画面に入った起点: ステータス表示 latch を arm
    if not w._chargen_status_display_armed:
        w._chargen_status_display_armed = True
        _log.info(
            "chargen_latch: status_armed=0->1 source=DistributePoints (%s)",
            source)
    # 説明ダイアログ表示開始。閉幕検出はダイアログフラグ +0xB7C4 の
    # 1→0 遷移で判定するため、開幕観測 latch をリセットする。
    w._chargen_explanation_active = "distribute"
    w._chargen_explanation_distribute_dlg_seen_open = False
    w._chargen_explanation_distribute_npc_snapshot = None
    _log.info(
        "chargen_latch: explanation_active=None->distribute "
        "(dlg_seen_open reset) source=DistributePoints")
    _log.info(
        "chargen: DistributePoints fired (source=%s, state=0x%02X, "
        "goyenow_state=%s)",
        source, chargen_state,
        ("0x%02X" % w._chargen_goyenow_state)
        if w._chargen_goyenow_state is not None else "None",
    )


def handle_npc_dialog(w, *, npc_dialog: str, entry_handled: bool,
                      is_corpse_loot: bool) -> None:
    """chargen 中の NPC バッファ翻訳を ChargenController に委譲する。

    chargen 中 (top_level_state=="chargen") の +0x1044 NPC ダイアログ
    バッファは、class advice / method 選択画面 / 10Q intro 等の chargen
    専用テキストを含む。これらを ChargenController の
    _handle_chargen_npc_dialog が翻訳・表示する。

    - entry_handled / is_corpse_loot は他経路で既に翻訳済の状態を示すため
      その場合は skip (= 上書き防止)
    - top_level が chargen でなければ skip (= normal-play で 1 文字断片を
      流す誤動作を防止)

    IMG-driven 画面の保護:
      プロローグ (INTRO*.IMG / _show_newgame_slide) や post-chargen
      cinematic (_chargen_opening_displayed=True / _fire_post_chargen_opening)
      は NPC バッファではなく IMG・memory 直読みで翻訳テキストを供給する。
      これらの画面では NPC バッファに残留・無関係テキストが残っており、
      _handle_chargen_npc_dialog のフォールバック (辞書未マッチ時の
      `_push_translation(npc_dialog, "")`) が IMG-driven 翻訳を毎 poll で
      上書きしてしまう。当該画面では NPC handler を skip する。
    """
    if entry_handled or is_corpse_loot:
        return
    if _current_top_level(w) != "chargen":
        return
    # プロローグ (newgame_intro): INTRO01-09.IMG の slideshow 表示中。
    # img_screen_controller._show_newgame_slide が IMG 遷移ごとに翻訳を
    # push する。NPC バッファは prologue 中に無関係/残留内容を持つため
    # 当画面では NPC handler を skip する。
    img = (getattr(w, "_img_name_prev", "") or "").upper()
    if img.startswith("INTRO") and img.endswith(".IMG"):
        return
    # post-chargen 旅立ち cinematic: ChargenController._fire_post_chargen_opening
    # が memory 直読みで翻訳を push する。NPC handler が併走すると上書きする。
    if getattr(w, "_chargen_opening_displayed", False):
        return
    w._chargen._handle_chargen_npc_dialog(npc_dialog)


def _poll_track_state(w) -> int:
    """chargen_state 読取 + 安定性追跡 (streak) フェーズ。

    Returns:
        chargen_state: 現在の chargen_state バイト値 (後段検出が使用)。
    """
    # chargen_state: 10Q イントロ検出のみ補助的に使用（サイクル値のため限定）
    try:
        chargen_state = w._analyzer.read_bytes(
            w._anchor + CHARGEN_STATE_OFFSET, 1)[0]
    except OSError:
        chargen_state = 0
    # 安定性追跡（確定仕様）: chargen_state は画面遷移時に cycle、画面安定時は stable。
    # 2 ポーリング連続同値（streak == 2）= 「安定確定」とみなす。
    if chargen_state == w._chargen_state_prev:
        w._chargen_state_streak += 1
    else:
        if w._chargen_state_streak >= 2:
            _log.info("chargen_state changed from stable 0x%02X to 0x%02X",
                      w._chargen_state_prev, chargen_state)
        w._chargen_state_streak = 1
        w._chargen_state_prev = chargen_state

    # 画面安定ログ（streak == 2 の瞬間のみ 1 度出力）
    if w._chargen_state_streak == 2:
        _log.info(
            "chargen_state stable at 0x%02X "
            "(in_advice=%s, advice=%s, method_window=%s, 10q=%s, goyenow=%s, "
            "distribute=%s, choose_attrs=%s, appearance=%s, done=%s)",
            chargen_state, w._chargen_in_advice,
            (f"0x{w._chargen_advice_state:02X}"
             if w._chargen_advice_state is not None else "None"),
            w._chargen_method_window,
            w._chargen_10q_displayed, w._chargen_goyenow_displayed,
            w._chargen_distribute_displayed,
            w._chargen_choose_attrs_displayed,
            w._chargen_appearance_displayed,
            w._chargen_done_prev,
        )
    return chargen_state


def _read_a845(w) -> int | None:
    """NPC会話主判定信号 +0xA845 を読む (画面遷移検出用)。"""
    try:
        return w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        return None


# 以下 4 つは離脱検出をサブ状態別のハンドラへ分割したもの (検出側 1軸化)。
# dispatch (_poll_detect) が substate ごとに 1 つだけ呼ぶため、
# method_window / in_advice / attrs_phase_seen 等の cross-substate selector
# ガードは持たない (一意性は制御フロー構造=dispatch が保証)。streak>=2 の
# 安定ゲートと a845 変化等の離脱シグナルのみを残す。


def _detect_method_exit(w, chargen_state: int, a845: int | None) -> None:
    """method（クラス選択方法）サブ状態の離脱検出: a845 変化で → 10Q intro。"""
    if w._chargen_state_streak < 2:
        return
    # 基準 +0xA845 の捕捉 (未捕捉のとき)。10Q intro 判定の基準値。
    if getattr(w, "_chargen_method_a845", None) is None and a845 is not None:
        w._chargen_method_a845 = a845
        _log.info("chargen: method a845 baseline = 0x%02X", a845)
    # 10Q イントロ検出: 捕捉時の +0xA845 から変化したら発火する。
    if (w._chargen_method_state is not None
            and not w._chargen_10q_displayed
            and a845 is not None
            and getattr(w, "_chargen_method_a845", None) is not None
            and a845 != w._chargen_method_a845):
        entry = itl.lookup("_CHARGEN_10Q_", 0)
        if entry is not None:
            w._update_translate_tab(entry)
        w._chargen_10q_displayed = True
        w._chargen_method_window = False
        _log.info(
            "chargen: 10Q intro fired (a845 0x%02X->0x%02X)",
            w._chargen_method_a845, a845,
        )
    # クラス選択方法画面の安定状態 + 基準 +0xA845 を捕捉 (NPC 検出後の最初の安定値)。
    elif w._chargen_method_state is None:
        w._chargen_method_state = chargen_state
        w._chargen_method_a845 = a845
        _log.info(
            "chargen: method captured (state=0x%02X, a845=%s)",
            chargen_state,
            "None" if a845 is None else f"0x{a845:02X}",
        )


def _detect_advice_exit(w, chargen_state: int, a845: int | None) -> None:
    """class_advice（クラスアドバイス）サブ状態の離脱検出: a845 変化で → GoYeNow。"""
    if w._chargen_state_streak < 2:
        return
    # advice 基準 +0xA845 の捕捉 (未捕捉のとき)。
    if getattr(w, "_chargen_advice_a845", None) is None and a845 is not None:
        w._chargen_advice_a845 = a845
        _log.info("chargen: advice a845 baseline = 0x%02X", a845)
    # advice 安定状態 + 基準捕捉。捕捉済みなら a845 変化で GoYeNow 発火。
    if w._chargen_advice_state is None:
        w._chargen_advice_state = chargen_state
        w._chargen_advice_a845 = a845
        w._advice_capture_age = 0
        _log.info(
            "chargen: advice captured (state=0x%02X, a845=%s)",
            chargen_state,
            "None" if a845 is None else f"0x{a845:02X}",
        )
    elif (not w._chargen_goyenow_displayed
            and a845 is not None
            and getattr(w, "_chargen_advice_a845", None) is not None
            and a845 != w._chargen_advice_a845):
        entry = itl.lookup("_CHARGEN_GOYENOW_", 0)
        if entry is not None:
            w._update_translate_tab(entry)
        w._chargen_goyenow_displayed = True
        w._chargen_goyenow_state = chargen_state
        w._chargen_in_advice = False
        _log.info(
            "chargen: GoYeNow fired (a845 0x%02X->0x%02X)",
            w._chargen_advice_a845, a845,
        )


def _detect_goyenow_exit(w, chargen_state: int) -> None:
    """goyenow サブ状態の離脱検出: goyenow_state + 0x1C で → DistributePoints。

    GoYeNow が scan_string fallback で検出された場合、実際の chargen_state は
    advice_state + 0x1C とはずれるため、GoYeNow 実測値 (goyenow_state) を基準にする。
    """
    if w._chargen_state_streak < 2:
        return
    if (w._chargen_goyenow_state is not None
            and not w._chargen_distribute_displayed):
        expected_distribute = (w._chargen_goyenow_state + 0x1C) & 0xFF
        if chargen_state == expected_distribute:
            _fire_distribute_points(w, chargen_state,
                                    source="chargen_state+0x1C")


def _detect_attrs_appearance_candidate(w, chargen_state: int) -> None:
    """attrs サブ状態: Appearance candidate 診断ログ (state-change のみ、発火しない)。

    state-change ベースの自動 Appearance 確定は撤回済。
    `bonus_pts == 0` は「ボーナスを使い切った」だけで、まだ能力値画面上に
    あり Save/Reroll 確認も未経由のため確定条件にしてはならない。Appearance
    の確定は外見画面固有シグナル (FACES*.CIF IMG / dlg_flag 一致) に限定し、
    本関数は診断ログのみを出す。
    """
    if w._chargen_state_streak < 2:
        return
    if (not w._chargen_appearance_displayed
            and w._chargen_attrs_state_anchor is not None
            and chargen_state != w._chargen_attrs_state_anchor):
        try:
            _bonus_raw = w._analyzer.read_bytes(w._anchor + 0x129C, 1)
            _bonus_pts = _bonus_raw[0] if _bonus_raw else 0
        except (OSError, AttributeError):
            _bonus_pts = 0
        try:
            _img_raw = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_now = _img_raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_now = ""
        _anchor_val = w._chargen_attrs_state_anchor
        _log.info(
            "chargen_appearance_candidate: state=0x%02X anchor=0x%02X "
            "bonus_pts=%d img=%s accepted=0 reason=state_change_only_not_sufficient",
            chargen_state, _anchor_val, _bonus_pts, _img_now,
        )


def _poll_detect_appearance(w) -> None:
    """Appearance 確定経路フェーズ (FACES IMG / dlg_flag + 観測 3 バイト一致)。"""
    # Appearance 確定経路:
    # 主判定: 能力値分配中 (attrs_phase_seen=True) かつダイアログフラグ=0x01
    #         かつ +0xA845/+0xA846/+0xA847 が観測値 (0x38/0x19/0x34) と一致
    # 補助判定 1 (既存): SCREEN_IMG が FACES*.CIF (外見画面進入後の IMG 確定)
    # 補助判定 2 (経路 A 既存): 汎用バッファに "Thou wilt now choose thy
    #         appearance." (`_handle_chargen_npc_dialog` で別途発火)
    if _appearance_detection_allowed(w):
        try:
            _img_raw2 = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_check = _img_raw2.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_check = ""
        # 補助判定 1: FACES*.CIF IMG
        if _img_check.startswith("FACES") and _img_check.endswith(".CIF"):
            entry = itl.lookup("_CHARGEN_APPEARANCE_", 0)
            if entry is not None:
                w._update_translate_tab(entry)
            w._chargen_appearance_displayed = True
            _log.info(
                "chargen: Appearance fired (img=%s, FACES detection)",
                _img_check)
        # 主判定: 能力値分配 + ダイアログフラグ=0x01 + 観測 3 バイト一致
        elif w._chargen_attrs_phase_seen:
            try:
                _dlg_flag = w._analyzer.read_bytes(
                    w._anchor + OFF_DIALOG_FLAG, 1)[0]
            except (OSError, AttributeError):
                _dlg_flag = 0xFF
            if _dlg_flag == 0x01:
                try:
                    _ph_bytes = w._analyzer.read_bytes(
                        w._anchor + OFF_NPC_PHASE, OFF_NPC_PHASE_LEN)
                except (OSError, AttributeError):
                    _ph_bytes = b""
                if (len(_ph_bytes) >= 3
                        and _ph_bytes[0] == APPEARANCE_DLG_BYTES[0]
                        and _ph_bytes[1] == APPEARANCE_DLG_BYTES[1]
                        and _ph_bytes[2] == APPEARANCE_DLG_BYTES[2]):
                    entry = itl.lookup("_CHARGEN_APPEARANCE_", 0)
                    if entry is not None:
                        w._update_translate_tab(entry)
                    w._chargen_appearance_displayed = True
                    # 外見選択説明ダイアログ表示中 → 翻訳タブにも
                    # 翻訳を表示するため explanation_active を立てる。
                    # 閉幕はダイアログフラグが 0x00 になった瞬間に検出。
                    w._chargen_explanation_active = "appearance"
                    _log.info(
                        "chargen_latch: explanation_active=None->appearance "
                        "source=Appearance_dlg_bytes_match")
                    _log.info(
                        "chargen: Appearance fired (dlg_flag=0x01, "
                        "+0xA845/6/7=0x%02X/0x%02X/0x%02X)",
                        _ph_bytes[0], _ph_bytes[1], _ph_bytes[2])

        # クラス一覧画面 (Choose thy class) の検出は NPC バッファ側で行う
        # （_handle_chargen_npc_dialog → _activate_class_list_for_class）。
        # 当画面では NPC バッファにハイライト中のクラス名が書き込まれるため、
        # chargen_state ではなく NPC バッファの内容そのものを決定的シグナルとする。


def _poll_detect_goyenow_fallback(w, chargen_state: int) -> None:
    """GoYeNow フォールバック検出フェーズ (hint addr 直読み / scan_string)。"""
    # GoYeNow フォールバック検出。
    # 仕組み:
    #   hint addr 0x106D0930 直読み + 縮小 scan の二段構え。
    #   advice_state 確定と同 poll で hint addr が誤発火し goyenow_state に
    #     advice_state 値が誤保存される事例があるため、chargen_state ベースでなく
    #     時間ベース（advice_capture_age）ガードを用いる。
    #     +0x1C ルールが破綻し chargen_state が advice 画面のまま固定する場合
    #     でも fallback を block しないようにするため。advice_state capture 後
    #     6 poll (3 秒) 経過後に fallback を許可する。これで同 poll 誤発火と
    #     +0x1C 破綻の両方をカバーする。
    # 検出側 1軸化: 旧 cross-substate 相互排他連鎖 (not goyenow /
    # distribute / choose_attrs / appearance / opening) は撤去。本関数は
    # dispatch から substate=='class_advice' のときのみ呼ばれ、それらの否定は
    # dispatch 構造が保証する。残すのは class_advice 内の進行ゲート
    # (advice_state 捕捉済 / age>=6 / done==0 / budget>0) のみ。
    if (w._chargen_in_advice
            and w._chargen_advice_state is not None
            and w._advice_capture_age >= 6
            and not w._chargen_goyenow_displayed
            and w._chargen_done_prev == 0
            and w._goyenow_scan_budget > 0):
        w._goyenow_scan_budget -= 1
        fired = False

        # (1) hint addr 直読み（高速パス、観測 2 run 仮説）
        # 上の状態ガードで「ユーザーが advice 画面から離脱済み」を担保。
        try:
            head = w._analyzer.read_bytes(
                _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN)
        except OSError:
            head = b""
        if head.startswith(_CHARGEN_GOYENOW_PREFIX):
            entry = itl.lookup("_CHARGEN_GOYENOW_", 0)
            if entry is not None:
                w._update_translate_tab(entry)
            w._chargen_goyenow_displayed = True
            w._chargen_goyenow_state = chargen_state
            w._chargen_in_advice = False
            fired = True
            _log.info("chargen: GoYeNow fired (hint addr direct, "
                      "addr=0x%X, state=0x%02X, budget=%d)",
                      _CHARGEN_GOYENOW_HINT_ADDR, chargen_state,
                      w._goyenow_scan_budget)

        # (2) hint addr 失敗時は縮小範囲で scan_string
        if not fired:
            try:
                results = w._analyzer.scan_string(
                    "Go ye now in peace",
                    _CHARGEN_GOYENOW_SCAN_START,
                    _CHARGEN_GOYENOW_SCAN_END,
                )
            except (OSError, RuntimeError, AttributeError) as exc:
                results = []
                _log.debug("chargen: GoYeNow scan_string error: %s", exc)
            if results:
                entry = itl.lookup("_CHARGEN_GOYENOW_", 0)
                if entry is not None:
                    w._update_translate_tab(entry)
                w._chargen_goyenow_displayed = True
                w._chargen_goyenow_state = chargen_state
                w._chargen_in_advice = False
                _log.info("chargen: GoYeNow fired (scan_string fallback, "
                          "addr=0x%X, state=0x%02X, budget=%d)",
                          results[0].address, chargen_state,
                          w._goyenow_scan_budget)


def _poll_detect_distribute_safety(w, chargen_state: int) -> None:
    """DistributePoints 安全措置フェーズ (GoYeNow snapshot 変化で進入判定)。"""
    # 安全措置: 能力値配分説明画面の主判定 (+0x1C ルール)
    # の取り逃しで発火しなかった場合の保険。
    # GoYeNow 文 ("Go ye now in peace...") は汎用バッファに書き込まれ
    # ない (0x929E 側の別バッファに書かれる) ため、汎用バッファに常に
    # 前画面 (クラスアドバイス画面) の残留テキスト ("Thy body and mind...")
    # が居る。`startswith("Go ye now in peace")` チェックは常に False
    # となり即時に誤発火するため、スナップショット差分方式を用いる。
    #
    # 正しい仕組み: GoYeNow 検出時に汎用バッファの内容をスナップショットとして
    # 保存し、後の poll で汎用バッファが別の値に変化した瞬間を捕捉する
    # (実機観測: GoYeNow 時 "Thy body and mind..." → DistributePoints 時 "+0")。
    if (w._chargen_goyenow_displayed
            and not w._chargen_distribute_displayed):
        try:
            from arena_bridge import (
                NPC_DIALOG_OFFSET as _NPC_OFF_S,
                NPC_DIALOG_MAXLEN as _NPC_LEN_S,
            )
            _npc_now_raw = w._analyzer.read_bytes(
                w._anchor + _NPC_OFF_S, _NPC_LEN_S)
            _npc_now_bytes = _npc_now_raw.split(b"\x00", 1)[0]
        except (OSError, AttributeError, ImportError):
            _npc_now_bytes = None
        # GoYeNow 検出時のスナップショットを初回 poll で確立
        if (_npc_now_bytes is not None
                and w._chargen_goyenow_npc_snapshot is None):
            w._chargen_goyenow_npc_snapshot = _npc_now_bytes
            _log.info(
                "chargen_latch: goyenow_npc_snapshot=%r source=GoYeNow_initial",
                _npc_now_bytes[:40])
        # スナップショットから変化したら DistributePoints 進入と判定
        if (_npc_now_bytes is not None
                and w._chargen_goyenow_npc_snapshot is not None
                and _npc_now_bytes != w._chargen_goyenow_npc_snapshot
                and _npc_now_bytes):
            _fire_distribute_points(
                w, chargen_state,
                source="npc_buf_changed_from_goyenow_snapshot")


def _poll_detect_distribute_by_dialog(w, chargen_state: int) -> None:
    """DistributePoints 検出 (説明ダイアログ開幕ゲート版)。

    goyenow サブ状態中に、ダイアログフラグ +0xB7C4 が 0x00 (ダイアログなし) から
    非0 (表示中) へ変化した瞬間を、能力値配分の説明ダイアログ開幕＝
    DistributePoints 進入とみなして発火する。

    観測 (仮説・観測 1 回): GoYeNow → 能力値配分ステータス画面の切替時、主判定/
    フェーズバイト +0xA845 は凍結し得る (クエスト同行人残留に起因する
    Arena 側挙動)。このため a845 変化 (_detect_advice_exit) や chargen_state(+0x4B8F)+0x1C
    (_detect_goyenow_exit) では離脱を検出できない場合がある。一方、説明ダイアログ
    の開幕はダイアログフラグ +0xB7C4 の 0x00→非0 変化で凍結に影響されず確定でき
    (GoYeNow 時 0x00 → 能力値配分説明 時 0x04 を実機観測で確認)、+0xA83B が
    0x00→0x01 (応答中へ遷移) も同時に観測されている。
    既存の +0x1C / NPC バッファ変化検出は保険として併存させる (撤去しない)。
    """
    if not (w._chargen_goyenow_displayed
            and not w._chargen_distribute_displayed):
        return
    try:
        _b7c4 = w._analyzer.read_bytes(
            w._anchor + OFF_DIALOG_FLAG, 1)[0]
    except (OSError, AttributeError):
        return
    _prev = w._chargen_goyenow_b7c4_prev
    w._chargen_goyenow_b7c4_prev = _b7c4
    # 0x00 (ダイアログなし) → 非0 (表示中) のエッジ = 説明ダイアログ開幕。
    # 初回 poll は _prev=None のため発火せず baseline 確立のみ。
    if _prev == 0x00 and _b7c4 != 0x00:
        _fire_distribute_points(
            w, chargen_state,
            source="dialog_gate_b7c4(0x00->0x%02X)" % _b7c4)


def _poll_detect_questions(w) -> int:
    """chargen 個別設問 (10Q intro / Q1-Q10) 検出フェーズ。

    Returns:
        chargen_q_seq: 設問シーケンス番号 (0-10、後段 probe ログでも使用)。
    """
    # chargen 個別設問検出（+16583 がシーケンス番号 1-10 に変化したとき）
    try:
        chargen_q_seq = w._analyzer.read_bytes(
            w._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
    except OSError:
        chargen_q_seq = 0
    # 検出側 1軸化: 旧 q_phase_active_base (class_list/advice/goyenow/
    # distribute/choose_attrs/appearance を否定する cross-substate 相互排他
    # ガード) は撤去。本関数は dispatch (_poll_detect) から substate ∈
    # {method, ten_questions} のときのみ呼ばれ、それ以外のサブ状態の否定は
    # dispatch 構造が保証するため、実行時ガードは不要。

    # 10Q intro 検出 fallback (priority 12):
    # 「10Q intro stable または Q1〜Q10 NPC 検出時」を担保する。
    # 主経路 (chargen_state == method_state + 0x1C) は run によっては
    # chargen_state が変化せず成立しないため、SCROLL02.DFA / SCROLL01.DFA
    # (= chargen scroll 系 IMG) + q_seq==0 + method_window True を組合せた
    # IMG ベースの fallback を併設。method 画面のままでは fire させない
    # (= 両者の IMG 差で識別)。
    if not w._chargen_10q_displayed and w._chargen_method_window:
        try:
            _img_raw = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_now = _img_raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_now = ""
        # 10Q intro / scroll 画面: PARCH.CIF (= 自動生成選択直後の
        # parchment 表示) または SCROLL01/02.DFA (= scroll animation)
        # 観測根拠: IMG=PARCH.CIF が観測されたが従来 fallback
        # は SCROLL02.DFA のみ対象だったため fire しなかった。
        _10q_imgs = ("SCROLL02.DFA", "SCROLL01.DFA")
        if (_img_now in _10q_imgs
                and chargen_q_seq == 0):
            entry = itl.lookup("_CHARGEN_10Q_", 0)
            if entry is not None:
                w._update_translate_tab(entry)
            w._chargen_10q_displayed = True
            w._chargen_method_window = False
            _log.info(
                "chargen: 10Q intro fired (fallback IMG=%s q_seq=0)",
                _img_now)
    if chargen_q_seq != w._chargen_q_seq_prev:
        w._chargen_q_seq_prev = chargen_q_seq
        # Q1-Q10 抑止条件:
        # 「現在の接続で観測した画面進行フラグ」のみで判定する。
        # `_chargen_class_ja is None` を条件に入れると、
        # 接続時の ChooseAttributes auto-activate で前回 player struct から
        # `_chargen_class_ja` が復元され、新規 chargen の Q1 表示時にも残留して
        # `q_phase_active=False` になり Q1 翻訳が抑止される不具合がある。
        # `_chargen_class_ja` は UI 表示・復帰補助の state であり、フェーズ判定の
        # 決定的条件には使えないため除外。
        # 注意: _chargen_done_prev == 0 はガード条件に入れない。chargen_done の
        # 意味は観測上「chargen 中=1 / cinematic=0」と判明しており逆方向のため。
        if 1 <= chargen_q_seq <= 10:
            try:
                q_num = w._analyzer.read_bytes(
                    w._anchor + CHARGEN_Q_ARRAY_OFFSET + (chargen_q_seq - 1), 1)[0]
            except OSError:
                q_num = 0
            if q_num >= 1:
                entry = itl.lookup(f"_CHARGEN_Q_{q_num}_", 0)
                if entry is not None:
                    w._update_translate_tab(entry)
                _log.info("chargen: Q fired (seq=%d, q_num=%d)", chargen_q_seq, q_num)
    return chargen_q_seq


def _poll_evaluate_modal(w) -> str | None:
    """能力値配分 modal 再評価 + 説明ダイアログ閉幕検出フェーズ。

    Returns:
        new_modal_kind: "bonus_required" / "stat_save_confirm" / None。
    """
    # 能力値配分中の modal を毎 poll メモリから再評価 (sticky latch 防止)。
    # 検出条件はダイアログフラグ (`+0xB7C4`) ベース。
    # - bonus_required: ダイアログフラグ=0x01 かつ 0x929E に
    #   "You must distribute all your bonus points."
    # - stat_save_confirm: ダイアログフラグ=0x01 かつ 汎用バッファに
    #   "Which dost thou choose?"
    # - ダイアログフラグ=0x00 (= ダイアログ表示なし) なら modal なし
    # `npc_phase != 0` 条件は採らない (実機観測 1 例のみで安定性不明)。
    # 外見画面進入後 (appearance_displayed=True) はダイアログフラグの瞬間的な
    # 0x01 変化を無視するため modal なし固定。
    new_modal_kind: str | None = None
    if (w._chargen_attrs_phase_seen
            and not w._chargen_appearance_displayed):
        try:
            _dlg_flag_eval = w._analyzer.read_bytes(
                w._anchor + OFF_DIALOG_FLAG, 1)[0]
        except (OSError, AttributeError):
            _dlg_flag_eval = 0xFF
        if _dlg_flag_eval == 0x01:
            # ダイアログ表示中 → bonus_required / stat_save_confirm を判別
            try:
                _b131_raw = w._analyzer.read_bytes(
                    w._anchor + OFF_BONUS_WARN_BUF, 64)
                _b131_str = _b131_raw.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").strip()
            except (OSError, AttributeError):
                _b131_str = ""
            if _b131_str == "You must distribute all your bonus points.":
                new_modal_kind = "bonus_required"
            else:
                try:
                    from arena_bridge import NPC_DIALOG_OFFSET as _NPC_OFF
                    _npc_raw = w._analyzer.read_bytes(
                        w._anchor + _NPC_OFF, 64)
                    _npc_now = _npc_raw.split(b"\x00", 1)[0].decode(
                        "ascii", errors="replace").strip()
                except (OSError, AttributeError, ImportError):
                    _npc_now = ""
                if _npc_now == "Which dost thou choose?":
                    new_modal_kind = "stat_save_confirm"
    # 説明ダイアログ閉幕の検出 (毎 poll メモリ再評価):
    # - distribute: 観測 (3 回確認) で +0xFAEA == 0x94 で閉幕。
    # - appearance: ダイアログフラグが 0x00 になったら閉幕
    if w._chargen_explanation_active == "distribute":
        try:
            _faea_d = w._analyzer.read_bytes(
                w._anchor + OFF_AUX_OBS_FAEA, 1)[0]
        except (OSError, AttributeError):
            _faea_d = 0
        if _faea_d == 0x94:
            _log.info(
                "chargen_latch: explanation_active=distribute->None "
                "(+0xFAEA=0x94) source=dismissed")
            w._chargen_explanation_active = None
            w._chargen_explanation_distribute_npc_snapshot = None
            w._chargen_explanation_distribute_dlg_seen_open = False
    elif w._chargen_explanation_active == "appearance":
        try:
            _dlg_cur = w._analyzer.read_bytes(
                w._anchor + OFF_DIALOG_FLAG, 1)[0]
        except (OSError, AttributeError):
            _dlg_cur = 0xFF
        if _dlg_cur == 0x00:
            _log.info(
                "chargen_latch: explanation_active=appearance->None "
                "(dlg_flag=0x00) source=dismissed")
            w._chargen_explanation_active = None

    _old_modal_kind = w._chargen_attrs_modal_kind
    if new_modal_kind != _old_modal_kind:
        _log.info(
            "chargen_latch: modal_kind=%s->%s source=re_evaluate",
            _old_modal_kind or "None", new_modal_kind or "None")
        w._chargen_attrs_modal_kind = new_modal_kind
        w._chargen_attrs_modal_active = (new_modal_kind is not None)
        # stat_save_confirm 進入時は _CHARGEN_CHOOSE_ATTRIBUTES_ の翻訳本文
        # (Save stats / Reroll stats 含む) を翻訳タブに push する。
        # renderer はこの後 translate モードへ切替える。
        if new_modal_kind == "stat_save_confirm":
            entry = itl.lookup("_CHARGEN_CHOOSE_ATTRIBUTES_", 0)
            if entry is not None:
                try:
                    w._update_translate_tab(entry)
                except (AttributeError, RuntimeError):
                    pass
    return new_modal_kind


def _poll_diagnostics(w, chargen_state: int,
                      new_modal_kind: str | None) -> None:
    """chargen_diagnostics 診断ログフェーズ (値変化時に 1 行 dump)。"""
    # 診断ログ (chargen_diagnostics): キャラクター作成中の全画面で
    # 値変化時に 1 行 dump。メモリ調査ワークフローの仮説検証
    # ループで使用。10Q / GoYeNow / 能力値分配 / 外見選択 / 旅立ち 全画面
    # で同じ項目を出力し、画面ごとの安定値を比較分析できるようにする。
    if _current_top_level(w) == "chargen":
        try:
            _img_lr = ""
            _b131_lr = ""
            _bonus_lr = -1
            _npc_lr = ""
            _cd_lr = -1
            _dlg_lr = 0xFF
            _ph_b0 = 0
            _ph_b1 = 0
            _ph_b2 = 0
            _aux1_lr = 0
            _aux2_lr = 0
            _aux3_lr = 0
            _aux_faea = 0
            _race_cg = 0
            _race_pl = 0
            _face_cn = 0
            try:
                _r = w._analyzer.read_bytes(
                    w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
                _img_lr = _r.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").upper()
            except OSError:
                pass
            try:
                _r = w._analyzer.read_bytes(
                    w._anchor + OFF_BONUS_WARN_BUF, 64)
                _b131_lr = _r.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").strip()[:40]
            except OSError:
                pass
            try:
                _bonus_lr = w._analyzer.read_bytes(
                    w._anchor + OFF_BONUS_PTS, 1)[0]
            except OSError:
                pass
            try:
                from arena_bridge import NPC_DIALOG_OFFSET as _NPC_OFF2
                _r = w._analyzer.read_bytes(w._anchor + _NPC_OFF2, 48)
                _npc_lr = _r.split(b"\x00", 1)[0].decode(
                    "ascii", errors="replace").strip()[:40]
            except (OSError, ImportError):
                pass
            try:
                _cd_lr = w._analyzer.read_bytes(
                    w._anchor + CHARGEN_DONE_OFFSET, 1)[0]
            except OSError:
                pass
            try:
                _dlg_lr = w._analyzer.read_bytes(
                    w._anchor + OFF_DIALOG_FLAG, 1)[0]
            except OSError:
                pass
            try:
                _r = w._analyzer.read_bytes(
                    w._anchor + OFF_NPC_PHASE, OFF_NPC_PHASE_LEN)
                if len(_r) >= 3:
                    _ph_b0, _ph_b1, _ph_b2 = _r[0], _r[1], _r[2]
            except OSError:
                pass
            try:
                _aux1_lr = w._analyzer.read_bytes(
                    w._anchor + OFF_AUX_OBS_1, 1)[0]
            except OSError:
                pass
            try:
                _aux2_lr = w._analyzer.read_bytes(
                    w._anchor + OFF_AUX_OBS_2, 1)[0]
            except OSError:
                pass
            try:
                _aux3_lr = w._analyzer.read_bytes(
                    w._anchor + OFF_AUX_OBS_3, 1)[0]
            except OSError:
                pass
            try:
                _aux_faea = w._analyzer.read_bytes(
                    w._anchor + OFF_AUX_OBS_FAEA, 1)[0]
            except OSError:
                pass
            try:
                _race_cg = w._analyzer.read_bytes(
                    w._anchor + OFF_RACE_CHARGEN, 1)[0]
            except OSError:
                pass
            try:
                _race_pl = w._analyzer.read_bytes(
                    w._anchor + OFF_RACE_PLAY, 1)[0]
            except OSError:
                pass
            try:
                _face_cn = w._analyzer.read_bytes(
                    w._anchor + OFF_FACE_CLICK, 1)[0]
            except OSError:
                pass
            _log_hash = (chargen_state, _img_lr, _bonus_lr, _npc_lr,
                         _b131_lr, _dlg_lr, _ph_b0, _ph_b1, _ph_b2,
                         _aux1_lr, _aux2_lr, _aux3_lr, _aux_faea,
                         _race_cg, _race_pl, _face_cn,
                         w._chargen_method_window,
                         w._chargen_10q_displayed,
                         w._chargen_in_advice,
                         w._chargen_goyenow_displayed,
                         w._chargen_distribute_displayed,
                         w._chargen_choose_attrs_displayed,
                         new_modal_kind if w._chargen_attrs_phase_seen
                         else None,
                         w._chargen_appearance_displayed,
                         w._chargen_opening_displayed,
                         w._chargen_explanation_active)
            if w._chargen_attrs_phase_log_prev != _log_hash:
                w._chargen_attrs_phase_log_prev = _log_hash
                _log.info(
                    "chargen_diagnostics: state=0x%02X img=%s bonus=%d "
                    "npc=%r b131=%r dlg=0x%02X "
                    "ph845/6/7=0x%02X/0x%02X/0x%02X "
                    "aux8F6E=0x%02X aux8F74=0x%02X aux8F7A=0x%02X "
                    "auxFAEA=0x%02X "
                    "race_cg=%d race_pl=%d face_cn=%d "
                    "method=%s 10q=%s advice=%s goyenow=%s distribute=%s "
                    "choose=%s modal=%s explain=%s appearance=%s opening=%s "
                    "anchor=%s",
                    chargen_state, _img_lr, _bonus_lr, _npc_lr, _b131_lr,
                    _dlg_lr, _ph_b0, _ph_b1, _ph_b2,
                    _aux1_lr, _aux2_lr, _aux3_lr, _aux_faea,
                    _race_cg, _race_pl, _face_cn,
                    w._chargen_method_window,
                    w._chargen_10q_displayed,
                    w._chargen_in_advice,
                    w._chargen_goyenow_displayed,
                    w._chargen_distribute_displayed,
                    w._chargen_choose_attrs_displayed,
                    (new_modal_kind or "none")
                    if w._chargen_attrs_phase_seen else "n/a",
                    w._chargen_explanation_active or "none",
                    w._chargen_appearance_displayed,
                    w._chargen_opening_displayed,
                    ("0x%02X" % w._chargen_attrs_state_anchor)
                    if w._chargen_attrs_state_anchor is not None
                    else "None")
        except Exception:  # noqa: BLE001
            pass


@dataclass(frozen=True)
class ChargenView:
    """chargen 描画の単一判定結果 (1軸 view)。

    ``classify_chargen_view`` が生成し ``render_chargen_view`` が消費する。
    施設ノードの classify_view→render(view消費) と同じ判定描画セット分離。
    """
    is_chargen: bool
    panel_visible: bool
    target_panel_mode: str | None
    reason: str
    freeze_status: bool
    freeze_ok: bool  # freeze 判定が例外なく算出できたか (False なら適用しない)
    substate: str    # chargen_substate(w): 現サブ状態 1軸名 (診断/将来の dispatch 用)


def classify_chargen_view(w) -> ChargenView:
    """chargen 描画の単一判定 (1軸)。副作用なし・tab/status を読まない。

    翻訳タブ panel_mode 目標 + ステータス凍結フラグを 1 つの view へ集約する。
    実際の適用 (panel_mode 切替 / freeze 反映) は ``render_chargen_view`` が行う
    (= 判定描画セット分離。render 内で再判定しない)。施設ノードの
    classify_view→render(view消費) と同じ判定描画セット分離。

    翻訳タブの本来の役割は「状況に応じたアシスト UI 提供」。
    翻訳パネル表示時はパネルが基本翻訳を担うため、タブはアシスト UI に専念。
    翻訳パネル非表示時はタブが翻訳表示も兼ね、メイン画面のときだけアシスト UI、
    説明ポップアップ・確認ダイアログ・モーダルでは画面通りの翻訳を出す。
    設定 translate_tab_emulate_panel_hidden = True の場合、翻訳パネルが表示中でも
    翻訳タブは「パネル非表示時の挙動」で動作する (検証用、デフォルト False)。
    """
    is_chargen = _current_top_level(w) == "chargen"
    _emulate_panel_hidden = bool(
        settings.get("translate_tab_emulate_panel_hidden", False))
    panel_visible = (
        w._layout_translate_panel is not None
        and not _emulate_panel_hidden
    )
    target_mode: str | None = None
    reason = ""
    if is_chargen:
        # _chargen_target_panel_mode は memory 直読みを含むため、旧実装の
        # try/except 包囲 (= 失敗時は panel 適用スキップ) と同等にする。
        try:
            target_mode, reason = _chargen_target_panel_mode(
                w, panel_visible=panel_visible)
        except (AttributeError, RuntimeError):
            target_mode, reason = None, ""
    # 後半 chargen 中のステータス表示凍結:
    # ボーナス分配完了後 (= Save/Reroll 確認 → Appearance) 以降は memory
    # location +0x1CD 等にゴミ値が書き込まれるため、AttributesPanel が異常値
    # (全て同値 / 負値 / Race=不明 等) を表示する。凍結条件 (いずれか):
    #   a. _chargen_appearance_displayed=True (外見選択画面)
    #   b. NPC dialog に "dost thou choose" (= Save/Reroll 確認)
    #   c. NPC dialog に "choose thy appearance" (= Appearance テキスト)
    freeze_status = False
    freeze_ok = True
    try:
        _npc_str = (w._npc_dialog_prev or "").lower()
        _post_distribute = (
            "dost thou choose" in _npc_str
            or "choose thy appearance" in _npc_str
        )
        freeze_status = (
            is_chargen
            and (w._chargen_appearance_displayed or _post_distribute)
        )
    except (AttributeError, RuntimeError):
        freeze_ok = False
    substate = chargen_substate(w) if is_chargen else ""
    return ChargenView(
        is_chargen=is_chargen, panel_visible=panel_visible,
        target_panel_mode=target_mode, reason=reason,
        freeze_status=freeze_status, freeze_ok=freeze_ok,
        substate=substate)


def render_chargen_view(w, view: ChargenView) -> None:
    """``ChargenView`` を消費して描画適用する (内部再判定なし)。"""
    # panel_mode 適用: classify 済 target を現在値と比較して切替えるだけ。
    try:
        if view.is_chargen:
            current_mode = w._tab_translate.panel_mode()
            target_mode = view.target_panel_mode
            if target_mode is not None and current_mode != target_mode:
                _log.info(
                    "chargen_panel: target_mode=%s reason=%s prev=%s "
                    "substate=%s",
                    target_mode, view.reason, current_mode, view.substate)
                if target_mode == "choose_attributes":
                    w._activate_choose_attributes_panel(
                        priority=_CHARGEN_PANEL_PRIORITY)
                elif target_mode == "appearance_faces":
                    _set_panel_mode(w, "appearance_faces",
                                    priority=_CHARGEN_PANEL_PRIORITY)
                    entry = itl.lookup("_CHARGEN_APPEARANCE_", 0)
                    if entry is not None:
                        tab_orig = itl.get_text_display(entry) or ""
                        tab_disp = itl.get_translation_display(entry)
                        tab_trans = (tab_disp if isinstance(tab_disp, str)
                                     else "")
                        try:
                            w._tab_translate.appearance_faces_panel(
                                ).set_translation_message(tab_orig, tab_trans)
                        except (AttributeError, RuntimeError):
                            pass
                elif target_mode == "class_list":
                    # クラス一覧 (前景): mode を高優先で立て、**同 poll・同 priority** で
                    # 画面本文 "Choose thy class..." の翻訳も push する。propose_display は
                    # 同 priority の panel_mode と translation のみ 1 件へ merge する
                    # (priority 不一致だと translation 側が落ちる)。本文を priority 0 で
                    # 出すと mode (priority 30) に負けて表示されず、前画面 (クラス選択方法/
                    # クラス確認) の訳が残留する。よって本文も
                    # _CHARGEN_PANEL_PRIORITY で push して mode と merge させ下部に出す。
                    # クラス一覧の NPC バッファはハイライト中クラス名で本文プロンプトを
                    # 持たないため、renderer が明示 push する必要がある。
                    _set_panel_mode(w, "class_list",
                                    priority=_CHARGEN_PANEL_PRIORITY)
                    cls_entry = itl.lookup("_CHARGEN_CHOOSE_CLASS_", 0)
                    if cls_entry is not None:
                        try:
                            w._ui_router.update_panel_translation(
                                itl.get_text_panel(cls_entry),
                                itl.get_translation(cls_entry) or "",
                                priority=_CHARGEN_PANEL_PRIORITY)
                        except (AttributeError, RuntimeError):
                            pass
                else:
                    # race_list (前景) は高優先・translate (本文/モーダル)
                    # は priority 0 で翻訳 push と merge させ本文を出す。
                    _set_panel_mode(
                        w, target_mode,
                        priority=(0 if target_mode == "translate"
                                  else _CHARGEN_PANEL_PRIORITY))
        else:
            # 非 chargen で appearance_faces 残留 → translate に戻す
            current_mode = w._tab_translate.panel_mode()
            if current_mode == "appearance_faces":
                _log.info(
                    "chargen_panel: target_mode=translate reason=non_chargen_reset prev=%s",
                    current_mode)
                _set_panel_mode(w, "translate")
    except (AttributeError, RuntimeError):
        pass
    # ステータス凍結適用 (共有 AttributesPanel = 翻訳/ステータス両タブに作用)。
    if view.freeze_ok:
        try:
            if w._tab_status is not None:
                w._tab_status.set_freeze_updates(view.freeze_status)
        except (AttributeError, RuntimeError):
            pass


def _poll_revert_appearance_flag(w) -> None:
    """Appearance フラグの自動巻戻しフェーズ。"""
    # Appearance フラグの自動巻戻し:
    # ボーナスポイント警告 / リロールで Appearance 画面から ChooseAttributes
    # 画面に戻った際に、Appearance フラグが立ったままになりステータス表示が
    # 消失する症状を防ぐ。
    # 条件: chargen 中 AND _chargen_appearance_displayed=True AND
    #       IMG=MRSHIRT.IMG (ステータス画面) AND bonus_pts が「振分中の
    #       有効範囲 1-30」内
    # → Appearance フラグを巻戻し + ボーナス警告翻訳を表示
    #
    # bonus_pts > 0 の単純比較は危険。
    # Appearance 画面では Arena が 0x129C に 0xFF (=255 unsigned) 等の
    # ゴミ値を書く場合があり、誤って巻戻しが連続発火する。
    # 「0 <= bonus_pts <= 30」の有効レンジ判定に
    # 限定する (ChooseAttributes 中の正常値はこの範囲内)。
    if (w._chargen_appearance_displayed
            and _current_top_level(w) == "chargen"):
        try:
            _bonus_pts = w._analyzer.read_bytes(
                w._anchor + 0x129C, 1)[0]
        except (OSError, AttributeError):
            _bonus_pts = 0
        try:
            _img_raw = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_now = _img_raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_now = ""
        if (1 <= _bonus_pts <= 30
                and _img_now == "MRSHIRT.IMG"):
            w._chargen_appearance_displayed = False
            entry = itl.lookup("_CHARGEN_BONUS_REMAINING_", 0)
            if entry is not None:
                w._update_translate_tab(entry)
            try:
                w._activate_choose_attributes_panel()
            except (AttributeError, RuntimeError):
                pass
            _log.info(
                "chargen: appearance flag reverted "
                "(bonus_pts=%d in valid range, img=%s)",
                _bonus_pts, _img_now)


def _poll_probe_diagnostics(w, chargen_state: int, chargen_q_seq: int) -> None:
    """chargen_probe 診断ログフェーズ (method/Q/class list 活性時のみ)。"""
    # chargen_probe 診断ログ（検証用）。
    # 10Q intro の検出条件は 0x66 観測で破綻し得るため、現時点で
    # 仕様未確定。Generate / Select / 2回目 New Game の 3 パスでサンプルを
    # 収集して仕様化するため、関連 poll を時系列で記録する。
    # 出力対象は method 画面中・Q 進行中・class list 活性中のみに限定して
    # ログ量を抑制する。
    if (w._chargen_method_window
            or (1 <= chargen_q_seq <= 10)
            or w._chargen_class_list_active):
        try:
            first_q_num = w._analyzer.read_bytes(
                w._anchor + CHARGEN_Q_ARRAY_OFFSET, 1)[0]
        except OSError:
            first_q_num = 0
        method_state_str = (f"0x{w._chargen_method_state:02X}"
                            if w._chargen_method_state is not None
                            else "None")
        # IMG 名も診断ログに含める (10Q intro 検出のため、method 画面と
        # 10Q intro 画面で実際に IMG がどう変化するかを観測)
        try:
            _img_raw_probe = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_probe = _img_raw_probe.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_probe = "?"
        _log.info(
            "chargen_probe: state=0x%02X streak=%d method=%s "
            "method_state=%s class_list=%s q_seq=%d q0=%d 10q=%s "
            "img=%r npc=%r",
            chargen_state,
            w._chargen_state_streak,
            w._chargen_method_window,
            method_state_str,
            w._chargen_class_list_active,
            chargen_q_seq,
            first_q_num,
            w._chargen_10q_displayed,
            _img_probe,
            w._npc_dialog_prev[:60],
        )


def _poll_bonus_warning(w) -> None:
    """能力値ボーナス未消費警告の翻訳表示フェーズ。

    "You must distribute all your bonus points." をメッセージバッファ
    (+0x929E) から検出して翻訳表示する。L1=chargen 関心のため chargen 系統
    が所有する (旧実装は C1 金貨ドロップ単位に同居=L1 跨ぎ・是正済)。
    バッファ変化検出は本単位所有の prev (`_chargen_bonus_b131_prev`) で
    行う。modal 状態管理は poll() 側に集約済みのため、ここでは翻訳 push
    のみ行う (sticky latch 回避)。
    """
    try:
        _raw = w._analyzer.read_bytes(w._anchor + 0x929E, 64)
        _msg = _raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    except (OSError, AttributeError):
        _msg = ""
    _prev = getattr(w, "_chargen_bonus_b131_prev", "")
    _changed = (_msg != _prev)
    w._chargen_bonus_b131_prev = _msg
    if not (_changed and _msg.strip()
            == "You must distribute all your bonus points."):
        return
    entry = itl.lookup("_CHARGEN_BONUS_REMAINING_", 0)
    if entry is not None:
        try:
            w._update_translate_tab(entry)
        except (AttributeError, RuntimeError) as exc:
            _log.debug("chargen BONUS_REMAINING update failed: %s", exc)
        _log.info(
            "chargen: BONUS_REMAINING translation pushed from 0x929E "
            "(phase_seen=%s)",
            getattr(w, "_chargen_attrs_phase_seen", False))


def _poll_cinematic(w) -> None:
    """chargen 完了フラグ監視 + post-chargen cinematic 表示更新フェーズ。"""
    # chargen 完了フラグ（anchor+4760）:
    # - 0→1: post-chargen cinematic 開始フェーズへ。0x10764C10 から原文を
    #   読み取って表示する。ただし Arena は chargen_done を立てた直後ではなく
    #   一拍遅れて cinematic テキストを書き込むため、初回読取で失敗しても
    #   次の poll で再試行できるようリトライウィンドウを設ける。
    # - 1→0: chargen 再開（メニューから New Game 等）→ 状態フラグリセット
    try:
        chargen_done = w._analyzer.read_bytes(
            w._anchor + CHARGEN_DONE_OFFSET, 1)[0]
    except OSError:
        chargen_done = w._chargen_done_prev
    # chargen_done 0→1 遷移で post-chargen cinematic 用のリトライカウンタを
    # 起動する。観測上 chargen_done は
    # 「chargen 中=1 / cinematic 起動=0 / 0→1 で再び 1 になる」という挙動を
    # しているように見えるが、いずれにせよ「0→1 の瞬間」が cinematic 表示の
    # 機会となる。
    #
    # `chargen_done 1→0` を「ニューゲーム開始」とみなして全 chargen
    # 状態をリセットしてはならない。この 1→0 は Appearance Done 直後の
    # cinematic 起動準備時に発火するため、リセット直後に q_phase_active が
    # True になり、残骸の chargen_q_seq でQ が誤発火 → Appearance 翻訳を
    # 上書きする。1→0 リセットは行わず、
    # 代わりに class_list 再活性化時にニューゲーム検出する方式を用いる
    # (`_activate_class_list_for_class` 参照)。
    if chargen_done == 1 and w._chargen_done_prev == 0:
        w._chargen_opening_retry = 240  # 120 秒（poll 500ms × 240）
        w._chargen_opening_displayed = False
        w._chargen_opening_text_prev = ""
    # cinematic 表示更新: chargen_done=1 中は毎 poll 試行（ページ更新追従）
    if chargen_done == 1 and w._chargen_opening_retry > 0:
        w._chargen_opening_retry -= 1
        if w._chargen._fire_post_chargen_opening():
            w._chargen_opening_displayed = True
            w._chargen_appearance_displayed = False
            # opening 到達 → attrs anchor は不要なため破棄
            w._chargen_attrs_state_anchor = None
            w._chargen_attrs_phase_seen = False
            w._chargen_attrs_modal_active = False
            # 訂正: status latch は arm しない。CHOOSE_ATTRIBUTES 経由で
            # 既に arm 済みであれば単調 latch のまま True を保持する。
    w._chargen_done_prev = chargen_done


def _poll_detect(w, chargen_state: int) -> tuple[int, str | None]:
    """検出側 1軸: 現サブ状態の離脱検出のみ実行する。

    ``chargen_substate(w)`` を dispatch 軸とし、そのサブ状態の離脱検出
    ハンドラだけを 1 poll につき 1 経路だけ呼ぶ。「毎 poll 全検出器を
    逐次実行＋各検出器内の相互排他ガードで自分の番か再判定」(並列評価モデル)
    を採らず、一意性を制御フロー構造で保証する。

    - method/class_advice: a845 変化ベースの遷移のため a845 を読む。
    - method/ten_questions: 設問検出 (10Q intro / Q1-Q10)。
    - attrs/appearance: 能力値配分 modal 再評価 + 説明閉幕検出。
    - その他 (opening/class_list/race_*/name/sex/complete): 外部 latch 主導の
      ため poll 検出器を持たない。

    Returns:
        (chargen_q_seq, new_modal_kind): 後段の probe / diagnostics が使用。
    """
    sub = chargen_substate(w)

    if sub == "method":
        _detect_method_exit(w, chargen_state, _read_a845(w))
    elif sub == "class_advice":
        _detect_advice_exit(w, chargen_state, _read_a845(w))
        _poll_detect_goyenow_fallback(w, chargen_state)
    elif sub == "goyenow":
        _detect_goyenow_exit(w, chargen_state)
        _poll_detect_distribute_by_dialog(w, chargen_state)
        _poll_detect_distribute_safety(w, chargen_state)
    elif sub == "attrs":
        _detect_attrs_appearance_candidate(w, chargen_state)
        _poll_detect_appearance(w)

    # 設問検出 (q_seq 読取を含む): method (10Q intro) / ten_questions (Q1-Q10)。
    # それ以外のサブ状態では q_seq を読むだけ (probe 用)、発火経路は持たない。
    if sub in ("method", "ten_questions"):
        chargen_q_seq = _poll_detect_questions(w)
    else:
        try:
            chargen_q_seq = w._analyzer.read_bytes(
                w._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
        except OSError:
            chargen_q_seq = 0

    # 能力値配分 modal 再評価 + 説明閉幕検出: attrs / appearance。
    if sub in ("attrs", "appearance"):
        new_modal_kind = _poll_evaluate_modal(w)
    else:
        new_modal_kind = None

    return chargen_q_seq, new_modal_kind


def poll(w) -> None:
    """chargen 状態時の描画・検出処理。

    advice_capture_age インクリメント / chargen_state 安定性判定 / 各種
    chargen 検出 / cinematic 表示更新を一括で実行する。

    ``_top_level_state != "chargen"`` の時は no-op (= 冒頭 guard)。
    chargen 専用の advice_capture_age 加算 / state 安定性判定 / 各種
    検出が normal-play / pregame 中に副作用を起こさないようにする。
    ``handle_npc_dialog()`` 冒頭 guard と同形式。
    """
    if _current_top_level(w) != "chargen":
        return
    # advice_capture_age を毎 poll でインクリメント。
    # advice_state capture 時に 0 にセットされ、ここで 1 ずつ増える。
    # GoYeNow fallback ブロックの age >= 6 ガードで使用。
    if w._advice_capture_age >= 0:
        w._advice_capture_age += 1

    # ステータス/マップ/ジャーナル表示の有効/無効を毎 poll で同期。
    # chargen の sub-state (能力値配分発火等) に応じて status の有効化が
    # 切り替わるため、状態変化を漏らさず反映する。
    try:
        w._apply_display_active_for_state()
    except AttributeError:
        pass

    # 2. chargen_state 読取 + 安定性追跡 (streak)
    chargen_state = _poll_track_state(w)

    # 3. 検出側 1軸 dispatch: chargen_substate を軸に、現サブ状態の
    #    離脱検出のみ実行する (method/advice/goyenow/distribute
    #    /questions/modal の毎poll並列実行は採らない)。q_seq / modal_kind を返す。
    chargen_q_seq, new_modal_kind = _poll_detect(w, chargen_state)

    # 9. chargen_diagnostics 診断ログ (値変化時に 1 行 dump)
    _poll_diagnostics(w, chargen_state, new_modal_kind)

    # race 系 latch クリアは NPC テキスト経由 (`_CHARGEN_GENDER_` 等 次画面 NPC
    # 到達で chargen_controller がクリア) に委ねる。
    # `+0xA847==0x02` での自前クリアは採らない。
    # race_select / race_desc を一律クリアしてしまうため、説明ポップアップを閉じた
    # 直後に種族選択画面の翻訳まで消える副作用があるため。

    # 10. 描画 1軸seam: classify_chargen_view(判定) → render_chargen_view
    #     (view 消費・内部再判定なし)。panel_mode 切替 + ステータス凍結を集約。
    render_chargen_view(w, classify_chargen_view(w))

    # 11. 能力値ボーナス未消費警告 (+0x929E・L1=chargen 関心の自前検出)
    _poll_bonus_warning(w)

    # 12. Appearance フラグの自動巻戻し
    _poll_revert_appearance_flag(w)

    # 13. chargen_probe 診断ログ (method/Q/class list 活性時のみ)
    _poll_probe_diagnostics(w, chargen_state, chargen_q_seq)

    # 14. chargen 完了フラグ監視 + post-chargen cinematic 表示更新
    _poll_cinematic(w)
