"""C1 dungeon runtime dialog axis.

This module is the single reader for dungeon runtime message visibility.
It keeps the observed DLGFLG-family bytes together so individual renderers
do not each invent their own dialog-active rule.
"""
from __future__ import annotations

from dataclasses import dataclass


A845_OFFSET = 0xA845
A847_OFFSET = 0xA847
A84D_OFFSET = 0xA84D
CURRENT_TEXT_PTR_OFFSET = 0xA844

# Observed C1/runtime values. Several are also the high byte of the current
# text pointer (+0xA844), so this is deliberately treated as a display axis,
# not as a pure semantic phase byte.
KNOWN_C1_A845_VALUES = frozenset({
    0x10,  # NPC_DIALOG / corpse/no-loot response buffer high byte
    0x4F,  # level-up dialog observation
    0x79,  # runtime red-text buffer high byte
    0x92,  # gold-drop / response buffer high byte
    0x9A,  # message buffer / building-entry observation
})
KNOWN_C1_A84D_VALUES = frozenset({0x40})


@dataclass(frozen=True)
class C1DialogAxis:
    """One C1 runtime-message visibility decision for a poll."""

    active: bool
    prev_active: bool
    opened: bool
    closed: bool
    a845: int
    a84d: int
    a847: int
    current_ptr: int | None
    ptr_is_runtime: bool
    reason: str


def _read_u8(w, offset: int) -> int:
    try:
        return w._analyzer.read_bytes(w._anchor + offset, 1)[0]
    except (OSError, AttributeError, TypeError, IndexError):
        return 0


def _read_ptr(w) -> int | None:
    try:
        raw = w._analyzer.read_bytes(w._anchor + CURRENT_TEXT_PTR_OFFSET, 2)
    except (OSError, AttributeError, TypeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def _is_runtime_ptr(ptr: int | None) -> bool:
    try:
        from active_template_reader import is_response_buffer_pointer
        return is_response_buffer_pointer(ptr)
    except Exception:  # noqa: BLE001
        if ptr is None:
            return False
        return any(start <= ptr < start + length for start, length in (
            (0x1044, 512),
            (0x7979, 68),
            (0x929E, 512),
            (0x9A9E, 512),
        ))


def read_c1_dialog_axis(
    w,
    *,
    c_area: str | None,
    in_gameplay: bool = True,
    update_prev: bool = False,
) -> C1DialogAxis:
    """Read the C1 runtime dialog axis.

    ``+0xA847`` is an auxiliary observed byte with known delayed-clear risk,
    so it does not start the axis by itself. It can hold an already-owned
    runtime message while paired with the stronger DLGFLG-family evidence.
    """
    a845 = _read_u8(w, A845_OFFSET)
    a84d = _read_u8(w, A84D_OFFSET)
    a847 = _read_u8(w, A847_OFFSET)
    current_ptr = _read_ptr(w)
    ptr_is_runtime = _is_runtime_ptr(current_ptr)

    in_c1 = (c_area == "dungeon")
    owner = ""
    try:
        owner = w._ui_router.current_owner() or ""
    except (AttributeError, RuntimeError):
        owner = getattr(w, "_panel_owner", "") or ""
    runtime_owner = owner in (
        "red_text_dialog",
        "c1_runtime_dialog",
        "gold_drop",
    )

    reason_parts: list[str] = []
    if ptr_is_runtime:
        reason_parts.append("ptr")
    if a845 in KNOWN_C1_A845_VALUES:
        reason_parts.append("a845")
    if a84d in KNOWN_C1_A84D_VALUES:
        reason_parts.append("a84d")
    strong_signal = bool(reason_parts)
    if a847 != 0 and (strong_signal or runtime_owner):
        reason_parts.append("a847")

    active = (
        in_c1
        and in_gameplay
        and not bool(getattr(w, "_npc_conversation_active", False))
        and (strong_signal or (runtime_owner and a847 != 0))
    )
    prev_active = bool(getattr(w, "_c1_dialog_axis_active_prev", False))
    opened = active and not prev_active
    closed = prev_active and not active
    if update_prev:
        w._c1_dialog_axis_active_prev = active
        w._c1_dialog_axis_prev = (a845, a84d, a847, current_ptr)

    return C1DialogAxis(
        active=active,
        prev_active=prev_active,
        opened=opened,
        closed=closed,
        a845=a845,
        a84d=a84d,
        a847=a847,
        current_ptr=current_ptr,
        ptr_is_runtime=ptr_is_runtime,
        reason="+".join(reason_parts),
    )


__all__ = [
    "A845_OFFSET",
    "A847_OFFSET",
    "A84D_OFFSET",
    "C1DialogAxis",
    "read_c1_dialog_axis",
]
