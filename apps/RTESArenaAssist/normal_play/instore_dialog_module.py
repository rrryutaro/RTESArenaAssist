"""店内ダイアログ表示単位 (NPC会話系・店主クリック割り込みNPC を含む)。

店主クリック後メニュー表示前に割り込むイベント (クエスト受注打診等) の
ダイアログメッセージや、店内の応答 (+0x929E 等の応答面) を、自前の前景
テキストポインタ probe で判定し表示する判定描画セット (route1=店内応答)。
npc_dialog_module から物理分離 (npc_conversation_module /
npc_message_module と対称)。

window 側状態: _instore_resp_text_by_offset / _instore_resp_current_key /
_instore_resp_prev / _ui_router。表示ヘルパー `_show_npc_dialog_text` のみ
関数ローカル import で参照する (owner は "npc_dialog" のまま)。

相互排他 (1軸化): 前 poll の描画結果 (panel_owner) からの逆算は持たない。
当 poll の判定描画結論 (施設 session latch / メニュー・一覧の可視 /
detector kind / negotiation・active_template の描画結論) と、前 poll の
店内 surface 種別 (`w._shop_kind_prev_poll` = 宿屋 classify 単位が所有
する poll 間履歴) で確定する。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")


# 「一覧 → 応答」の正規遷移を許可する前 poll の店内 surface 種別。
# 前 poll でメニュー/一覧が前景で、当 poll に前景テキストポインタが応答面
# を指した場合のみ応答表示へ切り替える (単なる残留 response buffer では
# 発火しない)。
_SHOP_SURFACE_KINDS = (
    "shop_menu", "shop_buy", "shop_rooms", "shop_rumor_type",
)


def _poll_route1_instore_response(
        w, ctx, *, entry_handled: bool, npc_overlay_active: bool,
        in_interior: bool, npc_phase_raw, facility_active_now: bool,
        instore_resp_handled: bool,
        internalized_facility_active: bool = False,
        shop_menu_visible: bool = False,
        shop_buy_active: bool = False,
        shop_state_kind: str = "none",
        negot_handled: bool = False,
        active_tmpl_handled: bool = False):
    """経路 1: 店内 NPC 応答 (+0x929E 等)。

    戻り値: (instore_resp_handled, entry_handled)。
    """
    # 分離原則対応: 判定式から「翻訳タブ表示モード = 翻訳表示モード」を削除。
    # 翻訳表示モードへの強制復帰は描画側 (= UiRouter.update_translation) で行う。
    #
    # 相互排他の確定 (1軸化): 旧実装は前 poll の panel_owner を L4 owner
    # 集合と照合する逆算 (実行時相互排他ガード) だった。当 poll の判定描画
    # 結論で確定する:
    #   - 神殿/武具店/ギルドは応答を内製化済み (dedicated owner) のため、
    #     session active (単一の真実 latch) 中は本経路を全面 skip する。
    #   - 宿屋系 surface (メニュー/一覧/negotiation/active_template) が
    #     当 poll に描画されている間は skip する (= 描画中の侵食防止)。
    #   - 宿屋 Rumors 応答や酒応答は誰も内製化していないため
    #     full block にせず、上記 surface 非描画の poll で本経路が描画する。
    _l4_surface_now = (
        internalized_facility_active
        or shop_menu_visible
        or shop_buy_active
        or shop_state_kind in _SHOP_SURFACE_KINDS
        or negot_handled
        or active_tmpl_handled
    )

    _response_probe_done = False
    _response_cands = []
    _response_current_ptr = None
    _contains_pointer = lambda _candidate, _ptr: False

    def _read_response_probe():
        nonlocal _response_probe_done
        nonlocal _response_cands
        nonlocal _response_current_ptr
        nonlocal _contains_pointer
        if _response_probe_done:
            return (_response_cands, _response_current_ptr,
                    _contains_pointer)
        _response_probe_done = True
        try:
            from popup11_response_reader import (
                candidate_contains_pointer,
                read_current_text_pointer,
                read_response_candidates_all,
            )
        except Exception:  # noqa: BLE001
            return (_response_cands, _response_current_ptr,
                    _contains_pointer)
        _contains_pointer = candidate_contains_pointer
        try:
            _response_cands = read_response_candidates_all(
                w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            _response_cands = []
        try:
            _response_current_ptr = read_current_text_pointer(
                w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            _response_current_ptr = None
        return (_response_cands, _response_current_ptr, _contains_pointer)

    def _has_visible_response_hit() -> bool:
        _cands_probe, _ptr_probe, _contains = _read_response_probe()
        return any(
            c.text and c.lookup_hit and _contains(c, _ptr_probe)
            for c in _cands_probe
        )

    # 「一覧 → 応答」の正規遷移: 前 poll の店内 surface 種別 (宿屋 classify
    # 単位が所有する poll 間履歴 `_shop_kind_prev_poll`) がメニュー/一覧で、
    # 当 poll の前景テキストポインタが応答面の候補を指す場合のみ発火する。
    _prev_poll_shop_kind = getattr(w, "_shop_kind_prev_poll", "none")
    _facility_response_override = (
        not entry_handled
        and in_interior
        and facility_active_now
        and _prev_poll_shop_kind in _SHOP_SURFACE_KINDS
        and _has_visible_response_hit()
    )
    _route1_active = npc_overlay_active or _facility_response_override
    # 判定描画セット原則: 店内応答 (npc_dialog) は自前の ptr probe で
    # 「応答が前景か」を判定し自身で描画する独立の判定描画セット。施設の単一判定
    # (render_owner) に従属させると、その判定の誤りが応答描画を殺す。相互排他は
    # 当 poll の判定描画結論 (_l4_surface_now) で構造確定する (前 poll の
    # panel_owner 逆算は持たない=1軸化)。
    _route1_surface_allowed = (
        not _l4_surface_now or _facility_response_override)

    if (not entry_handled and _route1_active and in_interior
            and _route1_surface_allowed):
        _cands, _current_ptr, candidate_contains_pointer = (
            _read_response_probe())

        _hits = [c for c in _cands if c.lookup_hit and c.text]
        _text_by_offset = dict(
            getattr(w, "_instore_resp_text_by_offset", {}))
        _changed_hits = [
            c for c in _hits
            if _text_by_offset.get(c.source_offset) != c.text
        ]
        for c in _cands:
            if c.text:
                _text_by_offset[c.source_offset] = c.text
        w._instore_resp_text_by_offset = _text_by_offset

        _ptr_cands = [
            c for c in _cands
            if c.text and candidate_contains_pointer(c, _current_ptr)
        ]
        _ptr_hits = [c for c in _ptr_cands if c.lookup_hit]

        if _ptr_hits:
            _chosen = _ptr_hits[0]
            _chosen_reason = (
                "ptr_surface_override"
                if _facility_response_override and _l4_surface_now
                else "ptr"
            )
        elif _changed_hits:
            _chosen = _changed_hits[0]
            _chosen_reason = "source_changed"
        else:
            _chosen = None
            _chosen_reason = ""

        _ptr_miss_cands = [c for c in _ptr_cands if not c.lookup_hit]
        if _ptr_miss_cands:
            for c in _ptr_miss_cands:
                try:
                    raw_head = w._analyzer.read_bytes(
                        w._anchor + c.source_offset, 128)
                    _raw_hex = raw_head.hex()
                except (OSError, AttributeError):
                    _raw_hex = "<read err>"
                _log.debug(
                    "in_store_resp ptr_match lookup miss "
                    "(src=0x%X ptr=0x%04X text=%r raw=%s)",
                    c.source_offset, _current_ptr or 0,
                    c.text[:120], _raw_hex)

        _chosen_key = ((_chosen.source_offset, _chosen.text)
                       if _chosen is not None else None)
        _current_key = getattr(w, "_instore_resp_current_key", None)

        if _chosen is not None and _chosen_key != _current_key:
            w._instore_resp_current_key = _chosen_key
            w._instore_resp_prev = _chosen.text
            try:
                from normal_play.npc_dialog_module import (
                    _show_npc_dialog_text,
                )
                import npc_dialog_lookup as _ndl_msg
                _ndl_result = _ndl_msg.lookup(_chosen.text)
                if _ndl_result:
                    _ndl_ja_tmpl, _ndl_ph = _ndl_result
                    _ndl_ja = _ndl_msg.format_japanese(
                        _ndl_ja_tmpl, _ndl_ph)
                    _show_npc_dialog_text(
                        w, _chosen.text, _ndl_ja,
                        panel_only=ctx.panel_only_interior_message)
                    instore_resp_handled = True
                    entry_handled = True
                    _log.info(
                        "npc_dialog message displayed "
                        "(route=in_store_resp src=0x%X reason=%s "
                        "panel_only=%s ptr=%s text=%r ph=%s)",
                        _chosen.source_offset, _chosen_reason,
                        ctx.panel_only_interior_message,
                        f"0x{_current_ptr:04X}"
                        if _current_ptr is not None else "?",
                        _chosen.text[:80], _ndl_ph)
            except (ImportError, AttributeError):
                pass
        elif _chosen is not None:
            _log.debug(
                "in_store_resp held "
                "(src=0x%X reason=%s ptr=%s text=%r)",
                _chosen.source_offset, _chosen_reason,
                f"0x{_current_ptr:04X}"
                if _current_ptr is not None else "?",
                _chosen.text[:60])
        elif not _cands:
            _log.debug(
                "in_store_resp no candidate "
                "(phase=0x%s overlay=%s in_interior=%s)",
                f"{npc_phase_raw:02X}" if npc_phase_raw is not None
                else "??",
                npc_overlay_active, in_interior)
        else:
            _summary = ", ".join(
                f"0x{c.source_offset:X}:hit={c.lookup_hit} "
                f"changed={c in _changed_hits} "
                f"ptr_match={candidate_contains_pointer(c, _current_ptr)} "
                f"text={c.text[:60]!r}"
                for c in _cands
            )
            _log.debug(
                "in_store_resp no display candidate (ptr=%s %s)",
                f"0x{_current_ptr:04X}" if _current_ptr is not None
                else "?",
                _summary)
    elif in_interior:
        if not npc_overlay_active:
            pass
        elif entry_handled:
            _log.debug(
                "in_store_resp skipped: _entry_handled=True (phase=0x%s)",
                f"{npc_phase_raw:02X}" if npc_phase_raw is not None
                else "??")

    return instore_resp_handled, entry_handled


__all__ = [
    "_poll_route1_instore_response",
]
