"""session/mages_guild_session.py — 魔術師ギルド会話セッション。

魔術師ギルドの対話 UI が画面に出ている間だけ active にする latch。
TavernSession / TempleSession と同じ設計原則 (入店だけでは start せず、メニュー UI が
出た瞬間 active / 退店・別施設遷移・top-level 離脱で即 stop / ヒステリシスで吸収)。

完全分離: 本セッションは owner_kind=="mages_guild" でのみ start/継続し、
他施設 (宿屋/神殿/武具店) の判定・描画には一切関与しない。描画は当面 L4 内の共有
メニュー経路が担い、本セッションは latch のみを所有する (一覧メモリ詳細は実機観測後に
充足する)。

境界:
- 開始 (try_start): top_level=="normal-play" AND in_interior AND
  owner_kind=="mages_guild" (= Buy/Detect Magic/Spellmaker/Steal/Exit メニュー観測)。
- 継続 (try_stop=False): owner=="mages_guild" の shop kind / SPELLMKR.IMG /
  YESNO.IMG / negotiation / ギルド UI surface 上の mages_* panel_owner。
- 即 stop: in_interior 喪失 / top-level 離脱 / 既知の non-mages interior。
- ヒステリシス: none が N=3 poll 連続で stop。
"""
from __future__ import annotations

from .session_base import SessionBase, SessionContext


def _norm_facility_kind(fk: str) -> str:
    """facility_kind を表記ゆれ非依存キーへ正規化 (大文字化 + 区切り除去)。

    'MAGES_GUILD' / 'MagesGuild' / 'magesguild' を 'MAGESGUILD' に揃える。
    """
    return (fk or "").upper().replace("_", "").replace(" ", "")


# 魔術師ギルドの自施設 interior MIF 接頭辞 (= MAGE1.MIF / MAGE2.MIF / MAGES1.MIF)
_MAGES_MIF_PREFIXES = ("MAGE",)
# 他施設の interior MIF 接頭辞 (= 既知の別施設へ遷移したら即 stop する判定用)。
# 未知の MIF では誤 stop しないよう、既知の他施設のみを列挙する。
_OTHER_FACILITY_MIF_PREFIXES = ("TAVERN", "TEMPLE", "EQUIP", "ARMOR", "PALACE")


# 魔術師ギルド owner の表示 surface kind (shop_popup_detector が報告するもの)
_MAGES_OWNER_KINDS = frozenset({
    "shop_menu",  # MENU OPTIONS / PICK ITEM 等のメニュー surface
})

_MAGES_UI_IMGS = frozenset({
    "MENU_RT.IMG",
    "SPELLMKR.IMG",
    "BUYSPELL.IMG",
    "YESNO.IMG",
    "NEGOTBUT.IMG",
    "POPUP.IMG",
    "POPUP7.IMG",
    "NEWPOP.IMG",
})

# 魔術師ギルドの店内会話で観測される専用 family 値。
_MAGES_NPC_PHASES = frozenset({
    0x6F,  # メニュー / 探知 / 呪文作成
    0x70,  # 呪文購入詳細
})


# ギルド系 panel_owner の集合 (shop_state.kind=none の一時的瞬間でも L4 を維持)。
_MAGES_PANEL_OWNERS = frozenset({
    # 自施設 L4 owner (mages_guild_render_module / mages_reply_module が描画)
    "mages_menu",
    "mages_list",
    "mages_spellmaker",
    "mages_effect_menu",  # 効果追加/修正/削除メニュー
    "mages_spelldetail",  # 呪文購入詳細 (spell_detail パネル)
    "mages_prompt",       # 入力/見積りプロンプト
    "mages_confirm",      # 確認ダイアログ (Are you sure?)
    "mages_negotiation",  # 価格交渉 (NEGOTBUT/YESNO・武具店と同型)
    "mages_reply",  # 応答 (完全分離・内製化済み)
    # 共有 owner (negotiation/active_template/npc_dialog) への相乗りは
    # 行わない。ギルドの L4 は上記 mages_* 専用 owner に閉じる。
})


# kind=="none" 連続時の stop 閾値 (約 0.6 秒 @ 5Hz poll、他施設と同じ)
_MAGES_NONE_HYSTERESIS_POLLS = 3


class MagesGuildSession(SessionBase):
    """魔術師ギルド会話セッション (owner_kind=="mages_guild" 中のみ active)。"""

    name = "mages_guild"

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        self._last_img: str = ""

    # ------------------------------------------------------------------
    # context 判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_mages_context(ctx: SessionContext) -> bool:
        """ctx の interior_mif_name / facility_kind から魔術師ギルドか判定。

        ギルドの interior MIF は MAGE* (= MAGE1.MIF / MAGE2.MIF / MAGES1.MIF)。
        facility_kind は表記ゆれ (MAGES_GUILD / MagesGuild / magesguild) を正規化。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif.startswith(_MAGES_MIF_PREFIXES):
            return True
        if _norm_facility_kind(ctx.facility_kind) == "MAGESGUILD":
            return True
        return False

    @staticmethod
    def _known_non_mages_context(ctx: SessionContext) -> bool:
        """既知の他施設 interior であることが明確に判るか (= 即 stop 判定)。

        別施設の interior_mif (TAVERN/TEMPLE/EQUIP/ARMOR/PALACE) や 既知の
        facility_kind (ギルド以外) へ遷移したら即 stop する。未知の MIF では誤 stop
        しないよう、既知の他施設接頭辞のみで判定する (安全側設計)。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif and mif.startswith(_OTHER_FACILITY_MIF_PREFIXES):
            return True
        fk = _norm_facility_kind(ctx.facility_kind)
        if fk and fk != "MAGESGUILD":
            return True
        return False

    # ------------------------------------------------------------------
    # shop state 検出 (kind + owner_kind)
    # ------------------------------------------------------------------

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        """shop_popup_detector の (kind, owner_kind) を取得する。"""
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
                    "mages_guild"
                    if self._active or self._is_mages_context(ctx)
                    else ""),
            )
            return (state.kind or "none", state.owner_kind or "")
        except Exception:
            return ("none", "")

    # ------------------------------------------------------------------
    # 継続判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_guild_modal_img(ctx: SessionContext) -> bool:
        """ギルド固有の modal IMG か。"""
        img = (ctx.img_name or "").upper()
        return img in _MAGES_UI_IMGS or (
            img.startswith("FORM") and img.endswith(".IMG"))

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

    def _is_mages_panel_owned(self, ctx: SessionContext) -> bool:
        """直近 poll でギルド系 panel_owner が描画権を claim 中か。"""
        extras_owner = (ctx.extras.get("mages_panel_owner")
                        if ctx.extras else None)
        if extras_owner is not None:
            return extras_owner in _MAGES_PANEL_OWNERS
        w = ctx.extras.get("window") if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, "_panel_owner", "") or ""
        return owner in _MAGES_PANEL_OWNERS

    def _is_mages_panel_surface_active(self, ctx: SessionContext) -> bool:
        """mages_* owner が現在のギルド UI surface 上で有効か。

        LOADSAVE 後に MOUNT011.IMG / DTAV.IMG へ戻っても
        古い mages_menu owner だけで L3 latch を保持すると、翻訳タブの
        優先表示が通常探索へ復帰できない。panel_owner は shop_state の
        一時 none を吸収する補助信号なので、実際のギルド UI IMG または
        ギルド会話 phase が同時に見えている時だけ継続根拠にする。
        """
        if not self._is_mages_panel_owned(ctx):
            return False
        if self._is_guild_modal_img(ctx):
            return True
        if self._is_negotiation_active(ctx):
            return True
        return ctx.npc_phase in _MAGES_NPC_PHASES

    # ------------------------------------------------------------------
    # 公開ヘルパ
    # ------------------------------------------------------------------

    @property
    def last_img(self) -> str:
        """直前 poll で観測した img_name。"""
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
        if owner == "mages_guild" and kind in _MAGES_OWNER_KINDS:
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
        if self._known_non_mages_context(ctx):
            return self._stop()

        # 2-5. 継続条件
        kind, owner = self._detect_shop_state(ctx)
        if owner == "mages_guild" and kind in _MAGES_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_guild_modal_img(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_mages_panel_surface_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False

        # 6. ヒステリシス
        self._none_shop_polls += 1
        if self._none_shop_polls >= _MAGES_NONE_HYSTERESIS_POLLS:
            return self._stop()
        self._last_img = ctx.img_name or ""
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理。

        描画は当面 L4 内の共有メニュー経路が担うため本メソッドは no-op。
        将来的な物理移植 (= ギルド専用の閉じた描画モジュール) の受け皿として残す。
        """
        return None


__all__ = ["MagesGuildSession"]
