"""normal_play/c1_gold_drop_module.py — C1 金貨ドロップ表示単位。

死体クリック時の金貨有無メッセージ (+0x929E) の判定描画セットと、
INF 断片補完の分離関心を trigger_module から物理分離 (挙動不変)。
トリガー表示 payload 描画 (_render_trigger_entry) は trigger 表示単位の
所有のため import して使う (一方向依存)。

chargen ボーナス警告 (旧 同居関心) は L1=chargen 関心のため
`top_level.chargen_state._poll_bonus_warning` へ移設 (L1 跨ぎの解消)。
"""
from __future__ import annotations

import logging
import re as _re

import inf_text_lookup as itl
from top_level.top_level_dispatcher import current_state as _current_top_level
from normal_play.trigger_module import _render_trigger_entry

_log = logging.getLogger("RTESArenaAssist")

_GOLD_DROP_RE = _re.compile(r"^You have found \d+ gold pieces?!!?")
_INF_FRAG_EXCLUDE_RE = _re.compile(
    r"^(You have found |You open door |Bag of \d+ gold pieces)",
    _re.IGNORECASE,
)


def _poll_gold_inf_fragment(w, b131_str: str, inf_name: str,
                            mif_name: str) -> None:
    """+0x929E が gold 形式でない変化を INF テキスト断片として補完する別関心処理。

    gold-drop とは別関心 (トリガーバナーの断片を INF lookup で補完) で、従来
    poll_gold_drop の elif に同居していたものを分離。多重 push 抑止/除外/最低長/
    NEWPOP open 中スキップ等の既存ガードはそのまま保持 (挙動不変)。
    """
    _log.debug("b131 0x929E changed but not gold-drop format: %r",
               b131_str[:64])
    _inf_fragment_pushed = getattr(w, "_b131_inf_fragment_pushed", "")
    _newpop_open_now = getattr(w, "_b32_newpop_open", False)
    try:
        _inf_excluded = bool(_INF_FRAG_EXCLUDE_RE.match(b131_str))
    except Exception:
        _inf_excluded = False

    # inf_name 不明時、MIF basename から INF 名を推定
    _inf_for_lookup = inf_name
    if not _inf_for_lookup and mif_name:
        _mif_base = mif_name.split(".")[0].upper()
        if _mif_base:
            _inf_for_lookup = f"{_mif_base}.INF"

    _skip_reason = ""
    if _inf_excluded:
        _skip_reason = "excluded by special pattern"
    elif _newpop_open_now:
        _skip_reason = "NEWPOP open"
    elif w._npc_conversation_active:
        _skip_reason = "NPC conversation active"
    elif b131_str == _inf_fragment_pushed:
        _skip_reason = "same as last pushed"
    elif len(b131_str.strip()) < 16:
        _skip_reason = "fragment too short"
    elif _current_top_level(w) != "normal-play":
        _skip_reason = "not in normal-play"
    elif not _inf_for_lookup:
        _skip_reason = "no inf_name nor mif_name to infer"

    if not _skip_reason:
        try:
            _inf_entry = itl.lookup_by_substring(_inf_for_lookup, b131_str)
        except Exception as exc:
            _inf_entry = None
            _log.debug("INF fragment lookup_by_substring error: %s", exc)
        if _inf_entry is not None:
            try:
                _render_trigger_entry(w, _inf_entry)
                w._b131_inf_fragment_pushed = b131_str
                _log.info(
                    "b131 INF fragment resolved (inf=%s, source=%s): %r",
                    _inf_entry.get("inf"), _inf_for_lookup, b131_str[:48])
            except (AttributeError, RuntimeError) as exc:
                _log.debug("INF fragment update failed: %s", exc)
        else:
            _log.debug(
                "b131 INF fragment lookup miss (inf=%s): %r",
                _inf_for_lookup, b131_str[:48])
    else:
        _log.debug(
            "b131 INF fragment fallback skipped (%s): %r",
            _skip_reason, b131_str[:48])


def poll_gold_drop(w, *, b30: dict, inf_name: str, mif_name: str,
                   c1_fg: str = "") -> None:
    # 単一前景が gold_drop 以外の C1 ダイアログ面を指す poll では gold-dialog の
    # 描画を抑止する (= 1軸)。検出 (+0x929E 読取・prev 更新) は走らせる。chargen
    # bonus / INF fragment fallback は別関心のため c1_fg ゲート対象外。
    _c1_fg_blocks_gold = bool(c1_fg and c1_fg != "gold_drop")
    try:
        _b131_raw = w._analyzer.read_bytes(w._anchor + 0x929E, 64)
        _b131_str = _b131_raw.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace")
    except (OSError, AttributeError):
        _b131_str = ""
    _b131_prev = getattr(w, "_b131_str_prev", "")
    _b131_changed = (_b131_str != _b131_prev)
    w._b131_str_prev = _b131_str

    # chargen ボーナス警告 (旧 同居関心) は chargen 系統
    # (`chargen_state._poll_bonus_warning`) が自前 prev で検出する。
    # 本単位 (normal-play C1) は gold-drop 形式のみを扱う。chargen 中の
    # 当該文言は下の elif (INF 断片) に入っても "not in normal-play" で
    # skip される (= 表示の二重化なし)。
    _b131_match = bool(_b131_str and _GOLD_DROP_RE.match(_b131_str))

    _axis = b30.get("c1_dialog_axis")
    _c1_gold_axis_active = bool(
        _axis
        and _axis.active
        and (
            _axis.a845 == 0x92
            or (
                _axis.current_ptr is not None
                and 0x929E <= _axis.current_ptr < 0x929E + 512
            )
        )
    )
    if (_b131_changed or _c1_gold_axis_active) and _b131_match:
        if (b30["in_gameplay"] and not w._npc_conversation_active
                and not _c1_fg_blocks_gold):
            import dungeon_msg_lookup as _dml131
            _b131_ja = _dml131.lookup(_b131_str)
            _log.info("b131 gold drop msg: %r -> %r", _b131_str, _b131_ja)
            if _b131_ja:
                _keep = (_b131_str, _b131_ja)
                if (_b131_changed
                        or _c1_gold_axis_active
                        and not (
                            getattr(w, "_gold_drop_keep_key", None) == _keep
                            and w._ui_router.is_owner("gold_drop"))):
                    w._gold_drop_keep_key = _keep
                    w._ui_router.update_translation(
                        "gold_drop", _b131_str, _b131_ja,
                        speech_role="situation")
        else:
            _log.info(
                "b131 gold drop matched but skipped (not-in-gameplay "
                "screen=%s img=%s top=%s): %r",
                getattr(w, "_screen_id_prev", None), b30["img_name"],
                _current_top_level(w, default="?"),
                _b131_str[:64])
    elif _b131_changed and _b131_str:
        # +0x929E が gold 形式でない変化 = INF テキスト断片の可能性。別関心
        # (トリガーバナーの断片補完) のため専用関数へ委譲。
        _poll_gold_inf_fragment(w, _b131_str, inf_name, mif_name)


__all__ = ["poll_gold_drop"]
