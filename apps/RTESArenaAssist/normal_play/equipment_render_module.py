"""normal_play/equipment_render_module.py — 武具店 L4 会話の描画オーナー。

完全分離: 武具店店主会話の各子画面 (メニュー / 一覧) の判定・描画・
終了時整理を本モジュールに閉じて所有する。owner 名前空間は ``equipment_*`` 専用で、
宿屋 (tavern_render_module / shop_menu / shop_buy / shop_rooms / tavern state) には
一切流さない。共有するのは副作用なしの純粋 helper (build_menu_display /
translate_shop_menu_items / read_shop_item_list / translate_shop_item_list) と、
owner を引数で受ける UiRouter の汎用描画 API のみ。

Buy 武器/防具一覧は遠方バッファ (anchor+0x273B74 / +0x2752E4) を読み、
宿屋とは別 owner の ``equipment_list`` で表示する。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from types import SimpleNamespace

from session.facility_node import FacilityView

from normal_play.equipment_list_reader import (
    _read_list_items,
    _stabilize_list_items,
    _load_static_weapon_items,
    _LIST_STABLE_ATTR,
    _LIST_PENDING_ATTR,
)

_log = logging.getLogger("RTESArenaAssist")

# 武具店専用 owner 名前空間 (宿屋 shop_menu / shop_buy とは別物)
MENU_OWNER = "equipment_menu"
LIST_OWNER = "equipment_list"
NEGOTIATION_OWNER = "equipment_negotiation"
# 応答 owner は equipment_reply_module が定義する単一の真実を参照する
# (classify が前景を reply に確定する際の owner 名)。
from normal_play.equipment_reply_module import REPLY_OWNER  # noqa: E402

# 武具店の一覧 IMG: 武器=POPUP3 / 防具=POPUP4 / 売却・修理・盗み=NEWPOP
LIST_IMGS = ("POPUP3.IMG", "POPUP4.IMG", "NEWPOP.IMG")
_DIALOG_PTR = 0x001E
_REPLY_BLOCK_IMGS = frozenset({
    "YESNO.IMG",
    "FACES00.CIF",
    "STATUS.CIF",
})
_REPAIR_REPLY_PREFIXES = (
    "Your ",
    "Fixing that ",
    "Sure I could fix that ",
    "Fine. I can get it done in ",
    "Fine, I'll charge you ",
    "Then I'll get started",
    "Good, I'll get to it",
    "I understand. You might consider",
    "Well, if you change your mind",
    "Can't you afford it?",
    "Can't you wait that long?",
    "Maybe you're not interested?",
    "Which job do you wish to inspect?",
    "Sorry, I already have my hands full.",
)
_NEWPOP_REPAIR_PROMPT_PREFIXES = (
    "I can cut down the time",
    "I can cut the cost",
)
_NEWPOP_REPAIR_RESULT_PREFIXES = (
    "Then I'll get started",
    "Good, I'll get to it",
    "I understand. You might consider",
    "Well, if you change your mind",
)
_TERMINAL_REPLY_MIN_POLLS = 4
_TERMINAL_REPLY_MIN_SECONDS = 1.4
_NO_REPAIR_REPLY_MIN_SECONDS = 2.8
_MENU_RETURN_STABLE_POLLS = 2
# 前景判別フラグ (u8): メニュー表示=0x51 / ポップアップ表示=0x00。
# 武具店メニュー上に応答・見積り・一覧などのポップアップが重なっているかを
# 1 byte で確定判定し、終端応答の「保持」⇔「メニュー復帰」、および見積り/一覧
# 表示を時間・回数の推測に依存せず分離する。
_VIEW_FLAG_OFFSET = 0x8F74
_VIEW_FLAG_MENU = 0x51
_VIEW_FLAG_POPUP = 0x00
_VIEW_FLAG_MENU_STABLE_POLLS = 2
# 前景フラグを参照する画像 (メニュー/応答/見積り/一覧)。買い物一覧 POPUP3/4 は対象外。
_VIEW_FLAG_IMGS = frozenset({
    "MENU_RT.IMG", "YESNO.IMG", "NEWPOP.IMG", "FACES00.CIF", "STATUS.CIF",
})
_LIST_TITLES = {
    "POPUP3.IMG": ("Weapons", "武器一覧"),
    "POPUP4.IMG": ("Armor", "防具一覧"),
    "NEWPOP.IMG": ("Inventory", "所持品一覧"),
}
_MENU_KEY = "_equipment_menu_key_prev"
_LIST_KEY = "_equipment_list_key_prev"


@dataclass(frozen=True)
class EquipmentView(FacilityView):
    """武具店 L4 の単一判定 (1軸) 結論 (FacilityView 拡張, 宿屋 TavernView と同型)。

    ``classify_equipment_view`` が 1 poll に 1 回だけ前景子画面を確定し、
    ``render_equipment_view`` がこの結論を**消費するだけ**で描画する
    (描画側は前景判定を一切再計算しない = 完全分離 / 1軸化)。

    ``l4_kind`` / ``render_owner`` / ``reason`` は FacilityView 由来の共通 view 契約。
    以下のフィールドは描画分岐に必要な確定済み判定で、render が参照する。
    """
    # --- render が分岐に用いる確定済み前景判定 (classify で 1 回算出) ---
    img: str = ""
    shop_state: object = None          # fallback 補完後の解決済み shop_state
    is_negot_img: bool = False
    is_main_menu: bool = False
    terminal_reply_text: str = ""
    menu_foreground: bool = False
    reply_foreground: bool = False
    newpop_reply_foreground: bool = False
    newpop_no_repair_foreground: bool = False
    terminal_menu_foreground: bool = False
    menu_return_override: bool = False
    terminal_reply_hold_blocks_menu: bool = False
    terminal_reply_allows_list: bool = False
    negot_foreground: bool = False


def _resolve_equipment_l4(*, img, shop_state, is_main_menu, is_negot_img,
                          terminal_reply_text, menu_foreground,
                          reply_foreground, newpop_reply_foreground,
                          terminal_menu_foreground, menu_return_override,
                          terminal_reply_hold_blocks_menu,
                          terminal_reply_allows_list, negot_foreground):
    """確定済み判定から前景子画面 (l4_kind / owner / reason) を 1 つに確定する。

    描画分岐 (render_equipment_view) と同じ優先順位の要約。施設ノード共通の
    view 契約 (l4_kind / render_owner / reason) を満たす。
    """
    if menu_return_override and terminal_menu_foreground and is_main_menu:
        return ("menu", MENU_OWNER, "equipment_menu")
    if terminal_reply_text and not terminal_reply_allows_list:
        return ("reply", REPLY_OWNER, "equipment_reply")
    if (reply_foreground or newpop_reply_foreground
            or terminal_reply_hold_blocks_menu):
        return ("reply", REPLY_OWNER, "equipment_reply")
    if negot_foreground:
        return ("negotiation", NEGOTIATION_OWNER, "equipment_negotiation")
    if terminal_menu_foreground and is_main_menu:
        return ("menu", MENU_OWNER, "equipment_menu")
    if img in LIST_IMGS:
        return ("list", LIST_OWNER, "equipment_list")
    if menu_foreground:
        return ("menu", MENU_OWNER, "equipment_menu")
    if is_negot_img:
        return ("negotiation", NEGOTIATION_OWNER, "equipment_negotiation")
    if (not is_negot_img and shop_state is not None
            and getattr(shop_state, "kind", "") == "shop_menu"
            and getattr(shop_state, "owner_kind", "") == "equipment"):
        return ("menu", MENU_OWNER, "equipment_menu")
    return ("none", "", "equipment:seam")


def classify_equipment_view(w, *, shop_state=None, shop_img_name: str = "",
                            **_ignored) -> "EquipmentView":
    """武具店 L4 の前景子画面を 1 つだけ確定する単一判定 (1軸)。

    終端応答ホールド / メニュー復帰 / 前景フラグ追跡を含む**全前景判定をここに
    閉じる**。描画 (render_equipment_view) は本結論を消費するだけで前景を再判定
    しない (完全分離 / 1軸化)。状態追跡 (終端応答 / 前景フラグ) は
    1 poll に 1 回ここで実施する。
    """
    img = (shop_img_name or "").upper()
    is_negot_img = _is_negotiation_img(img)
    terminal_reply_text = _current_terminal_reply_text(w)
    _track_terminal_reply_display(w, terminal_reply_text)
    # 前景フラグはメニュー/応答/見積り/一覧の判別に使う。買い物一覧などフラグが
    # 無関係な画像では読まない (= 余計なメモリ読みと判定ブレを避ける)。
    if img in _VIEW_FLAG_IMGS:
        _track_view_flag(w)
    else:
        w._equipment_view_flag_value = None
        w._equipment_view_flag_menu_polls = 0
        w._equipment_view_menu_stable = False
    # 前景フラグがポップアップ(0x00)を明示する間は、残留抑制やメニュー文字列残りで
    # 見積り/一覧/応答をメニュー描画に奪われないようにする。
    view_popup_foreground = (
        getattr(w, "_equipment_view_flag_value", None) == _VIEW_FLAG_POPUP)
    suppressed_terminal_return = _has_suppressed_terminal_reply(w)

    if not is_equipment_menu_foreground(shop_state):
        fallback_menu_state = read_menu_rt_equipment_menu_state(w, img)
        if fallback_menu_state is not None:
            shop_state = fallback_menu_state
    menu_foreground = is_equipment_menu_foreground(shop_state)
    if (not menu_foreground
            and (terminal_reply_text or suppressed_terminal_return)
            and img in ("YESNO.IMG", "NEWPOP.IMG")):
        fallback_menu_state = read_menu_rt_equipment_menu_state(
            w, img, allow_sticky_img=True)
        if fallback_menu_state is not None:
            shop_state = fallback_menu_state
            menu_foreground = is_equipment_menu_foreground(shop_state)
    is_main_menu = is_main_equipment_menu_state(shop_state)
    reply_foreground = _has_equipment_reply_foreground(w, img)
    newpop_reply_foreground = (
        img == "NEWPOP.IMG"
        and (has_active_repair_reply_foreground(w)
             or has_newpop_repair_reply_foreground(w)))
    newpop_no_repair_foreground = (
        img == "NEWPOP.IMG" and has_newpop_no_repair_reply_foreground(w))
    terminal_menu_foreground = (
        menu_foreground
        or (terminal_reply_text
            and img == "MENU_RT.IMG"
            and is_main_menu)
    )
    menu_return_override = (
        terminal_menu_foreground
        and is_main_menu
        and not view_popup_foreground
        and (suppressed_terminal_return
             or _can_terminal_reply_return_to_menu(
                 w, terminal_reply_text, img, shop_state)))
    terminal_reply_hold_blocks_menu = (
        terminal_reply_text
        and terminal_menu_foreground
        and is_main_menu
        and not menu_return_override
    )
    terminal_reply_allows_list = (
        img in LIST_IMGS
        and _is_no_repair_terminal_reply_text(terminal_reply_text)
        and not newpop_reply_foreground
        and not newpop_no_repair_foreground
    )
    negot_foreground = (
        is_negot_img
        and (not menu_foreground or has_equipment_negotiation_foreground(w))
    )

    l4_kind, render_owner, reason = _resolve_equipment_l4(
        img=img, shop_state=shop_state, is_main_menu=is_main_menu,
        is_negot_img=is_negot_img, terminal_reply_text=terminal_reply_text,
        menu_foreground=menu_foreground, reply_foreground=reply_foreground,
        newpop_reply_foreground=newpop_reply_foreground,
        terminal_menu_foreground=terminal_menu_foreground,
        menu_return_override=menu_return_override,
        terminal_reply_hold_blocks_menu=terminal_reply_hold_blocks_menu,
        terminal_reply_allows_list=terminal_reply_allows_list,
        negot_foreground=negot_foreground)
    return EquipmentView(
        l4_kind=l4_kind, render_owner=render_owner,
        l4_visible=(l4_kind != "none"), reason=reason,
        img=img, shop_state=shop_state, is_negot_img=is_negot_img,
        is_main_menu=is_main_menu, terminal_reply_text=terminal_reply_text,
        menu_foreground=menu_foreground, reply_foreground=reply_foreground,
        newpop_reply_foreground=newpop_reply_foreground,
        newpop_no_repair_foreground=newpop_no_repair_foreground,
        terminal_menu_foreground=terminal_menu_foreground,
        menu_return_override=menu_return_override,
        terminal_reply_hold_blocks_menu=terminal_reply_hold_blocks_menu,
        terminal_reply_allows_list=terminal_reply_allows_list,
        negot_foreground=negot_foreground)


def render_equipment_view(w, *, view, shop_state=None, shop_img_name: str = "",
                          top_level_state: str = "normal-play",
                          **_ignored) -> tuple[bool, bool, bool, bool]:
    """classify_equipment_view の結論 (view) を消費して武具店子画面を所有描画する。

    前景判定は一切再計算せず view を参照するだけ (1軸化)。
    戻り値: (negot_handled, active_tmpl_handled, menu_visible, list_visible)。
    negotiation / active_template は poll_controller 後段の共有 L4 module 経路が
    処理するため本モジュールでは扱わず False を返す (= 二重描画回避)。
    """
    img = view.img
    shop_state = view.shop_state
    negot_visible = False
    menu_visible = False
    list_visible = False
    setattr(w, "_equipment_reply_polled_in_render", True)
    setattr(w, "_equipment_reply_handled_in_render", False)
    setattr(w, "_equipment_menu_return_override", False)

    if (view.terminal_reply_text and not view.menu_return_override
            and not view.terminal_reply_allows_list):
        if getattr(w, "_panel_owner", "") != "equipment_reply":
            if _poll_reply_first(w, img):
                _cleanup(w, menu_visible, list_visible, negot_visible)
                return (False, False, False, False)
        setattr(w, "_equipment_reply_handled_in_render", True)
        _cleanup(w, menu_visible, list_visible, negot_visible)
        return (False, False, False, False)

    if (not view.menu_return_override) and _poll_reply_first(w, img):
        _cleanup(w, menu_visible, list_visible, negot_visible)
        return (False, False, False, False)

    if ((view.reply_foreground or view.newpop_reply_foreground
            or view.terminal_reply_hold_blocks_menu)
            and not view.menu_return_override):
        setattr(w, "_equipment_reply_handled_in_render", True)
        if not (view.terminal_reply_text and view.menu_foreground
                and view.is_main_menu):
            _reset_menu_return_stability(w)
        _cleanup(w, menu_visible, list_visible, negot_visible)
        return (False, False, False, False)

    if view.negot_foreground:
        negot_visible = _render_negotiation(w, img, top_level_state)
        if negot_visible:
            _cleanup(w, menu_visible, list_visible, negot_visible)
            return (negot_visible, False, False, False)
    if view.terminal_menu_foreground and view.is_main_menu:
        if view.menu_return_override:
            setattr(w, "_equipment_menu_return_override", True)
            if view.terminal_reply_text:
                _mark_terminal_reply_suppressed(w, view.terminal_reply_text)
            _release_terminal_reply_after_menu_return(w)
        menu_visible = _render_menu(w, shop_state, img)
    elif img in LIST_IMGS:
        list_visible = _render_list(w, img)
    elif view.menu_foreground:
        menu_visible = _render_menu(w, shop_state, img)
    elif view.is_negot_img:
        negot_visible = _render_negotiation(w, img, top_level_state)
        _cleanup(w, menu_visible, list_visible, negot_visible)
        return (negot_visible, False, False, False)
    elif (not view.is_negot_img and shop_state is not None
            and shop_state.kind == "shop_menu"
            and getattr(shop_state, "owner_kind", "") == "equipment"):
        menu_visible = _render_menu(w, shop_state, img)

    _cleanup(w, menu_visible, list_visible, negot_visible)
    return (False, False, menu_visible, list_visible)


def poll_equipment_render(w, *, shop_state=None, shop_img_name: str = "",
                          top_level_state: str = "normal-play",
                          **_ignored) -> tuple[bool, bool, bool, bool]:
    """互換 entry: 判定 (classify) → 描画 (render) を 1 回ずつ実行する薄いラッパ。

    施設ノード経由 (poll_controller) では classify_view → render(view) と
    呼ぶため本関数は経由しない。tests / 後方互換のため判定描画を内部結線する。
    """
    view = classify_equipment_view(
        w, shop_state=shop_state, shop_img_name=shop_img_name)
    return render_equipment_view(
        w, view=view, shop_state=shop_state, shop_img_name=shop_img_name,
        top_level_state=top_level_state)


def _is_negotiation_img(img: str) -> bool:
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return False
    return get_negotiation_profile(img) is not None


def read_menu_rt_equipment_menu_state(
        w, img: str, *, allow_sticky_img: bool = False):
    """MENU_RT の武具店メニュー bytes から shop_state 揺れを補完する。"""
    img_u = (img or "").upper()
    if img_u != "MENU_RT.IMG" and not (
            allow_sticky_img and img_u in ("YESNO.IMG", "NEWPOP.IMG")):
        return None
    try:
        from popup11_response_reader import read_current_text_pointer
        from shop_menu_reader import (
            SHOP_MENU_BUFFER_MAXLEN,
            SHOP_MENU_BUFFER_OFFSET,
            parse_menu_groups,
            select_menu_group_by_ptr,
        )
        ptr = read_current_text_pointer(w._analyzer, w._anchor)
        raw = w._analyzer.read_bytes(
            w._anchor + SHOP_MENU_BUFFER_OFFSET,
            SHOP_MENU_BUFFER_MAXLEN)
        groups = parse_menu_groups(raw, base_offset=SHOP_MENU_BUFFER_OFFSET)
        group = select_menu_group_by_ptr(groups, ptr)
        if group is None and isinstance(ptr, int):
            group = _read_equipment_menu_group_near_ptr(w, ptr)
        if group is None:
            group = _fallback_equipment_menu_group(groups, w)
        if group is None:
            return None
        items = [it.text for it in group.items]
        hotkeys = [it.hotkey for it in group.items]
        item_key = tuple(items)
        if item_key == ("Buy", "Sell", "Repair", "Steal", "Exit"):
            title = "MENU OPTIONS"
        elif item_key == ("Weapon", "Armor"):
            title = "BUY OPTIONS"
        else:
            return None
        return SimpleNamespace(
            kind="shop_menu",
            owner_kind="equipment",
            menu_items=items,
            menu_item_hotkeys=hotkeys,
            menu_title_en=title,
            ptr=ptr,
        )
    except Exception:  # noqa: BLE001
        return None


def _read_equipment_menu_group_near_ptr(w, ptr: int):
    """0x8Axx 側など、0x725F 以外に置かれた武具店メニュー group を読む。"""
    if ptr < 0x200:
        return None
    try:
        from shop_menu_reader import parse_menu_groups, select_menu_group_by_ptr
        base = ptr - 0x200
        raw = w._analyzer.read_bytes(w._anchor + base, 0x400)
        groups = parse_menu_groups(raw, base_offset=base)
        return select_menu_group_by_ptr(groups, ptr)
    except Exception:  # noqa: BLE001
        return None


def _fallback_equipment_menu_group(groups, w):
    """ptr がメニュー項目外へ揺れた MENU_RT 復帰フレーム用の補完。"""
    exact_groups = []
    for group in groups:
        items = tuple(it.text for it in group.items)
        if items in (
                ("Buy", "Sell", "Repair", "Steal", "Exit"),
                ("Weapon", "Armor")):
            exact_groups.append(group)
    if len(exact_groups) == 1:
        return exact_groups[0]
    if getattr(w, "_panel_owner", "") == "equipment_reply":
        for group in exact_groups:
            if tuple(it.text for it in group.items) == (
                    "Buy", "Sell", "Repair", "Steal", "Exit"):
                return group
    try:
        from hierarchy_state import active_facility_session_name
        session_name = active_facility_session_name(w)
    except Exception:  # noqa: BLE001
        session_name = ""
    if session_name == "equipment":
        for group in exact_groups:
            if tuple(it.text for it in group.items) == (
                    "Buy", "Sell", "Repair", "Steal", "Exit"):
                return group
    return None


def _current_terminal_reply_text(w) -> str:
    text = (getattr(w, "_equipment_reply_current_text", "") or "").strip()
    if not text:
        return ""
    if text.startswith("Your "):
        if ("does not need any repairing" in text
                or text.endswith(" is ready.")):
            return text
        return ""
    if text.startswith(_NEWPOP_REPAIR_RESULT_PREFIXES):
        return text
    return ""


def _is_no_repair_terminal_reply_text(text: str) -> bool:
    text = (text or "").strip()
    return text.startswith("Your ") and "does not need any repairing" in text


def _terminal_reply_key(text: str) -> str:
    return " ".join((text or "").strip().split())


def _now() -> float:
    try:
        return time.monotonic()
    except Exception:  # noqa: BLE001
        return 0.0


def _track_terminal_reply_display(w, text: str) -> None:
    key = _terminal_reply_key(text)
    if not key:
        w._equipment_terminal_reply_key = ""
        w._equipment_terminal_reply_polls = 0
        w._equipment_terminal_reply_first_seen_at = None
        _reset_menu_return_stability(w)
        return
    prev = getattr(w, "_equipment_terminal_reply_key", "")
    if prev == key:
        w._equipment_terminal_reply_polls = (
            int(getattr(w, "_equipment_terminal_reply_polls", 0) or 0) + 1)
        if getattr(w, "_equipment_terminal_reply_first_seen_at", None) is None:
            w._equipment_terminal_reply_first_seen_at = _now()
    else:
        w._equipment_terminal_reply_key = key
        w._equipment_terminal_reply_polls = 1
        w._equipment_terminal_reply_first_seen_at = _now()
        _reset_menu_return_stability(w)


def _terminal_reply_visible_long_enough(w, text: str = "") -> bool:
    polls_ok = int(getattr(w, "_equipment_terminal_reply_polls", 0) or 0) >= (
        _TERMINAL_REPLY_MIN_POLLS)
    first_seen = getattr(w, "_equipment_terminal_reply_first_seen_at", None)
    if first_seen is None:
        return False
    min_seconds = (
        _NO_REPAIR_REPLY_MIN_SECONDS
        if _is_no_repair_terminal_reply_text(text)
        else _TERMINAL_REPLY_MIN_SECONDS
    )
    seconds_ok = (_now() - float(first_seen)) >= min_seconds
    return polls_ok and seconds_ok


def _reset_menu_return_stability(w) -> None:
    w._equipment_menu_return_candidate = None
    w._equipment_menu_return_stable_polls = 0


def _menu_return_is_stable(w, text: str, img: str, shop_state) -> bool:
    ptr = getattr(shop_state, "ptr", None)
    candidate = (_terminal_reply_key(text), (img or "").upper(), ptr)
    if getattr(w, "_equipment_menu_return_candidate", None) == candidate:
        w._equipment_menu_return_stable_polls = (
            int(getattr(w, "_equipment_menu_return_stable_polls", 0) or 0) + 1)
    else:
        w._equipment_menu_return_candidate = candidate
        w._equipment_menu_return_stable_polls = 1
    return int(getattr(w, "_equipment_menu_return_stable_polls", 0) or 0) >= (
        _MENU_RETURN_STABLE_POLLS)


def _mark_terminal_reply_suppressed(w, text: str) -> None:
    w._equipment_terminal_reply_suppressed_key = _terminal_reply_key(text)


def _has_suppressed_terminal_reply(w) -> bool:
    return bool(getattr(w, "_equipment_terminal_reply_suppressed_key", ""))


def _release_terminal_reply_after_menu_return(w) -> None:
    """メニュー復帰後に古い終端応答が次の一覧/応答を塞がないよう解放する。"""
    w._equipment_reply_hold_polls = 0
    w._equipment_reply_current_key = None
    w._equipment_reply_current_text = None
    w._equipment_terminal_reply_key = ""
    w._equipment_terminal_reply_polls = 0
    w._equipment_terminal_reply_first_seen_at = None
    _reset_menu_return_stability(w)


def _poll_reply_first(w, img: str) -> bool:
    """武具店応答をメニュー/一覧より先に描画し、L4 owner の競合を防ぐ。"""
    if img not in ("", "MENU_RT.IMG", "YESNO.IMG", "NEWPOP.IMG",
                   "FACES00.CIF", "STATUS.CIF"):
        return False
    if (img == "NEWPOP.IMG"
            and not (has_active_repair_reply_foreground(w)
                     or has_newpop_repair_reply_foreground(w)
                     or has_newpop_no_repair_reply_foreground(w))):
        return False
    try:
        from normal_play.equipment_reply_module import poll_equipment_reply
        handled = poll_equipment_reply(
            w,
            equipment_active=True,
            equipment_just_started=False,
            img_name=img,
            shop_menu_visible=False,
        )
    except Exception:  # noqa: BLE001
        _log.exception("equipment reply pre-render failed")
        return False
    setattr(w, "_equipment_reply_handled_in_render", bool(handled))
    return bool(handled)


def has_terminal_repair_reply_displayed(w) -> bool:
    """直前にメニュー復帰可能な修理終端応答を表示しているか。"""
    return bool(_current_terminal_reply_text(w))


def _read_view_flag(w):
    """前景判別フラグ (+0x8F74) の生バイトを読む。読めない場合は None。"""
    try:
        raw = w._analyzer.read_bytes(w._anchor + _VIEW_FLAG_OFFSET, 1)
    except Exception:  # noqa: BLE001
        return None
    return raw[0] if raw else None


def _track_view_flag(w) -> None:
    """前景フラグを毎 poll 読み、メニュー値が連続した回数を更新する。

    一瞬のブレ (1 poll だけ別値) を吸収するため、メニュー値が安定して続いた
    ときだけ「メニュー前景」と見なす。値が読めないフレームは安定状態を持ち越す。
    """
    val = _read_view_flag(w)
    w._equipment_view_flag_value = val
    if val is None:
        return
    if val == _VIEW_FLAG_MENU:
        w._equipment_view_flag_menu_polls = int(
            getattr(w, "_equipment_view_flag_menu_polls", 0) or 0) + 1
    else:
        w._equipment_view_flag_menu_polls = 0
    w._equipment_view_menu_stable = (
        int(getattr(w, "_equipment_view_flag_menu_polls", 0) or 0)
        >= _VIEW_FLAG_MENU_STABLE_POLLS)


def _can_terminal_reply_return_to_menu(w, text: str, img: str, shop_state) -> bool:
    if not text:
        return False
    if not is_main_equipment_menu_state(shop_state):
        return False
    # 主判定: 前景フラグが安定してメニューを示せば確定的に復帰し、ポップアップを
    # 示す間は応答を保持する (時間・ポーリング数・ptr 閾値の推測に依存しない)。
    if getattr(w, "_equipment_view_flag_value", None) is not None:
        return bool(getattr(w, "_equipment_view_menu_stable", False))
    # フラグが読めないフレームのみ従来の保持時間ベース判定にフォールバックする。
    if (img or "").upper() not in ("MENU_RT.IMG", "YESNO.IMG", "NEWPOP.IMG"):
        return False
    return _terminal_reply_visible_long_enough(w, text) and _menu_return_is_stable(
        w, text, img, shop_state)


def _has_equipment_reply_foreground(w, img: str) -> bool:
    """武具店応答表示中は背景メニュー描画で上書きしない。"""
    if img not in _REPLY_BLOCK_IMGS:
        return False
    current_text = getattr(w, "_equipment_reply_current_text", "") or ""
    hold_polls = int(getattr(w, "_equipment_reply_hold_polls", 0) or 0)
    if current_text and hold_polls > 0:
        return True
    try:
        from popup11_response_reader import read_response_candidates_all
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return False
    for cand in cands:
        if not cand.lookup_hit:
            continue
        text = cand.text or ""
        if text.startswith("Your ") and "repair" not in text:
            continue
        if text.startswith(_REPAIR_REPLY_PREFIXES):
            return True
    try:
        from active_template_reader import read_active_template_candidates
        import npc_dialog_lookup as _ndl
        active_cands = read_active_template_candidates(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        active_cands = []
        _ndl = None
    for cand in active_cands:
        text = (getattr(cand, "text", "") or "").strip()
        if not text.startswith(_REPAIR_REPLY_PREFIXES):
            continue
        try:
            if _ndl is not None and _ndl.lookup(text) is not None:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def has_newpop_repair_reply_foreground(w) -> bool:
    """NEWPOP の修理プロンプト/結果応答が前景にあるか。"""
    try:
        from popup11_response_reader import read_response_candidates_all
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return False
    for cand in cands:
        text = (getattr(cand, "text", "") or "").strip()
        if not getattr(cand, "lookup_hit", False):
            continue
        if text.startswith(_NEWPOP_REPAIR_PROMPT_PREFIXES):
            return True
        if text.startswith(_NEWPOP_REPAIR_RESULT_PREFIXES):
            return True
    return False


def has_newpop_no_repair_reply_foreground(w) -> bool:
    """NEWPOP 上の修理不要応答が前景候補にあるか。"""
    try:
        from popup11_response_reader import read_response_candidates_all
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return False
    for cand in cands:
        text = (getattr(cand, "text", "") or "").strip()
        if not getattr(cand, "lookup_hit", False):
            continue
        if _is_no_repair_terminal_reply_text(text):
            return True
    return False


def has_newpop_repair_prompt_foreground(w) -> bool:
    """互換用: NEWPOP の修理応答前景判定。"""
    return has_newpop_repair_reply_foreground(w)


def has_active_repair_reply_foreground(w) -> bool:
    """NEWPOP の修理応答 active slot が前景にあるか。"""
    try:
        from active_template_reader import read_active_template_candidates
        import npc_dialog_lookup as _ndl
        active_cands = read_active_template_candidates(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return False
    for cand in active_cands:
        text = (getattr(cand, "text", "") or "").strip()
        if not text.startswith(_REPAIR_REPLY_PREFIXES):
            continue
        try:
            if _ndl.lookup(text) is not None:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def _render_negotiation(w, img: str, top_level_state: str) -> bool:
    """武具店のアイテム交渉を equipment_negotiation owner で描画する。"""
    try:
        from normal_play.negotiation_module import (
            poll_negotiation,
            cleanup_if_owner as cleanup_negotiation,
        )
        handled = poll_negotiation(
            w, img_name=img, top_level_state=top_level_state,
            owner=NEGOTIATION_OWNER)
        if not handled:
            cleanup_negotiation(w, owner=NEGOTIATION_OWNER)
        return handled
    except Exception:  # noqa: BLE001
        _log.exception("equipment_negotiation update failed")
        return False


def _render_menu(w, shop_state, img: str) -> bool:
    """MENU OPTIONS / BUY OPTIONS 等のメニューを equipment_menu owner で描画。"""
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        owner_taken = (w._panel_owner != MENU_OWNER)
        if key_now != getattr(w, _MENU_KEY, None) or owner_taken:
            setattr(w, _MENU_KEY, key_now)
            # 武具店メニューは context-aware 直引き (公開版安全)。
            menu_tr = translate_shop_menu_items(items, owner_kind="equipment")
            title_en = shop_state.menu_title_en or ""
            title_ja = ((translate_ui_text("equipment", title_en) or title_en)
                        if title_en else "")
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(
                menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(
                MENU_OWNER, tab_en, tab_ja,
                panel_en=panel_en, panel_ja=panel_ja)
            _log.info(
                "equipment_menu update (img=%r title=%r items=%r "
                "owner_taken=%s)", img, title_en, items, owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("equipment_menu update failed")
    return True


def _render_list(w, img: str) -> bool:
    """一覧を equipment_list owner で描画する。"""
    title_en, title_ja = _LIST_TITLES.get(img, ("Items", "アイテム"))
    items = _stabilize_list_items(w, img, _read_list_items(w, img))
    try:
        owner_taken = (w._panel_owner != LIST_OWNER)
        tr = []
        source = ""
        if items:
            tr = items
            source = "memory"
        elif img == "POPUP3.IMG":
            tr = _load_static_weapon_items()
            source = "static_weapons"
        if tr:
            key_now = ("list", img, tuple(
                (it.get("en", ""), it.get("hands", ""),
                 it.get("protects", ""), it.get("protects_ja", ""),
                 it.get("weight", ""), it.get("price_display", ""))
                for it in tr))
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                _reset_reply_generation_for_list(w)
                # 施設専用 list intent (= 宿屋 shop_buy とは別 identity/mode)
                w._ui_router.update_facility_list(
                    LIST_OWNER, tr, title_en, title_ja)
                _log.info(
                    "equipment_list update (img=%r items=%d source=%s)",
                    img, len(tr), source)
        else:
            # 未解析: 施設専用 owner で「解析中」を表示 (宿屋一覧へ流さない)
            key_now = ("unparsed", img)
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                _reset_reply_generation_for_list(w)
                w._ui_router.update_translation(
                    LIST_OWNER,
                    f"{title_en} (list parsing...)",
                    f"{title_ja} (解析中)")
                _log.info("equipment_list unparsed placeholder (img=%r)", img)
    except Exception:  # noqa: BLE001
        _log.exception("equipment_list update failed")
    return True


def _reset_reply_generation_for_list(w) -> None:
    """一覧を新しい選択世代として扱い、同一修理応答の再表示を許可する。"""
    w._equipment_reply_text_by_offset = {}
    w._equipment_reply_current_key = None
    w._equipment_reply_current_text = None
    w._equipment_reply_baselined = False
    w._equipment_reply_hold_polls = 0
    w._equipment_terminal_reply_suppressed_key = ""
    w._equipment_terminal_reply_key = ""
    w._equipment_terminal_reply_polls = 0
    w._equipment_terminal_reply_first_seen_at = None
    _reset_menu_return_stability(w)


def is_main_equipment_menu_state(shop_state) -> bool:
    """POPUP*.IMG が残留していても、主メニュー検出時はメニューを優先する。"""
    if not (shop_state is not None and shop_state.kind == "shop_menu"
            and getattr(shop_state, "owner_kind", "") == "equipment"):
        return False
    title = getattr(shop_state, "menu_title_en", "") or ""
    items = tuple(getattr(shop_state, "menu_items", []) or [])
    return title == "MENU OPTIONS" or items == (
        "Buy", "Sell", "Repair", "Steal", "Exit")


def is_equipment_menu_foreground(shop_state) -> bool:
    """shop_state が現在前景の武具店メニューを指すかを判定する。

    NEGOTBUT.IMG は交渉完了後もしばらく残るため、画像名だけで交渉を優先すると
    REJECT/戻る直後の BUY OPTIONS を描けない。一方、対案入力/結果中は current ptr
    が 0x001E になり、背後のメニュー文字列が残っても shop menu として採用しない。
    """
    if not (shop_state is not None and shop_state.kind == "shop_menu"
            and getattr(shop_state, "owner_kind", "") == "equipment"):
        return False
    ptr = getattr(shop_state, "ptr", None)
    if ptr is None:
        return True
    try:
        return int(ptr) != _DIALOG_PTR
    except (TypeError, ValueError):
        return True


def has_equipment_negotiation_foreground(w) -> bool:
    """武具店交渉本文が現在前景にあるかを本文 active slot で確認する。

    金額提示中でも shop menu ptr が残る一方、本文側は
    `+0x987A` の active slot として前景に出る。REJECT 後の
    `NEGOTBUT.IMG` 残留ではこの本文前景 slot が無いため、メニュー復帰と分離する。
    """
    try:
        from negotiation_reader import (
            NEGOT_RENDERED_OFFSET, read_negotiation_diagnostic,
        )
        _raw, _canon, _rendered, matched = read_negotiation_diagnostic(
            w._analyzer, w._anchor)
        if not matched:
            return False
        from active_template_reader import read_active_template_candidates
        for c in read_active_template_candidates(w._analyzer, w._anchor):
            if getattr(c, "ptr", None) != NEGOT_RENDERED_OFFSET:
                continue
            text = (getattr(c, "text", "") or "").strip()
            if not text:
                return True
            head = text[: min(len(text), 48)]
            if matched.startswith(head) or text.startswith(matched[:48]):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _cleanup(w, menu_visible: bool, list_visible: bool,
             negot_visible: bool = False) -> None:
    """前景でない自施設 owner の残置を片付ける (自 owner のみ)。"""
    if not menu_visible and getattr(w, _MENU_KEY, None) is not None:
        setattr(w, _MENU_KEY, None)
        if w._panel_owner == MENU_OWNER:
            w._ui_router.clear_if_owner(MENU_OWNER)
    if not list_visible and getattr(w, _LIST_KEY, None) is not None:
        setattr(w, _LIST_KEY, None)
        setattr(w, _LIST_STABLE_ATTR, {})
        setattr(w, _LIST_PENDING_ATTR, {})
        try:
            if w._tab_translate.panel_mode() == "facility_list":
                w._ui_router.set_panel_mode("translate")
        except AttributeError:
            pass
        if w._panel_owner == LIST_OWNER:
            w._ui_router.clear_if_owner(LIST_OWNER, mode="translate")
    if not negot_visible:
        try:
            from normal_play.negotiation_module import (
                cleanup_if_owner as cleanup_negotiation,
            )
            cleanup_negotiation(w, owner=NEGOTIATION_OWNER)
        except Exception:  # noqa: BLE001
            _log.exception("equipment_negotiation cleanup failed")


__all__ = [
    "poll_equipment_render", "classify_equipment_view",
    "render_equipment_view", "EquipmentView",
    "MENU_OWNER", "LIST_OWNER", "LIST_IMGS",
    "NEGOTIATION_OWNER", "is_main_equipment_menu_state",
    "is_equipment_menu_foreground", "has_equipment_negotiation_foreground",
    "has_active_repair_reply_foreground",
    "has_newpop_repair_reply_foreground",
    "has_newpop_repair_prompt_foreground",
    "has_terminal_repair_reply_displayed",
    "read_menu_rt_equipment_menu_state",
]
