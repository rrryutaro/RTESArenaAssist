"""session/temple_session.py — 神殿神官会話セッション。

神殿の神官との対話 UI が画面に出ている間だけ active にする latch。
「TEMPLE*.MIF 在室中」ではなく「神官 popup/menu/応答が進行中」を表す。

TavernSession と同じ設計原則:
  - 入店だけでは start しない (= 神官をクリックして UI が出るまで inactive)
  - 神官 UI の流れを 1 セッションとして保持 (= menu → cost → 応答 → 復帰)
  - 退店 / 別施設遷移 / top-level 離脱で即 stop

境界:
- 開始 (try_start): 次のすべてを満たす瞬間
    1. `top_level_state == "normal-play"`
    2. `in_interior == True`
    3. 現在地が Temple と判定できる
       - `interior_mif_name` が `TEMPLE*.MIF`
       - または `facility_kind == "TEMPLE"`
       - または施設情報が空 (起動直後など) で owner_kind=="temple"
    4. `shop_popup_detector` の `owner_kind == "temple"`
       (= Bless/Cure/Heal/Exit メニュー観測)

- 継続 (try_stop = False):
    1. `owner_kind == "temple"` の shop kind が出ている
    2. `img_name == "YESNO.IMG"` (= 神殿コスト確認画面、temple active 中のみ)
    3. 神官応答や入力 prompt が神殿分離内の reader / response buffer から検出される
       (= TempleSession.was_recent_owner で判定、helper として外部に提供)
    4. 神殿系 panel_owner (= 神官メニュー / 費用 / 入力 / 神官応答)
       が描画権を持っている (= 神官の顔画面遷移時の一時的 shop_state=none を
       吸収して L3 離脱を防ぐ、TavernSession と同型)

- 即 stop:
    1. `in_interior == False`
    2. `top_level_state != "normal-play"`
    3. 既知の non-temple interior へ遷移

- ヒステリシス:
    上記のいずれにも当てはまらない場合 N=3 poll 連続で stop (TavernSession と同じ)

内部状態:
  TempleSession は last_img を保持し、YESNO.IMG → MENU_RT.IMG の遷移を検出
  できるようにする (poll_controller がメニュー復帰判定に使う)。
"""
from __future__ import annotations

from .session_base import SessionBase, SessionContext


# 神殿 owner の表示 surface kind (shop_popup_detector が報告するもの)
_TEMPLE_OWNER_KINDS = frozenset({
    "shop_menu",  # Bless/Cure/Heal/Exit メニュー
    # 神殿の YESNO や応答は別 mechanism のため、kind ベースでは shop_menu のみ。
    # owner_kind=="temple" を併用する。
})


# 神殿系 panel_owner の集合。これらが panel を所有中の poll は
# shop_state.kind=none でも L3 latch を維持する (= 神官の顔画面表示等で
# 一時的に shop_popup_detector が none を返す瞬間を吸収する)。
# TavernSession の _TAVERN_PANEL_OWNERS と同型。
_TEMPLE_PANEL_OWNERS = frozenset({
    "temple_menu",         # 神官メニュー (Bless/Cure/Heal/Exit、temple 専用 owner)
    "temple_priest_reply",  # 神官応答テキスト (完全分離・内製化済み)
    "temple_cost",         # 費用確認 (完全分離・内製化済み)
    "temple_prompt",       # 寄付金額入力 (完全分離・内製化済み)
    # 共有 owner (negotiation/active_template/npc_dialog) への相乗りは
    # 行わない。神殿の L4 は上記 temple_* 専用 owner に閉じる。
})


# kind=="none" が連続した時の stop 閾値 (約 0.6 秒 @ 5Hz poll、TavernSession と同じ)
_TEMPLE_NONE_HYSTERESIS_POLLS = 3


class TempleSession(SessionBase):
    """神殿神官会話セッション (神官 UI 中のみ active)。"""

    name = "temple"

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0
        # 直前 IMG を保持し、YESNO.IMG → MENU_RT.IMG 遷移検出に使う。
        # poll_controller が menu redraw key reset に使う。
        self._last_img: str = ""

    # ------------------------------------------------------------------
    # Temple context 判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_temple_context(ctx: SessionContext) -> bool:
        """ctx の interior_mif_name / facility_kind から Temple か判定。"""
        mif = (ctx.interior_mif_name or "").upper()
        if mif.startswith("TEMPLE"):
            return True
        if ctx.facility_kind == "TEMPLE":
            return True
        return False

    @staticmethod
    def _facility_info_unknown(ctx: SessionContext) -> bool:
        """interior_mif_name / facility_kind がともに空 (情報未取得) か。"""
        return not ctx.interior_mif_name and not ctx.facility_kind

    @staticmethod
    def _known_non_temple_context(ctx: SessionContext) -> bool:
        """Temple 以外の interior であることが明確に判定できるか。"""
        mif = (ctx.interior_mif_name or "").upper()
        if mif and not mif.startswith("TEMPLE"):
            return True
        if ctx.facility_kind and ctx.facility_kind != "TEMPLE":
            return True
        return False

    # ------------------------------------------------------------------
    # shop state 検出 (kind + owner_kind)
    # ------------------------------------------------------------------

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        """shop_popup_detector の (kind, owner_kind) を取得する。

        テスト容易性のため:
          - ctx.extras["shop_kind"] / ["owner_kind"] が与えられればそれを使う
          - なければ shop_popup_detector を実呼び出し
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
                    "temple"
                    if self._active or self._is_temple_context(ctx)
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
        """ctx.img_name が YESNO.IMG か (= 神殿コスト確認等)。"""
        return (ctx.img_name or "").upper() == "YESNO.IMG"

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        """negotiation 系 IMG (NEGOTBUT/YESNO 等) か。

        active 中の継続信号にのみ使う (inactive からの start には使わない)。
        """
        img = (ctx.img_name or "").upper()
        if not img:
            return False
        try:
            from negotiation_reader import get_negotiation_profile
        except ImportError:
            return False
        return get_negotiation_profile(img) is not None

    @staticmethod
    def _detect_temple_phase(ctx: SessionContext) -> str:
        """神殿 L4 phase を返す。読めない場合は空文字。

        ctx.extras["temple_phase"] はテスト/診断用の明示 override。
        """
        extras_phase = (
            ctx.extras.get("temple_phase") if ctx.extras else None)
        if extras_phase is not None:
            return str(extras_phase or "")
        if ctx.analyzer is None:
            return ""
        try:
            from temple_dialog_reader import classify_temple_phase
        except ImportError:
            return ""
        try:
            phase, _values = classify_temple_phase(ctx.analyzer, ctx.anchor)
            return phase or ""
        except Exception:
            return ""

    # 神殿テンプレ (active_template prompt / response) が
    # 表示中の poll では try_stop を継続させる。
    # current_ptr 由来候補のみで判定 (= stale 排除)。
    # 加えて active_slot 由来 input prompt (A155 寺院 寄付金額入力) も
    #       継続判定に含める (= current_ptr が menu item を指す一方、
    #       A155 は active_slot +0xFACE に出るため)。
    #       active_slot の response 系 (A152/A153/A154) は継続
    #       判定から除外する (= stale 防止)。
    @staticmethod
    def _is_temple_template_active(ctx: SessionContext) -> bool:
        """active_template に神殿関連テンプレが出ているか判定する。

        テスト容易性のため:
          - ctx.extras["temple_template_active"] が与えられればそれを使う
          - なければ read_active_template_candidates + npc_dialog_lookup で
            current_ptr 候補、または既知 input prompt (A155 等) を対象に判定。
            active_slot 由来でも temple input prompt なら継続判定 OK。
            response 系 active_slot は除外 (= stale 防止)。
        """
        extras_flag = (ctx.extras.get("temple_template_active")
                       if ctx.extras else None)
        if extras_flag is not None:
            return bool(extras_flag)
        if ctx.analyzer is None:
            return False
        try:
            from active_template_reader import (
                read_active_template_candidates,
                input_prompt_facility,
            )
            import npc_dialog_lookup as _ndl
        except ImportError:
            return False
        try:
            cands = read_active_template_candidates(
                ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        for c in cands:
            # current_ptr 由来は無条件で継続候補
            if c.source == "current_ptr":
                try:
                    if _ndl.lookup(c.text) is not None:
                        return True
                except Exception:
                    continue
            # active_slot 由来は temple input prompt のみ採用
            elif c.source == "active_slot":
                if input_prompt_facility(c) != "temple":
                    continue
                try:
                    if _ndl.lookup(c.text) is not None:
                        return True
                except Exception:
                    continue
        return False

    @staticmethod
    def _is_temple_response_active(ctx: SessionContext) -> bool:
        """応答バッファ領域に神官応答が出ている/表示保持中かで継続判定する。

        神殿では 0xA844 はバッファ内 offset でない(0x001E 等)ため pointer 一致では
        判定できない。表示保持中(hold>0)か、baseline から変化した priest 候補が
        居る間を継続信号とする(= temple_dialog_module の領域走査に整合)。
        """
        extras_flag = (ctx.extras.get("temple_response_active")
                       if ctx.extras else None)
        if extras_flag is not None:
            return bool(extras_flag)
        w = ctx.extras.get("window") if ctx.extras else None
        if w is not None:
            try:
                if int(getattr(w, "_temple_dialog_hold_polls", 0) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                pass
        if ctx.analyzer is None:
            return False
        try:
            from temple_dialog_reader import read_temple_response_candidates
        except ImportError:
            return False
        try:
            read = read_temple_response_candidates(ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        if w is not None:
            prev_by_offset = dict(getattr(
                w, "_temple_dialog_text_by_offset", {}))
            baselined = bool(getattr(w, "_temple_dialog_baselined", False))
            if baselined:
                return any(
                    prev_by_offset.get(c.source_offset) != c.text
                    for c in read.candidates
                )
        return False

    def _is_temple_panel_owned(self, ctx: SessionContext) -> bool:
        """直近 poll で神殿系 panel_owner が描画権を claim 中か。

        神官メニューと神官の顔画像 (FACES00.CIF) の切替時など、
        shop_popup_detector の kind=none に陥る瞬間でも神殿会話が
        継続中である surface (= 神官メニュー / 費用 / 入力 / 神官応答)
        を捕捉する。TavernSession._is_tavern_panel_owned と同型。

        テスト容易性のため ctx.extras["temple_panel_owner"] が与えられて
        いればそれを優先する。
        """
        extras_owner = (ctx.extras.get("temple_panel_owner")
                        if ctx.extras else None)
        if extras_owner is not None:
            return extras_owner in _TEMPLE_PANEL_OWNERS
        w = ctx.extras.get("window") if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, "_panel_owner", "") or ""
        return owner in _TEMPLE_PANEL_OWNERS

    # ------------------------------------------------------------------
    # 公開ヘルパ
    # ------------------------------------------------------------------

    @property
    def last_img(self) -> str:
        """直前 poll で観測した img_name (= YESNO→MENU_RT 遷移判定用)。"""
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
        # Temple context (または起動直後の unknown) のみ許可
        if not (self._is_temple_context(ctx)
                or self._facility_info_unknown(ctx)):
            return False
        kind, owner = self._detect_shop_state(ctx)
        # owner_kind == "temple" の時のみ start
        if owner == "temple" and kind in _TEMPLE_OWNER_KINDS:
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
        if self._known_non_temple_context(ctx):
            return self._stop()

        # 2-5. 継続条件
        kind, owner = self._detect_shop_state(ctx)
        if owner == "temple" and kind in _TEMPLE_OWNER_KINDS:
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        # phase=out は神殿 L4 離脱の強い信号。古い
        # temple_priest_reply / temple_cost / temple_prompt owner や stale
        # response buffer だけで latch を延命しない。
        if self._detect_temple_phase(ctx) == "out":
            return self._stop()
        if self._is_yesno_active(ctx):
            # YESNO.IMG は神殿コスト確認等で出る。active 中は継続。
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        # 神殿テンプレ (A155 donate prompt / A152/A153/A154 等)
        # が active_template として表示中なら継続。current_ptr 由来候補で
        # 辞書 hit する場合のみ True (= stale 排除)。
        if self._is_temple_template_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        # 神官応答が response buffer に出た瞬間は shop_state から見えないため、
        # pointer が response buffer を指す lookup hit を L3 継続信号にする。
        if self._is_temple_response_active(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False
        # 神官の顔画面 (FACES00.CIF) など、shop_popup_detector が kind=none を
        # 返す瞬間でも神殿系 panel_owner が継続中なら L3 latch を維持する。
        if self._is_temple_panel_owned(ctx):
            self._none_shop_polls = 0
            self._last_img = ctx.img_name or ""
            return False

        # 6. ヒステリシス
        self._none_shop_polls += 1
        if self._none_shop_polls >= _TEMPLE_NONE_HYSTERESIS_POLLS:
            return self._stop()
        # 継続中も last_img を更新 (= IMG 遷移検出用)
        self._last_img = ctx.img_name or ""
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理。

        翻訳描画は poll_controller 側の temple route で行う
        (= memory アクセスのため analyzer / window 参照が必要)。本メソッドは
        将来的な物理移植の受け皿として残す。
        """
        return None


__all__ = ["TempleSession"]
