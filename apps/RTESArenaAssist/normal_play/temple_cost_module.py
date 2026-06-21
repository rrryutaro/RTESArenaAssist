"""normal_play/temple_cost_module.py — 神殿 L4 費用確認 / 寄付入力の描画オーナー。

完全分離: 神殿神官会話の「費用確認 (This service will cost N
gold ...)」と「寄付金額入力」の判定 (候補選択) と所有描画を神殿専用 owner
``temple_cost`` / ``temple_prompt`` に閉じる。共有 ``active_template_module`` 経路への
相乗りを撤廃し、神殿が自前で候補選択して描画する (= L4 が神殿分離内に閉じる)。

共有してよいのは:
- (A) 純粋データ取得 / 翻訳基本処理: ``active_template_reader`` の生バッファ読み取り
  (``read_active_template_candidates`` / ``read_current_text_pointer`` /
  ``template_surface_kind``)、辞書 lookup (``npc_dialog_lookup``)、YESNO ボタン
  ラベル (``negotiation_reader.get_negotiation_profile``)。
- (C) UiRouter 描画シンク (``update_translation`` / ``clear_if_owner``、owner 引数)。

候補選択 (= 判定) と owner 所有は本モジュール (神殿分離内) で完結する。共有セレクタ
``select_active_template_candidate`` は surface kind の接頭辞 (``tavern_cost_*``) から
facility を抽出し「神殿 active 文脈では宿屋接頭辞 surface を弾く」ため、神殿の費用確認
(宿/治癒 共用テンプレ A134/A135) が表示されない。本モジュールは当該 surface を
神殿として明示的に受理することでこれを解消する。
"""
from __future__ import annotations

import logging

_log = logging.getLogger("RTESArenaAssist")

# 神殿専用 owner 名前空間 (共有 active_template owner とは別物)。
COST_OWNER = "temple_cost"        # 費用表示 / 費用承諾確認 (YESNO)
PROMPT_OWNER = "temple_prompt"    # 寄付金額入力プロンプト
_KEY = "_temple_cost_key_prev"

# 神殿が受理する surface kind (= 宿/治癒 共用の費用テンプレ + 神殿寄付入力)。
# surface kind の接頭辞は 'tavern_' だが、A134/A135 の費用テンプレは宿屋と神殿
# (治癒費用) が物理的に同じテンプレ領域を共有するため、神殿でも受理する。
_COST_SURFACE_KINDS = frozenset({"tavern_cost_show", "tavern_cost_confirm"})
_PROMPT_SURFACE_KINDS = frozenset({"temple_donate_amount"})
_ACCEPTED_SURFACE_KINDS = _COST_SURFACE_KINDS | _PROMPT_SURFACE_KINDS

# IMG ごとに許可する surface (= 別 flow の active_slot 残置を誤採用しない)。
# 不明 IMG (= 下記以外) は制限なし。
_IMG_ALLOWED_SURFACE_KINDS = {
    "YESNO.IMG": frozenset({"tavern_cost_confirm", "temple_donate_amount"}),
    "NEWPOP.IMG": frozenset({"tavern_cost_show", "temple_donate_amount"}),
    "MENU_RT.IMG": frozenset({"tavern_cost_show", "temple_donate_amount"}),
}


def _with_yesno_buttons(img_name: str, kind: str,
                        en: str, ja: str) -> tuple[str, str]:
    """YESNO.IMG の費用承諾確認に YES/NO ボタンラベルを前置する。"""
    if kind not in _COST_SURFACE_KINDS:
        return en, ja
    if (img_name or "").upper() != "YESNO.IMG":
        return en, ja
    try:
        from negotiation_reader import get_negotiation_profile
        profile = get_negotiation_profile("YESNO.IMG")
    except ImportError:
        profile = None
    if not profile:
        return en, ja
    en_buttons = "  ".join(profile["buttons_en"])
    ja_buttons = "  ".join(profile["buttons_ja"])
    return f"{en_buttons}\n{en}", f"{ja_buttons}\n{ja}"


def _select(candidates, img: str, lookup_hit):
    """神殿の費用/入力 surface を候補から選ぶ (= 神殿分離内の候補選択)。

    優先順: source="current_ptr" → "active_slot"。surface kind が神殿受理集合に
    あり、IMG 許可集合 (あれば) を満たし、辞書 hit する最初の候補を採用する。

    戻り値: (採用 candidate or None, surface kind)。
    """
    from active_template_reader import template_surface_kind
    allowed = _IMG_ALLOWED_SURFACE_KINDS.get((img or "").upper())
    for want_source in ("current_ptr", "active_slot"):
        for c in candidates:
            if c.source != want_source:
                continue
            kind = template_surface_kind(c)
            if kind not in _ACCEPTED_SURFACE_KINDS:
                continue
            if allowed is not None and kind not in allowed:
                continue
            try:
                if lookup_hit(c.text):
                    return c, kind
            except Exception:  # noqa: BLE001
                continue
    return None, ""


def poll_temple_cost(w, *, img_name: str) -> bool:
    """神殿の費用確認 / 寄付入力を temple_cost / temple_prompt owner で所有描画する。

    戻り値: True なら本 poll で神殿が当該 owner を所有して描画した。False の場合は
    前景に費用/入力が無いとみなし、自 owner の残置を片付ける。
    """
    img = (img_name or "").upper()
    try:
        from active_template_reader import (
            read_active_template_candidates,
            read_current_text_pointer,
        )
        candidates = read_active_template_candidates(w._analyzer, w._anchor)
        _cur_ptr = read_current_text_pointer(w._analyzer, w._anchor)
    except Exception:  # noqa: BLE001
        _log.exception("temple_cost active_template read failed")
        _cleanup(w)
        return False

    try:
        import npc_dialog_lookup as _ndl
    except Exception:  # noqa: BLE001
        _log.exception("temple_cost npc_dialog_lookup import failed")
        _ndl = None

    selected = None
    kind = ""
    if _ndl is not None and candidates:
        def _hit(text: str, _ndl=_ndl) -> bool:
            try:
                return _ndl.lookup(text) is not None
            except Exception:  # noqa: BLE001
                return False
        selected, kind = _select(candidates, img, _hit)

    if selected is None or _ndl is None:
        _cleanup(w)
        return False

    en = selected.text.rstrip()
    try:
        _r = _ndl.lookup(en)
    except Exception:  # noqa: BLE001
        _r = None
    if not _r:
        _cleanup(w)
        return False

    owner = PROMPT_OWNER if kind in _PROMPT_SURFACE_KINDS else COST_OWNER
    _ja_tmpl, _ph = _r
    ja = _ndl.format_japanese(_ja_tmpl, _ph)
    en_text, ja_text = _with_yesno_buttons(img, kind, en, ja)
    w._temple_cost_current_owner = owner
    w._temple_cost_current_surface = kind
    w._temple_cost_current_text = en

    key = (owner, en_text, ja_text)
    owner_taken = (w._panel_owner != owner)
    if key != getattr(w, _KEY, None) or owner_taken:
        setattr(w, _KEY, key)
        w._ui_router.update_translation(owner, en_text, ja_text)
        _log.info(
            "temple_cost translated: owner=%s kind=%s img=%r en=%r ja=%r",
            owner, kind, img, en[:80], ja[:80])
    return True


def _cleanup(w) -> None:
    """前景に費用/入力が無い時、自施設 owner (temple_cost / temple_prompt) の
    残置のみ片付ける (他 owner は触らない)。"""
    if getattr(w, _KEY, None) is not None:
        setattr(w, _KEY, None)
    for attr in (
        "_temple_cost_current_owner",
        "_temple_cost_current_surface",
        "_temple_cost_current_text",
    ):
        try:
            setattr(w, attr, "")
        except AttributeError:
            pass
    for owner in (COST_OWNER, PROMPT_OWNER):
        try:
            if w._panel_owner == owner:
                w._ui_router.clear_if_owner(owner)
        except AttributeError:
            pass


__all__ = ["poll_temple_cost", "COST_OWNER", "PROMPT_OWNER"]
