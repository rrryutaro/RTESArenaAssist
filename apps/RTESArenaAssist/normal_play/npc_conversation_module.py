"""② 街中NPC会話 (ASK ABOUT? / 店内 rebuff) 表示単位。

`npc_dialog_lookup` を引いて街中 NPC 会話・店内 rebuff の応答を翻訳表示する経路
(旧 npc_dialog_module 経路4 ask_about) を物理分離した単位。前段観測 context は
呼び出し側 (poll_npc_dialog orchestrator) が 1 poll 分作って渡す。

分離方針 (V6 S7): 本増分は npc_dialog_module からの純粋な物理移設で、表示 owner は
当面 "npc_dialog" のまま (`_show_npc_dialog_text` 経由) = 挙動保存。owner 分離
(npc_dialog → npc_conversation) は後続増分で、共通層の clear/preserve ゲートを
全サイト更新したうえで行う。

循環回避: 本モジュールは npc_dialog_module を module レベルで import せず、共有
ヘルパー `_show_npc_dialog_text` のみ関数ローカル import で参照する。
"""
from __future__ import annotations

import logging

from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("RTESArenaAssist")

# V6 ② 通常NPC会話 (ASK ABOUT? / 街中NPC会話 / 道案内一覧 / NPC応答) の専用
# 表示 owner。③一方向msg(dungeon_msg/arrival) や ①施設応答が共有していた
# "npc_dialog" owner から分離し、② の判定描画セットを単一 owner に閉じる
# (分離化)。共通層の clear/preserve ゲートは本 owner を npc_dialog と同等扱いに
# する (behavior-preserving)。
NPC_CONVERSATION_OWNER = "npc_conversation"


def poll_npc_conversation(
        w, ctx, *, npc_dialog: str, npc_dialog_changed: bool,
        dialog_just_opened: bool, in_interior: bool,
        facility_active_now: bool, npc_translated: bool) -> None:
    """経路 4: npc_dialog_lookup (街中 NPC 会話 / 店内 rebuff)。"""
    # 経路 3 と同じく変化 or +0xA845 立ち上がりエッジで push する。
    # 分離原則対応: 判定式から「翻訳タブ表示モード = 翻訳表示モード」を
    # 削除。翻訳表示モードへの強制復帰は描画側 (= UiRouter) で行う。
    # フォールバックマップ表示モード残留時に街路 NPC 会話応答が描画されない
    # 不具合の根本対応。
    # 上位 surface visible 抑止を facility_active_now のみに限定する。
    _route4_eligible = (
        not npc_translated and bool(npc_dialog)
        and (npc_dialog_changed or dialog_just_opened)
        and (w._npc_conversation_active or in_interior)
        and not facility_active_now
    )
    if _route4_eligible:
        try:
            import npc_dialog_lookup as _ndl
            _ndl_result = _ndl.lookup(npc_dialog)
            if _ndl_result:
                _ndl_ja_tmpl, _ndl_ph = _ndl_result
                _ndl_ja = _ndl.format_japanese(_ndl_ja_tmpl, _ndl_ph)
                # V6 ② owner 分離: 街中NPC会話の応答は専用 owner
                # "npc_conversation" で push (③一方向msg=_show_npc_dialog_text の
                # "npc_dialog" 共有から離脱)。panel_only は owner を持たない
                # パネル限定更新のため従来どおり。
                if ctx.panel_only_interior_message:
                    w._ui_router.update_panel_translation(
                        npc_dialog, _ndl_ja, speech_role="conversation")
                else:
                    w._ui_router.update_translation(
                        NPC_CONVERSATION_OWNER, npc_dialog, _ndl_ja,
                        speech_role="conversation")
                _log.info(
                    "npc_dialog message displayed "
                    "(route=ask_about panel_only=%s text=%r)",
                    ctx.panel_only_interior_message, npc_dialog)
            else:
                # 観測ログ: 経路 4 入口は通ったが lookup miss だった場合
                _log.info(
                    "route4 lookup miss "
                    "(npc_conv=%s in_interior=%s changed=%s "
                    "just_opened=%s text=%r)",
                    w._npc_conversation_active, in_interior,
                    npc_dialog_changed, dialog_just_opened,
                    npc_dialog[:120])
        except (ImportError, AttributeError):
            pass
    elif (npc_dialog
            and _current_top_level(w) == "normal-play"
            and w._npc_conversation_active):
        # 観測ログ: NPC 会話中なのに経路 4 を素通りした場合の理由
        # 判定式から panel_mode 条件を削除したため、skip 理由から除外。
        _r4_reasons = []
        if npc_translated:
            _r4_reasons.append("translated_by_route2")
        if not (npc_dialog_changed or dialog_just_opened):
            _r4_reasons.append("no_change_no_edge")
        if not (w._npc_conversation_active or in_interior):
            _r4_reasons.append("no_conv_no_interior")
        if facility_active_now:
            _r4_reasons.append("facility_active")
        if _r4_reasons:
            _route4_skip_key = (tuple(_r4_reasons), npc_dialog[:80])
            _prev_skip_key = getattr(w, "_b263_route4_skip_prev", None)
            if _route4_skip_key != _prev_skip_key:
                w._b263_route4_skip_prev = _route4_skip_key
                _log.info(
                    "route4 skipped (reasons=%s text=%r)",
                    "|".join(_r4_reasons), npc_dialog[:80])


__all__ = ["poll_npc_conversation", "NPC_CONVERSATION_OWNER"]
