from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

_FG_PTR_OFFSET = 0xA844
_DIALOG_OFF_MIN = 0x9000
_DIALOG_OFF_MAX = 0xA000
_OWNER = "palace_dialog"


def is_palace_interior_mif(interior_mif_name: str | None) -> bool:
    u = (interior_mif_name or "").upper()
    return u.startswith(("PALACE", "TOWNPAL", "VILPAL"))


def assemble_dialog_text(raw: bytes) -> str:
    chunks: list[str] = []
    for seg in raw.split(b"\x00"):
        s = seg.decode("ascii", errors="replace").strip()
        if not s:
            continue
        printable = sum(1 for c in s if 0x20 <= ord(c) <= 0x7E)
        if len(s) >= 8 and printable / len(s) >= 0.85:
            chunks.append(s)
        elif chunks:
            break
    joined = " ".join(c.replace("\n", " ").replace("\r", " ") for c in chunks)
    return " ".join(joined.split())


def _read_full_text(w, off: int) -> str:
    try:
        raw = w._analyzer.read_bytes(w._anchor + off, 1200)
    except (OSError, AttributeError):
        return ""
    return assemble_dialog_text(raw)


def poll_palace_dialog(w, *, palace_active: bool) -> bool:
    if not palace_active:
        if w._ui_router.is_owner(_OWNER):
            w._ui_router.release_if_owner(_OWNER)
        w._palace_dialog_last_off = None
        w._palace_dialog_prev_key = None
        return False

    try:
        fgraw = w._analyzer.read_bytes(w._anchor + _FG_PTR_OFFSET, 2)
        fg = fgraw[0] | (fgraw[1] << 8)
    except (OSError, AttributeError):
        fg = 0
    in_band_fg = _DIALOG_OFF_MIN <= fg <= _DIALOG_OFF_MAX

    try:
        import npc_dialog_lookup as _ndl
    except ImportError:
        return False

    def _emit(off: int, text: str, ja: str, *, yesno: bool) -> bool:
        if yesno:
            ja = f"{ja}\n\n  はい\n  いいえ"
        w._palace_dialog_last_off = off
        display_key = (text, yesno)
        if (getattr(w, "_palace_dialog_prev_key", None) == display_key
                and w._ui_router.is_owner(_OWNER)):
            return True
        w._palace_dialog_prev_key = display_key
        w._ui_router.update_translation(
            _OWNER, text, ja, speech_role="conversation")
        _log.info("panel_owner -> palace_dialog (off=0x%04X yesno=%s text=%r)",
                  off, yesno, text[:60])
        return True

    if in_band_fg:
        text = _read_full_text(w, fg)
        if text:
            result = _ndl.lookup(text)
            if result and result[0]:
                ja = _ndl.format_japanese(result[0], result[1])
                return _emit(fg, text, ja, yesno=False)

    last_off = getattr(w, "_palace_dialog_last_off", None)
    if last_off is not None and last_off != fg:
        text = _read_full_text(w, last_off)
        if text and text.rstrip().endswith("?"):
            result = _ndl.lookup(text)
            if result and result[0]:
                ja = _ndl.format_japanese(result[0], result[1])
                return _emit(last_off, text, ja, yesno=True)

    if w._ui_router.is_owner(_OWNER):
        w._ui_router.release_if_owner(_OWNER)
    w._palace_dialog_prev_key = None
    w._palace_dialog_last_off = None
    _log.debug("palace_dialog cleared (fg=0x%04X in_band=%s)", fg, in_band_fg)
    return False


__all__ = [
    "poll_palace_dialog",
    "is_palace_interior_mif",
    "assemble_dialog_text",
]
