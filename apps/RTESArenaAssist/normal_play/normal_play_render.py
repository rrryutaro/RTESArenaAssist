"""normal_play/normal_play_render.py — 通常プレイ(C 通常ゲーム中)の描画
ディスパッチを所有する node 側モジュール。

L1=通常プレイ中の描画 surface 群の駆動を poll_controller のオーケストレータ
から normal-play 分離化単位へ移管する (= L1 描画所有の node 化)。各 surface の
判定/描画モジュール (trigger_module 等) への委譲はここに閉じる。

現状は C1(ダンジョン)文脈の surface ディスパッチと、② NPC popup
(POPUP11 sub-state / ASK ABOUT? 単一軸) クラスタを移管済み。後続増分で
施設 render ディスパッチも本モジュールへ集約していく。
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from controllers.poll_diag import (
    _checkpoint,
    _phase_record,
    _phase_start,
)
from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("normal_play_render")


def poll_c1_surface_dispatch(
        w, b30, *, npc_dialog_changed, inf_name, mif_name,
        instore_resp_handled):
    """C1(ダンジョン)文脈の表示 surface 群を駆動する単一ディスパッチ点。

    各 surface (cinematic / +0x7979 runtime メッセージ / +0x929E 死体クリック時の
    金貨有無 / ダイアログclose) を現挙動どおりの順で呼ぶ (= behavior-preserving)。
    単一前景判定 `classify_c1_dialog_substate`(a845/fg-ptr=単一値)で C1 ダイアログ
    面は構造的に相互排他とし、各 surface へ前景 owner を渡して自面でない poll は
    描画を抑止させる (= 同時に複数面が前景にならない事を制御フローで保証)。
    """
    from normal_play.trigger_module import (
        poll_red_text as _poll_red_text,
        poll_dialog_close as _poll_dialog_close,
        classify_c1_dialog_substate as _classify_c1_dialog_substate,
    )
    from normal_play.c1_cinematic_module import (
        poll_vision_cinematic as _poll_vision_cinematic,
        poll_death_cinematic as _poll_death_cinematic,
    )
    from normal_play.c1_gold_drop_module import (
        poll_gold_drop as _poll_gold_drop,
    )
    _c1_fg = _classify_c1_dialog_substate(
        w, b30, npc_dialog_changed=npc_dialog_changed)
    # 単一前景を poll-scoped 単一ソースとして公開する。後段の close-lifecycle
    # 消費者 (level_up cleanup 等) が散在する生イベントフラグ (red_changed/
    # npc_dialog_changed) を再導出する代わりに、この単一前景を消費する
    # (真1軸化: 「自面が前景でない時のみ clear」へ統一)。
    w._c1_dialog_foreground = _c1_fg
    _poll_vision_cinematic(w, b30=b30)
    _poll_death_cinematic(w)
    _poll_red_text(w, b30=b30, npc_dialog_changed=npc_dialog_changed,
                   c1_fg=_c1_fg)
    _poll_gold_drop(w, b30=b30, inf_name=inf_name, mif_name=mif_name,
                    c1_fg=_c1_fg)
    _poll_dialog_close(w, b30=b30, npc_dialog_changed=npc_dialog_changed,
                       instore_resp_handled=instore_resp_handled,
                       c1_fg=_c1_fg)


# ASK ABOUT? main の再表示を抑止すべき POPUP11 list_state の集合。
# これらの状態中に ASK ABOUT? main を上書きすると、Where is 場所一覧 /
# 動的場所一覧 / NPC 応答テキスト が ASK ABOUT? メイン表示で潰される。
# rumor_type は _show_ask_about_menu() 側でサブメニュー表示に切り替える
# 設計のため抑止対象に含めない。
_ASK_ABOUT_MAIN_BLOCKING_LIST_STATES = frozenset({
    "where_is_list",
    "dynamic_place_list",
    "npc_response",
})

_ASK_ABOUT_MENU_PTR_MIN = 0x8000
_ASK_ABOUT_MENU_PTR_MAX = 0x9000
_ASK_ABOUT_MAIN_RECOVERY_STATE = "ask_about_main_recovery"


def blocks_ask_about_main(list_state: str) -> bool:
    """list_state が ASK ABOUT? main 再表示を抑止対象か。pure helper。"""
    return list_state in _ASK_ABOUT_MAIN_BLOCKING_LIST_STATES


def ask_about_main_display_allowed(
        list_state: str, img_name: str, current_ptr: int) -> bool:
    """ASK ABOUT? main を現在 poll で表示してよいか。

    POPUP11.IMG が前面の間は場所一覧 / NPC 応答を ASK ABOUT? main で
    上書きしない。一方で、NPC 立ち絵へ戻り +0xA844 がメニュー定義範囲を
    指している場合は、ゲーム側は ASK ABOUT? main へ復帰済みと判断する。
    """
    if not blocks_ask_about_main(list_state):
        return True
    if (img_name or "").upper() == "POPUP11.IMG":
        return False
    try:
        ptr = int(current_ptr)
    except (TypeError, ValueError):
        return False
    return _ASK_ABOUT_MENU_PTR_MIN <= ptr < _ASK_ABOUT_MENU_PTR_MAX


def _render_ask_about_main_recovery(w, prev_list_state: str) -> None:
    """POPUP11 内で ASK ABOUT? main 復帰を確定表示する。

    復帰判定後に「後段の ASK ABOUT? 検出」へ委ねるだけだと、ポインタ変化が
    ない poll では発火せず、直前の場所一覧が残る。判定と描画を同じ NPC
    会話 L4 表示単位で閉じる。
    """
    if prev_list_state != _ASK_ABOUT_MAIN_RECOVERY_STATE:
        w._img_screen._show_ask_about_menu()
    w._popup11_list_state_prev = _ASK_ABOUT_MAIN_RECOVERY_STATE
    w._popup11_exit_pending_ask_about = False


def _classify_popup11_substate(w, _img_name, _list_state_eligible):
    """② POPUP11 sub-state 分類 (軸A・純計算)。

    detect_popup11_list_state + 復帰/stale override を適用し、最終 sub-state と
    応答ブランチ選択値を SimpleNamespace で返す (判定描画セットの判定側)。検出
    bookkeeping (_popup11_ask_recovery / _popup11_item_dyn_prev / _cap159_diag_prev)
    の更新は現挙動どおり本関数で行う。描画は _render_popup11_substate が消費する。
    """
    if _list_state_eligible:
        try:
            from popup11_list_detector import (
                detect_popup11_list_state,
                POPUP11_ITEM_COUNT_OFFSET,
                POPUP11_DYN_COUNT_OFFSET,
            )
            _list_state = detect_popup11_list_state(w._analyzer, w._anchor)
            # ASK_ABOUT_MAIN 復帰検出のため item_count/dyn_count を別途読む
            try:
                _ic_raw = w._analyzer.read_bytes(
                    w._anchor + POPUP11_ITEM_COUNT_OFFSET, 1)
                _dc_raw = w._analyzer.read_bytes(
                    w._anchor + POPUP11_DYN_COUNT_OFFSET, 1)
                _item_dyn_now = (_ic_raw[0], _dc_raw[0])
            except (OSError, AttributeError, IndexError):
                _item_dyn_now = (-1, -1)
        except Exception:
            _list_state = "npc_response"
            _item_dyn_now = (-1, -1)
    else:
        # CIF 中は list 判定をスキップし、応答テキストのみ処理
        _list_state = "npc_response"
        _item_dyn_now = (-1, -1)

    # 応答 → ASK_ABOUT_MAIN 復帰の検出 (メモリ残留対応)
    # 改訂:
    # 復帰対象を dynamic_place_list のみに限定する。where_is_list は
    # dyn_count 残留対応 (sub_marker='Exit' && dyn_count != item_count) で
    # 正しく場所一覧と判定されるため、recovery 対象から除外しないと
    # 場所一覧表示が ASK_ABOUT_MAIN 復帰として上書きされる。
    # 復帰フラグは where_is_list / rumor_type / npc_response の判定が
    # 出た時点で必ず解除する (item_count/dyn_count 変化単独では Rumor /
    # 応答 / where_is_list 間で同じ値が再利用され解除されないため)。
    # 改訂:
    # 応答画面から場所一覧画面への実遷移 (= ユーザーが「どこにある?」を
    # 選んだ瞬間にゲーム側が item_count/dyn_count を新しい値で書き込む)
    # は item_dyn 値の前回 poll からの変化として検出できる。値変化があれば
    # 残置値による誤判定ではないため、recovery を発動しない / 解除する。
    _prev_list_state_for_recovery = getattr(w, "_popup11_list_state_prev", "")
    _prev_item_dyn_for_recovery = getattr(
        w, "_popup11_item_dyn_prev", (-1, -1))
    _item_dyn_changed = (
        _prev_item_dyn_for_recovery != (-1, -1)
        and _prev_item_dyn_for_recovery != _item_dyn_now
    )
    if (_prev_list_state_for_recovery == "npc_response"
            and _list_state == "dynamic_place_list"
            and not _item_dyn_changed):
        # 残置値による誤判定 (= 値変化なし) のみ復帰扱い
        w._popup11_ask_recovery = True
    elif _list_state in ("where_is_list", "rumor_type", "npc_response"):
        # list_state が非 dynamic_place_list に変化したら復帰中解除
        w._popup11_ask_recovery = False
    elif (_list_state == "dynamic_place_list"
            and _item_dyn_changed):
        # 実遷移 (= 値変化あり) の dynamic_place_list は復帰中解除
        w._popup11_ask_recovery = False
    # else: 残置値の dynamic_place_list は _popup11_ask_recovery を維持
    w._popup11_item_dyn_prev = _item_dyn_now

    # 復帰中は dynamic_place_list 判定を ask_about_main_recovery に書き換え、
    # 後段の分岐で list 表示をスキップし ASK ABOUT? main を確定表示する。
    if w._popup11_ask_recovery and _list_state == "dynamic_place_list":
        _list_state = _ASK_ABOUT_MAIN_RECOVERY_STATE

    # NPC 応答テキスト候補を 0x929E / 0x1044 / 0x9A9E から読み、
    # npc_dialog_lookup でヒットするものを最優先で採用する。lookup
    # ヒットがあれば list state の残留に関わらず応答表示を優先する。
    try:
        from popup11_response_reader import read_response_candidate
        _resp_cand = read_response_candidate(w._analyzer, w._anchor)
    except Exception:
        _resp_cand = None

    _fresh_response_text = _resp_cand.text if _resp_cand else ""
    _response_lookup_hit = bool(_resp_cand and _resp_cand.lookup_hit)

    _prev_list_state = getattr(w, "_popup11_list_state_prev", "")
    _response_is_new = (
        _fresh_response_text
        and _fresh_response_text != w._npc_dialog_text_prev
    )
    # 詳細場所一覧 / 場所一覧 から detector が npc_response 側へ落ちた
    # 状態遷移時は、テキストが前回と同一でも翻訳タブの内容を強制的に
    # 応答表示へ戻す（list 表示の残留を防ぐ）。
    _state_transition_to_response = (
        _list_state == "npc_response"
        and _prev_list_state in ("where_is_list", "dynamic_place_list")
    )

    # 診断ログ: POPUP11 list_state 分岐のどれが選ばれたかを
    # 追跡する。状態遷移時のみ INFO で出す (5Hz poll なので毎 poll
    # の冗長出力を避ける)。確認したい組合せ:
    #   (1) _list_state, _response_lookup_hit, _prev_list_state
    #   (2) _resp_cand の source_offset と text 先頭 48 文字
    #   (3) どの分岐に入ったか (taken_branch)
    _diag_resp_off = _resp_cand.source_offset if _resp_cand else -1
    _diag_resp_text = (_resp_cand.text[:48] if _resp_cand else "")
    _diag_key = (
        _img_name, _list_state, _response_lookup_hit,
        _prev_list_state, _diag_resp_off, _diag_resp_text,
    )
    _diag_prev_key = getattr(w, "_cap159_diag_prev", None)
    _diag_changed = (_diag_prev_key != _diag_key)
    if _diag_changed:
        w._cap159_diag_prev = _diag_key

    # stale list override。
    # 初回 NPC 会話「あなたは誰？」応答が出ない症状の原因は、
    # `popup11_list_detector` が前回の item_count/dyn_count/sub_marker
    # 残置値から `where_is_list` / `dynamic_place_list` を誤判定する
    # こと。応答テキスト lookup hit があり、かつ list 判定が明らかに
    # stale な場合は npc_response を優先する。
    # 実 Where is 一覧 (= dyn_count ≒ 10 等) は壊さない (= dyn_count
    # が 32 を超える、もしくは fresh response at +0x1044 を条件にする)。
    # 改訂 (場所一覧表示の根本対応):
    # _fresh_at_npcd 判定に「応答テキストが前回 poll から変化した」を
    # 追加する。前画面の応答テキストが残置されたまま場所一覧画面に
    # 遷移した場合 (= text 変化なし = 残置値継続) は override しない。
    # 新規応答時のみ override を発動し、残置値で list 判定を奪わない。
    _stale_list_override = False
    if (_response_lookup_hit
            and _list_state in (
                "where_is_list", "dynamic_place_list")):
        _dyn_count = _item_dyn_now[1] if _item_dyn_now else -1
        _unnatural_dyn = (_dyn_count > 32 or _dyn_count < 0)
        _response_text_changed = (
            _fresh_response_text
            != getattr(w, "_npc_dialog_text_prev", "")
        )
        _fresh_at_npcd = (
            _diag_resp_off == 0x1044
            and bool(_fresh_response_text)
            and _response_text_changed
        )
        if _unnatural_dyn or _fresh_at_npcd:
            _stale_list_override = True
    if _stale_list_override:
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RESPONSE_OVERRIDE_STALE_LIST "
                "img=%r prev_list=%r stale=%r dyn_count=%d "
                "resp_off=0x%X resp_text=%r",
                _img_name, _prev_list_state, _list_state,
                _item_dyn_now[1] if _item_dyn_now else -1,
                _diag_resp_off if _diag_resp_off >= 0 else 0,
                _diag_resp_text)
        _list_state = "npc_response"  # = override
    return SimpleNamespace(
        list_state=_list_state,
        prev_list_state=_prev_list_state,
        item_dyn_now=_item_dyn_now,
        diag_resp_off=_diag_resp_off,
        diag_resp_text=_diag_resp_text,
        diag_changed=_diag_changed,
        fresh_response_text=_fresh_response_text,
        response_lookup_hit=_response_lookup_hit,
        response_is_new=_response_is_new,
        state_transition_to_response=_state_transition_to_response,
    )


def _render_popup11_substate(w, _img_name, sub):
    """② POPUP11 sub-state 描画 (軸A・view 消費・内部再判定なし)。

    _classify_popup11_substate の判定結果を消費し、対応する _show_*() と
    latch (_popup11_list_state_prev / _npc_dialog_text_prev) 更新のみを行う。
    """
    _list_state = sub.list_state
    _prev_list_state = sub.prev_list_state
    _item_dyn_now = sub.item_dyn_now
    _diag_resp_off = sub.diag_resp_off
    _diag_resp_text = sub.diag_resp_text
    _diag_changed = sub.diag_changed
    _fresh_response_text = sub.fresh_response_text
    _response_lookup_hit = sub.response_lookup_hit
    _response_is_new = sub.response_is_new
    _state_transition_to_response = sub.state_transition_to_response

    # 分岐順序: _list_state がリスト状態 (rumor_type /
    # where_is_list / dynamic_place_list) のときは無条件でリスト表示を
    # 優先する。これは _response_lookup_hit が「+0x929E / +0x1044 /
    # +0x9A9E のメモリ残留応答テキスト」を拾って True になっても、ゲーム
    # 側で現在表示中のリスト表示を阻害しないため。
    # _response_lookup_hit / _response_is_new 判定は _list_state ==
    # "npc_response" のときのみ意味を持つ。
    # ask_about_main_recovery は応答後 ASK_ABOUT_MAIN 復帰中で、
    # list 表示をスキップして ASK ABOUT? 検出経路に処理を委ねる。
    if _list_state == _ASK_ABOUT_MAIN_RECOVERY_STATE:
        # ASK_ABOUT_MAIN 復帰中: 残置 dynamic_place_list を表示せず、
        # この NPC 会話 L4 内で ASK ABOUT? main を確定表示する。
        # 後段の ASK ABOUT? 検出だけに委ねると、0xA844 が変化しない
        # poll で再発火せず、直前の場所一覧が残る。
        if _diag_changed:
            _log.info(
                "cap162 diag: branch=ASK_MAIN_RECOVERY "
                "img=%r prev_list=%r item_dyn=%r resp_off=0x%X resp_text=%r",
                _img_name, _prev_list_state, _item_dyn_now,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        _render_ask_about_main_recovery(w, _prev_list_state)
    elif _list_state == "rumor_type":
        # Rumor Type サブメニュー: _show_ask_about_menu 側で content
        # 検出して build_panel_display_sub を呼ぶ。
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RUMOR_TYPE "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "rumor_type":
            w._img_screen._show_ask_about_menu()
        w._popup11_list_state_prev = "rumor_type"
    elif _list_state == "where_is_list":
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=WHERE_IS_LIST "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "where_is_list":
            w._img_screen._show_where_is_list()
        w._popup11_list_state_prev = "where_is_list"
    elif _list_state == "dynamic_place_list":
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=DYNAMIC_PLACE_LIST "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        if _prev_list_state != "dynamic_place_list":
            w._img_screen._show_dynamic_place_list()
        w._popup11_list_state_prev = "dynamic_place_list"
    elif _response_lookup_hit:
        # lookup ヒット = 確実に NPC 応答テキスト → 状態として latch する。
        # 同一テキストが継続している間は再描画を状態遷移時のみに限定する。
        # latch は POPUP11 離脱で外れる (上の _popup11_list_state_prev =
        # "" リセットによって)。
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=RESPONSE_LOOKUP_HIT "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        _needs_redraw = (
            _fresh_response_text != w._npc_dialog_text_prev
            or _prev_list_state != "npc_response"
        )
        if _needs_redraw:
            w._npc_dialog_text_prev = _fresh_response_text
            w._img_screen._show_npc_dialog(text_override=_fresh_response_text)
        w._popup11_list_state_prev = "npc_response"
    elif _response_is_new or _state_transition_to_response:
        # lookup ミスだが応答テキストっぽい候補が新着 or 状態遷移。
        # 確認済み NPC 文脈 (POPUP11.IMG 表示中、または直前 list_state
        # が NPC 応答系で latch されている) でない場合は、未登録応答
        # を翻訳 UI に出さない。未確認 .CIF が `_npc_popup_active`
        # に巻き込まれた際の誤上書きを防ぐ defense-in-depth。
        _confirmed_npc_context = (
            _img_name == "POPUP11.IMG"
            or _prev_list_state in (
                "npc_response", "rumor_type",
                "where_is_list", "dynamic_place_list",
            )
        )
        if _confirmed_npc_context:
            if _diag_changed:
                _log.info(
                    "cap159 diag: branch=RESPONSE_NEW_CONFIRMED "
                    "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                    _img_name, _list_state, _prev_list_state,
                    _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
            if _fresh_response_text:
                w._npc_dialog_text_prev = _fresh_response_text
            w._popup11_list_state_prev = "npc_response"
            w._img_screen._show_npc_dialog(text_override=_fresh_response_text)
        else:
            if _diag_changed:
                _log.info(
                    "cap159 diag: branch=RESPONSE_NEW_UNCONFIRMED "
                    "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                    _img_name, _list_state, _prev_list_state,
                    _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
            _log.debug(
                "NPC response lookup miss in unconfirmed context "
                "(img=%r prev=%r) - skip display: %r",
                _img_name, _prev_list_state, _fresh_response_text[:48])
    else:
        if _diag_changed:
            _log.info(
                "cap159 diag: branch=FALLBACK_NPC_RESPONSE "
                "img=%r list_state=%r prev_list=%r resp_off=0x%X resp_text=%r",
                _img_name, _list_state, _prev_list_state,
                _diag_resp_off if _diag_resp_off >= 0 else 0, _diag_resp_text)
        # 既に同一応答状態 → なにもしない
        w._popup11_list_state_prev = "npc_response"


def _poll_npc_conversation_foreground(
        w, _img_name, _shop_menu_visible, _shop_buy_active,
        _npc_popup_active, _list_state_eligible, _npc_detection_allowed):
    """② NPC会話 前景サーフェスの単一軸ディスパッチ (V6 真1軸化 Inc2/Inc3)。

    軸A(POPUP11 list_state) と 旧軸B(ASK ABOUT? メニュー検出) を単一の
    判定→描画へ統合する。両者が別経路で同 owner を描画し相互排他
    ガード (blocks_ask_about_main / ask_about_main_display_allowed) を要した状態
    (=1軸化未達) を解消し、優先順の制御フロー構造で「1 poll 1 描画」を
    保証する。

    優先順 (旧挺動の再現): ASK ABOUT? メニューが復帰条件を満たす poll では
    メニューを描画し、それ以外は軸A sub-state を描画する。旧コードは軸A描画
    →軸Bメニュー上書き の順で、メニューが出る poll では軸Aの応答描画が無駄に
    先行していた (= .CIF 復帰時に直前応答が一瞬残るチラツキ / recovery の
    メニュー二重描画)。単一軸化でこの無駄な先行描画を排除する
    (= cross-poll チラツキ解消・behavior-changing・要実機)。
    """
    # 軸A 判定 (描画はまだ行わない=純判定)。bookkeeping (ask_recovery /
    # item_dyn_prev / cap159_diag) は現挺動どおり classify 内で更新される。
    _sub = (_classify_popup11_substate(w, _img_name, _list_state_eligible)
            if _npc_popup_active else None)
    # 軸A が描画する sub-state = render 後の _popup11_list_state_prev の予測値。
    _predicted_lsp = (
        _sub.list_state if _sub is not None
        else getattr(w, "_popup11_list_state_prev", ""))

    # ASK ABOUT? メニュー検出 (city_npc_active == 0x4385)。fragile な
    # メモリ読取を try に隔離する (旧軸B 全体の try/except を踏襲=読取
    # 失敗時は ASK ABOUT? 検出/終了クリアをスキップ)。
    _ok = True
    _city_npc = -1
    try:
        from screen_detector import CITY_NPC_ACTIVE_OFFSET, _read_u16_le
        _city_npc = _read_u16_le(
            w._analyzer, w._anchor + CITY_NPC_ACTIVE_OFFSET)
    except Exception:  # noqa: BLE001
        _ok = False

    _ask_about_active = False
    _cur_ptr = -1
    _ptr_changed = False
    _blocking = False
    _fire = False
    _skip = False
    if _ok:
        # 宿屋系 popup が active な間は
        # ASK ABOUT? 検出を block (city_npc 残置値でタブ上書きを防ぐ)。
        _ask_about_active = (
            _city_npc == 0x4385
            and _npc_detection_allowed
            and not _shop_menu_visible
            and not _shop_buy_active
        )
        if _ask_about_active:
            try:
                _ptr_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
                _cur_ptr = _ptr_raw[0] | (_ptr_raw[1] << 8)
            except (OSError, AttributeError, IndexError):
                _cur_ptr = -1
        _ptr_changed = (
            _ask_about_active
            and _cur_ptr != getattr(w, "_ask_about_current_ptr_prev", -1))
        # メニュー再描画の復帰条件 (初回 fire / exit pending / 0xA844 ptr 変化)。
        _refire = (
            not w._ask_about_menu_active_prev
            or getattr(w, "_popup11_exit_pending_ask_about", False)
            or _ptr_changed)
        # 軸A sub-state がリスト/応答を前景に持つ間は ASK ABOUT? main で
        # 上書きしない (旧 cross-axis ガードを単一軸の優先順へ組み込み)。
        _blocking = blocks_ask_about_main(_predicted_lsp)
        _allowed = ask_about_main_display_allowed(
            _predicted_lsp, _img_name, _cur_ptr)
        _fire = _ask_about_active and _refire and _allowed
        _skip = _ask_about_active and _refire and not _allowed

    # ----- 単一軸 描画: ASK ABOUT? メニュー優先 / さもなくば軸A sub-state -----
    if _fire:
        # 旧軸B: メニュー描画 + blocking sub の latch クリア。軸A の応答描画
        # (無駄な先行) はここでは行わない (= チラツキ解消)。
        if _blocking:
            w._popup11_list_state_prev = ""
        elif _sub is not None:
            # 非 blocking sub (recovery / rumor) の latch を維持
            # (旧: 軸A render が設定済み)。
            w._popup11_list_state_prev = _predicted_lsp
        w._img_screen._show_ask_about_menu()
        w._popup11_exit_pending_ask_about = False
    elif _npc_popup_active:
        _render_popup11_substate(w, _img_name, _sub)
    if _skip:
        _log.info(
            "cap160 diag: ASK_ABOUT_SKIP "
            "(list_state=%r img=%r ptr=0x%04X ptr_changed=%s)",
            _predicted_lsp, _img_name,
            _cur_ptr if _cur_ptr >= 0 else 0, _ptr_changed)

    if _ok:
        if _ask_about_active:
            w._ask_about_current_ptr_prev = _cur_ptr
        else:
            # ASK ABOUT? 離脱時は prev をリセット。再進入時に必ず初回 fire。
            w._ask_about_current_ptr_prev = -1
        w._ask_about_menu_active_prev = _ask_about_active

        # NPC 会話終了: city_npc_active 非0→0 で表示をクリア。
        # NPC 立絵 (FACES00.CIF) 中は screen_id が game_screen のままだが
        # on_screen_id_changed で検出できないため、メモリ状態変化で明示クリア。
        _city_npc_was_nonzero = getattr(
            w, "_city_npc_active_was_nonzero_prev", False)
        if (_current_top_level(w) == "normal-play"
                and _city_npc_was_nonzero and _city_npc == 0):
            w._img_screen._reset_npc_dialog_display()
        w._city_npc_active_was_nonzero_prev = (_city_npc != 0)


def _poll_npc_popup_display(w, _img_name, _shop_menu_visible, _shop_buy_active):
    """NPC会話 POPUP11 list-state / 応答表示 + ASK ABOUT? メニュー検出を
    poll() から純粋抽出 (de-bloat・挙動不変)。全状態は w.* に保持し、
    入力ローカル (_img_name/_shop_menu_visible/_shop_buy_active) のみ受け取る。
    """
    # POPUP11.IMG 表示中または NPC 会話中の武器 CIF 表示中の動的テキスト変化検出
    # （5Hz poll で再照合）
    # 画面遷移時クリアポリシー: 前 poll の screen_id が NPC 会話と
    # 無関係な subscreen (system_menu / equipment / spellbook 等) だった場合、
    # メモリ残置値による誤検出を防ぐため検出をスキップする。
    # 上記に加えて NPC会話状態 = True を
    # 必須条件として併用し、NPC関連検出を NPC会話状態スコープに閉じ込める。
    _NPC_DIALOG_INCOMPATIBLE_SCREENS = frozenset({
        "system_menu", "equipment", "spellbook", "spell_detail",
        "automap", "logbook", "status_page", "bonus_screen", "loading",
    })
    _prev_sid = getattr(w, "_screen_id_prev", None)
    # 1軸化: 施設会話中の通常 NPC 会話経路の抑止は
    # _npc_conversation_active(単一の真実)に委ねる。
    # _poll_update_npc_conversation_latch が施設会話 latch on
    # (_facility_active_now) の間は latch を False に保つ
    # (= 階層化の唯一の表現)。旧来あったアクティブセッション逆引きの
    # 二重の防御(= 実行時相互排他ガード = 1軸化未達シグナル)を撤去した。
    # 登録セッションは tavern/temple/equipment/mages/npc_chat/palace(常時非
    # active)のみで latch False ⟺ 4施設 active(= _facility_active_now)の
    # ため、セッション逆引きは latch 抑止と等価。npc_chat は freeze 対象外
    # で latch が立つため従来どおり NPC 検出可。
    _npc_detection_allowed = (
        _current_top_level(w) == "normal-play"
        and _prev_sid not in _NPC_DIALOG_INCOMPATIBLE_SCREENS
        and w._npc_conversation_active
    )
    # .CIF を NPC 応答継続として扱うのは、直前に POPUP11 由来の NPC
    # 文脈が latch されている (_popup11_list_state_prev が非空) 場合のみ。
    # ダンジョンイベント CIF (HAND.CIF 等) は POPUP11 を経由せずに出現
    # するため、これを NPC 応答に巻き込まないように除外する。
    _cif_continuation = (
        _img_name.endswith(".CIF")
        and _current_top_level(w) == "normal-play"
        and bool(getattr(w, "_popup11_list_state_prev", ""))
    )
    _npc_popup_active = _npc_detection_allowed and (
        _img_name == "POPUP11.IMG" or _cif_continuation
    )
    # 観測ログ: NPC 会話中なのに _npc_popup_active が False の場合の
    # 構成要素を変化時に出力 (= 街中 NPC 応答未表示の原因切分)
    try:
        if w._npc_conversation_active and not _npc_popup_active:
            _diag_b263_key = (
                _img_name,
                _npc_detection_allowed,
                _cif_continuation,
                getattr(w, "_popup11_list_state_prev", ""),
            )
            _diag_b263_prev = getattr(
                w, "_b263_npc_popup_active_diag_prev", None)
            if _diag_b263_key != _diag_b263_prev:
                w._b263_npc_popup_active_diag_prev = _diag_b263_key
                _log.info(
                    "npc_popup_active=False during npc_conv "
                    "(img=%r detect_allowed=%s cif_cont=%s "
                    "list_state_prev=%r)",
                    _img_name, _npc_detection_allowed,
                    _cif_continuation,
                    getattr(w, "_popup11_list_state_prev", ""))
    except (AttributeError, OSError):
        pass
    # POPUP11 list_state 判定 (where_is_list / dynamic_place_list) は
    # POPUP11.IMG 表示中のみ有効。.CIF 中（NPC 立絵 FACES00.CIF 等）は
    # メモリ上の `0x512B` / `0xA860` が前回 POPUP11 表示時の値を保持し
    # 続けるため、判定対象に含めると残置値で誤検出する。
    _list_state_eligible = _npc_popup_active and _img_name == "POPUP11.IMG"

    # 観測ログ: _npc_popup_active=False で応答描画ロジック未実行だが
    # 応答候補テキストが読める場合、その内容を変化時に INFO 出力する。
    # NPC 会話 ON 時のみ実行 (= 通常 poll の冗長化を避ける)。
    if (not _npc_popup_active and w._npc_conversation_active
            and _current_top_level(w) == "normal-play"):
        try:
            from popup11_response_reader import (
                read_response_candidate as _read_resp_cand_diag,
            )
            _diag_cand = _read_resp_cand_diag(w._analyzer, w._anchor)
            _diag_text = _diag_cand.text if _diag_cand else ""
            _diag_off = _diag_cand.source_offset if _diag_cand else -1
            _diag_hit = bool(
                _diag_cand and _diag_cand.lookup_hit)
            if _diag_text:
                _diag_b263_resp_key = (
                    _diag_off, _diag_hit, _diag_text[:80])
                _diag_b263_resp_prev = getattr(
                    w, "_b263_unpicked_resp_prev", None)
                if _diag_b263_resp_key != _diag_b263_resp_prev:
                    w._b263_unpicked_resp_prev = _diag_b263_resp_key
                    _log.info(
                        "unpicked response candidate "
                        "(img=%r src_off=0x%X lookup_hit=%s "
                        "text=%r)",
                        _img_name,
                        _diag_off if _diag_off >= 0 else 0,
                        _diag_hit, _diag_text[:120])
        except Exception:  # noqa: BLE001
            pass

    _poll_npc_conversation_foreground(
        w, _img_name, _shop_menu_visible, _shop_buy_active,
        _npc_popup_active, _list_state_eligible, _npc_detection_allowed)


# S3 統一ディスパッチ対象の施設名。施設会話の前景所有を
# session_manager.active_session() の単一の真実から解決する (= 施設別
# is_active() 個別追跡を経由しない 1軸ディスパッチ)。段階移行中は移行済みの
# 武具店のみを対象とし、未移行施設は従来の if/elif 経路を残す。
_UNIFIED_DISPATCH_FACILITIES = ("equipment", "mages_guild", "temple")


def _unified_facility_node(w):
    """active_session() の単一の真実から統一ディスパッチ対象の施設ノードを返す。

    対象外の施設名 / 非施設セッション (npc_chat) / active なし は None。
    poll_controller の施設分岐はこの結果を前景所有の唯一の根拠とする
    (= 施設別 is_active() フラグを経由しない 1軸化)。
    """
    try:
        active = w._session_manager.active_session()
    except AttributeError:
        return None
    name = getattr(active, "name", "") if active is not None else ""
    if name not in _UNIFIED_DISPATCH_FACILITIES:
        return None
    # 施設ノード registry は各ノード module の import 副作用で登録される。
    # facility_nodes を import して全ノードを確実に registry へ載せてから引く
    # (旧経路は分岐内の遅延 import で登録していた。統一ディスパッチでも
    # ここで明示 populate しないとランタイムで registry 未登録→None になる)。
    from session import facility_nodes  # noqa: F401
    from session.facility_node import get_facility_node
    return get_facility_node(name)


def _poll_compute_temple_gate(w, *, _temple_active_now):
    """神殿 L4 の粗い menu/popup hint (+0x8F74 ゲート) を算出する
    (poll から純抽出・挙動不変)。

    入力は _temple_active_now。出力ローカルは無い (副作用は w._temple_menu_fg/
    _temple_popup_fg/_temple_gate_stable_value/_temple_gate_stable_count の更新。
    ブロックローカル _temple_gate_now は関数内に閉じる)。
    """
    if _temple_active_now:
        try:
            from temple_dialog_reader import temple_gate_foreground
            (w._temple_menu_fg, w._temple_popup_fg,
             _temple_gate_now) = temple_gate_foreground(
                w, w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            w._temple_menu_fg = False
            w._temple_popup_fg = False
    else:
        w._temple_menu_fg = False
        w._temple_popup_fg = False
        w._temple_gate_stable_value = None
        w._temple_gate_stable_count = 0


def _poll_shared_negotiation_and_template(
        w, *,
        _shop_menu_visible, _shop_buy_active, _shop_img_name,
        _temple_active_now, _tavern_active_now, _tavern_l4_kind,
        _poll_hierarchy_area, _negot_handled, _active_tmpl_handled):
    """非施設文脈の共有 negotiation(宿泊交渉) + active_template(費用/入力/
    結果) 描画経路を poll() から純粋抽出 (de-bloat・挙動不変)。

    呼出は施設ディスパッチの非施設分岐 (`_unified_node is None and not
    _facility_tavern`) でのみ行う。施設 active 時は各施設ノードが L4 描画・
    終了時整理を処理済み。旧実装が持っていた内部の実行時相互排他ガード
    (施設/closed active 判定による pass/skip=1軸化未達のシグナル) は呼出側の
    ディスパッチ構造へ移して撤去した (挙動同一)。
    戻り値: (_negot_handled, _active_tmpl_handled) = 当 poll の共有経路
    描画結論 (店内ダイアログ単位が前 poll owner 逆算の代わりに消費する)。"""
    # 交渉ダイアログ描画モジュール (旧 NegotiationSession を解体)。
    # NEGOTBUT.IMG / YESNO.IMG が表示中の間、本文 (+0x929E / +0x987A) +
    # 固定ボタン + active prompts を翻訳パネルに描画する。
    # session_manager 排他から外したため tavern_session / temple_session
    # と並列で動作する (= L3 latch + L4 module 並列)。
    from normal_play.negotiation_module import (
        poll_negotiation as _poll_negotiation,
        cleanup_if_owner as _cleanup_negotiation,
    )
    # 宿屋・神殿・武具店・ギルドは各施設が自施設分離内で L4 描画を所有・
    # 処理済みのため、本ブロックは非施設文脈専用の共有経路として残す。
    # 神殿/武具店/ギルドは交渉を持たず、応答は各施設専用 owner
    # (temple_priest_reply / equipment_reply / mages_reply) で内製化済み
    # (= 共有 negotiation/active_template/npc_dialog への相乗りを撤廃)。
    if _shop_menu_visible:
        _negot_handled = False
        _cleanup_negotiation(w)
    else:
        _negot_handled = _poll_negotiation(
            w,
            img_name=_shop_img_name,
            top_level_state=_current_top_level(w),
        )
        if not _negot_handled:
            _cleanup_negotiation(w)

    # 直接描画テンプレ (active_template) 翻訳経路。
    # active_facility (temple / tavern / "") に基づき stale 排除
    # された candidate を選択し、入力プロンプト等を翻訳表示する。
    # negotiation_module が active な poll では active_template
    # を呼ばない (= 同一 panel への二重描画を回避)。
    from normal_play.active_template_module import (
        poll_active_template as _poll_active_template,
        cleanup_if_owner as _cleanup_active_template,
    )
    _at_active_facility = (
        "temple" if _temple_active_now
        else "tavern" if _tavern_active_now
        else ""
    )
    # 宿屋・神殿・武具店・ギルドは各施設が active_template 描画 (費用/入力/
    # 結果) を自施設分離内で所有・処理済みのため、本ブロックは非施設文脈
    # 専用の共有経路として残す。神殿は temple_cost/temple_prompt owner で
    # 内製化済み。武具店/ギルドの費用/入力 surface 細分化は実機観測後。
    if _negot_handled:
        _active_tmpl_handled = False
    else:
        _t_active_tmpl = _phase_start()
        _active_tmpl_handled = _poll_active_template(
            w,
            shop_img_name=_shop_img_name,
            shop_menu_visible=_shop_menu_visible,
            shop_buy_active=_shop_buy_active,
            active_facility=_at_active_facility,
            allow_during_shop_menu=(
                _temple_active_now or _tavern_active_now),
            tavern_l4_kind=_tavern_l4_kind,
            c_area=_poll_hierarchy_area,
        )
        _phase_record(w, "active_template", _t_active_tmpl)
    if not _active_tmpl_handled and not _negot_handled:
        _cleanup_active_template(w)
    return (_negot_handled, _active_tmpl_handled)


def _poll_facility_render_dispatch(
        w, *, _shop_state, _shop_img_name, _facility_tavern, _tview,
        _temple_active_now, _tavern_active_now, _tavern_l4_kind,
        _poll_hierarchy_area, _shop_menu_visible, _shop_buy_active):
    """施設 render の単一ディスパッチ (poll から純抽出・挙動不変)。

    統一ノード(武具店/神殿/ギルド) classify→render、宿屋 TAVERN_NODE.render、
    非施設文脈の共有 shop route + negotiation/active_template を 1軸ディスパッチ
    する。下流消費の (_negot_handled, _active_tmpl_handled,
    _shop_menu_visible, _shop_buy_active) = 当 poll の描画結論を返す
    (戻り順は caller unpack と一致)。ブロックローカル(_unified_node/
    _closed_facility_active/_uview)は関数内に閉じる。
    """
    _unified_node = _unified_facility_node(w)
    _closed_facility_active = (_unified_node is not None)
    # 神殿 L4 の粗い menu/popup hint = +0x8F74 ゲート(ヒステリシス付)を
    # facility_render の前に 1 回だけ算出し、temple_render / temple_dialog が
    # 共用する。メニュー中も gate が振動するため、
    # temple_dialog は popup_fg だけを結果前景の根拠にはしない。
    # 神殿 L4 menu/popup hint ゲート算出 (純抽出: 出力ローカルなし)
    _poll_compute_temple_gate(w, _temple_active_now=_temple_active_now)
    w._equipment_reply_polled_in_render = False
    w._equipment_reply_handled_in_render = False
    w._mages_reply_polled_in_render = False
    w._mages_reply_handled_in_render = False
    _t_facility_render = _phase_start()
    # S3 統一ディスパッチ: 移行済み施設 (武具店) は active_session() の
    # 単一の真実からノードを解決し、classify_view (1軸判定) → render
    # (view 消費) の単一経路で所有描画する。前景所有を施設別 is_active()
    # フラグから逆算しない。
    # B-2 ⑤: facility render は施設 active 時のみ negot/active_tmpl を
    # 設定するため既定値を先に置く (非active 時は下流の共有
    # negotiation/active_template ブロックが確定する。挙動中立)。
    _negot_handled = False
    _active_tmpl_handled = False
    if _unified_node is not None:
        _uview = _unified_node.classify_view(
            w, shop_state=_shop_state, shop_img_name=_shop_img_name)
        (_negot_handled, _active_tmpl_handled,
         _shop_menu_visible, _shop_buy_active) = _unified_node.render(
            w, view=_uview, shop_state=_shop_state,
            shop_img_name=_shop_img_name,
            top_level_state=_current_top_level(w))
    elif _facility_tavern:
        # 宿屋施設ノードが描画を所有する (poll_tavern_render
        # へ委譲)。返り値フラグは poll_controller 後段が参照。
        # 宿屋は classify_view の引数が施設固有 (shop_kind/shop_owner/
        # img/in_interior/facility_tavern/npc_phase) かつ MIF フォール
        # バックを含むため、統一ディスパッチへの移行は別途扱う。
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE
        (_negot_handled, _active_tmpl_handled,
         _shop_menu_visible, _shop_buy_active) = _TAVERN_NODE.render(
            w,
            view=_tview,
            shop_state=_shop_state,
            shop_img_name=_shop_img_name,
            top_level_state=_current_top_level(w),
        )
    _phase_record(w, "facility_render", _t_facility_render)
    _checkpoint(w, "facility_render")

    # 宿屋ディスパッチ 1軸化 (V2/V3): 共有 shop route + negotiation/
    # active_template は「施設 session 非active (非施設文脈)」でのみ実行
    # する。旧実装は各 helper 内部に `if _facility_tavern or
    # _closed_facility_active: return/pass` の実行時相互排他ガード
    # (= 1軸化未達のシグナル) を持っていた。本条件
    # `_unified_node is None and not _facility_tavern` は施設ディスパッチ
    # (上の if _unified_node / elif _facility_tavern) の else に相当し、
    # 旧ガードの否定 (`not _closed_facility_active and not _facility_tavern`)
    # と完全一致する。ガードをディスパッチ構造へ移して撤去し、相互排他を
    # 制御フロー構造で保証する (挙動同一)。
    if _unified_node is None and not _facility_tavern:
        # V2: 非施設文脈の宿屋 shop surface 描画も宿屋ノードが所有する
        # (dispatch 入口を node へ単一化・実装/クリーンアップは従来と同一)。
        from session.tavern_node import TAVERN_NODE as _TAVERN_NODE_NS
        (_shop_buy_active, _shop_menu_visible) = (
            _TAVERN_NODE_NS.render_no_session_shop(
                w,
                shop_state=_shop_state,
                shop_img_name=_shop_img_name,
                shop_buy_active=_shop_buy_active,
                shop_menu_visible=_shop_menu_visible,
            ))

        (_negot_handled, _active_tmpl_handled) = (
            _poll_shared_negotiation_and_template(
                w,
                _shop_menu_visible=_shop_menu_visible,
                _shop_buy_active=_shop_buy_active,
                _shop_img_name=_shop_img_name,
                _temple_active_now=_temple_active_now,
                _tavern_active_now=_tavern_active_now,
                _tavern_l4_kind=_tavern_l4_kind,
                _poll_hierarchy_area=_poll_hierarchy_area,
                _negot_handled=_negot_handled,
                _active_tmpl_handled=_active_tmpl_handled,
            ))
    return (_negot_handled, _active_tmpl_handled,
            _shop_menu_visible, _shop_buy_active)


def _poll_l4_dialog_dispatch(
        w, *, in_interior, msg_buf, npc_dialog, _npc_dialog_changed,
        _npc_phase_raw, _img_name_now, _building_entry_active,
        _entry_phase_prev, _shop_state, _shop_img_name,
        _shop_menu_visible, _shop_buy_active,
        _facility_active_now, _poll_hierarchy_area,
        _temple_active_now, _temple_just_started,
        _equipment_active_now, _equipment_just_started,
        _mages_active_now, _mages_just_started,
        _negot_handled, _active_tmpl_handled):
    """L4 (NPC会話系) 前景翻訳サーフェスの調停を poll() から純粋抽出
    (de-bloat・挙動不変)。building_entry/palace/temple/equipment/
    mages/npc_dialog/C1(dungeon) の逐次 dispatch と _entry_handled claim を
    そのまま保持する。全状態は w.* に保持し、境界を跨ぐローカルのみ受け取る。
    chargen 中の NPC バッファ翻訳は L1=chargen 系統 (poll 側で handler を
    直接呼ぶ) が担い、normal-play の L4 chain には内包しない (L1 排他)。
    戻り値: (_entry_handled, _instore_resp_handled)。"""
    from arena_bridge import (
        NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING,
        NPC_PHASE_IDLE, NPC_PHASE_ASKING,
    )
    from normal_play.building_entry_module import (
        poll_building_entry as _poll_building_entry,
    )
    # 店内 NPC overlay (rebuff / response / 依頼ダイアログ表示中) signal。
    # +0xA845 == 0x6E の依頼ダイアログ
    # 表示期間を 0x9A/0x10 固定 gate が除外していた問題に対応。
    # 0x9A/0x10 に加え、in_interior かつ MENU_RT.IMG で
    # phase が IDLE/ASKING でない期間も「店内 dialog surface」として
    # 候補走査対象にする (= 0x6E 等の今後の表示値にも整合)。
    # _building_entry_active 中は従来通り除外。
    _phase_overlay = _npc_phase_raw in (
        NPC_PHASE_BUILDING_ENTRY, NPC_PHASE_RESPONDING)
    _menu_overlay = (
        in_interior
        and _img_name_now == "MENU_RT.IMG"
        and _npc_phase_raw not in (NPC_PHASE_IDLE, NPC_PHASE_ASKING)
    )
    # shop_menu / shop_buy active 中は NPC overlay
    # ではない。+0xA845 は ptr の上位 byte で phase byte ではないため、
    # 店主メニュー中 (ptr=0x72xx) の +0xA845==0x72 を「dialog surface」と
    # 誤認していた。
    _npc_overlay_active = (
        (_phase_overlay or _menu_overlay)
        and not _building_entry_active
        and not _shop_buy_active
        and not _shop_menu_visible
    )
    _npc_overlay_active_prev = getattr(
        w, "_npc_overlay_active_prev", False)
    w._npc_overlay_active_prev = _npc_overlay_active
    # active overlay 開始エッジで現在採用 key だけリセット。
    # offset 別 text 履歴は残す (= 残留バッファを新規扱いしないため)。
    # 同一文言の再表示は current_key を下ろすことで許可する。
    if _npc_overlay_active and not _npc_overlay_active_prev:
        w._instore_resp_prev = ""
        w._instore_resp_current_key = None

    _entry_handled = _poll_building_entry(
        w,
        building_entry_active=_building_entry_active,
        entry_phase_prev=_entry_phase_prev,
        msg_buf=msg_buf,
        npc_dialog=npc_dialog,
    )

    # building_entry が claim 済の poll では palace も評価しない
    # (= 単一経路・S2-3)。palace は claim しない独立 L4 surface
    # (building_entry のみ譲る)で、_entry_handled 時は元々 no-op
    # (palace_active=False)のため gate は挙動等価。
    if not _entry_handled:
        # 宮殿 統治者会話 (L4)。他施設会話とは完全分離した独立経路で、
        # 宮殿在室中に前景テキストポインタの指す本文を翻訳表示する。
        from normal_play.palace_dialog_module import (
            poll_palace_dialog as _poll_palace_dialog,
            is_palace_interior_mif as _is_palace_interior_mif,
        )
        _palace_active = (
            in_interior
            and _is_palace_interior_mif(
                getattr(w, "_interior_mif_name", None))
        )
        _poll_palace_dialog(w, palace_active=_palace_active)

    # === 施設会話 reply の単一ディスパッチ (B-2 S2-2・1軸化) =================
    # session_manager の単一 active 相互排他により temple/equipment/mages は
    # 同時 active になり得ない。各 reply は active時のみ描画する純責務(S2-1)で
    # 非active クリーンアップは stop/context 終了エッジへ分離済。よって優先順
    # (temple context → equipment → mages) の単一 if/elif dispatch で1つだけ
    # 描画する (旧: 3ブロック逐次無条件呼び=実行時相互排他の暗黙ガードを解消)。
    # 各分岐は施設専用 reply 関数を呼ぶ=L4 物理分離は維持 (S3 統一ディスパッチ
    # と同型・dispatch 層のみ単一軸化)。
    from normal_play.temple_dialog_module import (
        poll_temple_dialog as _poll_temple_dialog,
        reset_temple_reply_on_stop as _reset_temple_reply_on_stop,
    )
    from normal_play.equipment_reply_module import (
        poll_equipment_reply as _poll_equipment_reply,
    )
    from normal_play.mages_reply_module import (
        poll_mages_reply as _poll_mages_reply,
    )
    _temple_shop_owner_now = (
        _shop_state is not None
        and getattr(_shop_state, "owner_kind", "") == "temple"
    )
    # context から hold>0 を除去。継続は TempleSession latch が担う。
    _temple_dialog_context = (_temple_active_now or _temple_shop_owner_now)
    _temple_context_prev = getattr(w, "_temple_dialog_context_prev", False)
    # context(shop_owner 含む)終了エッジで temple 応答クリーンアップ
    # (render から分離・S2-1)。
    if _temple_context_prev and not _temple_dialog_context:
        _reset_temple_reply_on_stop(w)

    # 施設 reply render は building_entry が claim 済の poll では評価しない
    # (= 単一経路・S2-3)。入店phaseと施設 active は排他のため挙動等価。
    # cleanup エッジ(上)と context_prev tracking(下)は無条件(render と分離)。
    _facility_reply_handled = False
    if not _entry_handled and _temple_dialog_context:
        _t_temple_dialog = _phase_start()
        _facility_reply_handled = _poll_temple_dialog(
            w,
            temple_active=True,
            temple_just_started=(
                _temple_just_started
                or (_temple_shop_owner_now and not _temple_context_prev)),
            img_name=_shop_img_name,
            shop_menu_visible=_shop_menu_visible,
            # +0x8F74 ゲート由来の menu/popup hint。結果表示は temple 側で
            # 本文差分または結果 edge と組み合わせて決める。
            menu_foreground=bool(getattr(w, "_temple_menu_fg", False)),
            popup_foreground=bool(getattr(w, "_temple_popup_fg", False)),
        )
        _phase_record(w, "temple_dialog", _t_temple_dialog)
    elif not _entry_handled and _equipment_active_now:
        # 武具店店主応答は武具店専用 owner equipment_reply で内製化。
        if getattr(w, "_equipment_reply_polled_in_render", False):
            _facility_reply_handled = bool(getattr(
                w, "_equipment_reply_handled_in_render", False))
        else:
            _facility_reply_handled = _poll_equipment_reply(
                w,
                equipment_active=True,
                equipment_just_started=_equipment_just_started,
                img_name=_shop_img_name,
                shop_menu_visible=_shop_menu_visible,
            )
    elif not _entry_handled and _mages_active_now:
        # ギルド応答はギルド専用 owner mages_reply で内製化。
        if getattr(w, "_mages_reply_polled_in_render", False):
            _facility_reply_handled = bool(getattr(
                w, "_mages_reply_handled_in_render", False))
        else:
            _facility_reply_handled = _poll_mages_reply(
                w,
                mages_active=True,
                mages_just_started=_mages_just_started,
                img_name=_shop_img_name,
                shop_menu_visible=_shop_menu_visible,
            )
    w._temple_dialog_context_prev = _temple_dialog_context
    if _facility_reply_handled:
        _entry_handled = True

    from normal_play.npc_dialog_module import (
        poll_npc_dialog as _poll_npc_dialog,
    )
    # 判定描画セット原則: 店内応答 (npc_dialog) は独立の判定描画
    # セット (自前 ptr probe で判定・描画)。施設の単一判定 render_owner に
    # 従属させない (= 堅牢な動作を維持。応答/割込NPC/噂応答を殺さない)。
    # 1軸化: 先行で claim 済 (_entry_handled) の poll では評価しない。
    # 旧実装は entry_handled=True で route1 描画・route2-4 とも
    # gate され純 no-op だったため、呼び出し自体の skip は等価。
    _instore_resp_handled = False
    if not _entry_handled:
        _instore_resp_handled = _poll_npc_dialog(
            w,
            entry_handled=False,
            npc_overlay_active=_npc_overlay_active,
            in_interior=in_interior,
            npc_phase_raw=_npc_phase_raw,
            shop_buy_active=_shop_buy_active,
            shop_menu_visible=_shop_menu_visible,
            facility_active_now=_facility_active_now,
            npc_dialog=npc_dialog,
            npc_dialog_changed=_npc_dialog_changed,
            c_area=_poll_hierarchy_area,
            # 当 poll の判定描画結論 (1軸化): 店内ダイアログ単位は前 poll の
            # panel_owner 逆算ではなくこれらの結論で相互排他を確定する。
            # 神殿/武具店/ギルドは応答内製化済み=session latch で全面ブロック。
            internalized_facility_active=(
                _temple_active_now or _equipment_active_now
                or _mages_active_now),
            shop_state_kind=(
                _shop_state.kind if _shop_state is not None else "none"),
            negot_handled=_negot_handled,
            active_tmpl_handled=_active_tmpl_handled,
        )
        if _instore_resp_handled:
            _entry_handled = True

    # B-4 (階層化/分離化): C1 (ダンジョン) runtime dialog は C1 専用
    # 表示単位が描画する。領域 (c_area) ディスパッチを poll 側で行い、
    # 汎用 NPC 会話経路 (npc_dialog) は C1 owner を保持しない。
    if _poll_hierarchy_area == "dungeon" and not _entry_handled:
        from normal_play.c1_runtime_dialog_module import (
            poll_c1_runtime_dialog as _poll_c1_runtime_dialog,
        )
        if _poll_c1_runtime_dialog(
                w,
                npc_dialog=npc_dialog,
                npc_dialog_changed=_npc_dialog_changed,
                facility_active_now=_facility_active_now):
            _instore_resp_handled = True
            _entry_handled = True
    return _entry_handled, _instore_resp_handled


__all__ = [
    "poll_c1_surface_dispatch",
    "blocks_ask_about_main",
    "ask_about_main_display_allowed",
]
