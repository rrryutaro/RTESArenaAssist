"""normal_play/mages_guild_render_module.py — 魔術師ギルド L4 会話の描画オーナー。

完全分離: ギルド会話の各子画面 (メニュー / サブメニュー / 一覧 /
Spellmaker / 応答) の判定・描画・終了時整理を本モジュールに閉じて所有する。owner
名前空間は ``mages_*`` 専用で、宿屋・武具店・神殿には一切流さない。再利用したい処理
(前景フラグ読み・一覧パース・FORM 数値読み) は魔術師ギルド系のローカルモジュール
(``mages_signals`` / ``mages_list_reader`` / ``mages_spellmaker``) に閉じてコピー実装し、
他施設の render/reply/list/negotiation 関数は呼ばない。

共有してよいのは副作用なしの中立 helper のみ:
``shop_menu_reader`` (メニュー項目翻訳) / ``shop_render_common.build_menu_display`` /
``popup11_response_reader`` (現在描画ptr) / ``mages_reply_module`` (自施設 owner)。
"""
from __future__ import annotations

import logging
import re

from normal_play.mages_render_common import (
    _SPELLDETAIL_KEY,
    _NPC_DIALOG_OFFSET,
    _PROMPT_EXTRA_SCAN_OFFSETS,
    _read_cost_string,
    _casting_cost_from_spell_cost,
    _buy_price_for,
)
from normal_play.mages_spellmaker_render import (
    _SPELL_KEY,
    _SPELLMAKER_LIST_TITLES,
    _SPELLMAKER_PROMPT_LITERALS,
    _SPELLMAKER_PROMPT_FRAGMENT_LITERALS,
    _SPELLMAKER_REFRESH_DETAIL_PROMPTS,
    _read_spellmaker_live_spell_cost,
    _resolve_spellmaker_spell_cost,
    _resolve_spellmaker_prompt,
)

_log = logging.getLogger("RTESArenaAssist")

# ギルド専用 owner 名前空間 (宿屋 / 武具店 owner とは別物)
MENU_OWNER = "mages_menu"
LIST_OWNER = "mages_list"
SPELLMAKER_OWNER = "mages_spellmaker"
EFFECT_MENU_OWNER = "mages_effect_menu"

# ギルドの一覧 IMG: 魔法アイテム=POPUP7 / 呪文・対象/効果=POPUP / 購入呪文・所持品=NEWPOP
LIST_IMGS = ("POPUP7.IMG", "POPUP.IMG", "NEWPOP.IMG")
SPELLMAKER_IMG = "SPELLMKR.IMG"
BUYSPELL_IMG = "BUYSPELL.IMG"
MENU_OWNER_CONFIRM = "mages_confirm"
MENU_OWNER_SPELLDETAIL = "mages_spelldetail"
NEGOTIATION_OWNER = "mages_negotiation"
# 確認ダイアログ（YESNO「Are you sure ?」）は text family=0x4B で判定できる
# （通常の作成族 0x6F / 購入族 0x70 とは別値）。本文テンプレは anchor+0x4B50。
_CONFIRM_FAMILY = 0x4B
_CONFIRM_DIALOG_OFFSET = 0x4B50
# 確認ダイアログ翻訳（自施設分離内・ローカル）
_CONFIRM_TR = {
    "Are you sure ?": "本当によろしいですか？",
    "Are you sure": "本当によろしいですか？",
    "Yes": "はい",
    "No": "いいえ",
}
# 購入/探知フロー等の応答プロンプト（npc_dialog 領域 0x1044 に描画される）
MENU_OWNER_PROMPT = "mages_prompt"
_PROMPT_KEY = "_mages_prompt_key_prev"
_MAGES_MENU_TEXT_OFFSET = 0x6F5C
_MAGES_MENU_PTR_START = 0x6F00
_MAGES_MENU_PTR_END = 0x7040
_PROMPT_CACHE_ATTR = "_mages_prompt_resolve_cache"
# 応答プロンプトの文末（? ! .）。一文を切り出して辞書照合する。
_RESPONSE_END_RE = re.compile(r"[?!.]")
_DETECT_MAGIC_QUOTE_PREFIX = "I can tell you if that is magical"
_DETECT_MAGIC_ALREADY_KNOWN = "You already know what that is!"
# 一覧の torn-read（バッファ再描画中の部分読み）抑制用の安定化キャッシュ。
# 武具店の _stabilize_list_items と同型を魔術師ギルド分離内にローカルコピー。
_LIST_STABLE_ATTR = "_mages_list_stable_by_key"
_LIST_PENDING_ATTR = "_mages_list_pending_by_key"
_LIST_STABLE_CONFIRM = 3
_LIST_TITLE_ATTR = "_mages_list_title_en"
_MENU_KEY = "_mages_menu_key_prev"
_LIST_KEY = "_mages_list_key_prev"
_EFFECT_MENU_KEY = "_mages_effect_menu_key_prev"
_CONFIRM_KEY = "_mages_confirm_key_prev"


def poll_mages_render(w, *, view=None, shop_state=None, shop_img_name: str = "",
                      top_level_state: str = "",
                      **_ignored) -> tuple[bool, bool, bool, bool]:
    """魔術師ギルドの子画面を自施設 owner で描画する。

    戻り値: (negot_handled, active_tmpl_handled, menu_visible, list_visible)。
    価格交渉(NEGOTBUT/YESNO)は武具店と同型に自施設 owner(mages_negotiation)で
    描画する（共有 negotiation owner は施設 owner でなく表示不変条件に弾かれ
    古い一覧が残るため）。active_template は後段の共有経路が処理する。
    """
    img = (shop_img_name or "").upper()
    menu_visible = False
    list_visible = False
    spell_visible = False
    effect_menu_visible = False
    prompt_visible = False
    negot_visible = False
    reply_visible = False
    confirm_visible = False
    detail_visible = False

    # 判定は MagesGuildNode.classify_view が単一の真実 (分離化: classify→render
    # セット)。本関数は view.l4_kind を消費して対応する _render_* を呼ぶのみで、
    # 信号/img からの前景再判定はしない。spellmaker/list の描画本体は中立 reader
    # を呼ぶため信号 (sig) と数値入力画面判定 (is_form_img) のみ読む。
    sig = _read_signals(w)
    state = _classify(sig)
    is_form_img = (img.startswith("FORM") and img.endswith(".IMG"))
    view_kind = (getattr(view, "l4_kind", "") or "")

    if view_kind == "confirm":
        confirm_visible = _render_confirm(w)
        spell_visible = confirm_visible
    elif view_kind == "effect_menu":
        effect_menu_visible = _render_effect_menu(w)
    elif view_kind == "menu":
        menu_visible = _render_menu(w, shop_state, img)
    elif view_kind == "negotiation":
        # 価格交渉本文を mages_negotiation owner で翻訳描画（武具店 _render_negotiation
        # と同型・中立 negotiation_module を自施設 owner で呼ぶ）。
        negot_visible = _render_negotiation(w, img, top_level_state)
    elif view_kind == "spelldetail":
        # 呪文購入の詳細（SPELLBOOK パーチメント）。確定済み呪文なので中立
        # spell_reader で読み、同体裁で表示する。
        detail_visible = _render_buyspell_detail(w)
    elif view_kind == "spellmaker" and is_form_img:
        spell_visible = _render_spellmaker(w, sig, form_img=img)
    elif view_kind == "spellmaker":
        if _render_spellmaker_prompt_overlay(w, sig):
            prompt_visible = True
            spell_visible = True
        else:
            spell_visible = _render_spellmaker(w, sig)
    elif view_kind == "prompt":
        prompt_visible = _render_buy_prompt(w)
    elif view_kind == "reply":
        reply_visible = _render_reply(w, img)
    elif view_kind == "list":
        if _is_spellmaker_return_from_residual_list(w, sig, img, state):
            spell_visible = _render_spellmaker(w, sig)
        else:
            list_visible = _render_list(w, sig, img)
    # view_kind == "" (seam) は何も描かない。active template 等は共有経路へ委譲し、
    # _cleanup が自施設 owner の残骸を確実に片付ける。

    _cleanup(w, menu_visible, list_visible, spell_visible, confirm_visible,
             prompt_visible, detail_visible, negot_visible,
             effect_menu_visible, reply_visible)
    # 交渉は negot_handled=True で返し、後段共有 negotiation の二重描画を抑止する。
    # spellmaker / 確認 / プロンプト / 詳細は後段 gate へは list_visible として伝える。
    return (negot_visible, False, menu_visible,
            list_visible or spell_visible or confirm_visible
            or prompt_visible or detail_visible or effect_menu_visible
            or reply_visible)


def _read_signals(w) -> dict:
    try:
        from mages_signals import read_signals
        return read_signals(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return {}


def _classify(sig: dict) -> str:
    try:
        from mages_signals import classify
        return classify(sig)
    except Exception:  # noqa: BLE001
        return "unknown"


def _read_current_ptr(w):
    try:
        from popup11_response_reader import read_current_text_pointer
        return read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return None


def _render_menu(w, shop_state, img: str) -> bool:
    """MENU OPTIONS / PICK ITEM / Edit Effects 等を mages_menu owner で描画。"""
    try:
        from shop_menu_reader import translate_shop_menu_items, translate_ui_text
        from normal_play.shop_render_common import build_menu_display
        items = shop_state.menu_items
        hotkeys = shop_state.menu_item_hotkeys
        key_now = (tuple(items), tuple(hotkeys))
        owner_taken = (w._panel_owner != MENU_OWNER)
        if key_now != getattr(w, _MENU_KEY, None) or owner_taken:
            setattr(w, _MENU_KEY, key_now)
            # ギルドメニューは context-aware 直引き。
            menu_tr = translate_shop_menu_items(items, owner_kind="mages_guild")
            title_en = shop_state.menu_title_en or ""
            title_ja = ((translate_ui_text("mages_guild", title_en) or title_en)
                        if title_en else "")
            tab_en, tab_ja, panel_en, panel_ja = build_menu_display(
                menu_tr, hotkeys, title_en, title_ja)
            w._ui_router.update_translation(
                MENU_OWNER, tab_en, tab_ja,
                panel_en=panel_en, panel_ja=panel_ja)
            _log.info(
                "mages_menu update (img=%r title=%r items=%r owner_taken=%s)",
                img, title_en, items, owner_taken)
    except Exception:  # noqa: BLE001
        _log.exception("mages_menu update failed")
    return True


def _render_effect_menu(w) -> bool:
    """Spellmaker の Edit Effects を詳細タブ維持の下部パネル overlay として表示する。"""
    title_en = "Edit Effects"
    items = ["Add", "Modify", "Delete"]
    en = title_en + "".join(f"\n  {item}" for item in items)
    title_ja = _translate_ui(title_en)
    ja = title_ja + "".join(f"\n  {_translate_ui(item)}" for item in items)
    try:
        key_now = ("effect_menu", en)
        if key_now != getattr(w, _EFFECT_MENU_KEY, None):
            setattr(w, _EFFECT_MENU_KEY, key_now)
            _log.info("mages_effect_menu update")
        if not _render_spellmaker_detail(
                w, panel_en=en, panel_ja=ja,
                reason="mages_effect_menu_overlay"):
            w._ui_router.update_translation(
                EFFECT_MENU_OWNER, en, ja,
                panel_en=en, panel_ja=ja,
                update_tab=False,
                update_panel=True,
                keep_owner=True,
                mode=None,
                priority=95,
                reason="mages_effect_menu")
    except Exception:  # noqa: BLE001
        _log.exception("mages_effect_menu update failed")
    return True


# 一覧バッファ選択: family(0xA845) + img + 現在描画ptr で確定
def _select_list_source(w, sig: dict, img: str):
    """(title_en, title_ja, items) を返す。読めなければ items 空。"""
    from mages_list_reader import (
        POTION_LIST_OFFSET, SPELL_LIST_OFFSET, INVENTORY_LIST_OFFSET,
        SPELLMAKER_TARGET_OFFSET, SPELLMAKER_EFFECT_OFFSET,
        SPELLMAKER_SUBLIST_OFFSET, EFFECT_PICK_OFFSET,
        read_priced_list, read_name_list, read_magic_item_list,
        read_active_priced_list, looks_like_potion_list,
        read_active_list_offset, classify_spellmaker_name_items,
        enrich_unidentified_by_index,
    )
    family = sig.get("family")
    cur = _read_current_ptr(w)
    cur = cur if isinstance(cur, int) else 0

    def _classified(offset: int):
        items = read_name_list(w._analyzer, w._anchor, offset)
        return classify_spellmaker_name_items(items)

    # 効果選択（削除/修正） family=0x59 → 0x1044
    if family == 0x59:
        tried: set[int] = set()
        ptr = read_active_list_offset(w._analyzer, w._anchor)
        for off in (ptr, EFFECT_PICK_OFFSET):
            if off is None or off in tried:
                continue
            tried.add(off)
            classified = _classified(off)
            if classified:
                return classified
        return ("Effects", "効果一覧", [])
    # 購入族 family=0x70
    if family == 0x70:
        if img == "POPUP7.IMG":
            # 魔法アイテム: 名前先・価格後の遠隔バッファをシグネチャ走査で読む
            return ("Magic Items", "魔法アイテム一覧",
                    read_magic_item_list(w._analyzer, w._anchor))
        # NEWPOP: ポーション/呪文。固定 offset では判別不能（非アクティブ buffer に
        # 旧データが残る）ため、アクティブ一覧ポインタで実際の一覧を取得し、内容
        # （Potion of 接頭辞）で見出しを決める。
        items = read_active_priced_list(w._analyzer, w._anchor)
        if items:
            if looks_like_potion_list(items):
                return ("Potions", "ポーション一覧", items)
            return ("Spells", "呪文一覧", items)
        # ポインタが取れない場合の従来フォールバック
        if SPELL_LIST_OFFSET <= cur < 0x9C00:
            return ("Spells", "呪文一覧",
                    read_priced_list(w._analyzer, w._anchor, SPELL_LIST_OFFSET))
        return ("Potions", "ポーション一覧",
                read_priced_list(w._analyzer, w._anchor, POTION_LIST_OFFSET))
    # メニュー/探知/作成族 family=0x6F
    if family == 0x6F:
        if img == "NEWPOP.IMG":
            # 所持品（Detect Magic）: アクティブ一覧ポインタ優先、無ければ固定 offset
            off = read_active_list_offset(w._analyzer, w._anchor)
            inv_items = read_name_list(w._analyzer, w._anchor,
                                       off if off else INVENTORY_LIST_OFFSET)
            # 各行に未鑑定フラグを付与（行順序はインベントリ構造体順と一致）。
            inv_items = enrich_unidentified_by_index(
                w._analyzer, w._anchor, inv_items)
            return ("Inventory", "所持品一覧", inv_items)
        # POPUP: 対象/効果/効果サブ。現在ptr では確実に判別できないため、
        # アクティブ一覧ポインタが指す実際の一覧を読み、先頭エントリ（ゲーム定数）で
        # 見出しを確定する。対象は必ず "Caster only" 始まり、効果は必ず "Cause" 始まり。
        ptr = read_active_list_offset(w._analyzer, w._anchor)
        if ptr is not None:
            classified = _classified(ptr)
            if classified:
                return classified
        # ポインタが取れない場合の従来フォールバック（現在ptr 範囲判別）
        if 0x5561 <= cur < 0x5690:
            classified = _classified(SPELLMAKER_SUBLIST_OFFSET)
            if classified:
                return classified
            return ("Effect Options", "効果オプション", [])
        if 0x5690 <= cur < 0x5800:
            classified = _classified(SPELLMAKER_TARGET_OFFSET)
            if classified:
                return classified
            return ("Targets", "対象一覧", [])
        classified = _classified(SPELLMAKER_EFFECT_OFFSET)
        if classified:
            return classified
        return ("Effects", "効果一覧", [])
    return ("Items", "一覧", [])


def _list_signature(items: list[dict]) -> tuple:
    """一覧の同一性判定用シグネチャ（名前＋価格＋未鑑定）。

    未鑑定フラグを含めることで、鑑定により所持品一覧の表示が変わったときに
    torn-read 抑制を抜けて再描画される。
    """
    return tuple(
        (it.get("en", ""), it.get("price_display", ""),
         it.get("is_unidentified", False)) for it in items)


def _stabilize_list(w, list_key: str, items: list[dict]) -> list[dict]:
    """一覧バッファ再描画中の torn-read（部分/空読み）を抑制する。

    一覧種別 (list_key=title_en) ごとに直近の安定リストを保持し、
    空・短い候補は直前の安定リストを返す。短い候補は連続 N 回同じ内容に
    なるまで採用しない（武具店 _stabilize_list_items 同型のローカルコピー）。
    """
    if not list_key:
        return items
    stable_by_key = getattr(w, _LIST_STABLE_ATTR, None)
    if stable_by_key is None:
        stable_by_key = {}
    pending_by_key = getattr(w, _LIST_PENDING_ATTR, None)
    if pending_by_key is None:
        pending_by_key = {}
    stable = stable_by_key.get(list_key, [])
    if not stable:
        if items:
            stable_by_key[list_key] = [dict(it) for it in items]
            setattr(w, _LIST_STABLE_ATTR, stable_by_key)
        return items
    if not items:
        _log.info("mages_list transient empty suppressed (key=%r)", list_key)
        return [dict(it) for it in stable]

    stable_sig = _list_signature(stable)
    sig = _list_signature(items)
    if sig == stable_sig:
        pending_by_key.pop(list_key, None)
        setattr(w, _LIST_PENDING_ATTR, pending_by_key)
        return [dict(it) for it in stable]

    if len(items) < len(stable):
        prev_sig, count = pending_by_key.get(list_key, (None, 0))
        count = count + 1 if prev_sig == sig else 1
        pending_by_key[list_key] = (sig, count)
        setattr(w, _LIST_PENDING_ATTR, pending_by_key)
        if count < _LIST_STABLE_CONFIRM:
            _log.info(
                "mages_list transient partial suppressed "
                "(key=%r stable=%d candidate=%d count=%d)",
                list_key, len(stable), len(items), count)
            return [dict(it) for it in stable]

    stable_by_key[list_key] = [dict(it) for it in items]
    pending_by_key.pop(list_key, None)
    setattr(w, _LIST_STABLE_ATTR, stable_by_key)
    setattr(w, _LIST_PENDING_ATTR, pending_by_key)
    return items


def _render_list(w, sig: dict, img: str) -> bool:
    """魔術師ギルドの一覧を mages_list owner で描画（ローカルバッファ選択）。"""
    try:
        title_en, title_ja, items = _select_list_source(w, sig, img)
    except Exception:  # noqa: BLE001
        _log.exception("mages_list source select failed")
        title_en, title_ja, items = ("Items", "一覧", [])
    setattr(w, _LIST_TITLE_ATTR, title_en)
    # torn-read 抑制（一覧種別ごとに安定化）
    items = _stabilize_list(w, title_en, items)
    try:
        owner_taken = (w._panel_owner != LIST_OWNER)
        if items:
            key_now = ("list", title_en, tuple(
                (it.get("en", ""), it.get("price_display", ""),
                 it.get("is_unidentified", False)) for it in items))
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_facility_list(
                    LIST_OWNER, items, title_en, title_ja,
                    priority=90, reason=f"mages_list:{title_en}")
                _log.info("mages_list update (img=%r title=%r items=%d)",
                          img, title_en, len(items))
        else:
            key_now = ("unparsed", img)
            if key_now != getattr(w, _LIST_KEY, None) or owner_taken:
                setattr(w, _LIST_KEY, key_now)
                w._ui_router.update_translation(
                    LIST_OWNER,
                    f"{title_en} (list parsing...)",
                    f"{title_ja} (解析中)",
                    priority=90,
                    reason=f"mages_list_unparsed:{title_en}")
                _log.info("mages_list unparsed placeholder (img=%r)", img)
    except Exception:  # noqa: BLE001
        _log.exception("mages_list update failed")
    return True


def _render_spellmaker(w, sig: dict, form_img: str = "") -> bool:
    """Spellmaker 画面を mages_spellmaker owner で描画する。

    form_img（FORMn.IMG）が与えられれば数値入力画面として FORM 値を表示し、
    そうでなければ Spellmaker 背景を spell_detail 体裁で表示する。
    """
    if not form_img:
        return _render_spellmaker_detail(w)
    try:
        tab_en, tab_ja, panel_en, panel_ja = _spellmaker_display(
            w, sig, form_img)
        owner_taken = (w._panel_owner != SPELLMAKER_OWNER)
        key_now = ("spellmaker", tab_en)
        if key_now != getattr(w, _SPELL_KEY, None) or owner_taken:
            setattr(w, _SPELL_KEY, key_now)
            # 数値入力ではパネルはタイトルのみ、翻訳タブはタイトル+原文+訳。
            w._ui_router.update_translation(
                SPELLMAKER_OWNER, tab_en, tab_ja,
                panel_en=panel_en, panel_ja=panel_ja)
            _log.info("mages_spellmaker update: %r", tab_en[:60])
    except Exception:  # noqa: BLE001
        _log.exception("mages_spellmaker update failed")
    return True


def _render_spellmaker_detail(
        w, *, panel_en: str = "", panel_ja: str = "",
        reason: str = "mages_spellmaker_detail") -> bool:
    """Spellmaker 背景を mages_spellmaker owner の呪文詳細として表示する。"""
    try:
        from spell_reader import read_spell_detail
        from mages_list_reader import translate_name
        data = read_spell_detail(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("mages_spellmaker detail read failed")
        return False

    name = (data.get("name") or "").strip()
    translated_name = translate_name(name) if name else ""
    data["name_ja"] = translated_name if translated_name != name else ""
    casting_cost = _read_cost_string(w)
    spell_cost = _resolve_spellmaker_spell_cost(
        w, data, casting_cost=casting_cost)
    data["spell_cost"] = spell_cost
    if casting_cost is not None:
        data["casting_cost"] = casting_cost
    else:
        data["casting_cost"] = _casting_cost_from_spell_cost(
            spell_cost, data.get("player_level")) if spell_cost else 0
    # 新規作成直後は効果未設定。0x1044 の残留文を拾わないよう明示的に空表示する。
    if all(x == 0xFF for x in data.get("effects", [])):
        data["effect_en"] = ""
        data["effect_ja"] = ""
        data["text_en"] = ""
        data["text_ja"] = ""
    if not panel_en and not panel_ja:
        panel_en = "Spellmaker"
        panel_ja = "呪文作成"
    try:
        key_now = (
            "spellmaker_detail", data.get("name"), data.get("target_id"),
            data.get("element_id"), tuple(data.get("effects", [])),
            data.get("cost"), data.get("spell_cost"),
            data.get("casting_cost"), data.get("text_en"),
            tuple(
                (d.get("effect_en", ""), d.get("text_en", ""),
                 d.get("text_ja", ""))
                for d in (data.get("effect_details") or [])
                if isinstance(d, dict)
            ))
        key_changed = key_now != getattr(w, _SPELL_KEY, None)
        owner_taken = (w._panel_owner != SPELLMAKER_OWNER)
        try:
            mode_taken = w._tab_translate.panel_mode() != "spell_detail"
        except (AttributeError, RuntimeError):
            mode_taken = False
        setattr(w, _SPELL_KEY, key_now)
        w._ui_router.propose_spell_detail(
            SPELLMAKER_OWNER, data, panel_en=panel_en, panel_ja=panel_ja,
            priority=90, reason=reason)
        if key_changed or owner_taken or mode_taken:
            _log.info("mages_spellmaker detail update: %r", name)
    except Exception:  # noqa: BLE001
        _log.exception("mages_spellmaker detail update failed")
    return True


def _spellmaker_display(w, sig: dict, form_img: str = "") -> tuple[
        str, str, str, str]:
    """(tab_en, tab_ja, panel_en, panel_ja) を返す。

    数値入力（FORMn.IMG）はゲーム画面の行構成を再現し、Spell Cost も併記する。
    パネルは効果タイトルのみ（数値はゲーム画面に出ているため）、翻訳タブは
    タイトル + 原文レイアウト + 訳レイアウト + Spell Cost を表示する。
    """
    if form_img:
        try:
            from mages_spellmaker import (
                read_form_values, field_label_ja, format_form_layout,
                format_form_display_html,
                resolve_edit_slot, resolve_effect_title_from_record)
            form = form_img[:-4] if form_img.endswith(".IMG") else form_img
            title = _read_effect_title(w)
            if not title:
                title = resolve_effect_title_from_record(
                    w._analyzer, w._anchor, form)
            head_en = title or "Spell Effect"
            if title:
                try:
                    from mages_list_reader import translate_name
                    head_ja = translate_name(title)
                except Exception:  # noqa: BLE001
                    head_ja = _translate_ui(title)
            else:
                head_ja = "呪文効果"
            slot = resolve_edit_slot(w._analyzer, w._anchor, title)
            vals = read_form_values(w._analyzer, w._anchor, form, slot=slot)
            en_lines, ja_only_lines = format_form_layout(form, vals)
            cost = _read_cost_string(w)
            if not en_lines:
                # レイアウト未定義 FORM はラベル:値の素直な並びにフォールバック。
                en_lines = [f"{k}: {v}" for k, v in vals.items()]
                ja_only_lines = [f"{k} / {field_label_ja(k)}: {v}"
                                 for k, v in vals.items()]
            if cost is not None:
                en_lines = list(en_lines) + [f"Spell Cost: {cost}"]
            tab_en = head_en + ("\n" + "\n".join(en_lines) if en_lines else "")
            if ja_only_lines or cost is not None:
                tab_ja = format_form_display_html(
                    form, vals, cost=cost, title_en=head_en, title_ja=head_ja)
            else:
                head_display_ja = (
                    f"{head_en} {head_ja}"
                    if head_en and head_ja and head_en != head_ja
                    else (head_ja or head_en))
                tab_ja = head_display_ja
            # パネルはタイトルのみ（数値はゲーム画面に表示済み）。
            return tab_en, tab_ja, head_en, head_ja
        except Exception:  # noqa: BLE001
            _log.exception("spellmaker form read failed")
    en = "Spellmaker (New Spell / Buy Spell / Exit)"
    ja = "呪文作成 (新規呪文 / 呪文購入 / 終了)"
    return en, ja, en, ja


def _render_spellmaker_prompt_overlay(w, sig: dict) -> bool:
    """Spellmaker 背景上の応答プロンプトを下部パネルだけで表示する。"""
    info = _resolve_spellmaker_prompt(w, sig)
    if not info:
        return False
    en, ja = info
    if en in _SPELLMAKER_REFRESH_DETAIL_PROMPTS:
        if _render_spellmaker_detail(
                w, panel_en=en, panel_ja=ja,
                reason="mages_prompt_overlay"):
            return True
    try:
        key_now = ("prompt_overlay", en)
        if key_now != getattr(w, _PROMPT_KEY, None):
            setattr(w, _PROMPT_KEY, key_now)
            _log.info("mages_prompt overlay update: %r", en[:50])
        w._ui_router.update_translation(
            MENU_OWNER_PROMPT, en, ja,
            panel_en=en, panel_ja=ja,
            update_tab=False,
            update_panel=True,
            keep_owner=True,
            mode=None,
            priority=95,
            reason="mages_prompt_overlay")
    except Exception:  # noqa: BLE001
        _log.exception("mages_prompt overlay update failed")
    return True


def _read_effect_title(w) -> str:
    """数値入力ポップアップの効果タイトルを応答候補から推定する。"""
    try:
        from popup11_response_reader import read_response_candidates_all
        from mages_spellmaker import EFFECT_TO_FORM
        cands = read_response_candidates_all(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return ""
    for cand in cands:
        text = (getattr(cand, "text", "") or "").strip()
        for effect in EFFECT_TO_FORM:
            if text == effect or text.startswith(effect):
                return text
    return ""


def _is_negotiation_img(img: str) -> bool:
    """NEGOTBUT.IMG / YESNO.IMG 等の交渉画像か（中立 negotiation_reader 判定）。"""
    try:
        from negotiation_reader import get_negotiation_profile
    except ImportError:
        return False
    return get_negotiation_profile(img) is not None


def _render_negotiation(w, img: str, top_level_state: str) -> bool:
    """魔術師ギルドの価格交渉を mages_negotiation owner で描画する。

    武具店 _render_negotiation と同型。中立 negotiation_module を自施設 owner で
    呼び、共有 'negotiation' owner（施設 owner でなく表示不変条件に弾かれる）を避ける。
    """
    try:
        from normal_play.negotiation_module import (
            poll_negotiation, cleanup_if_owner as cleanup_negotiation,
        )
        handled = poll_negotiation(
            w, img_name=img, top_level_state=top_level_state,
            owner=NEGOTIATION_OWNER)
        if not handled:
            cleanup_negotiation(w, owner=NEGOTIATION_OWNER)
        return handled
    except Exception:  # noqa: BLE001
        _log.exception("mages_negotiation update failed")
        return False


def _render_reply(w, img: str) -> bool:
    """Detect Magic 等のギルド応答を mages_reply owner で描画する。"""
    setattr(w, "_mages_reply_polled_in_render", True)
    try:
        from normal_play.mages_reply_module import poll_mages_reply
        handled = poll_mages_reply(
            w,
            mages_active=True,
            mages_just_started=False,
            img_name=img,
            shop_menu_visible=False,
        )
    except Exception:  # noqa: BLE001
        _log.exception("mages_reply render failed")
        handled = False
    setattr(w, "_mages_reply_handled_in_render", bool(handled))
    return bool(handled)


def _render_buyspell_detail(w) -> bool:
    """呪文購入の詳細を mages_spelldetail owner で呪文詳細体裁により表示する。"""
    try:
        from spell_reader import read_spell_detail
        from mages_list_reader import translate_name
        data = read_spell_detail(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        return False
    name = (data.get("name") or "").strip()
    if not name:
        return False
    # Casting Cost は描画文字列 C= から（spell_reader の cost は呪文購入では不正確）。
    cc = _read_cost_string(w)
    if cc is not None:
        data["casting_cost"] = cc
    # Spell Cost = 一覧の購入価格。Casting Cost×2 概算ではなく実価格を渡す。
    price = _buy_price_for(w, name)
    if price is not None:
        data["spell_cost"] = price
        if cc is None:
            data["casting_cost"] = price // 4
    data["name_ja"] = translate_name(name)
    try:
        key_now = ("spelldetail", name, data.get("cost"),
                   data.get("spell_cost"), data.get("casting_cost"),
                   data.get("text_en"))
        key_changed = key_now != getattr(w, _SPELLDETAIL_KEY, None)
        owner_taken = (w._panel_owner != MENU_OWNER_SPELLDETAIL)
        try:
            mode_taken = w._tab_translate.panel_mode() != "spell_detail"
        except (AttributeError, RuntimeError):
            mode_taken = False
        setattr(w, _SPELLDETAIL_KEY, key_now)
        # ステータス画面の呪文詳細と同じ spell_detail パネルで表示する。
        # raw screen は game_screen のままなので、poll 後段の通常 resync に負けない
        # よう BUYSPELL 表示中は毎 poll 高優先度で再アサートする。
        w._ui_router.propose_spell_detail(
            MENU_OWNER_SPELLDETAIL, data, priority=90,
            reason="mages_buyspell_detail")
        if key_changed or owner_taken or mode_taken:
            _log.info("mages_spelldetail update: %r", name)
    except Exception:  # noqa: BLE001
        _log.exception("mages_spelldetail update failed")
    return True


def _read_confirm_dialog(w):
    """YESNO 確認ダイアログ（Are you sure ?）の本文と選択肢を読む。

    本文テンプレは anchor+0x4B50 に常駐し ``本文\\r\\0YN\\0...\\0Yes\\r\\0No\\r\\0``
    の形。family=0x4B のときのみ呼ばれる前提（= 確認がアクティブ）。
    """
    try:
        raw = w._analyzer.read_bytes(w._anchor + _CONFIRM_DIALOG_OFFSET, 0x40)
    except (OSError, AttributeError):
        return None
    segs = []
    for s in raw.split(b"\x00"):
        t = s.decode("ascii", errors="replace").replace("\r", "").strip()
        if t:
            segs.append(t)
    title = next((s for s in segs if "?" in s or "Are you sure" in s), "")
    buttons = [s for s in segs if s in ("Yes", "No")]
    if not title:
        return None
    return title, (buttons or ["Yes", "No"])


def _render_confirm(w) -> bool:
    """確認ダイアログを詳細タブ維持の下部パネル overlay として表示する。"""
    info = _read_confirm_dialog(w)
    if not info:
        return False
    title, buttons = info
    try:
        en = title + "".join(f"\n  {b}" for b in buttons)
        ja_title = _CONFIRM_TR.get(title) or _CONFIRM_TR.get(
            title.rstrip(" ?").strip(), title)
        ja = ja_title + "".join(
            f"\n  {_CONFIRM_TR.get(b, b)}" for b in buttons)
        key_now = ("confirm", en)
        if key_now != getattr(w, _CONFIRM_KEY, None):
            setattr(w, _CONFIRM_KEY, key_now)
            _log.info("mages_confirm update: %r", en[:40])
        if not _render_spellmaker_detail(
                w, panel_en=en, panel_ja=ja,
                reason="mages_confirm_overlay"):
            w._ui_router.update_translation(
                MENU_OWNER_CONFIRM, en, ja,
                panel_en=en, panel_ja=ja,
                update_tab=False,
                update_panel=True,
                keep_owner=True,
                mode=None,
                priority=95,
                reason="mages_confirm")
    except Exception:  # noqa: BLE001
        _log.exception("mages_confirm update failed")
    return True


def _resolve_response_prompt(w):
    """購入/探知フロー等の応答プロンプトを npc_dialog 領域から抽出・翻訳する。

    応答本文は anchor+0x1044 域に描画されるが、直前の効果説明等の残骸と癒着して
    断片化することがある（read_live_buffer は先頭 NUL で打ち切られ拾えない）。
    プロンプトは必ず大文字始まりの一文なので、本文中の各大文字位置から一文を切り
    出して npc_dialog 辞書に照合し、最初に一致したものを (原文, 和訳) で返す。
    探知見積り / 探知不要 / 購入数量入力など、辞書に在る応答を一律に翻訳できる。
    """
    try:
        raw = w._analyzer.read_bytes(w._anchor + _NPC_DIALOG_OFFSET, 512)
    except (OSError, AttributeError):
        raw = b""
    extra_chunks: list[bytes] = []
    for off in _PROMPT_EXTRA_SCAN_OFFSETS:
        try:
            extra_chunks.append(w._analyzer.read_bytes(w._anchor + off, 160))
        except (OSError, AttributeError):
            extra_chunks.append(b"")
    # 生バッファをキーにキャッシュ（辞書照合は高コストのため変化時のみ再解析）
    cache_key = (raw, tuple(extra_chunks))
    cache = getattr(w, _PROMPT_CACHE_ATTR, None)
    if cache is not None and cache[0] == cache_key:
        return cache[1]
    text = "".join(
        c if 0x20 <= ord(c) <= 0x7E else " "
        for c in raw.decode("ascii", errors="replace"))
    literal_text = text + " " + " ".join(
        "".join(
            c if 0x20 <= ord(c) <= 0x7E else " "
            for c in chunk.decode("ascii", errors="replace"))
        for chunk in extra_chunks)
    try:
        from npc_dialog_lookup import lookup as _nd_lookup
        from npc_dialog_lookup import format_japanese as _nd_format
    except Exception:  # noqa: BLE001
        return None
    normalized_text = " ".join(literal_text.split())
    result = None
    if _DETECT_MAGIC_QUOTE_PREFIX in normalized_text:
        try:
            from popup11_response_reader import read_current_text_pointer
            cur_ptr = read_current_text_pointer(w._analyzer, w._anchor)
        except Exception:  # noqa: BLE001
            cur_ptr = None
        if (isinstance(cur_ptr, int)
                and _MAGES_MENU_PTR_START <= cur_ptr < _MAGES_MENU_PTR_END):
            try:
                raw_known = w._analyzer.read_bytes(
                    w._anchor + _MAGES_MENU_TEXT_OFFSET, 80)
            except (OSError, AttributeError):
                raw_known = b""
            known = raw_known.split(b"\x00", 1)[0].decode(
                "ascii", errors="replace").strip()
            if known == _DETECT_MAGIC_ALREADY_KNOWN:
                res = _nd_lookup(_DETECT_MAGIC_ALREADY_KNOWN)
                if res:
                    try:
                        result = (
                            _DETECT_MAGIC_ALREADY_KNOWN,
                            _nd_format(res[0], res[1]))
                    except Exception:  # noqa: BLE001
                        result = (
                            _DETECT_MAGIC_ALREADY_KNOWN,
                            _DETECT_MAGIC_ALREADY_KNOWN)
    for literal in _SPELLMAKER_PROMPT_LITERALS:
        if literal not in normalized_text:
            continue
        res = _nd_lookup(literal)
        if res:
            try:
                result = (literal, _nd_format(res[0], res[1]))
            except Exception:  # noqa: BLE001
                result = (literal, literal)
            break
    if result is None:
        lowered_text = normalized_text.lower()
        for needles, literal in _SPELLMAKER_PROMPT_FRAGMENT_LITERALS:
            if not all(needle in lowered_text for needle in needles):
                continue
            res = _nd_lookup(literal)
            if res:
                try:
                    result = (literal, _nd_format(res[0], res[1]))
                except Exception:  # noqa: BLE001
                    result = (literal, literal)
                break
    seen: set[str] = set()
    for i, ch in enumerate(text):
        if result is not None or not ch.isupper():
            continue
        seg = text[i:i + 160]
        end = _RESPONSE_END_RE.search(seg)
        if not end:
            continue
        cand = " ".join(seg[:end.end()].split())
        if len(cand) < 10 or cand in seen:
            continue
        seen.add(cand)
        res = _nd_lookup(cand)
        if res:
            try:
                result = (cand, _nd_format(res[0], res[1]))
            except Exception:  # noqa: BLE001
                result = (cand, cand)
            break
    setattr(w, _PROMPT_CACHE_ATTR, (cache_key, result))
    return result


def _render_buy_prompt(w) -> bool:
    """購入/探知フロー等の応答プロンプトを mages_prompt owner で翻訳表示する。"""
    info = _resolve_response_prompt(w)
    if not info:
        return False
    en, ja = info
    try:
        owner_taken = (w._panel_owner != MENU_OWNER_PROMPT)
        key_now = ("prompt", en)
        if key_now != getattr(w, _PROMPT_KEY, None) or owner_taken:
            setattr(w, _PROMPT_KEY, key_now)
            w._ui_router.update_translation(MENU_OWNER_PROMPT, en, ja)
            _log.info("mages_prompt update: %r", en[:50])
    except Exception:  # noqa: BLE001
        _log.exception("mages_prompt update failed")
    return True


def _translate_ui(en: str) -> str:
    """ui.json で UI 文字列を翻訳する（魔術師ギルド文脈・未登録は原文）。

    context-aware 直引き (`translate_ui_text("mages_guild", en)`)。
    未登録は旧 `_load_ui_dict()` fallback 経由で None になるため原文 (en) を返す。
    """
    try:
        from shop_menu_reader import translate_ui_text
        return translate_ui_text("mages_guild", en) or en
    except Exception:  # noqa: BLE001
        return en


def _last_spellmaker_list_title(w) -> str:
    title = (getattr(w, _LIST_TITLE_ATTR, "") or "").strip()
    return title if title in _SPELLMAKER_LIST_TITLES else ""


def _is_spellmaker_return_from_residual_list(
        w, sig: dict, img: str, state: str) -> bool:
    """POPUP.IMG 残留でも実前景が閉じていれば Spellmaker 背景へ戻す。"""
    return (
        img in LIST_IMGS
        and bool(_last_spellmaker_list_title(w))
        and state == "reply"
        and sig.get("list") != 0x00
    )


def _cleanup(w, menu_visible: bool, list_visible: bool,
             spell_visible: bool, confirm_visible: bool = False,
             prompt_visible: bool = False, detail_visible: bool = False,
             negot_visible: bool = False,
             effect_menu_visible: bool = False,
             reply_visible: bool = False) -> None:
    """前景でない自施設 owner の残置を片付ける (自 owner のみ)。"""
    if not reply_visible:
        try:
            from normal_play.mages_reply_module import (
                REPLY_OWNER, reset_mages_reply_state,
            )
            reset_mages_reply_state(w)
            if w._panel_owner == REPLY_OWNER:
                w._ui_router.clear_if_owner(REPLY_OWNER)
        except Exception:  # noqa: BLE001
            pass
    if not negot_visible and w._panel_owner == NEGOTIATION_OWNER:
        # 交渉から離れたら mages_negotiation owner を片付ける（自 owner のみ）。
        try:
            from normal_play.negotiation_module import cleanup_if_owner
            cleanup_if_owner(w, owner=NEGOTIATION_OWNER)
        except Exception:  # noqa: BLE001
            pass
    if not detail_visible and getattr(w, _SPELLDETAIL_KEY, None) is not None:
        setattr(w, _SPELLDETAIL_KEY, None)
        if w._panel_owner == MENU_OWNER_SPELLDETAIL:
            w._ui_router.clear_if_owner(MENU_OWNER_SPELLDETAIL)
    if not prompt_visible and getattr(w, _PROMPT_KEY, None) is not None:
        setattr(w, _PROMPT_KEY, None)
        if w._panel_owner == MENU_OWNER_PROMPT:
            w._ui_router.clear_if_owner(MENU_OWNER_PROMPT)
    if not confirm_visible and getattr(w, _CONFIRM_KEY, None) is not None:
        setattr(w, _CONFIRM_KEY, None)
        if w._panel_owner == MENU_OWNER_CONFIRM:
            w._ui_router.clear_if_owner(MENU_OWNER_CONFIRM)
    if (not effect_menu_visible
            and getattr(w, _EFFECT_MENU_KEY, None) is not None):
        setattr(w, _EFFECT_MENU_KEY, None)
        if w._panel_owner == EFFECT_MENU_OWNER:
            w._ui_router.clear_if_owner(EFFECT_MENU_OWNER)
    if not menu_visible and getattr(w, _MENU_KEY, None) is not None:
        setattr(w, _MENU_KEY, None)
        if w._panel_owner == MENU_OWNER:
            w._ui_router.clear_if_owner(MENU_OWNER)
    if not list_visible and getattr(w, _LIST_KEY, None) is not None:
        setattr(w, _LIST_KEY, None)
        setattr(w, _LIST_TITLE_ATTR, "")
        # 一覧を離れたら安定化キャッシュも破棄（前回訪問の残留表示を防ぐ）
        setattr(w, _LIST_STABLE_ATTR, {})
        setattr(w, _LIST_PENDING_ATTR, {})
        try:
            if w._tab_translate.panel_mode() == "facility_list":
                w._ui_router.set_panel_mode("translate")
        except AttributeError:
            pass
        if w._panel_owner == LIST_OWNER:
            w._ui_router.clear_if_owner(LIST_OWNER, mode="translate")
    if not spell_visible and getattr(w, _SPELL_KEY, None) is not None:
        setattr(w, _SPELL_KEY, None)
        if w._panel_owner == SPELLMAKER_OWNER:
            w._ui_router.clear_if_owner(SPELLMAKER_OWNER)


__all__ = [
    "poll_mages_render", "MENU_OWNER", "LIST_OWNER", "SPELLMAKER_OWNER",
    "EFFECT_MENU_OWNER", "LIST_IMGS", "SPELLMAKER_IMG",
    # テストが mages_guild_render_module 経由で直接参照する内部関数を再エクスポート:
    "_read_cost_string", "_casting_cost_from_spell_cost", "_buy_price_for",
    "_read_spellmaker_live_spell_cost", "_resolve_spellmaker_spell_cost",
    "_read_effect_title",
]
