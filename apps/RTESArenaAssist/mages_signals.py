# -*- coding: utf-8 -*-
"""mages_signals.py — 魔術師ギルド L4 の前景判別信号（完全分離・ローカル実装）。

観測結果のバッファマップの信号値に基づき、魔術師ギルドの会話子画面を
確定的に分類する。武具店/神殿/宿屋のコードを呼ばず、本ファイルに閉じて offset を
ローカル定数として保持する（中立な analyzer.read_bytes のみ使用）。
"""
from __future__ import annotations

# 前景判別フラグ（u8）
VIEW_FLAG_OFFSET = 0x8F74     # 51=メインメニュー / 65=サブメニュー / 81=Edit Effects / 00=ポップアップ
VIEW_TYPE_OFFSET = 0x8F7A     # B1=メイン / 97=購入サブ / 8A=盗む / 8F=Edit Effects / C7=ポップアップ
LIST_FLAG_OFFSET = 0xB7C4     # 00=一覧/選択 / 01=応答・詳細
DIALOG_ACTIVE_OFFSET = 0xA847  # 00=交渉(barter) / 3D=通常
TEXT_FAMILY_OFFSET = 0xA845   # 6F=メニュー/探知/作成族 / 70=購入族 / 59=効果族 / 71=盗む
SUBSTATE_OFFSET = 0xA83B      # 探知/作成等の補助サブ状態
VIEW_DESC_OFFSET = 0x8F6E     # 探知応答では low=2F
RESULT_HINT_OFFSET = 0xADB6   # 探知_不要=9A / 金額提示=0A
CURRENT_TEXT_PTR_OFFSET = 0xA844
RESPONSE_TEXT_OFFSET = 0x1044
MAGES_MENU_TEXT_OFFSET = 0x6F5C
NEGOTIATION_TEXT_OFFSET = 0x929E

VIEW_MENU = 0x51
VIEW_SUBMENU = 0x65
VIEW_EDIT_EFFECTS = 0x81
VIEW_POPUP = 0x00
TYPE_BUY_SUB = 0x97
TYPE_STEAL = 0x8A
TYPE_POPUP = 0xC7
LIST_ON = 0x00
DIALOG_NEGOTIATION = 0x00
DIALOG_NORMAL = 0x3D
FAMILY_MENU_DETECT_CREATE = 0x6F
DETECT_KNOWN_HINT = 0x9A
DETECT_COST_HINT = 0x0A
MAGES_MENU_PTR_START = 0x6F00
MAGES_MENU_PTR_END = 0x7040
DETECT_MAGIC_QUOTE_PREFIX = "I can tell you if that is magical"
DETECT_MAGIC_ALREADY_KNOWN = "You already know what that is!"
DETECT_MAGIC_IDENTIFIED = "The item is now identified in your inventory."
MENU_STATES = frozenset({
    "main_menu", "buy_submenu", "steal_menu", "edit_effects_menu",
})


def _u8(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 1)
    except (OSError, AttributeError):
        return None
    return raw[0] if raw else None


def _u16(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def _ascii_cstr(analyzer, anchor: int, off: int, length: int = 128) -> str:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError):
        return ""
    return raw.split(b"\x00", 1)[0].decode(
        "ascii", errors="replace").strip()


def _normalize_text(text: str) -> str:
    return " ".join((text or "").replace("\r", " ").replace("\n", " ").split())


def _contains_normalized(analyzer, anchor: int, off: int,
                         length: int, needle: str) -> bool:
    try:
        raw = analyzer.read_bytes(anchor + off, length)
    except (OSError, AttributeError):
        return False
    text = raw.decode("ascii", errors="replace").replace("\x00", " ")
    return needle in _normalize_text(text)


def read_signals(analyzer, anchor: int) -> dict:
    """魔術師ギルド判別信号を一括で読む。"""
    view_desc = _u16(analyzer, anchor, VIEW_DESC_OFFSET)
    return {
        "view": _u8(analyzer, anchor, VIEW_FLAG_OFFSET),
        "type": _u8(analyzer, anchor, VIEW_TYPE_OFFSET),
        "list": _u8(analyzer, anchor, LIST_FLAG_OFFSET),
        "dialog": _u8(analyzer, anchor, DIALOG_ACTIVE_OFFSET),
        "family": _u8(analyzer, anchor, TEXT_FAMILY_OFFSET),
        "sub": _u8(analyzer, anchor, SUBSTATE_OFFSET),
        "view_desc": view_desc,
        "view_desc_lo": (view_desc & 0xFF) if view_desc is not None else None,
        "result_hint": _u8(analyzer, anchor, RESULT_HINT_OFFSET),
    }


def classify(sig: dict) -> str:
    """信号から子画面種別を返す。

    返り値: main_menu / buy_submenu / steal_menu / edit_effects_menu /
            list / negotiation / reply / unknown
    """
    view = sig.get("view")
    if view == VIEW_MENU:
        return "main_menu"
    if view == VIEW_SUBMENU:
        if sig.get("type") == TYPE_STEAL:
            return "steal_menu"
        return "buy_submenu"
    if view == VIEW_EDIT_EFFECTS:
        return "edit_effects_menu"
    if view == VIEW_POPUP:
        if sig.get("list") == LIST_ON:
            return "list"
        if sig.get("dialog") == DIALOG_NEGOTIATION:
            return "negotiation"
        return "reply"
    return "unknown"


def detect_magic_reply_kind(sig: dict, img_name: str = "") -> str:
    """Detect Magic 応答前景の旧観測パターンを細分類する。

    探知応答は family=0x6F, B7C4=0x01,
    8F6E low=0x2F で、+0xADB6 が 0x9A（識別不要）または 0x0A
    （識別費提示）に分岐する。YESNO.IMG は交渉画像と同じなので、
    画像名だけでは分類しない。
    """
    img = (img_name or "").upper()
    if img not in ("NEWPOP.IMG", "YESNO.IMG", ""):
        return ""
    if sig.get("view") != VIEW_POPUP:
        return ""
    if sig.get("type") not in (None, TYPE_POPUP):
        return ""
    if sig.get("list") in (None, LIST_ON):
        return ""
    if sig.get("dialog") != DIALOG_NORMAL:
        return ""
    if sig.get("family") != FAMILY_MENU_DETECT_CREATE:
        return ""
    if sig.get("sub") not in (None, 0x00):
        return ""
    if sig.get("view_desc_lo") != 0x2F:
        return ""
    hint = sig.get("result_hint")
    if img == "NEWPOP.IMG" and hint == DETECT_KNOWN_HINT:
        return "detect_known"
    if img == "YESNO.IMG" and hint == DETECT_COST_HINT:
        return "detect_cost"
    return ""


def is_detect_magic_reply_foreground(sig: dict, img_name: str = "") -> bool:
    return bool(detect_magic_reply_kind(sig, img_name))


def detect_magic_reply_kind_from_memory(
        analyzer, anchor: int, img_name: str = "", sig: dict | None = None) -> str:
    """実メモリの表示バッファも含めて Detect Magic 応答を確定する。

    バッファは残留するため、`0x6F5C` や `0x1044` の本文だけでは前景にしない。
    まず L4 前景信号（一覧/メニュー/ポップアップ）を確定し、その内側で
    Detect Magic の本文バッファを読む。これにより一覧・メニュー復帰・交渉を
    探知応答が奪わない。
    """
    sig = sig if sig is not None else read_signals(analyzer, anchor)
    img = (img_name or "").upper()
    if img not in ("NEWPOP.IMG", "YESNO.IMG", ""):
        return ""
    if sig.get("dialog") != DIALOG_NORMAL:
        return ""

    state = classify(sig)
    if state == "list":
        return ""
    if state in MENU_STATES:
        return ""

    is_popup_reply = (
        sig.get("view") == VIEW_POPUP
        and sig.get("type") in (None, TYPE_POPUP)
        and sig.get("list") not in (None, LIST_ON)
    )
    if (img == "YESNO.IMG"
            and is_popup_reply
            and _contains_normalized(
                analyzer, anchor, NEGOTIATION_TEXT_OFFSET, 256,
                DETECT_MAGIC_IDENTIFIED)):
        return "detect_result"

    if sig.get("family") != FAMILY_MENU_DETECT_CREATE:
        return ""

    old_kind = detect_magic_reply_kind(sig, img_name)
    if old_kind:
        return old_kind

    current_ptr = _u16(analyzer, anchor, CURRENT_TEXT_PTR_OFFSET)
    known_text = _ascii_cstr(analyzer, anchor, MAGES_MENU_TEXT_OFFSET, 96)
    response_text = _normalize_text(
        _ascii_cstr(analyzer, anchor, RESPONSE_TEXT_OFFSET, 160))

    if (img == "NEWPOP.IMG"
            and sig.get("list") not in (None, LIST_ON)
            and isinstance(current_ptr, int)
            and MAGES_MENU_PTR_START <= current_ptr < MAGES_MENU_PTR_END
            and known_text == DETECT_MAGIC_ALREADY_KNOWN):
        return "detect_known"
    if (img == "YESNO.IMG"
            and is_popup_reply
            and DETECT_MAGIC_QUOTE_PREFIX in response_text):
        return "detect_cost"
    return ""


__all__ = [
    "VIEW_FLAG_OFFSET", "VIEW_TYPE_OFFSET", "LIST_FLAG_OFFSET",
    "DIALOG_ACTIVE_OFFSET", "TEXT_FAMILY_OFFSET", "SUBSTATE_OFFSET",
    "VIEW_DESC_OFFSET", "RESULT_HINT_OFFSET", "CURRENT_TEXT_PTR_OFFSET",
    "RESPONSE_TEXT_OFFSET", "MAGES_MENU_TEXT_OFFSET",
    "NEGOTIATION_TEXT_OFFSET",
    "VIEW_MENU", "VIEW_SUBMENU", "VIEW_EDIT_EFFECTS", "VIEW_POPUP",
    "TYPE_POPUP", "DIALOG_NORMAL", "FAMILY_MENU_DETECT_CREATE",
    "DETECT_KNOWN_HINT", "DETECT_COST_HINT",
    "DETECT_MAGIC_QUOTE_PREFIX", "DETECT_MAGIC_ALREADY_KNOWN",
    "DETECT_MAGIC_IDENTIFIED", "MENU_STATES",
    "read_signals", "classify", "detect_magic_reply_kind",
    "detect_magic_reply_kind_from_memory", "is_detect_magic_reply_foreground",
]
