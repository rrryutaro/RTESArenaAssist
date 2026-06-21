"""controllers/translation_update_controller.py — 翻訳タブ/パネル更新。

トリガーエントリの翻訳タブ表示 (update_translate_tab) と翻訳ペアの
タブ・レイアウトパネル反映 (push_translation) を assist_window から
純抽出 (挙動不変)。window 状態は win 経由で参照する。
"""
from __future__ import annotations

import logging

import inf_text_lookup as itl

_log = logging.getLogger("assist_window")


def update_translate_tab(win, entry: dict) -> None:
    """トリガーエントリを翻訳タブに表示する。"""
    # chargen エントリの表示中はゲーム状態行を隠す。非 chargen は表示する。
    inf_key = (entry.get("inf") or "").upper()
    win._set_chargen_ui_state(inf_key.startswith("_CHARGEN_"))
    # method 画面 → 10Q 窓の管理:
    # - _CHARGEN_ (method 画面) NPC を見たら窓を開く
    # - 他の chargen 進行があれば窓を閉じる
    # Arena DOSBox は New Game 後もメモリ値（chargen_done / live_mif /
    # q_seq / q_array 等）をリセットしない。2 回目以降の chargen でも
    # 10Q intro を再発火させるため、method 画面の再進入時に method_state と
    # 10q_displayed を初期化する。
    # method 画面 NPC `_CHARGEN_` 検出 = 新規 chargen 開始の合図。
    # 個別フラグの場当たりクリアではなく
    # `_reset_chargen_state_for_restart` で全 chargen 進行 state を漏れなく
    # 一括リセットする。個別クリアだと advice/goyenow/distribute 系の漏れがあり、
    # 2 回目以降の chargen で前回フラグが残留して Q1 抑止等の不具合の原因になる。
    # 「NPC 検出時 streak>=2 なら即時 method_state 捕捉」を維持するため、
    # streak / state_prev は退避してリセット後に復帰する。
    if inf_key == "_CHARGEN_":
        saved_streak = win._chargen_state_streak
        saved_state_prev = win._chargen_state_prev
        win._chargen._reset_chargen_state_for_restart(
            reason="method NPC detected (new chargen start)")
        # streak / state_prev を復帰（即時 method_state 捕捉のため）
        win._chargen_state_streak = saved_streak
        win._chargen_state_prev = saved_state_prev
        # method 窓を開く
        win._chargen_method_window = True
        # 即時 method_state 捕捉（streak が既に stable 圏なら）
        if saved_streak >= 2:
            win._chargen_method_state = saved_state_prev
            _log.info(
                "chargen: method state captured at NPC detection = 0x%02X "
                "(streak=%d)",
                saved_state_prev, saved_streak,
            )
        try:
            win._sync_attributes_race_class()
        except (AttributeError, RuntimeError) as exc:
            _log.debug("chargen: _sync_attributes_race_class skipped: %s", exc)
    elif inf_key == "_CHARGEN_PROVINCE_":
        # race_select 進入。
        # method 窓は閉じる、race_select 窓を開く。
        win._chargen_method_window = False
        win._chargen_race_select_displayed = True
        # 10Q phase および class_accept は完了済み → クリア
        win._chargen_10q_displayed = False
        win._chargen_class_accept_displayed = False
        win._chargen_class_list_active = False
        # 残留 chargen_complete をクリア
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_PROVINCE_CONFIRM_":
        # confirm dialog 表示中。
        # race_select_displayed は維持（No 戻りで PROVINCE 再表示に対応）。
        # Yes で次の chargen NPC（_CHARGEN_RACE_*）が来たら下の elif で False。
        win._chargen_method_window = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_RESULT_"):
        # 10Q 結果確認画面 "Thou wouldst survive longest as a..."
        # 実エントリ名は _CHARGEN_RESULT_<CLASS>_ の形式（class_accept フェーズ）
        # 10Q phase は完了済み
        win._chargen_class_accept_displayed = True
        win._chargen_method_window = False
        win._chargen_10q_displayed = False
        win._chargen_class_list_active = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_RACE_"):
        # 種族説明画面 "Know ye this also: ..."
        win._chargen_race_desc_displayed = True
        win._chargen_method_window = False
        win._chargen_race_select_displayed = False  # confirm Yes 後の遷移
        win._chargen_class_accept_displayed = False
        win._chargen_10q_displayed = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_CLASS_ADVICE_"):
        # クラスアドバイス進入時に他フラグをクリア（既存の in_advice は別所で True）
        win._chargen_race_desc_displayed = False
        win._chargen_race_select_displayed = False
        win._chargen_method_window = False
        win._chargen_10q_displayed = False
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_GENDER_":
        # 性別選択画面
        win._chargen_sex_select_displayed = True
        win._in_chargen_name = False
        win._chargen_method_window = False
        win._chargen_class_list_active = False
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_APPEARANCE_":
        # 外見選択画面
        win._chargen_appearance_displayed = True
        win._chargen_sex_select_displayed = False
        win._in_chargen_name = False
        win._chargen_complete_displayed = False
        # Appearance phase 進入 → attrs phase 抜けたので anchor 破棄
        # (再度 ChooseAttributes に戻ることはない)
        win._chargen_attrs_state_anchor = None
        win._chargen_attrs_phase_seen = False
        win._chargen_attrs_modal_active = False
        win._chargen_attrs_modal_kind = None
        # 訂正: status latch は arm しない。CHOOSE_ATTRIBUTES が arm
        # 済みなら latch は True のまま保持される (単調 latch)。
        # CHOOSE_ATTRIBUTES を経由していない再接続経由 Appearance 時は
        # ステータスタブ非表示のまま (要件どおり、能力値選択経由でのみ
        # ステータスタブが有効になる)。
    elif inf_key.startswith("_CHARGEN_"):
        # 他の chargen NPC（特定パターン外、例: _CHARGEN_BONUS_REMAINING_）
        # method / race_select / その他フラグを汎用クリア
        win._chargen_method_window = False
        win._chargen_race_select_displayed = False
        win._chargen_class_accept_displayed = False
        win._chargen_race_desc_displayed = False
        win._chargen_complete_displayed = False
        # modal 状態は chargen_state.poll() で毎 poll メモリから再評価
        # するため、ここでは触らない (sticky latch を避ける)。
    typ = entry.get("type", "")
    if typ == "riddle":
        original   = entry.get("question", "")
        trans      = itl.get_translation(entry)
        translated = trans.get("question", "") if isinstance(trans, dict) else ""
        win._push_translation(original, translated)
    else:
        # 3-layer スキーマ:
        # - タブ EN: text_display → text_panel → text (get_text_display)
        # - タブ JA: translations_display.ja → translations.ja (get_translation_display)
        # - パネル EN: text_panel → text_display → text (get_text_panel)
        # - パネル JA: translations.ja
        tab_orig    = itl.get_text_display(entry)
        tab_disp    = itl.get_translation_display(entry)
        tab_trans   = tab_disp if isinstance(tab_disp, str) else ""
        panel_orig  = itl.get_text_panel(entry)
        panel_basic = itl.get_translation(entry)
        panel_trans = panel_basic if isinstance(panel_basic, str) else ""
        win._push_translation(tab_orig, tab_trans,
                                panel_original=panel_orig,
                                panel_translated=panel_trans)


def push_translation(win, original: str, translated: str,
                      panel_original: str | None = None,
                      panel_translated: str | None = None,
                      speech_role: str | None = None) -> None:
    """翻訳ペアをタブ・レイアウトパネルへ反映する。

    二段スキーマ:
    - panel_original / panel_translated を指定した場合: パネルには基本翻訳、
      タブには original / translated（補足説明付き）を表示
    - 指定しない場合: パネル・タブ共に同じ original / translated を表示
      （後方互換）

    翻訳キャッシュ:
    chargen subscreen 中は、空文字での push（lookup 失敗時等）を無視して
    直前の翻訳を維持する。スクロール時の翻訳消失対策。

    通常翻訳テキスト表示時はクラス一覧・ChooseAttributes モードから抜けて翻訳表示に戻す。
    """
    # chargen 中の翻訳キャッシュ判定
    chargen_sub = None
    try:
        from screen_detector import get_chargen_subscreen
        chargen_sub = get_chargen_subscreen(win)
    except (ImportError, AttributeError):
        pass

    # 空文字 push かつ chargen 中 → キャッシュ維持（前回表示のまま）
    if (not original and not translated
            and chargen_sub is not None
            and getattr(win, "_last_chargen_subscreen", None) == chargen_sub):
        _log.debug("push_translation: chargen cache hit (skip empty push, sub=%s)",
                   chargen_sub)
        return

    try:
        mode = win._tab_translate.panel_mode()
        if win._chargen_class_list_active or mode == "class_list":
            win._set_class_list_panel_mode(False)
            mode = "translate"
        # ChooseAttributes 中（_chargen_choose_attrs_displayed=True
        # かつ _chargen_appearance_displayed=False）は、stat 分配中の transient
        # NPC dialog（"+1" 等）で panel mode を奪い AttributesPanel が消える
        # ため、choose_attributes フェーズ中はモード切替を抑止する。
        # LOADSAVE.IMG 表示中は load_screen → translate に戻さない
        # （ロード画面のセーブスロット一覧を翻訳タブで表示するため）。
        # IMG が LOADSAVE 以外になった時のみ defensive に translate へ戻す。
        if mode == "load_screen":
            img_name_now = (
                getattr(win, "_img_name_prev", "") or "").upper()
            if img_name_now != "LOADSAVE.IMG":
                win._ui_router.set_panel_mode("translate")
        # chargen 関連の panel_mode 切替 (choose_attributes / appearance_faces)
        # は本関数では行わない。chargen renderer
        # (top_level/chargen_state.poll() 内) が phase/modal/anchor から
        # target_mode を決定して再アサートする責務分離設計。
        # _push_translation は汎用翻訳 API として、ラベル/パネルへの
        # テキスト更新のみを担う。
    except AttributeError:
        pass
    # タブ側は補足説明付き（指定された original / translated）、
    # パネル側は基本翻訳（panel_* 指定なしなら original / translated を流用）。
    # _push_translation は汎用翻訳 API なので、表示 payload は
    # UiRouter に集約しつつ panel_owner は維持する。
    p_orig = panel_original if panel_original is not None else original
    p_trans = panel_translated if panel_translated is not None else translated
    # キャラクター作成中はこの汎用 API で出る説明文・10質問・各種案内を
    # 基本的に読み上げる。発生源(=chargen 状態)で「状況説明」を既定宣言する
    # (明示 speech_role があれば優先)。通常プレイの popup 等(非chargen)は未宣言のまま。
    # 読み上げ/ログは「画面どおりのパネル本文(p_trans)」を使う。タブ本文(translated)は
    # 操作説明等の付加情報を含み画面に無いため、読み上げ対象にしない。
    _speech_text = None
    if getattr(win, "_top_level_state", "") == "chargen":
        if speech_role is None:
            speech_role = "situation"
        _speech_text = p_trans
    win._ui_router.update_translation(
        "", original, translated,
        mode=None,
        panel_en=p_orig,
        panel_ja=p_trans,
        keep_owner=True,
        speech_role=speech_role,
        speech_text=_speech_text)

    # 翻訳キャッシュ更新（chargen 中の有効 push のみ）
    if chargen_sub is not None and (original or translated):
        win._last_chargen_subscreen = chargen_sub
    elif chargen_sub is None:
        # chargen 終了 → キャッシュクリア
        win._last_chargen_subscreen = None


__all__ = ["update_translate_tab", "push_translation"]
