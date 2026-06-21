"""normal_play/mages_reply_module.py — 魔術師ギルド L4 応答の描画オーナー。

完全分離: ギルド応答文 (呪文購入/作成/Detect/Steal の結果文・
費用文等) を、全施設共有の堅牢な応答経路 (npc_dialog_module / owner ``npc_dialog``)
への相乗りから撤廃し、ギルド専用 owner ``mages_reply`` に閉じて描画する。

神殿 (temple_dialog_module / temple_priest_reply) と同型の機構をギルド専用 owner で
複製したもの。共有してよいのは:
- (A) 純粋データ取得 / 翻訳基本処理: ``popup11_response_reader`` の応答バッファ読み
  取り (= 全施設が物理的に共有する 1 つの応答バッファ)、辞書 lookup
  (``npc_dialog_lookup``)。
- (C) UiRouter 描画シンク (``update_translation``、owner 引数)。

候補選択 (= 判定) と owner 所有は本モジュール (ギルド分離内) で完結する。surface
種別単位の細分化 (mages_cost 等) は実機観測後に行う。それまで費用文も本 owner で
表示し、共有 dispatch への非依存 (= 完全分離) を満たす。
"""
from __future__ import annotations

import logging

from popup11_response_reader import ResponseCandidate

_log = logging.getLogger("RTESArenaAssist")

REPLY_OWNER = "mages_reply"

_ALLOWED_IMGS = frozenset({
    "",
    "MENU_RT.IMG",
    "YESNO.IMG",
    "NEWPOP.IMG",
    "FACES00.CIF",
})
_RESPONSE_HOLD_POLLS = 18
_MAGES_MENU_TEXT_OFFSET = 0x6F5C
_MAGES_MENU_PTR_START = 0x6F00
_MAGES_MENU_PTR_END = 0x7040
_DETECT_MAGIC_QUOTE_PREFIX = "I can tell you if that is magical"
_DETECT_MAGIC_ALREADY_KNOWN = "You already know what that is!"
_DETECT_MAGIC_IDENTIFIED = "The item is now identified in your inventory."
_DETECT_MAGIC_RESULT_OFFSET = 0x929E


def _normalize_reply_text(text: str) -> str:
    """応答本文の改行/CR/NUL を空白へ正規化し連続空白を圧縮する（辞書照合用）。

    Arena は描画折り返しで本文中に CR/改行を挿入するため、辞書テンプレ（論理文）と
    照合するには空白を正規化する必要がある。ローカル処理（他施設に影響しない）。
    """
    s = (text or "").replace("\r", " ").replace("\n", " ").replace("\x00", " ")
    return " ".join(s.split())


def _reset_state(w) -> None:
    w._mages_reply_text_by_offset = {}
    w._mages_reply_current_key = None
    w._mages_reply_current_text = None
    w._mages_reply_baselined = False
    w._mages_reply_hold_polls = 0


def _clear_reply_owner(w) -> None:
    _reset_state(w)
    try:
        if getattr(w, "_panel_owner", "") == REPLY_OWNER:
            w._ui_router.clear_if_owner(REPLY_OWNER)
    except AttributeError:
        pass


def reset_mages_reply_state(w) -> None:
    """ギルド応答表示 state を初期化する。poll_controller / tests 用。"""
    _reset_state(w)


def _ensure_state(w) -> None:
    if not hasattr(w, "_mages_reply_text_by_offset"):
        w._mages_reply_text_by_offset = {}
    if not hasattr(w, "_mages_reply_current_key"):
        w._mages_reply_current_key = None
    if not hasattr(w, "_mages_reply_current_text"):
        w._mages_reply_current_text = None
    if not hasattr(w, "_mages_reply_baselined"):
        w._mages_reply_baselined = False
    if not hasattr(w, "_mages_reply_hold_polls"):
        w._mages_reply_hold_polls = 0


def _with_yesno_buttons(img_name: str, en: str, ja: str) -> tuple[str, str]:
    if (img_name or "").upper() != "YESNO.IMG":
        return en, ja
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile("YESNO.IMG")
    except ImportError:
        profile = None
    if not profile:
        return en, ja
    en_buttons = "  ".join(profile["buttons_en"])
    ja_buttons = "  ".join(profile["buttons_ja"])
    return f"{en_buttons}\n{en}", f"{ja_buttons}\n{ja}"


def _is_negotiation_img(img_name: str) -> bool:
    """交渉専用 IMG は mages_negotiation 側に委ねる。"""
    try:
        from negotiation_reader import get_negotiation_profile
        return get_negotiation_profile((img_name or "").upper()) is not None
    except ImportError:
        return False


def _read_detect_magic_already_known(w, current_ptr,
                                     candidates, *,
                                     force: bool = False) -> ResponseCandidate | None:
    """Detect Magic の「既に知っている」応答を 0x6F00 域から拾う。

    +0x1044 に直前の見積り文が残る一方、実表示は
    +0x6F5C の固定応答だった。現在ポインタが同じ 0x6F00 メニュー/応答
    ブロックを指し、かつ +0x1044 側に探知見積り候補が残っている時だけ
    この固定応答を前景として採用する。
    """
    if not force:
        if not (isinstance(current_ptr, int)
                and _MAGES_MENU_PTR_START <= current_ptr < _MAGES_MENU_PTR_END):
            return None
        if not any(_DETECT_MAGIC_QUOTE_PREFIX in _normalize_reply_text(c.text)
                   for c in candidates):
            return None
    try:
        raw = w._analyzer.read_bytes(
            w._anchor + _MAGES_MENU_TEXT_OFFSET, 80)
    except (OSError, AttributeError):
        return None
    text = raw.split(b"\x00", 1)[0].decode(
        "ascii", errors="replace").strip()
    if text != _DETECT_MAGIC_ALREADY_KNOWN:
        return None
    return ResponseCandidate(
        text=text, lookup_hit=True, source_offset=_MAGES_MENU_TEXT_OFFSET)


def _detect_magic_reply_kind(w, img: str) -> str:
    try:
        from mages_signals import (
            detect_magic_reply_kind_from_memory, read_signals,
        )
        sig = read_signals(w._analyzer, w._anchor)
        return detect_magic_reply_kind_from_memory(
            w._analyzer, w._anchor, img, sig)
    except Exception:  # noqa: BLE001
        return ""


def _current_mages_state(w) -> str:
    try:
        from mages_signals import classify, read_signals
        return classify(read_signals(w._analyzer, w._anchor))
    except Exception:  # noqa: BLE001
        return "unknown"


def _detect_magic_cost_candidate(candidates) -> ResponseCandidate | None:
    for c in candidates:
        if _DETECT_MAGIC_QUOTE_PREFIX in _normalize_reply_text(c.text):
            return c
    return None


def _detect_magic_result_candidate(w, candidates) -> ResponseCandidate | None:
    for c in candidates:
        if _DETECT_MAGIC_IDENTIFIED in _normalize_reply_text(c.text):
            return ResponseCandidate(
                text=_DETECT_MAGIC_IDENTIFIED,
                lookup_hit=True,
                source_offset=c.source_offset)
    try:
        raw = w._analyzer.read_bytes(w._anchor + _DETECT_MAGIC_RESULT_OFFSET, 256)
    except (OSError, AttributeError):
        raw = b""
    text = raw.decode("ascii", errors="replace")
    if _DETECT_MAGIC_IDENTIFIED in _normalize_reply_text(text):
        return ResponseCandidate(
            text=_DETECT_MAGIC_IDENTIFIED,
            lookup_hit=True,
            source_offset=_DETECT_MAGIC_RESULT_OFFSET)
    return None


def poll_mages_reply(w, *, mages_active: bool,
                     mages_just_started: bool,
                     img_name: str,
                     shop_menu_visible: bool) -> bool:
    """ギルド応答文を mages_reply owner で描画する。

    戻り値 True は、この poll でギルド応答を表示または保持したことを表す。
    """
    _ensure_state(w)
    # 分離化(B-2 S2-1): 非active時のクリーンアップ(state reset)は
    # poll_controller の施設 stop エッジ(reset_mages_reply_state)へ移設。
    # 本関数は active 時のみ描画する純責務に縮約する。
    if not mages_active:
        return False

    img = (img_name or "").upper()
    if img not in _ALLOWED_IMGS:
        return False
    detect_kind = _detect_magic_reply_kind(w, img)
    current_state = _current_mages_state(w)
    if (img == "NEWPOP.IMG" and not detect_kind
            and current_state in {
                "list", "main_menu", "buy_submenu", "steal_menu",
                "edit_effects_menu",
            }):
        _clear_reply_owner(w)
        return False
    if _is_negotiation_img(img) and not detect_kind:
        _clear_reply_owner(w)
        return False

    if mages_just_started:
        _reset_state(w)

    try:
        from popup11_response_reader import (
            candidate_contains_pointer,
            read_current_text_pointer,
            read_response_candidates_all,
        )
        import npc_dialog_lookup as _ndl
        candidates = read_response_candidates_all(w._analyzer, w._anchor)
        current_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("mages_reply response read failed")
        return False

    prev_by_offset = dict(getattr(w, "_mages_reply_text_by_offset", {}))
    baselined = bool(getattr(w, "_mages_reply_baselined", False))
    hold_polls = int(getattr(w, "_mages_reply_hold_polls", 0) or 0)

    if img == "MENU_RT.IMG" and shop_menu_visible:
        _clear_reply_owner(w)
        return False

    def _norm_hit(text: str) -> bool:
        try:
            return _ndl.lookup(_normalize_reply_text(text)) is not None
        except Exception:  # noqa: BLE001
            return False

    # 描画折り返しで CR/改行が入る応答 (例: 探知見積り) は素の lookup_hit が False に
    # なるため、正規化後の lookup でも hit 判定する。
    hits = [c for c in candidates
            if c.text and (c.lookup_hit or _norm_hit(c.text))]
    detect_known = (
        _read_detect_magic_already_known(
            w, current_ptr, candidates, force=True)
        if detect_kind == "detect_known"
        else None
    )
    detect_cost = (
        _detect_magic_cost_candidate(candidates)
        if detect_kind == "detect_cost"
        else None
    )
    detect_result = (
        _detect_magic_result_candidate(w, candidates)
        if detect_kind == "detect_result"
        else None
    )
    ptr_hits = [
        c for c in hits if candidate_contains_pointer(c, current_ptr)
    ]
    changed_hits = [
        c for c in hits
        if baselined and prev_by_offset.get(c.source_offset) != c.text
    ]

    now_by_offset = dict(prev_by_offset)
    for c in candidates:
        if c.text:
            now_by_offset[c.source_offset] = c.text
    w._mages_reply_text_by_offset = now_by_offset
    w._mages_reply_baselined = True

    if detect_result is not None:
        chosen = detect_result
        reason = "detect_result"
    elif detect_known is not None:
        chosen = detect_known
        reason = "detect_known"
    elif detect_cost is not None:
        chosen = detect_cost
        reason = "detect_cost"
    elif ptr_hits:
        chosen = ptr_hits[0]
        reason = "ptr"
    elif changed_hits:
        chosen = changed_hits[0]
        reason = "source_changed"
    else:
        current_text = getattr(w, "_mages_reply_current_text", None)
        if hold_polls > 0 and current_text:
            for c in candidates:
                if c.text == current_text:
                    chosen = c
                    reason = "hold"
                    break
            else:
                chosen = None
                reason = ""
        else:
            chosen = None
            reason = ""

    if chosen is None:
        w._mages_reply_hold_polls = 0
        if img == "MENU_RT.IMG":
            _clear_reply_owner(w)
        return False

    chosen_text = _normalize_reply_text(chosen.text)
    try:
        _r = _ndl.lookup(chosen_text)
    except Exception:  # noqa: BLE001
        _r = None
    if not _r:
        return False
    _ja_tmpl, _ph = _r
    ja = _ndl.format_japanese(_ja_tmpl, _ph)

    if reason == "detect_result":
        en_text, ja_text = chosen_text, ja
    else:
        en_text, ja_text = _with_yesno_buttons(img, chosen_text, ja)
    key = (img, chosen.source_offset, chosen.text, ja_text)
    owner_taken = (w._panel_owner != REPLY_OWNER)
    if reason == "source_changed":
        w._mages_reply_hold_polls = _RESPONSE_HOLD_POLLS
    elif reason == "hold":
        w._mages_reply_hold_polls = max(hold_polls - 1, 0)
    else:
        w._mages_reply_hold_polls = 0

    should_update = (
        key != w._mages_reply_current_key
        or (owner_taken and reason in (
            "ptr", "source_changed", "hold", "detect_known", "detect_cost",
            "detect_result"))
    )
    if should_update:
        w._mages_reply_current_key = key
        w._mages_reply_current_text = chosen.text
        w._ui_router.update_translation(
            REPLY_OWNER, en_text, ja_text, speech_role="conversation")
        _log.info(
            "mages_reply translated: src=0x%X reason=%s img=%r text=%r",
            chosen.source_offset, reason, img, chosen.text[:80])
    return True


__all__ = [
    "poll_mages_reply",
    "reset_mages_reply_state",
    "REPLY_OWNER",
]
