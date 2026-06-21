from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusPanelState:

    chargen_mode: bool
    is_bonus_screen: bool


def classify_status_panel_state(
    *, top_level: str, screen_id_stable: str | None
) -> StatusPanelState:
    return StatusPanelState(
        chargen_mode=(top_level == "chargen"),
        is_bonus_screen=(screen_id_stable == "bonus_screen"),
    )


__all__ = ["StatusPanelState", "classify_status_panel_state"]
