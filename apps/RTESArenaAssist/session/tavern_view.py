"""session/tavern_view.py — 宿屋店主会話の単一判定 (1軸化の中核)。

1 poll で「いま店主会話のどの子画面 (L4) が前景か」を **一度だけ** 決める
pure helper。描画 owner 振り分け・接続バー表記・会話セッション (L3 latch) の
継続判定は、すべて本関数の戻り値 (TavernView) **だけ** を見て行う。

設計意図:
  実機では img 名 (YESNO.IMG 固着) も current_ptr (確認中も店主メニューに残る)
  も曖昧で、各経路が別々に判定すると食い違って画面が崩れた。そこで判定材料を
  poll_controller が 1 度だけ集め (TavernSignals)、本関数が単一の結論
  (TavernView) を出す。「どの module が描くか」もここで決め、各 module は
  その指示に従う renderer に徹する。

入力 TavernSignals は memory 非依存の pure data (= 呼出側が読み取り済み)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# L4 子画面 → (描画 owner, 接続バー i18n key)
# owner はその子画面を描く正規経路。bar_key は接続バー併記用。
_L4_OWNER_BAR: dict[str, tuple[str, str]] = {
    "menu":          ("shop_menu",         "recognition.tavern_sub_menu"),
    "drinks":        ("shop_buy",          "recognition.tavern_sub_drinks"),
    "rooms":         ("shop_buy",          "recognition.tavern_sub_rooms"),
    # rumor_type の owner は呼出元 (shop 経由 or ASK ABOUT marker) で変わるため
    # classify 内で決める。bar_key は共通。
    "rumor_type":    ("",                  "recognition.tavern_sub_rumor_type"),
    "stay_days":     ("active_template",   "recognition.tavern_sub_stay_days"),
    "sneak_confirm": ("active_template",   "recognition.tavern_sub_sneak_confirm"),
    "sneak_result":  ("active_template",   "recognition.tavern_sub_sneak_result"),
    "room_contract": ("active_template",   "recognition.tavern_sub_room_contract"),
    "cost_show":     ("active_template",   "recognition.tavern_sub_cost_show"),
    "cost_confirm":  ("active_template",   "recognition.tavern_sub_cost_confirm"),
    "amount_present": ("negotiation",      "recognition.tavern_sub_amount_present"),
    "amount_counter": ("negotiation",      "recognition.tavern_sub_amount_counter"),
    "final_confirm": ("negotiation",       "recognition.tavern_sub_final_confirm"),
    "response":      ("npc_dialog",        "recognition.tavern_sub_response"),
    "none":          ("",                  ""),
}

# shop_popup_detector.kind → L4 子画面
_SHOP_KIND_TO_L4 = {
    "shop_menu": "menu",
    "shop_buy": "drinks",
    "shop_rooms": "rooms",
    "shop_rumor_type": "rumor_type",
}

# active_template surface kind → L4 子画面
_SURFACE_TO_L4 = {
    "tavern_stay_days": "stay_days",
    "tavern_sneak_confirm": "sneak_confirm",
    "tavern_sneak_result": "sneak_result",
    "tavern_room_contract": "room_contract",
    "tavern_cost_show": "cost_show",
    "tavern_cost_confirm": "cost_confirm",
}

# 同 poll に複数の active_template surface 候補が居る場合の採用優先度
# (= 確認/結果/契約/費用 は stay_days 残置より前景である)。
_SURFACE_PRIORITY = (
    "tavern_sneak_confirm", "tavern_cost_confirm",
    "tavern_sneak_result", "tavern_room_contract", "tavern_cost_show",
    "tavern_stay_days",
)

# 宿屋メニュー認識を示す shop kind 集合 (= L3 開始/継続の店主 UI)
_TAVERN_MENU_SHOP_KINDS = frozenset({
    "shop_menu", "shop_buy", "shop_rooms", "shop_rumor_type",
})

# active_template confirm/result surface (= YESNO 下で negotiation より優先)
_AT_YESNO_SURFACES = frozenset({
    "tavern_sneak_confirm", "tavern_cost_confirm",
    "tavern_sneak_result", "tavern_room_contract", "tavern_cost_show",
})


@dataclass
class TavernSignals:
    """単一判定の入力 (= memory 読み取り済みの pure data)。"""
    in_interior: bool = False
    facility_tavern: bool = False        # L3 宿屋文脈 (interior tavern / session)
    shop_kind: str = "none"              # recovery-aware shop_popup_detector kind
    shop_owner: str = ""                 # shop_popup_detector owner_kind
    img: str = ""                        # 大文字 IMG 名
    active_surfaces: frozenset = field(default_factory=frozenset)
    cur_ptr_surface: str = ""            # current_ptr 一致候補の surface kind
    negotiation_body: bool = False       # 交渉本文が読めるか
    negotiation_prompts: bool = False    # 交渉専用 prompts があるか
    counter_active: bool = False         # negotiation_counter 候補が前景か
    npc_response_hit: bool = False       # 店内応答 (酒/噂応答) が前景か
    rumor_marker: bool = False           # ASK ABOUT Rumor Type marker 可視か


@dataclass
class TavernView:
    """単一判定の結論。全消費者はこれだけを見る。"""
    l4_kind: str                 # _L4_OWNER_BAR のキー
    render_owner: str            # 描くべき正規 owner ('' = 何も描かない)
    bar_key: str                 # 接続バー i18n key ('' = 付記なし)
    l4_visible: bool             # L4 子画面が前景か (= latch 継続信号)
    l3_start: bool               # 店主 UI 認識による L3 開始信号
    reason: str = ""


def _pick_surface(signals: TavernSignals) -> str:
    """active_template 候補のうち採用する surface を 1 つ選ぶ。

    current_ptr 一致候補を最優先し、次に _SURFACE_PRIORITY 順。
    """
    if signals.cur_ptr_surface in _SURFACE_TO_L4:
        return signals.cur_ptr_surface
    for s in _SURFACE_PRIORITY:
        if s in signals.active_surfaces:
            return s
    return ""


def classify_tavern_view(signals: TavernSignals) -> TavernView:
    """店主会話の L4 子画面を 1 つに決める単一判定 (1軸化の中核)。"""
    def _mk(kind: str, owner: Optional[str] = None,
            reason: str = "") -> TavernView:
        _owner, _bar = _L4_OWNER_BAR[kind]
        if owner is not None:
            _owner = owner
        return TavernView(
            l4_kind=kind,
            render_owner=_owner,
            bar_key=_bar,
            l4_visible=(kind != "none"),
            l3_start=(signals.shop_owner == "tavern"
                      and signals.shop_kind in _TAVERN_MENU_SHOP_KINDS),
            reason=reason,
        )

    # 屋内でなく宿屋文脈でもなければ L4 なし
    if not signals.in_interior or not signals.facility_tavern:
        return _mk("none", reason="not_in_tavern")

    img = (signals.img or "").upper()

    # 1. 店主メニュー / 一覧 / 噂種別 (shop_popup_detector が ptr+recovery で確定)
    if signals.shop_owner == "tavern" and signals.shop_kind in _SHOP_KIND_TO_L4:
        l4 = _SHOP_KIND_TO_L4[signals.shop_kind]
        owner = "shop_rumor_type" if l4 == "rumor_type" else None
        return _mk(l4, owner=owner, reason="shop_kind")

    # 2. 宿泊金額 対案入力 (negotiation_counter 候補が前景)
    if signals.counter_active:
        return _mk("amount_counter", reason="counter")

    # 3. 宿泊交渉本文 (NEGOTBUT 金額提示 / YESNO 最終確認)
    #    YESNO は active_template の確認/結果 surface が無い時のみ交渉とする。
    _has_at_yesno = bool(signals.active_surfaces & _AT_YESNO_SURFACES)
    if (signals.negotiation_body or signals.negotiation_prompts):
        if img == "NEGOTBUT.IMG":
            return _mk("amount_present", reason="negotiation_negotbut")
        if img == "YESNO.IMG" and not _has_at_yesno:
            return _mk("final_confirm", reason="negotiation_yesno")

    # 4. active_template surface (確認/結果/入力/契約/費用)
    _surface = _pick_surface(signals)
    if _surface:
        return _mk(_SURFACE_TO_L4[_surface], reason=f"surface:{_surface}")

    # 5. 噂種別 marker (ASK ABOUT 借用)
    if signals.rumor_marker:
        return _mk("rumor_type", owner="tavern_rumor_type",
                   reason="rumor_marker")

    # 6. 店内 NPC 応答 (酒/噂応答)
    if signals.npc_response_hit:
        return _mk("response", reason="npc_response")

    # 7. なし
    return _mk("none", reason="no_visible_l4")


__all__ = [
    "TavernSignals",
    "TavernView",
    "classify_tavern_view",
]
