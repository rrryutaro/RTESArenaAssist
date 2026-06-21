from __future__ import annotations

from top_level.top_level_dispatcher import current_state as _current_top_level


_PREGAME_IMGS = frozenset({
    "QUOTE.IMG", "SCROLL01.IMG", "SCROLL02.IMG", "MENU.IMG", "LOADSAVE.IMG",
})


def check_load_save_transition(w, *, mif_name: str, img_name: str) -> None:
    if (_current_top_level(w) == "pregame"
            and w._pregame_loadsave_seen
            and mif_name
            and img_name not in _PREGAME_IMGS
            and not img_name.endswith(".XMI")):
        w._transition_top_level("normal-play",
                                f"loadsave+mif:{mif_name}")


__all__ = ["check_load_save_transition"]
