from __future__ import annotations

import logging

import inf_text_lookup as itl

_log = logging.getLogger("assist_window")


def update_translate_tab(win, entry: dict) -> None:
    inf_key = (entry.get("inf") or "").upper()
    win._set_chargen_ui_state(inf_key.startswith("_CHARGEN_"))
    if inf_key == "_CHARGEN_":
        saved_streak = win._chargen_state_streak
        saved_state_prev = win._chargen_state_prev
        win._chargen._reset_chargen_state_for_restart(
            reason="method NPC detected (new chargen start)")
        win._chargen_state_streak = saved_streak
        win._chargen_state_prev = saved_state_prev
        win._chargen_method_window = True
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
        win._chargen_method_window = False
        win._chargen_race_select_displayed = True
        win._chargen_10q_displayed = False
        win._chargen_class_accept_displayed = False
        win._chargen_class_list_active = False
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_PROVINCE_CONFIRM_":
        win._chargen_method_window = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_RESULT_"):
        win._chargen_class_accept_displayed = True
        win._chargen_method_window = False
        win._chargen_10q_displayed = False
        win._chargen_class_list_active = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_RACE_"):
        win._chargen_race_desc_displayed = True
        win._chargen_method_window = False
        win._chargen_race_select_displayed = False
        win._chargen_class_accept_displayed = False
        win._chargen_10q_displayed = False
        win._chargen_complete_displayed = False
    elif inf_key.startswith("_CHARGEN_CLASS_ADVICE_"):
        win._chargen_race_desc_displayed = False
        win._chargen_race_select_displayed = False
        win._chargen_method_window = False
        win._chargen_10q_displayed = False
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_GENDER_":
        win._chargen_sex_select_displayed = True
        win._in_chargen_name = False
        win._chargen_method_window = False
        win._chargen_class_list_active = False
        win._chargen_complete_displayed = False
    elif inf_key == "_CHARGEN_APPEARANCE_":
        win._chargen_appearance_displayed = True
        win._chargen_sex_select_displayed = False
        win._in_chargen_name = False
        win._chargen_complete_displayed = False
        win._chargen_attrs_state_anchor = None
        win._chargen_attrs_phase_seen = False
        win._chargen_attrs_modal_active = False
        win._chargen_attrs_modal_kind = None
    elif inf_key.startswith("_CHARGEN_"):
        win._chargen_method_window = False
        win._chargen_race_select_displayed = False
        win._chargen_class_accept_displayed = False
        win._chargen_race_desc_displayed = False
        win._chargen_complete_displayed = False
    typ = entry.get("type", "")
    if typ == "riddle":
        original   = entry.get("question", "")
        trans      = itl.get_translation(entry)
        translated = trans.get("question", "") if isinstance(trans, dict) else ""
        win._push_translation(original, translated)
    else:
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
    chargen_sub = None
    try:
        from screen_detector import get_chargen_subscreen
        chargen_sub = get_chargen_subscreen(win)
    except (ImportError, AttributeError):
        pass

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
        if mode == "load_screen":
            img_name_now = (
                getattr(win, "_img_name_prev", "") or "").upper()
            if img_name_now != "LOADSAVE.IMG":
                win._ui_router.set_panel_mode("translate")
    except AttributeError:
        pass
    p_orig = panel_original if panel_original is not None else original
    p_trans = panel_translated if panel_translated is not None else translated
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

    if chargen_sub is not None and (original or translated):
        win._last_chargen_subscreen = chargen_sub
    elif chargen_sub is None:
        win._last_chargen_subscreen = None


__all__ = ["update_translate_tab", "push_translation"]
