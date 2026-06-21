from __future__ import annotations

import logging
import re as _re

from arena_bridge import SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN
import inf_text_lookup as itl
from top_level.top_level_dispatcher import current_state as _current_top_level

_log = logging.getLogger("RTESArenaAssist")

_DEATH_CINEMATIC_HINT_ADDR = 0x10764C10
_DEATH_CINEMATIC_FULLREAD = 4096
_DEATH_CINEMATIC_SCAN_START = 0x10000000
_DEATH_CINEMATIC_SCAN_END = 0x12000000
_DEATH_GOOD_PREFIX = "With you died our last hope for justice."
_DEATH_BAD_PREFIX = "You were a fool to confront me,"
_DEATH_CINEMATIC_PREFIXES = (
    _DEATH_GOOD_PREFIX,
    _DEATH_BAD_PREFIX,
)
_VISION_XMI_NAME = "VISION.XMI"
_VISION_CINEMATIC_PREFIXES = (
    "Do not fear for it is I",
    "I see you have strengthened your arm",
    "It is said that Fang Lair was originally built",
    "It seems that you are well chosen",
    "I would congratulate you on retrieving the",
    "You have done well",
    "You have recovered the fourth piece",
    "It has become a habit",
    "Tharn is livid",
    "I would take no chances",
    "I had expected that with all eight pieces together",
    *_DEATH_CINEMATIC_PREFIXES,
)

_PLAYER_HP_CURRENT_OFFSET = 0x1FD
_PLAYER_NAME_OFFSET = 0x1AD
_PLAYER_NAME_LEN = 26
_DEATH_GOOD_JA = (
    "お前とともに、正義への最後の希望も死んだ。サーンは今や望むままに"
    "振る舞うだろう。美しいタムリエルの地が内側から腐っていくのを見るのは"
    "悲しい。さようなら、[名前]。来世で安らぎを得られますように..."
)
_DEATH_BAD_JA = (
    "愚かにも私に立ち向かい、ついに究極の代償を払ったな。今この時も、"
    "我が僕が貴様の朽ちた肉体を取りに向かっている。貴様は皇帝となった"
    "我が年月において、アンデッドとしてよく仕えることになる。もしかすると"
    "記憶の一部を残してやるかもしれん。そうすれば、失敗の代償が貴様にも"
    "意味を持つだろう...."
)


def _read_cinematic_block(w, address: int) -> str:
    data = b""
    for size in (_DEATH_CINEMATIC_FULLREAD, 2048, 1024, 512, 256):
        try:
            data = w._analyzer.read_bytes(address, size)
            if data:
                break
        except (OSError, AttributeError):
            continue
    if not data:
        return ""

    parts = data.split(b"\x00")
    text_parts: list[str] = []
    empty_run = 0
    for raw in parts:
        if not raw:
            empty_run += 1
            if empty_run >= 4 and text_parts:
                break
            continue
        empty_run = 0
        try:
            s = raw.decode("ascii", errors="replace").strip()
        except Exception:  # noqa: BLE001
            if text_parts:
                break
            continue
        if not s:
            continue
        printable = sum(1 for c in s if 0x20 <= ord(c) < 0x7F)
        if printable / max(len(s), 1) < 0.7:
            if text_parts:
                break
            continue
        if len(s) < 3 and text_parts:
            continue
        text_parts.append(s)
    return " ".join(text_parts).strip()


def _read_screen_img_name(w) -> str:
    try:
        raw = w._analyzer.read_bytes(
            w._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
    except (OSError, AttributeError, TypeError):
        return ""
    try:
        return raw.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace").upper()
    except Exception:  # noqa: BLE001
        return ""


def _is_vision_xmi_active(w, *, img_name: str | None = None) -> bool:
    name = img_name if img_name is not None else _read_screen_img_name(w)
    return (name or "").upper() == _VISION_XMI_NAME


def _read_player_name(w) -> str:
    try:
        raw = w._analyzer.read_bytes(
            w._anchor + _PLAYER_NAME_OFFSET, _PLAYER_NAME_LEN)
    except (OSError, AttributeError, TypeError):
        return ""
    try:
        return raw.split(b"\x00", 1)[0].decode(
            "ascii", errors="replace").strip()
    except Exception:  # noqa: BLE001
        return ""


def _death_cinematic_translation(text: str) -> str:
    if text.startswith(_DEATH_GOOD_PREFIX):
        name = "旅人"
        m = _re.search(r"Goodbye,\s+(.+?)\.", text)
        if m:
            name = m.group(1).strip()
        return _DEATH_GOOD_JA.replace("[名前]", name)
    if text.startswith(_DEATH_BAD_PREFIX):
        return _DEATH_BAD_JA
    return ""


def _lookup_vision_cinematic_payload(
        w, text: str) -> tuple[str, str, str] | None:
    if not text:
        return None

    death_ja = _death_cinematic_translation(text)
    if death_ja:
        return ("death_cinematic", text, death_ja)

    entry = itl.lookup_by_text("", text)
    if entry is None:
        return None
    tr = itl.get_translation(entry)
    ja = tr if isinstance(tr, str) else ""
    if not ja:
        return None
    player_name = _read_player_name(w)
    if player_name:
        ja = ja.replace("[名前]", player_name)
    return ("vision_cinematic", text, ja)


def _find_death_cinematic_text(w, *, allow_scan: bool = False) -> tuple[str, int]:
    block = _read_cinematic_block(w, _DEATH_CINEMATIC_HINT_ADDR)
    if block and _death_cinematic_translation(block):
        return block, _DEATH_CINEMATIC_HINT_ADDR

    if not allow_scan:
        return "", 0

    for prefix in _DEATH_CINEMATIC_PREFIXES:
        try:
            results = w._analyzer.scan_string(
                prefix,
                _DEATH_CINEMATIC_SCAN_START,
                _DEATH_CINEMATIC_SCAN_END,
            )
        except (OSError, RuntimeError, AttributeError) as exc:
            _log.debug("death cinematic scan_string error: %s", exc)
            continue
        if not results:
            continue
        for result in results:
            addr = getattr(result, "address", 0)
            if not addr:
                continue
            block = _read_cinematic_block(w, addr)
            if block and _death_cinematic_translation(block):
                return block, addr
    return "", 0


def _find_vision_cinematic_text(w) -> tuple[str, int]:
    block = _read_cinematic_block(w, _DEATH_CINEMATIC_HINT_ADDR)
    if block and _lookup_vision_cinematic_payload(w, block):
        return block, _DEATH_CINEMATIC_HINT_ADDR

    for prefix in _VISION_CINEMATIC_PREFIXES:
        try:
            results = w._analyzer.scan_string(
                prefix,
                _DEATH_CINEMATIC_SCAN_START,
                _DEATH_CINEMATIC_SCAN_END,
            )
        except (OSError, RuntimeError, AttributeError) as exc:
            _log.debug("vision cinematic scan_string error: %s", exc)
            continue
        if not results:
            continue
        for result in results:
            addr = getattr(result, "address", 0)
            if not addr:
                continue
            block = _read_cinematic_block(w, addr)
            if block and _lookup_vision_cinematic_payload(w, block):
                return block, addr
    return "", 0


def poll_vision_cinematic(w, *, b30: dict | None = None) -> None:
    if _current_top_level(w) != "normal-play":
        return
    img_name = b30.get("img_name") if isinstance(b30, dict) else None
    if not _is_vision_xmi_active(w, img_name=img_name):
        return

    text, addr = _find_vision_cinematic_text(w)
    payload = _lookup_vision_cinematic_payload(w, text)
    if payload is None:
        return
    owner, en, ja = payload
    prev_attr = (
        "_death_cinematic_text_prev"
        if owner == "death_cinematic"
        else "_vision_cinematic_text_prev"
    )
    if text == getattr(w, prev_attr, ""):
        return
    setattr(w, prev_attr, text)
    _log.info(
        "vision cinematic accepted owner=%s addr=0x%08X: %r",
        owner, addr, text[:96])
    try:
        w._ui_router.propose_translation(
            owner, en, ja, priority=46, reason="vision_cinematic",
            speech_role="situation")
    except AttributeError:
        w._ui_router.update_translation(
            owner, en, ja, speech_role="situation")


def poll_death_cinematic(w) -> None:
    if _current_top_level(w) != "normal-play":
        return
    if _is_vision_xmi_active(w):
        return
    text, addr = _find_death_cinematic_text(
        w, allow_scan=_current_hp_is_zero(w))
    if not text:
        return
    ja = _death_cinematic_translation(text)
    if not ja:
        return
    if text == getattr(w, "_death_cinematic_text_prev", ""):
        return
    w._death_cinematic_text_prev = text
    _log.info("death cinematic accepted addr=0x%08X: %r", addr, text[:96])
    try:
        w._ui_router.propose_translation(
            "death_cinematic", text, ja,
            priority=45, reason="death_cinematic",
            speech_role="situation")
    except AttributeError:
        w._ui_router.update_translation(
            "death_cinematic", text, ja, speech_role="situation")


def _current_hp_is_zero(w) -> bool:
    try:
        raw = w._analyzer.read_bytes(
            w._anchor + _PLAYER_HP_CURRENT_OFFSET, 2)
    except (OSError, AttributeError, TypeError):
        return False
    if not raw or len(raw) < 2:
        return False
    return int.from_bytes(raw[:2], "little") == 0


__all__ = [
    "poll_vision_cinematic",
    "poll_death_cinematic",
    "_current_hp_is_zero",
]
