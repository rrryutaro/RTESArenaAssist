"""session/equipment_session.py — 武具店 店主会話セッション。

武具店の店主との対話 UI が画面に出ている間だけ active にする latch。
TavernSession / TempleSession と同じ設計原則 (= 入店だけでは start せず、店主 UI が
出た瞬間 active / 退店・別施設遷移・top-level 離脱で即 stop / ヒステリシスで吸収)。

完全分離: 本セッションは owner_kind=="equipment" でのみ start/継続し、
他施設 (宿屋/神殿/魔術師ギルド) の判定・描画には一切関与しない。描画は当面 L4 内の
共有メニュー経路が担い、本セッションは latch のみを所有する (中身の一覧メモリ詳細は
実機観測後に充足する)。

境界:
- 開始 (try_start): top_level=="normal-play" AND in_interior AND
  shop_popup_detector の owner_kind=="equipment" (= Buy/Sell/Repair/Steal/Exit
  メニュー観測)。
- 継続 (try_stop=False): owner=="equipment" の shop kind / YESNO.IMG (費用確認) /
  negotiation (値切り) / 武具店系 panel_owner が claim 中。
- 即 stop: in_interior 喪失 / top-level 離脱 / 既知の non-equipment interior。
- ヒステリシス: いずれにも当てはまらない none が N=3 poll 連続で stop。
"""
from __future__ import annotations

from .session_base import SessionBase, SessionContext


def _norm_facility_kind(fk: str) -> str:
    """facility_kind を表記ゆれ非依存キーへ正規化 (大文字化 + 区切り除去)。

    'EQUIPMENT' / 'Equipment' / 'equipment' / 'MAGES_GUILD' / 'MagesGuild' を
    それぞれ 'EQUIPMENT' / 'MAGESGUILD' に揃える (facility_nodes と同方針)。
    """
    return (fk or "").upper().replace("_", "").replace(" ", "")


# 武具店の自施設 interior MIF 接頭辞 (= EQUIP1.MIF / EQUIPMNT.MIF / ARMOR*)
_EQUIPMENT_MIF_PREFIXES = ("EQUIP", "ARMOR")
# 他施設の interior MIF 接頭辞 (= 既知の別施設へ遷移したら即 stop する判定用)。
# 未知の MIF では誤 stop しないよう、既知の他施設のみを列挙する。
_OTHER_FACILITY_MIF_PREFIXES = ("TAVERN", "TEMPLE", "MAGE", "PALACE")


# 武具店 owner の表示 surface kind (shop_popup_detector が報告するもの)
_EQUIPMENT_OWNER_KINDS = frozenset({
    "shop_menu",  # MENU OPTIONS / BUY OPTIONS 等のメニュー surface
    "equipment_list",  # Sell/Repair 所持品一覧 NEWPOP surface
})


# 武具店系 panel_owner の集合 (shop_state.kind=none の一時的瞬間でも L4 を維持)。
# 当面は共有メニュー経路の汎用 owner を用いる (= TempleSession と同型)。
_EQUIPMENT_PANEL_OWNERS = frozenset({
    # 自施設 L4 owner (equipment_render_module / equipment_reply_module が描画)
    "equipment_menu",
    "equipment_list",
    "equipment_negotiation",
    "equipment_reply",  # 店主応答 (完全分離・内製化済み)
    # 共有 owner (negotiation/active_template/npc_dialog) への相乗りは
    # 行わない。武具店の L4 は上記 equipment_* 専用 owner に閉じる。
})

_EQUIPMENT_REPLY_START_IMGS = frozenset({
    "YESNO.IMG",
    "NEWPOP.IMG",
    "FACES00.CIF",
})
_EQUIPMENT_REPLY_PREFIXES = (
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
    "I can cut down the time",
    "I can cut the cost",
)

# kind=="none" 連続時の stop 閾値 (約 0.6 秒 @ 5Hz poll、Tavern/Temple と同じ)
_EQUIPMENT_NONE_HYSTERESIS_POLLS = 3


class EquipmentSession(SessionBase):
    """武具店店主会話セッション (owner_kind=="equipment" 中のみ active)。"""

    name = "equipment"

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ""

    # ------------------------------------------------------------------
    # context 判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_equipment_context(ctx: SessionContext) -> bool:
        """ctx の interior_mif_name / facility_kind から武具店か判定。

        武具店の interior MIF は EQUIP*/ARMOR* (= EQUIP1.MIF / EQUIPMNT.MIF 等)。
        facility_kind は表記ゆれ (EQUIPMENT / Equipment / equipment) を正規化。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif.startswith(_EQUIPMENT_MIF_PREFIXES):
            return True
        if _norm_facility_kind(ctx.facility_kind) == "EQUIPMENT":
            return True
        return False

    @staticmethod
    def _known_non_equipment_context(ctx: SessionContext) -> bool:
        """既知の他施設 interior であることが明確に判るか (= 即 stop 判定)。

        TavernSession / TempleSession と同型: 別施設の interior_mif (TAVERN/TEMPLE/
        MAGE/PALACE) や 既知の facility_kind (武具店以外) へ遷移したら即 stop する。
        未知の MIF では誤 stop しないよう、既知の他施設接頭辞のみで判定する
        (= 武具店 MIF の表記が想定外でも latch を落とさない安全側設計)。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif and mif.startswith(_OTHER_FACILITY_MIF_PREFIXES):
            return True
        fk = _norm_facility_kind(ctx.facility_kind)
        if fk and fk != "EQUIPMENT":
            return True
        return False

    # ------------------------------------------------------------------
    # shop state 検出 (kind + owner_kind)
    # ------------------------------------------------------------------

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        """shop_popup_detector の (kind, owner_kind) を取得する。

        テスト容易性のため ctx.extras["shop_kind"]/["owner_kind"] を優先する。
        """
        extras_kind = ctx.extras.get("shop_kind") if ctx.extras else None
        extras_owner = ctx.extras.get("owner_kind") if ctx.extras else None
        if extras_kind is not None or extras_owner is not None:
            kind = extras_kind if extras_kind is not None else "none"
            owner = extras_owner if extras_owner is not None else ""
            return (kind or "none", owner or "")
        try:
            from shop_popup_detector import detect_shop_popup_state
        except ImportError:
            return ("none", "")
        if ctx.top_level_state != "normal-play":
            return ("none", "")
        if not ctx.in_interior:
            return ("none", "")
        try:
            state = detect_shop_popup_state(
                ctx.analyzer, ctx.anchor,
                top_level_state=ctx.top_level_state,
                img_name=ctx.img_name,
                in_interior=ctx.in_interior,
                screen_id=ctx.screen_id,
                interior_mif_name=ctx.interior_mif_name or "",
                active_facility_name=(
                    "equipment"
                    if self._active or self._is_equipment_context(ctx)
                    else ""),
            )
            return (state.kind or "none", state.owner_kind or "")
        except Exception:
            return ("none", "")

    # ------------------------------------------------------------------
    # 継続判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_yesno_active(ctx: SessionContext) -> bool:
        """ctx.img_name が YESNO.IMG か (= 武具店の費用確認等)。"""
        return (ctx.img_name or "").upper() == "YESNO.IMG"

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        """negotiation 系 IMG (= 値切り) か。active 中の継続信号にのみ使う。"""
        img = (ctx.img_name or "").upper()
        if not img:
            return False
        try:
            from negotiation_reader import get_negotiation_profile
        except ImportError:
            return False
        return get_negotiation_profile(img) is not None

    def _is_equipment_panel_owned(self, ctx: SessionContext) -> bool:
        """直近 poll で武具店系 panel_owner が描画権を claim 中か。

        テスト容易性のため ctx.extras["equipment_panel_owner"] を優先する。
        """
        extras_owner = (ctx.extras.get("equipment_panel_owner")
                        if ctx.extras else None)
        if extras_owner is not None:
            return extras_owner in _EQUIPMENT_PANEL_OWNERS
        w = ctx.extras.get("window") if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, "_panel_owner", "") or ""
        return owner in _EQUIPMENT_PANEL_OWNERS

    @staticmethod
    def _has_equipment_reply_signal(ctx: SessionContext) -> bool:
        """Repair 等の武具店応答 hit が現在 surface に存在するか。

        Assist を Repair YESNO 画面上で起動すると、背景メニュー検出が
        取れず EquipmentSession が start しない。辞書 hit 済みの武具店 Repair
        応答に限定して、途中画面からの L4 開始信号として扱う。
        """
        if (ctx.img_name or "").upper() not in _EQUIPMENT_REPLY_START_IMGS:
            return False
        if ctx.analyzer is None:
            return False
        try:
            from popup11_response_reader import read_response_candidates_all
            cands = read_response_candidates_all(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        for cand in cands:
            if not cand.lookup_hit:
                continue
            text = cand.text or ""
            if text.startswith("Your ") and "repair" not in text:
                continue
            if text.startswith(_EQUIPMENT_REPLY_PREFIXES):
                return True
        return False

    # ------------------------------------------------------------------
    # 公開ヘルパ
    # ------------------------------------------------------------------

    @property
    def last_img(self) -> str:
        """直前 poll で観測した img_name (= IMG 遷移判定用)。"""
        return self._last_img

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def _stop(self) -> bool:
        self._none_shop_polls = 0
        self._last_img = ""
        self._set_active(False)
        return True

    def try_start(self, ctx: SessionContext) -> bool:
        if self._active:
            return False
        if ctx.top_level_state != "normal-play" or not ctx.in_interior:
            return False
        kind, owner = self._detect_shop_state(ctx)
        if owner == "equipment" and kind in _EQUIPMENT_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            self._set_active(True)
            return True
        if (not self._known_non_equipment_context(ctx)
                and self._has_equipment_reply_signal(ctx)):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        if not self._active:
            return False
        # 1. 即 stop 条件
        if ctx.top_level_state != "normal-play" or not ctx.in_interior:
            return self._stop()
        if self._known_non_equipment_context(ctx):
            return self._stop()

        # 2-5. 継続条件
        kind, owner = self._detect_shop_state(ctx)
        if owner == "equipment" and kind in _EQUIPMENT_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_yesno_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_equipment_panel_owned(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False

        # 6. ヒステリシス
        self._none_shop_polls += 1
        if self._none_shop_polls >= _EQUIPMENT_NONE_HYSTERESIS_POLLS:
            return self._stop()
        self._last_img = ctx.img_name or ""
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理。

        描画は当面 L4 内の共有メニュー経路が担うため本メソッドは no-op。
        将来的な物理移植 (= 武具店専用の閉じた描画モジュール) の受け皿として残す。
        """
        return None


__all__ = ["EquipmentSession"]
