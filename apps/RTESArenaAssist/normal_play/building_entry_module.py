from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

_MAX_DIAG_DUMPS = 6

_DIALOG_MENU_IMGS = frozenset({
    "MENU_RT.IMG", "POPUP11.IMG", "NEGOTBUT.IMG",
    "YESNO.IMG", "NEWPOP.IMG",
})
_NON_ENTRY_XMI_IMGS = frozenset({
    "VISION.XMI",
})
_ENTRY_CIF_IMGS = frozenset({
    "FACES00.CIF",
})


def should_poll_building_entry(*, entry_phase: bool, panel_owner: str,
                               pending: bool, img_name: str) -> bool:
    img_upper = (img_name or "").upper()
    if img_upper in _NON_ENTRY_XMI_IMGS:
        return False
    entry_xmi_surface = img_upper.endswith(".XMI") \
        and img_upper not in _DIALOG_MENU_IMGS
    entry_surface = entry_xmi_surface or img_upper in _ENTRY_CIF_IMGS
    if not entry_phase:
        return bool(pending and entry_surface)
    if panel_owner == "building_entry" or pending:
        return True
    if img_upper in _DIALOG_MENU_IMGS:
        return False
    return entry_surface


def _diag_dump_memory(w, msg_buf: str, npc_dialog: str) -> None:
    _dump_count = getattr(w, "_b288_entry_diag_count", 0)
    if _dump_count >= _MAX_DIAG_DUMPS:
        return
    w._b288_entry_diag_count = _dump_count + 1

    _log.warning(
        "entry diag [%d/%d]: msg_buf=%r npc_dialog=%r",
        _dump_count + 1, _MAX_DIAG_DUMPS,
        msg_buf[:120] if msg_buf else "",
        npc_dialog[:120] if npc_dialog else "")
    _diag_offsets = (
        (0x1044, 512, "0x1044 npc_dialog"),
        (0x929E, 512, "0x929E b131 buffer"),
        (0x9A9E, 512, "0x9A9E msg_buf"),
        (0x987A, 512, "0x987A negot_rendered"),
        (0x9000, 512, "0x9000+512"),
        (0x9400, 512, "0x9400+512"),
        (0x9600, 512, "0x9600+512"),
        (0x9800, 512, "0x9800+512"),
    )
    for _off, _len, _label in _diag_offsets:
        try:
            _raw = w._analyzer.read_bytes(w._anchor + _off, _len)
            _chunks: list[str] = []
            _pos = 0
            while _pos < len(_raw) and len(_chunks) < 6:
                if _raw[_pos] == 0x00:
                    _pos += 1
                    continue
                _end = _pos
                while _end < len(_raw) and _raw[_end] != 0x00:
                    _end += 1
                _frag = _raw[_pos:_end].decode("ascii", errors="replace")
                _printable = sum(1 for c in _frag
                                 if 0x20 <= ord(c) <= 0x7E)
                if _frag and _printable / len(_frag) >= 0.8 \
                        and len(_frag.strip()) >= 4:
                    _chunks.append(_frag.strip()[:120])
                _pos = _end + 1
            if _chunks:
                _log.warning(
                    "entry diag [%d/%d] %s: %s",
                    _dump_count + 1, _MAX_DIAG_DUMPS, _label,
                    " | ".join(f"{c!r}" for c in _chunks[:4]))
        except (OSError, AttributeError) as _exc:
            _log.debug("entry diag %s read failed: %s", _label, _exc)


def _read_b131_buffer(w) -> str:
    try:
        _raw = w._analyzer.read_bytes(w._anchor + 0x929E, 256)
        _end = _raw.find(b"\x00")
        if _end == -1:
            _end = len(_raw)
        _text = _raw[:_end].decode("ascii", errors="replace").strip()
        return _text if _text else ""
    except (OSError, AttributeError):
        return ""


def _read_b131_chunks(w) -> list[str]:
    try:
        raw = w._analyzer.read_bytes(w._anchor + 0x929E, 512)
    except (OSError, AttributeError):
        return []
    chunks: list[str] = []
    pos = 0
    while pos < len(raw):
        while pos < len(raw) and raw[pos] == 0x00:
            pos += 1
        if pos >= len(raw):
            break
        end = pos
        while end < len(raw) and raw[end] != 0x00:
            end += 1
        frag = raw[pos:end].decode("ascii", errors="replace").strip()
        printable = sum(1 for c in frag if 0x20 <= ord(c) <= 0x7E)
        if frag and printable / max(len(frag), 1) >= 0.8:
            chunks.append(frag)
        pos = end + 1
    return chunks


def _normalize_for_lookup(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " "))


def _read_msg_buf_chunks(w) -> list[str]:
    try:
        raw = w._analyzer.read_bytes(w._anchor + 0x9A9E, 512)
    except (OSError, AttributeError):
        return []
    chunks: list[str] = []
    for seg in raw.split(b"\x00"):
        frag = seg.decode("ascii", errors="replace").strip()
        printable = sum(1 for c in frag if 0x20 <= ord(c) <= 0x7E)
        if frag and printable / max(len(frag), 1) >= 0.8 and len(frag) >= 2:
            chunks.append(frag)
        elif chunks:
            break
    return chunks


def _build_entry_text_candidates(w, msg_buf: str) -> list[str]:
    if not msg_buf:
        return []
    _normalized_msg = _normalize_for_lookup(msg_buf).strip()
    candidates = [_normalized_msg]
    if _normalized_msg.endswith((".", "?", "!")):
        return candidates
    chunks = [
        _normalize_for_lookup(chunk).strip()
        for chunk in _read_b131_chunks(w)
        if chunk.strip()
    ]
    if not chunks:
        return candidates
    variants = []
    variants.append(" ".join(chunks))
    if len(chunks) > 1:
        variants.append(" ".join(reversed(chunks)))
    for suffix in variants:
        if not suffix or suffix in _normalized_msg:
            continue
        for candidate in (
                f"{_normalized_msg} {suffix}".strip(),
                f"{_normalized_msg}{suffix}".strip()):
            if candidate not in candidates:
                candidates.append(candidate)

    msg_chunks = _read_msg_buf_chunks(w)
    if len(msg_chunks) > 1:
        full_msg = _normalize_for_lookup(" ".join(msg_chunks)).strip()
        bodies = [full_msg]
        for suffix in variants:
            if not suffix or suffix in full_msg:
                continue
            bodies.append(f"{full_msg} {suffix}".strip())
            bodies.append(f"{full_msg}{suffix}".strip())
        for cand in bodies:
            if cand and cand not in candidates:
                candidates.append(cand)
    return candidates


def _build_full_entry_text(w, msg_buf: str) -> str:
    candidates = _build_entry_text_candidates(w, msg_buf)
    return candidates[0] if candidates else ""


def poll_building_entry(w, *, building_entry_active: bool,
                        entry_phase_prev: bool,
                        msg_buf: str, npc_dialog: str) -> bool:
    entry_handled = False
    if building_entry_active:
        try:
            from template_dat_building_lookup import lookup as _bld_lookup
            _full_texts = _build_entry_text_candidates(w, msg_buf)
            _entry_candidates = [
                *[
                    (f"msg_buf_full[{idx}]", txt)
                    for idx, txt in enumerate(_full_texts)
                ],
                ("msg_buf", msg_buf),
                ("b131", _read_b131_buffer(w)),
                ("npc_dialog", npc_dialog),
            ]
            for _src, _txt in _entry_candidates:
                if not _txt:
                    continue
                _entry_result = _bld_lookup(_txt)
                if _entry_result is None:
                    continue
                _entry_ja, _entry_meta = _entry_result
                w._ui_router.update_translation(
                    "building_entry", _txt, _entry_ja,
                    speech_role="situation")
                try:
                    from normal_play.copy_selector_observation import observe \
                        as _observe_copy
                    _observe_copy(w, _entry_meta, _txt, src=_src)
                except Exception:  # noqa: BLE001
                    pass
                w._building_entry_pending = False
                _log.info(
                    "panel_owner -> building_entry "
                    "(src=%s key=%s en=%r)",
                    _src, _entry_meta.get("matched_key"), _txt[:40])
                entry_handled = True
                break
        except Exception:  # noqa: BLE001
            _log.exception("building entry lookup failed")
        if not entry_handled:
            _diag_dump_memory(w, msg_buf, npc_dialog)
    elif entry_phase_prev or getattr(w, "_building_entry_pending", False):
        w._building_entry_pending = False
        if w._ui_router.is_owner("building_entry"):
            w._ui_router.release_if_owner("building_entry")
            _log.info("panel_owner -> '' (entry phase exited)")
    return entry_handled


__all__ = ["poll_building_entry", "should_poll_building_entry"]
