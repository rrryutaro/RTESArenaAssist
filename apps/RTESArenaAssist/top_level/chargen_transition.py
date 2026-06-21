"""chargen -> normal-play transition guards.

The only accepted B -> C transition is the post-chargen cinematic followed by
entering the first dungeon.  Arena keeps several memory values from previous
runs, so ``chargen_done`` and IMG names are not allowed to release chargen by
themselves.
"""
from __future__ import annotations


def normal_play_entry_reason(
    *,
    top_level_state: str,
    mif_name: str,
    img_name: str,
    post_chargen_reached: bool,
    chargen_done: int,
) -> str:
    """Return the chargen -> normal-play transition reason, or an empty string.

    This intentionally ignores ``chargen_done`` and ``img_name`` as release
    signals.  Both can be stale or context-dependent during a new character
    creation run, and allowing them here reopens B -> C1 leakage.
    """
    if top_level_state != "chargen":
        return ""

    mif = (mif_name or "").strip()
    if not mif:
        return ""

    mif_lower = mif.lower()
    if mif_lower == "start.mif" and post_chargen_reached:
        return "start.mif in chargen (post-chargen)"

    return ""


__all__ = ["normal_play_entry_reason"]
