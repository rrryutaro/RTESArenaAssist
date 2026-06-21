"""NPC dialog 系翻訳経路 (店内応答 / 状況 / ダンジョン msg / 街中 NPC 会話)。

NPC overlay 状態 (+0xA845 = 0x9A or 0x10) で動く NPC ダイアログ翻訳を
集約する。session 単独に紐づかない (= NpcChatSession の ASKING scope 外で
動く経路を含む) ため、normal_play module として独立配置する。

window 側状態: _instore_resp_text_by_offset / _instore_resp_current_key /
_instore_resp_prev / _ui_router / _panel_owner

呼び出し側は precomputed gates を渡す。

構成 (de-bloat): thin orchestrator `poll_npc_dialog` が前段観測 (`_build_dialog_context`)
を1回作り、4経路のルートヘルパーへ順に委譲する。各ヘルパーは挙動保存の純粋抽出で、
共有値 (前段観測 / panel-only 判定) は context 経由で受け渡す。経路間の単一軸化・
階層別ノード分離 (V6) は後続増分。
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.npc_conversation_module import poll_npc_conversation
# V6 ③ 物理分離: 一方向 NPC メッセージ (状況/非ダンジョンのダンジョンメッセージ/
# 街到着) の経路 helper と専用 owner 定数は npc_message_module へ分離。orchestrator
# は import で委譲する (②=npc_conversation_module と対称)。
from normal_play.npc_message_module import (
    NPC_MESSAGE_OWNER,
    _poll_route3_dungeon_msg,
    _poll_route4a_arrival,
)
# V6 ④ 物理分離: 店内ダイアログ (店主クリック割込クエスト打診を含む
# route1=店内応答) の判定描画セットは instore_dialog_module へ分離。
# orchestrator は import で委譲する (②③ と対称)。
from normal_play.instore_dialog_module import (
    _poll_route1_instore_response,
)

_log = logging.getLogger("RTESArenaAssist")

def _build_dialog_context(w, *, in_interior, facility_active_now):
    """各経路が共有する 1 poll 分の前段観測値を作る。

    Route 3 / Route 4 の push トリガ:
      - npc_dialog バッファ変化 (新規ダイアログ open / 内容更新), OR
      - +0xA845 (dialog active flag) の立ち上がりエッジ (0 → non-0)
        = 同一内容を再クリックした場合の再 push 用 (buffer 不変だが
          dialog は再 open されたケース)。
    立ち上がりエッジ判定は `_b30_dialog_active_prev` を参照する。本フラグは
    compute_b30_state (poll_npc_dialog より後段) が毎ポーリング末尾で更新する
    ため、poll_npc_dialog 入口での値は前ポーリングの観測値となる。

    C1 (ダンジョン) 軸の読み取りは本経路では行わない。C1 ダンジョン runtime
    dialog は `c1_runtime_dialog_module` に分離され、領域ディスパッチで poll 側
    から駆動される (分離化/階層化)。
    """
    # +0xA845 dialog_active 立ち上がりエッジ検出
    try:
        _dialog_byte = w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        _dialog_byte = 0x00
    _dialog_active_now = (_dialog_byte != 0x00)
    _dialog_active_prev = getattr(w, "_b30_dialog_active_prev", False)
    _dialog_just_opened = (_dialog_active_now and not _dialog_active_prev)
    try:
        _fg_raw = w._analyzer.read_bytes(w._anchor + 0xA844, 2)
        _fg_ptr = _fg_raw[0] | (_fg_raw[1] << 8)
        try:
            from active_template_reader import (
                is_response_text_buffer_pointer,
            )
            _response_text_on_screen = (
                _dialog_active_now
                and is_response_text_buffer_pointer(_fg_ptr)
            )
        except Exception:  # noqa: BLE001
            _response_text_on_screen = (
                _dialog_active_now
                and any(start <= _fg_ptr < start + length
                        for start, length in (
                            (0x1044, 512),
                            (0x929E, 512),
                            (0x9A9E, 512),
                        ))
            )
    except (OSError, AttributeError):
        _response_text_on_screen = False

    _panel_only_interior_message = (
        in_interior
        and not facility_active_now
        and not bool(getattr(w, "_npc_conversation_active", False))
    )

    return SimpleNamespace(
        dialog_just_opened=_dialog_just_opened,
        response_text_on_screen=_response_text_on_screen,
        panel_only_interior_message=_panel_only_interior_message,
    )


def _show_npc_dialog_text(w, en: str, ja: str, *, panel_only: bool) -> None:
    """会話セッション外の店内単発台詞は翻訳パネルだけ更新する。

    パネル限定でも店内の台詞は会話として読み上げを宣言する
    (タブ併記版と同じ内容なので役割も揃える)。
    """
    if panel_only:
        w._ui_router.update_panel_translation(
            en, ja, speech_role="conversation")
    else:
        w._ui_router.update_translation(
            "npc_dialog", en, ja, speech_role="conversation")


def poll_npc_dialog(w, *, entry_handled: bool,
                    npc_overlay_active: bool, in_interior: bool,
                    npc_phase_raw,
                    shop_buy_active: bool,
                    shop_menu_visible: bool,
                    facility_active_now: bool,
                    npc_dialog: str,
                    npc_dialog_changed: bool = True,
                    c_area: str = "",
                    internalized_facility_active: bool = False,
                    shop_state_kind: str = "none",
                    negot_handled: bool = False,
                    active_tmpl_handled: bool = False) -> bool:
    """戻り値: instore_resp_handled (= 下流の a845 close skip 判定用)。

    4経路 (店内応答 / 状況 / ダンジョン msg / 街中 NPC 会話) のルートヘルパーへ
    委譲する thin orchestrator。前段観測 (`_build_dialog_context`) を1回作り、
    経路1の結果 (entry_handled) で経路2-4 の実行可否を決める。経路2-4 (status /
    dungeon_msg / arrival / ask_about) は **優先順の単一軸 if/elif/else** で
    「最初に成立した1経路だけが翻訳する」ことを制御フロー構造で保証する
    (相互排他フラグを使わない=1軸化)。
    """
    ctx = _build_dialog_context(
        w, in_interior=in_interior,
        facility_active_now=facility_active_now)

    instore_resp_handled = False

    # =============== 経路 1: 店内 NPC 応答 (+0x929E 等) =====================
    instore_resp_handled, entry_handled = _poll_route1_instore_response(
        w, ctx,
        entry_handled=entry_handled,
        npc_overlay_active=npc_overlay_active,
        in_interior=in_interior,
        npc_phase_raw=npc_phase_raw,
        facility_active_now=facility_active_now,
        instore_resp_handled=instore_resp_handled,
        internalized_facility_active=internalized_facility_active,
        shop_menu_visible=shop_menu_visible,
        shop_buy_active=shop_buy_active,
        shop_state_kind=shop_state_kind,
        negot_handled=negot_handled,
        active_tmpl_handled=active_tmpl_handled)

    # =============== 経路 3-4: dungeon_msg / arrival / 街中NPC会話 ==========
    # 単一軸 (1軸化): NPC dialog バッファ翻訳は優先順
    #   経路3 dungeon_msg → 経路4a arrival → 経路4 街中NPC会話
    # で「最初に成立した1経路」だけが翻訳する。if/elif/else の制御フロー構造で
    # 同時に複数経路が翻訳する余地を構造的に無くす。
    # ステータス表示（位置/時刻/日付/重量/健康のポップアップ）は別の単一経路
    # （poll_controller._poll_status_template_parse → render_status・"status" owner・
    # popup 開閉ゲート付きで占有・閉じたらクリア）が担うため、本 orchestrator では
    # 扱わない（旧 route2 status を撤去＝二重経路を解消し 1軸化）。
    if (not entry_handled
            and _current_top_level(w) == "normal-play"
            and not shop_buy_active
            and not shop_menu_visible):
        if _poll_route3_dungeon_msg(
                w, ctx,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                facility_active_now=facility_active_now,
                c_area=c_area):
            # 経路 3: dungeon_msg_lookup は instore_resp_handled も立てる
            instore_resp_handled = True
        elif _poll_route4a_arrival(
                w,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                dialog_just_opened=ctx.dialog_just_opened,
                facility_active_now=facility_active_now):
            # 経路 4a: 街到着ポップアップ (travel arrival) が翻訳
            pass
        else:
            # 経路 4 (② 街中NPC会話): npc_conversation_module へ物理分離
            # (V6 S7)。ここに到達するのは経路2/3/4a が翻訳しなかった poll のみ
            # のため、旧 `npc_translated` 引数は常に False と等価。
            poll_npc_conversation(
                w, ctx,
                npc_dialog=npc_dialog,
                npc_dialog_changed=npc_dialog_changed,
                dialog_just_opened=ctx.dialog_just_opened,
                in_interior=in_interior,
                facility_active_now=facility_active_now,
                npc_translated=False)

    return instore_resp_handled


__all__ = ["poll_npc_dialog", "NPC_MESSAGE_OWNER"]
