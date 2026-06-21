"""③ 一方向 NPC メッセージ (非ダンジョンのダンジョンメッセージ / 街到着) 表示単位。

②通常NPC会話(npc_conversation_module) と同じく、npc_dialog_module の orchestrator
から委譲される ③ 経路 (route3 dungeon_msg / route4a arrival) の判定描画を物理分離した
単位。表示 owner は専用 `NPC_MESSAGE_OWNER` ("npc_message") で、②会話(npc_conversation)・
①店内応答(npc_dialog) と共有しない (分離化)。

（ステータス表示 (位置/時刻/日付/重量/健康) は別の単一経路
 poll_controller._poll_status_template_parse → render_status・"status" owner が
 popup 開閉ゲート付きで占有するため、本モジュールでは扱わない。）

前段観測 context は呼び出し側 (poll_npc_dialog orchestrator) が 1 poll 分作って
渡す。本モジュールは npc_dialog_module を import せず、共有値は引数で受け取る
(循環回避)。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

# V6 ③ owner 分離: 一方向 NPC メッセージの専用表示 owner。共通層の
# clear/preserve ゲートは本 owner を npc_dialog と同等扱いにする
# (behavior-preserving)。
NPC_MESSAGE_OWNER = "npc_message"


def _poll_route3_dungeon_msg(
        w, ctx, *, npc_dialog: str, npc_dialog_changed: bool,
        facility_active_now: bool, c_area: str) -> bool:
    """経路 3: dungeon_msg_lookup (非ダンジョン領域の死体クリック等の
    一方向メッセージ)。

    戻り値 _npc_translated (= True のとき呼出側で instore_resp_handled も True)。

    C1 (ダンジョン) の runtime dialog は本経路では扱わない。`c_area == "dungeon"`
    のときは C1 専用表示単位 `c1_runtime_dialog_module.poll_c1_runtime_dialog`
    が poll 側の領域ディスパッチで描画する (分離化/階層化)。本経路は非ダンジョン
    領域の一方向メッセージ表示のみを担う。
    """
    # バッファ変化 or +0xA845 立ち上がりエッジで push。
    # - 変化のみだと「同一文言を再クリック」(buffer 不変だが dialog 再 open)
    #   で UI クリア後の再 push がされない。
    # - +0xA845 立ち上がりエッジ (= dialog 再 open) を OR で含めることで、
    #   同一内容の再クリックでも再 push できる。
    # - 連続 push (flicker) は依然抑止される (継続中は変化なし & エッジなし)。
    # 分離原則対応: 判定式から「翻訳タブ表示モード = 翻訳表示モード」を
    # 削除。翻訳表示モードへの強制復帰は描画側 (= UiRouter) で行う。
    # facility session active 中は経路 3 を skip。
    # ダンジョン msg は屋内施設会話と競合しない設計だが、防衛的に抑止する。
    if (npc_dialog
            and c_area != "dungeon"
            and (npc_dialog_changed or ctx.dialog_just_opened
                 or ctx.response_text_on_screen)
            and not w._npc_conversation_active
            and not facility_active_now):
        try:
            import dungeon_msg_lookup as _dml
            _npc_ja = _dml.lookup(npc_dialog)
            if _npc_ja:
                _keep = (npc_dialog, _npc_ja)
                if (npc_dialog_changed or ctx.dialog_just_opened
                        or not (
                            getattr(w, "_npc_dialog_keep_key", None)
                            == _keep
                            and w._ui_router.is_owner(NPC_MESSAGE_OWNER))):
                    w._npc_dialog_keep_key = _keep
                    # ダンジョンの出来事メッセージ = 状況説明。
                    w._ui_router.update_translation(
                        NPC_MESSAGE_OWNER, npc_dialog, _npc_ja,
                        speech_role="situation")
                _log.info(
                    "panel_owner -> npc_message "
                    "(route=dungeon_msg, text=%r)", npc_dialog)
                return True
        except (ImportError, AttributeError):
            pass
    return False


def _poll_route4a_arrival(
        w, *, npc_dialog: str, npc_dialog_changed: bool,
        dialog_just_opened: bool, facility_active_now: bool) -> bool:
    """経路 4a: 街到着ポップアップ (travel arrival)。戻り値 _npc_translated。

    屋外かつ NPC 会話 latch 非アクティブでも表示が必要なため、経路 4 の
    屋内/会話ゲートとは独立に到着本文を lookup→表示する。到着本文は
    npc_dialog buffer に入り "You have arrived in" で始まる。
    """
    _arrival_text = " ".join(npc_dialog.split()) if npc_dialog else ""
    if (_arrival_text.startswith("You have arrived in")
            and (npc_dialog_changed or dialog_just_opened)
            and not facility_active_now):
        try:
            import npc_dialog_lookup as _ndl_arr
            _arr_result = _ndl_arr.lookup(npc_dialog)
            if _arr_result:
                _arr_tmpl, _arr_ph = _arr_result
                _arr_ja = _ndl_arr.format_japanese(_arr_tmpl, _arr_ph)
                w._ui_router.update_translation(
                    NPC_MESSAGE_OWNER, npc_dialog, _arr_ja,
                    speech_role="conversation")
                _log.info(
                    "npc_message displayed "
                    "(route=arrival text=%r)", npc_dialog[:80])
                return True
        except (ImportError, AttributeError):
            pass
    return False


__all__ = [
    "NPC_MESSAGE_OWNER",
    "_poll_route3_dungeon_msg",
    "_poll_route4a_arrival",
]
