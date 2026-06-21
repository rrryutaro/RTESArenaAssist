"""normal_play/equipment_reply_module.py — 武具店 L4 店主応答の描画オーナー。

完全分離: 武具店店主の応答文 (購入/売却/修理の結果文・費用文
等) を、全施設共有の堅牢な応答経路 (npc_dialog_module / owner ``npc_dialog``) への
相乗りから撤廃し、武具店専用 owner ``equipment_reply`` に閉じて描画する。

神殿 (temple_dialog_module / temple_priest_reply) と同型の機構を武具店専用 owner で
複製したもの。共有してよいのは:
- (A) 純粋データ取得 / 翻訳基本処理: ``popup11_response_reader`` の応答バッファ読み
  取り (= 全施設が物理的に共有する 1 つの応答バッファ)、辞書 lookup
  (``npc_dialog_lookup``)。
- (C) UiRouter 描画シンク (``update_translation``、owner 引数)。

候補選択 (= 判定) と owner 所有は本モジュール (武具店分離内) で完結する。surface
種別単位の細分化 (equipment_cost 等) は実機観測後に行う。それまで費用文も本 owner
で表示し、共有 dispatch への非依存 (= 完全分離) を満たす。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

REPLY_OWNER = "equipment_reply"

_ALLOWED_IMGS = frozenset({
    "",
    "MENU_RT.IMG",
    "YESNO.IMG",
    "NEWPOP.IMG",
    "FACES00.CIF",
})
_INITIAL_HIT_IMGS = frozenset({
    "YESNO.IMG",
})
_DIALOG_HIT_IMGS = frozenset({
    "YESNO.IMG",
    "FACES00.CIF",
    "STATUS.CIF",
})
_ACTIVE_REPLY_PREFIXES = (
    "Can't you afford it?",
    "Can't you wait that long?",
    "Maybe you're not interested?",
    "Which job do you wish to inspect?",
    "Sorry, I already have my hands full.",
)
_ACTIVE_REPLY_CHOICE_PREFIXES = (
    "Can't you afford it?",
    "Can't you wait that long?",
    "Maybe you're not interested?",
)
_NEWPOP_PROMPT_PREFIXES = (
    "I can cut down the time",
    "I can cut the cost",
)
_NEWPOP_RESULT_PREFIXES = (
    "Then I'll get started",
    "Good, I'll get to it",
    "I understand. You might consider",
    "Well, if you change your mind",
)
_RESPONSE_HOLD_POLLS = 60


def _reset_state(w) -> None:
    w._equipment_reply_text_by_offset = {}
    w._equipment_reply_current_key = None
    w._equipment_reply_current_text = None
    w._equipment_reply_baselined = False
    w._equipment_reply_hold_polls = 0
    w._equipment_terminal_reply_suppressed_key = ""
    w._equipment_terminal_reply_key = ""
    w._equipment_terminal_reply_polls = 0
    w._equipment_terminal_reply_first_seen_at = None
    w._equipment_menu_return_candidate = None
    w._equipment_menu_return_stable_polls = 0


def reset_equipment_reply_state(w) -> None:
    """武具店応答表示 state を初期化する。poll_controller / tests 用。"""
    _reset_state(w)


def _ensure_state(w) -> None:
    if not hasattr(w, "_equipment_reply_text_by_offset"):
        w._equipment_reply_text_by_offset = {}
    if not hasattr(w, "_equipment_reply_current_key"):
        w._equipment_reply_current_key = None
    if not hasattr(w, "_equipment_reply_current_text"):
        w._equipment_reply_current_text = None
    if not hasattr(w, "_equipment_reply_baselined"):
        w._equipment_reply_baselined = False
    if not hasattr(w, "_equipment_reply_hold_polls"):
        w._equipment_reply_hold_polls = 0
    if not hasattr(w, "_equipment_terminal_reply_first_seen_at"):
        w._equipment_terminal_reply_first_seen_at = None


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


def _read_active_reply_candidates(analyzer, anchor: int, ndl
                                  ) -> list["ResponseCandidate"]:
    """Repair 後の active_template 応答を equipment_reply 候補として読む。"""
    try:
        from popup11_response_reader import ResponseCandidate
        from active_template_reader import read_active_template_candidates
    except ImportError:
        return []
    if ndl is None:
        return []

    out: list[ResponseCandidate] = []
    seen: set[tuple[int, str]] = set()
    try:
        cands = read_active_template_candidates(analyzer, anchor)
    except Exception:  # noqa: BLE001
        return []
    for c in cands:
        text = (getattr(c, "text", "") or "").strip()
        ptr = getattr(c, "ptr", None)
        if not text or not isinstance(ptr, int):
            continue
        if not text.startswith(_ACTIVE_REPLY_PREFIXES):
            continue
        try:
            hit = ndl.lookup(text) is not None
        except Exception:
            hit = False
        if not hit:
            continue
        key = (ptr, text)
        if key in seen:
            continue
        out.append(ResponseCandidate(
            text=text, lookup_hit=True, source_offset=ptr))
        seen.add(key)
    return out


def _terminal_reply_key(text: str) -> str:
    return " ".join((text or "").strip().split())


def _is_terminal_repair_reply_text(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if text.startswith("Your "):
        return (
            "does not need any repairing" in text
            or text.endswith(" is ready."))
    return text.startswith(_NEWPOP_RESULT_PREFIXES)


def _is_no_repair_reply_text(text: str) -> bool:
    text = (text or "").strip()
    return text.startswith("Your ") and "does not need any repairing" in text


def _is_equipment_repair_reply_text(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if text.startswith("Your ") and "repair" not in text:
        return False
    return text.startswith((
        "Your ",
        "Fixing that ",
        "Sure I could fix that ",
        "Fine. I can get it done in ",
        "Fine, I'll charge you ",
        "Then I'll get started",
        "Good, I'll get to it",
        "I understand. You might consider",
        "Well, if you change your mind",
        "Can't you afford it?",
        "Can't you wait that long?",
        "Maybe you're not interested?",
        "Which job do you wish to inspect?",
        "Sorry, I already have my hands full.",
        "I can cut down the time",
        "I can cut the cost",
    ))


def _is_terminal_reply_suppressed(w, text: str) -> bool:
    key = getattr(w, "_equipment_terminal_reply_suppressed_key", "") or ""
    return bool(key) and key == _terminal_reply_key(text)


def _clear_terminal_reply_suppression(w) -> None:
    w._equipment_terminal_reply_suppressed_key = ""


def _read_c_string(analyzer, anchor: int, offset: int,
                   maxlen: int = 96) -> str:
    try:
        raw = analyzer.read_bytes(anchor + offset, maxlen)
    except (OSError, AttributeError):
        return ""
    end = raw.find(b"\x00")
    if end == -1:
        end = len(raw)
    return raw[:end].decode("ascii", errors="replace").strip()


def _read_active_reply_choice_group(analyzer, anchor: int,
                                    start_offset: int) -> list[str]:
    """A190 の連続3行選択肢を active slot 位置から読む。"""
    first = _read_c_string(analyzer, anchor, start_offset)
    if first != _ACTIVE_REPLY_CHOICE_PREFIXES[0]:
        return []
    out: list[str] = []
    cur = start_offset
    for expected in _ACTIVE_REPLY_CHOICE_PREFIXES:
        text = _read_c_string(analyzer, anchor, cur)
        if text != expected:
            break
        out.append(text)
        cur += len(text.encode("ascii", errors="ignore")) + 1
    return out if len(out) > 1 else []


def _format_reply_choice_group(lines: list[str], ndl) -> tuple[str, str]:
    en_lines: list[str] = []
    ja_lines: list[str] = []
    for line in lines:
        en_lines.append(line)
        try:
            result = ndl.lookup(line)
        except Exception:  # noqa: BLE001
            result = None
        if result is None:
            ja_lines.append(line)
        else:
            ja_tmpl, placeholders = result
            ja_lines.append(ndl.format_japanese(ja_tmpl, placeholders))
    return "\n".join(en_lines), "\n".join(ja_lines)


def _format_reply_choice_rows(lines: list[str], ndl) -> list[dict]:
    rows: list[dict] = []
    for line in lines:
        try:
            result = ndl.lookup(line)
        except Exception:  # noqa: BLE001
            result = None
        if result is None:
            ja = line
        else:
            ja_tmpl, placeholders = result
            ja = ndl.format_japanese(ja_tmpl, placeholders)
        rows.append({"en": line, "ja": ja})
    return rows


def _menu_rt_equipment_menu_present(w) -> bool:
    """shop_state が揺れた poll でも、MENU_RT の武具店メニュー復帰を拾う。"""
    try:
        from popup11_response_reader import read_current_text_pointer
        from shop_menu_reader import (
            parse_menu_groups,
            select_menu_group_by_ptr,
            SHOP_MENU_BUFFER_OFFSET,
            SHOP_MENU_BUFFER_MAXLEN,
        )
        ptr = read_current_text_pointer(w._analyzer, w._anchor)
        raw = w._analyzer.read_bytes(
            w._anchor + SHOP_MENU_BUFFER_OFFSET,
            SHOP_MENU_BUFFER_MAXLEN)
        groups = parse_menu_groups(raw)
        group = select_menu_group_by_ptr(groups, ptr)
        if group is None:
            return False
        items = tuple(it.text for it in group.items)
        return items == ("Buy", "Sell", "Repair", "Steal", "Exit")
    except Exception:  # noqa: BLE001
        return False


def poll_equipment_reply(w, *, equipment_active: bool,
                         equipment_just_started: bool,
                         img_name: str,
                         shop_menu_visible: bool) -> bool:
    """武具店店主の応答文を equipment_reply owner で描画する。

    戻り値 True は、この poll で武具店応答を表示または保持したことを表す。
    """
    _ensure_state(w)
    # 分離化: 非active時のクリーンアップ(state reset)は
    # poll_controller の施設 stop エッジ(reset_equipment_reply_state)へ移設。
    # 本関数は active 時のみ描画する純責務に縮約する。
    if not equipment_active:
        return False

    img = (img_name or "").upper()
    if img not in _ALLOWED_IMGS:
        return False

    if equipment_just_started:
        _reset_state(w)

    try:
        from popup11_response_reader import (
            ResponseCandidate,
            candidate_contains_pointer,
            read_current_text_pointer,
            read_response_candidates_all,
        )
        import npc_dialog_lookup as _ndl
        candidates = read_response_candidates_all(w._analyzer, w._anchor)
        active_reply_candidates = _read_active_reply_candidates(
            w._analyzer, w._anchor, _ndl)
        if img == "NEWPOP.IMG" and active_reply_candidates:
            candidates = active_reply_candidates + candidates
        else:
            candidates.extend(active_reply_candidates)
        current_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("equipment_reply response read failed")
        return False

    prev_by_offset = dict(getattr(w, "_equipment_reply_text_by_offset", {}))
    baselined = bool(getattr(w, "_equipment_reply_baselined", False))
    hold_polls = int(getattr(w, "_equipment_reply_hold_polls", 0) or 0)

    hits = [c for c in candidates if c.text and c.lookup_hit]
    hits = [
        c for c in hits
        if not (_is_terminal_repair_reply_text(c.text)
                and _is_terminal_reply_suppressed(w, c.text))
    ]
    current_reply_text = getattr(w, "_equipment_reply_current_text", "") or ""
    has_unsuppressed_repair_hit = any(
        _is_equipment_repair_reply_text(c.text) for c in hits)
    if _is_terminal_reply_suppressed(w, current_reply_text):
        w._equipment_reply_current_key = None
        w._equipment_reply_current_text = None
        w._equipment_reply_hold_polls = 0
        hold_polls = 0
    newpop_prompt_hits = [
        c for c in hits
        if img == "NEWPOP.IMG"
        and (c.text or "").startswith(_NEWPOP_PROMPT_PREFIXES)
    ]
    newpop_result_hits = [
        c for c in hits
        if img == "NEWPOP.IMG"
        and (c.text or "").startswith(_NEWPOP_RESULT_PREFIXES)
    ]
    newpop_no_repair_hits = [
        c for c in hits
        if img == "NEWPOP.IMG" and _is_no_repair_reply_text(c.text)
    ]
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
    w._equipment_reply_text_by_offset = now_by_offset
    w._equipment_reply_baselined = True

    if (img == "MENU_RT.IMG"
            and (shop_menu_visible or _menu_rt_equipment_menu_present(w))
            and not (
                getattr(w, "_equipment_reply_polled_in_render", False)
                and (has_unsuppressed_repair_hit
                     or _is_terminal_repair_reply_text(current_reply_text)))):
        w._equipment_reply_hold_polls = 0
        w._equipment_reply_current_key = None
        w._equipment_reply_current_text = None
        return False
    if (shop_menu_visible
            and getattr(w, "_equipment_menu_return_override", False)):
        w._equipment_reply_hold_polls = 0
        w._equipment_reply_current_key = None
        w._equipment_reply_current_text = None
        w._equipment_menu_return_override = False
        return False

    if ptr_hits:
        chosen = ptr_hits[0]
        reason = "ptr"
    elif img == "NEWPOP.IMG" and active_reply_candidates:
        chosen = active_reply_candidates[0]
        reason = "active_reply"
    elif newpop_prompt_hits:
        chosen = newpop_prompt_hits[0]
        reason = "newpop_prompt"
    elif newpop_result_hits:
        chosen = newpop_result_hits[0]
        reason = "newpop_result"
    elif newpop_no_repair_hits:
        chosen = newpop_no_repair_hits[0]
        reason = "newpop_no_repair"
    elif changed_hits:
        chosen = changed_hits[0]
        reason = "source_changed"
    elif hits and img in _DIALOG_HIT_IMGS:
        chosen = hits[0]
        reason = "dialog_hit"
    elif hits and not baselined and img in _INITIAL_HIT_IMGS \
            and not shop_menu_visible:
        chosen = hits[0]
        reason = "initial_dialog_hit"
    else:
        current_text = getattr(w, "_equipment_reply_current_text", None)
        if hold_polls > 0 and current_text:
            for c in candidates:
                if c.text == current_text:
                    chosen = c
                    reason = "hold"
                    break
            else:
                current_key = getattr(w, "_equipment_reply_current_key", None)
                source_offset = (
                    current_key[1]
                    if isinstance(current_key, tuple)
                    and len(current_key) >= 2
                    and isinstance(current_key[1], int)
                    else 0
                )
                chosen = ResponseCandidate(
                    text=current_text,
                    lookup_hit=True,
                    source_offset=source_offset,
                )
                reason = "hold_stale"
        else:
            chosen = None
            reason = ""

    if chosen is None:
        w._equipment_reply_hold_polls = 0
        if _is_no_repair_reply_text(
                getattr(w, "_equipment_reply_current_text", "") or ""):
            w._equipment_reply_current_key = None
            w._equipment_reply_current_text = None
        return False
    if not _is_terminal_repair_reply_text(chosen.text):
        _clear_terminal_reply_suppression(w)

    try:
        _r = _ndl.lookup(chosen.text)
    except Exception:  # noqa: BLE001
        _r = None
    if not _r:
        return False
    _ja_tmpl, _ph = _r
    ja = _ndl.format_japanese(_ja_tmpl, _ph)

    choice_rows: list[dict] = []
    choice_lines = _read_active_reply_choice_group(
        w._analyzer, w._anchor, chosen.source_offset)
    if choice_lines:
        en_text, ja_text = _format_reply_choice_group(choice_lines, _ndl)
        choice_rows = _format_reply_choice_rows(choice_lines, _ndl)
    else:
        en_text, ja_text = _with_yesno_buttons(img, chosen.text, ja)
    key = (img, chosen.source_offset, chosen.text, ja_text,
           tuple((row["en"], row["ja"]) for row in choice_rows))
    owner_taken = (w._panel_owner != REPLY_OWNER)
    if reason in ("source_changed", "dialog_hit", "newpop_no_repair"):
        w._equipment_reply_hold_polls = _RESPONSE_HOLD_POLLS
    elif reason in ("hold", "hold_stale"):
        if _is_no_repair_reply_text(chosen.text):
            w._equipment_reply_hold_polls = _RESPONSE_HOLD_POLLS
        else:
            w._equipment_reply_hold_polls = max(hold_polls - 1, 0)
    else:
        w._equipment_reply_hold_polls = 0

    should_update = (
        key != w._equipment_reply_current_key
        or (owner_taken and reason in (
            "ptr", "source_changed", "active_reply", "dialog_hit",
            "newpop_prompt", "newpop_result", "hold", "hold_stale",
            "initial_dialog_hit"))
    )
    if should_update:
        w._equipment_reply_current_key = key
        w._equipment_reply_current_text = chosen.text
        if choice_rows:
            w._ui_router.update_facility_list(
                REPLY_OWNER, choice_rows, "Repair Options", "修理の選択肢")
        else:
            w._ui_router.update_translation(
                REPLY_OWNER, en_text, ja_text, speech_role="conversation")
        _log.info(
            "equipment_reply translated: src=0x%X reason=%s img=%r text=%r",
            chosen.source_offset, reason, img, chosen.text[:80])
    return True


__all__ = [
    "poll_equipment_reply",
    "reset_equipment_reply_state",
    "REPLY_OWNER",
]
