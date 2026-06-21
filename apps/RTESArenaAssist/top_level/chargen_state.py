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

OFF_DIALOG_FLAG       = 0xB7C4
OFF_NPC_PHASE         = 0xA845
OFF_NPC_PHASE_LEN     = 3
OFF_AUX_OBS_1         = 0x8F6E
OFF_AUX_OBS_2         = 0x8F74
OFF_AUX_OBS_3         = 0x8F7A
OFF_AUX_OBS_FAEA      = 0xFAEA
OFF_BONUS_PTS         = 0x129C
OFF_BONUS_WARN_BUF    = 0x929E
OFF_RACE_CHARGEN      = 0x214
OFF_RACE_PLAY         = 0x1A8
OFF_FACE_CLICK        = 0x129A

APPEARANCE_DLG_BYTES  = (0x38, 0x19, 0x34)


_CHARGEN_PANEL_PRIORITY = 30


def _set_panel_mode(w, mode: str, *, priority: int = 0) -> None:
    w._ui_router.set_panel_mode(mode, priority=priority)


def _post_chargen_opening_active(w) -> bool:
    return (
        bool(getattr(w, "_chargen_opening_displayed", False))
        or bool(getattr(w, "_chargen_opening_text_prev", ""))
    )


def _appearance_detection_allowed(w) -> bool:
    return (
        _current_top_level(w) == "chargen"
        and not getattr(w, "_chargen_appearance_displayed", False)
        and not _post_chargen_opening_active(w)
    )


def _chargen_text_translation_reason(w) -> str:
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
    if getattr(w, "_chargen_opening_displayed", False):
        return ("translate", "opening")

    if getattr(w, "_chargen_class_list_active", False):
        return ("class_list", "class_list")

    if getattr(w, "_chargen_explanation_active", None) == "appearance":
        return ("translate", "appearance_explanation")

    if getattr(w, "_chargen_appearance_displayed", False):
        return ("appearance_faces", "appearance_main")

    if getattr(w, "_chargen_complete_displayed", False):
        return ("translate", "complete")

    if (getattr(w, "_chargen_choose_attrs_displayed", False)
            or getattr(w, "_chargen_distribute_displayed", False)
            or getattr(w, "_chargen_explanation_active", None) == "distribute"
            or getattr(w, "_chargen_attrs_modal_kind", None) in (
                "bonus_required", "stat_save_confirm")):
        if (getattr(w, "_chargen_explanation_active", None) == "distribute"
                or getattr(w, "_chargen_attrs_modal_kind", None) in (
                    "bonus_required", "stat_save_confirm")):
            return ("translate", "attrs_popup_or_modal")
        if panel_visible:
            return ("choose_attributes", "attrs_phase(panel_shown)")
        return ("choose_attributes", "attrs_main(panel_hidden)")

    if getattr(w, "_chargen_race_select_displayed", False):
        if panel_visible:
            return ("race_list", "race_select(panel_shown)")
        try:
            dlg_r = w._analyzer.read_bytes(
                w._anchor + OFF_DIALOG_FLAG, 1)[0]
        except (OSError, AttributeError):
            dlg_r = 0xFF
        if dlg_r != 0x00:
            return ("race_list",
                    "race_select_map(panel_hidden, dlg=0x%02X)" % dlg_r)
        return ("translate", "race_select_popup(panel_hidden, dlg=0x00)")

    if getattr(w, "_chargen_race_desc_displayed", False):
        return ("translate", "race_desc")

    reason = _chargen_text_translation_reason(w)
    if reason:
        return ("translate", reason)

    return (None, "")


CHARGEN_SUBSTATES = (
    "opening", "class_list", "appearance", "complete", "attrs",
    "race_select", "race_desc",
    "method", "ten_questions", "class_accept", "class_advice",
    "goyenow", "name_input", "sex_select",
)


def chargen_substate(w) -> str:
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
    if w._chargen_distribute_displayed:
        return
    entry = itl.lookup("_CHARGEN_DISTRIBUTE_POINTS_", 0)
    if entry is not None:
        w._update_translate_tab(entry)
    w._chargen_distribute_displayed = True
    if not w._chargen_attrs_phase_seen:
        w._chargen_attrs_state_anchor = chargen_state
        w._chargen_attrs_phase_seen = True
        _log.info(
            "chargen_latch: attrs_anchor=None->0x%02X source=DistributePoints (%s)",
            chargen_state, source)
    if not w._chargen_status_display_armed:
        w._chargen_status_display_armed = True
        _log.info(
            "chargen_latch: status_armed=0->1 source=DistributePoints (%s)",
            source)
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
    if entry_handled or is_corpse_loot:
        return
    if _current_top_level(w) != "chargen":
        return
    img = (getattr(w, "_img_name_prev", "") or "").upper()
    if img.startswith("INTRO") and img.endswith(".IMG"):
        return
    if getattr(w, "_chargen_opening_displayed", False):
        return
    w._chargen._handle_chargen_npc_dialog(npc_dialog)


def _poll_track_state(w) -> int:
    try:
        chargen_state = w._analyzer.read_bytes(
            w._anchor + CHARGEN_STATE_OFFSET, 1)[0]
    except OSError:
        chargen_state = 0
    if chargen_state == w._chargen_state_prev:
        w._chargen_state_streak += 1
    else:
        if w._chargen_state_streak >= 2:
            _log.info("chargen_state changed from stable 0x%02X to 0x%02X",
                      w._chargen_state_prev, chargen_state)
        w._chargen_state_streak = 1
        w._chargen_state_prev = chargen_state

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
    try:
        return w._analyzer.read_bytes(w._anchor + 0xA845, 1)[0]
    except (OSError, AttributeError):
        return None




def _detect_method_exit(w, chargen_state: int, a845: int | None) -> None:
    if w._chargen_state_streak < 2:
        return
    if getattr(w, "_chargen_method_a845", None) is None and a845 is not None:
        w._chargen_method_a845 = a845
        _log.info("chargen: method a845 baseline = 0x%02X", a845)
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
    elif w._chargen_method_state is None:
        w._chargen_method_state = chargen_state
        w._chargen_method_a845 = a845
        _log.info(
            "chargen: method captured (state=0x%02X, a845=%s)",
            chargen_state,
            "None" if a845 is None else f"0x{a845:02X}",
        )


def _detect_advice_exit(w, chargen_state: int, a845: int | None) -> None:
    if w._chargen_state_streak < 2:
        return
    if getattr(w, "_chargen_advice_a845", None) is None and a845 is not None:
        w._chargen_advice_a845 = a845
        _log.info("chargen: advice a845 baseline = 0x%02X", a845)
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
    if w._chargen_state_streak < 2:
        return
    if (w._chargen_goyenow_state is not None
            and not w._chargen_distribute_displayed):
        expected_distribute = (w._chargen_goyenow_state + 0x1C) & 0xFF
        if chargen_state == expected_distribute:
            _fire_distribute_points(w, chargen_state,
                                    source="chargen_state+0x1C")


def _detect_attrs_appearance_candidate(w, chargen_state: int) -> None:
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
    if _appearance_detection_allowed(w):
        try:
            _img_raw2 = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_check = _img_raw2.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_check = ""
        if _img_check.startswith("FACES") and _img_check.endswith(".CIF"):
            entry = itl.lookup("_CHARGEN_APPEARANCE_", 0)
            if entry is not None:
                w._update_translate_tab(entry)
            w._chargen_appearance_displayed = True
            _log.info(
                "chargen: Appearance fired (img=%s, FACES detection)",
                _img_check)
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
                    w._chargen_explanation_active = "appearance"
                    _log.info(
                        "chargen_latch: explanation_active=None->appearance "
                        "source=Appearance_dlg_bytes_match")
                    _log.info(
                        "chargen: Appearance fired (dlg_flag=0x01, "
                        "+0xA845/6/7=0x%02X/0x%02X/0x%02X)",
                        _ph_bytes[0], _ph_bytes[1], _ph_bytes[2])



def _poll_detect_goyenow_fallback(w, chargen_state: int) -> None:
    if (w._chargen_in_advice
            and w._chargen_advice_state is not None
            and w._advice_capture_age >= 6
            and not w._chargen_goyenow_displayed
            and w._chargen_done_prev == 0
            and w._goyenow_scan_budget > 0):
        w._goyenow_scan_budget -= 1
        fired = False

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
        if (_npc_now_bytes is not None
                and w._chargen_goyenow_npc_snapshot is None):
            w._chargen_goyenow_npc_snapshot = _npc_now_bytes
            _log.info(
                "chargen_latch: goyenow_npc_snapshot=%r source=GoYeNow_initial",
                _npc_now_bytes[:40])
        if (_npc_now_bytes is not None
                and w._chargen_goyenow_npc_snapshot is not None
                and _npc_now_bytes != w._chargen_goyenow_npc_snapshot
                and _npc_now_bytes):
            _fire_distribute_points(
                w, chargen_state,
                source="npc_buf_changed_from_goyenow_snapshot")


def _poll_detect_distribute_by_dialog(w, chargen_state: int) -> None:
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
    if _prev == 0x00 and _b7c4 != 0x00:
        _fire_distribute_points(
            w, chargen_state,
            source="dialog_gate_b7c4(0x00->0x%02X)" % _b7c4)


def _poll_detect_questions(w) -> int:
    try:
        chargen_q_seq = w._analyzer.read_bytes(
            w._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
    except OSError:
        chargen_q_seq = 0

    if not w._chargen_10q_displayed and w._chargen_method_window:
        try:
            _img_raw = w._analyzer.read_bytes(
                w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
            _img_now = _img_raw.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").upper()
        except (OSError, AttributeError):
            _img_now = ""
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
    new_modal_kind: str | None = None
    if (w._chargen_attrs_phase_seen
            and not w._chargen_appearance_displayed):
        try:
            _dlg_flag_eval = w._analyzer.read_bytes(
                w._anchor + OFF_DIALOG_FLAG, 1)[0]
        except (OSError, AttributeError):
            _dlg_flag_eval = 0xFF
        if _dlg_flag_eval == 0x01:
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
    is_chargen: bool
    panel_visible: bool
    target_panel_mode: str | None
    reason: str
    freeze_status: bool
    freeze_ok: bool
    substate: str


def classify_chargen_view(w) -> ChargenView:
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
        try:
            target_mode, reason = _chargen_target_panel_mode(
                w, panel_visible=panel_visible)
        except (AttributeError, RuntimeError):
            target_mode, reason = None, ""
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
                    _set_panel_mode(
                        w, target_mode,
                        priority=(0 if target_mode == "translate"
                                  else _CHARGEN_PANEL_PRIORITY))
        else:
            current_mode = w._tab_translate.panel_mode()
            if current_mode == "appearance_faces":
                _log.info(
                    "chargen_panel: target_mode=translate reason=non_chargen_reset prev=%s",
                    current_mode)
                _set_panel_mode(w, "translate")
    except (AttributeError, RuntimeError):
        pass
    if view.freeze_ok:
        try:
            if w._tab_status is not None:
                w._tab_status.set_freeze_updates(view.freeze_status)
        except (AttributeError, RuntimeError):
            pass


def _poll_revert_appearance_flag(w) -> None:
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
    try:
        chargen_done = w._analyzer.read_bytes(
            w._anchor + CHARGEN_DONE_OFFSET, 1)[0]
    except OSError:
        chargen_done = w._chargen_done_prev
    if chargen_done == 1 and w._chargen_done_prev == 0:
        w._chargen_opening_retry = 240
        w._chargen_opening_displayed = False
        w._chargen_opening_text_prev = ""
    if chargen_done == 1 and w._chargen_opening_retry > 0:
        w._chargen_opening_retry -= 1
        if w._chargen._fire_post_chargen_opening():
            w._chargen_opening_displayed = True
            w._chargen_appearance_displayed = False
            w._chargen_attrs_state_anchor = None
            w._chargen_attrs_phase_seen = False
            w._chargen_attrs_modal_active = False
    w._chargen_done_prev = chargen_done


def _poll_detect(w, chargen_state: int) -> tuple[int, str | None]:
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

    if sub in ("method", "ten_questions"):
        chargen_q_seq = _poll_detect_questions(w)
    else:
        try:
            chargen_q_seq = w._analyzer.read_bytes(
                w._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
        except OSError:
            chargen_q_seq = 0

    if sub in ("attrs", "appearance"):
        new_modal_kind = _poll_evaluate_modal(w)
    else:
        new_modal_kind = None

    return chargen_q_seq, new_modal_kind


def poll(w) -> None:
    if _current_top_level(w) != "chargen":
        return
    if w._advice_capture_age >= 0:
        w._advice_capture_age += 1

    try:
        w._apply_display_active_for_state()
    except AttributeError:
        pass

    chargen_state = _poll_track_state(w)

    chargen_q_seq, new_modal_kind = _poll_detect(w, chargen_state)

    _poll_diagnostics(w, chargen_state, new_modal_kind)


    render_chargen_view(w, classify_chargen_view(w))

    _poll_bonus_warning(w)

    _poll_revert_appearance_flag(w)

    _poll_probe_diagnostics(w, chargen_state, chargen_q_seq)

    _poll_cinematic(w)
