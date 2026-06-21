from __future__ import annotations
from typing import Optional, Tuple

from screen_detector import SCREEN_IDS, _tr


def detect_chargen_screen(
    chargen_hint: Optional[str],
    img_name: str,
    last_subscreen: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    img_upper = (img_name or "").upper()

    if img_upper.endswith(".XMI"):
        hint = chargen_hint or last_subscreen
        if hint and hint in SCREEN_IDS:
            return (hint, _tr(hint))
        return ("loading", _tr("loading"))

    if img_upper.startswith("INTRO") and img_upper.endswith(".IMG"):
        try:
            num = int(img_upper.replace("INTRO", "").replace(".IMG", ""))
            return ("newgame_intro", _tr("newgame_intro", n=num))
        except ValueError:
            pass

    if (chargen_hint == "opening_cinematic"
            or (last_subscreen == "opening_cinematic"
                and img_upper.startswith("FACES")
                and img_upper.endswith(".CIF"))):
        return ("opening_cinematic", _tr("opening_cinematic"))

    if img_upper.startswith("FACES") and img_upper.endswith(".CIF"):
        return ("appearance", _tr("appearance"))

    if chargen_hint and chargen_hint in SCREEN_IDS:
        return (chargen_hint, _tr(chargen_hint))

    if img_upper == "PARCH.CIF":
        return ("class_select", _tr("class_select"))

    if img_upper == "SCROLL02.DFA":
        sub = last_subscreen if last_subscreen in (
            "ten_questions", "class_select",
        ) else "ten_questions"
        return (sub, _tr(sub))

    if img_upper == "NOEXIT.IMG":
        if last_subscreen in ("name_input", "sex_select", "race_select", "race_confirm"):
            return (last_subscreen, _tr(last_subscreen))
        return ("name_input", _tr("name_input"))

    if img_upper == "TERRAIN.IMG":
        if last_subscreen in ("status_proclamation", "race_description", "class_advice"):
            return (last_subscreen, _tr(last_subscreen))
        return ("status_proclamation", _tr("status_proclamation"))

    if last_subscreen and last_subscreen in SCREEN_IDS:
        return (last_subscreen, _tr(last_subscreen))

    return None
