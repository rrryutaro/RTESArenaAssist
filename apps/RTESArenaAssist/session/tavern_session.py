"""session/tavern_session.py — 宿屋店主会話セッション。

宿屋店主との対話 UI が画面に出ている間だけ active にする latch。
「TAVERN*.MIF 在室中」ではなく「店主 popup/menu が進行中」を表す。

境界:
- 開始 (try_start): 次のすべてを満たす瞬間
    1. `top_level_state == "normal-play"`
    2. `in_interior == True`
    3. 現在地が Tavern と判定できる
       - `interior_mif_name` が `TAVERN*.MIF`
       - または `facility_kind == "TAVERN"`
       - または施設情報が空 (起動直後など) で shop kind が出ている fallback
    4. `shop_popup_detector.kind` が店主所有 kind に該当
       (`shop_menu` / `shop_buy` / `shop_rooms` / `shop_rumor_type`)
  → 入店しただけでは start しない。店主をクリックして UI が出た瞬間 active。

- 終了 (try_stop): 次の優先順
    1. `in_interior == False` / `top_level_state != "normal-play"`
       / Tavern 以外への遷移は即 stop
    2. shop kind が店主所有 kind なら継続 (none カウンタ reset)
    3. `img_name == NEGOTBUT.IMG` なら継続 (active 中に限る)。
       `YESNO.IMG` は宿屋 active_template surface 側で判定する。
    4. 店主 Rumors 由来の Rumor Type popup なら継続
       (ASK ABOUT buffer の active sub menu が "Rumor Type")
    5. 上記すべてに当てはまらない場合、`kind == "none"` が N=3 poll 連続で stop

`N=3` の根拠: poll が約 5Hz のため約 0.6 秒。一時的な none を吸収しつつ、
店主会話終了後に一般 NPC 会話を長時間ブロックしない。

設計意図: 「宿屋在室」latch だと宿屋内の一般 NPC 会話まで blocking してしまう。
店主会話 UI に絞ることで、店主と話していない時は NpcChatSession が
通常通り start でき、一般 NPC ASK ABOUT? / Where is... が動く。

分離設計:
- 本セッションは latch (= active/inactive 判定) + Rumor Type 描画のみ担当。
- 宿屋 YES/NO (= A131 等) は `active_template_module` が描画する。
- 宿屋から開始した交渉本文は `normal_play/negotiation_module` が描画する
  (session_manager 排他から外し並列動作可能な module 化)。
- 店主メニュー / 部屋一覧 / 酒一覧は `shop_menu_module` が描画する。
- 噂応答は経路 1 (= 店内 NPC 応答) が描画する。
- 屋内施設情報の保持は poll_controller 側で維持。
各 surface 描画は本セッションに集約せず、それぞれ専用 module へ分離する。
"""
from __future__ import annotations

from .session_base import SessionBase, SessionContext
from .npc_chat_session import NPC_PHASE_ASKING


# 店主所有 popup の kind 集合 (shop_popup_detector 出力)
_TAVERN_OWNER_KINDS = frozenset({
    "shop_menu",
    "shop_buy",
    "shop_rooms",
    "shop_rumor_type",
})


# kind=="none" が連続した時の stop 閾値 (約 0.6 秒 @ 5Hz poll)
_TAVERN_NONE_HYSTERESIS_POLLS = 3


class TavernSession(SessionBase):
    """宿屋店主との会話セッション (店主 UI 中のみ active)。"""

    name = "tavern"

    def __init__(self) -> None:
        super().__init__()
        self._none_shop_polls = 0

    # ------------------------------------------------------------------
    # Tavern context 判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_tavern_context(ctx: SessionContext) -> bool:
        """ctx の interior_mif_name / facility_kind から Tavern か判定。

        どちらも取得不能 (起動直後等) の場合は False を返し、呼び出し側で
        unknown fallback として扱う。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif.startswith("TAVERN"):
            return True
        if ctx.facility_kind == "TAVERN":
            return True
        return False

    @staticmethod
    def _facility_info_unknown(ctx: SessionContext) -> bool:
        """interior_mif_name / facility_kind がともに空 (情報未取得) か。"""
        return not ctx.interior_mif_name and not ctx.facility_kind

    @staticmethod
    def _known_non_tavern_context(ctx: SessionContext) -> bool:
        """Tavern 以外の interior であることが明確に判定できるか。

        try_stop で「テレポート等で別施設へ移動」を即 stop する判定に使う。
        """
        mif = (ctx.interior_mif_name or "").upper()
        if mif and not mif.startswith("TAVERN"):
            return True
        if ctx.facility_kind and ctx.facility_kind != "TAVERN":
            return True
        return False

    # ------------------------------------------------------------------
    # shop kind 検出
    # ------------------------------------------------------------------

    def _detect_shop_state(self, ctx: SessionContext) -> tuple[str, str]:
        """shop_popup_detector の (kind, owner_kind) を取得する。

        テスト容易性のため:
          - ctx.extras["shop_kind"] が与えられていればそれを kind に使う
          - ctx.extras["owner_kind"] が与えられていればそれを owner に使う
          - 与えられない場合は shop_popup_detector を実呼び出しして
            kind から推測 (= 後方互換)。
        """
        extras_kind = ctx.extras.get("shop_kind") if ctx.extras else None
        extras_owner = ctx.extras.get("owner_kind") if ctx.extras else None
        if extras_kind is not None or extras_owner is not None:
            kind = extras_kind if extras_kind is not None else "none"
            # owner 未指定 + kind が tavern owner kind の場合は tavern として扱う
            # (後方互換: 既存テストの "shop_kind=shop_menu" が tavern を意味する)
            owner = extras_owner if extras_owner is not None else (
                "tavern" if kind in _TAVERN_OWNER_KINDS else "")
            return (kind or "none", owner or "")
        try:
            from shop_popup_detector import detect_shop_popup_state
        except ImportError:
            return ("none", "")
        if ctx.top_level_state != "normal-play":
            return ("none", "")
        if not ctx.in_interior:
            return ("none", "")
        # YESNO.IMG 中の店主メニュー復帰可否は poll_controller が
        # 決定し window に保存している。本セッションが独自フラグ無しで再検出すると
        # YESNO 下のメニューを none と誤認して継続信号を失い、メニュー復帰中なのに
        # latch が停止 -> active_facility 喪失で画面が崩れる。同じ判定軸を使う。
        w = ctx.extras.get("window") if ctx.extras else None
        _allow_recovery = bool(
            getattr(w, "_yesno_menu_recovery_last", False)) if w else False
        try:
            state = detect_shop_popup_state(
                ctx.analyzer, ctx.anchor,
                top_level_state=ctx.top_level_state,
                img_name=ctx.img_name,
                in_interior=ctx.in_interior,
                screen_id=ctx.screen_id,
                allow_yesno_menu_recovery=_allow_recovery,
                interior_mif_name=ctx.interior_mif_name or "",
                active_facility_name=(
                    "tavern"
                    if self._active or self._is_tavern_context(ctx)
                    else ""),
            )
            kind = state.kind or "none"
            owner = state.owner_kind or ""
            # YESNO 復帰は宿屋フローでのみ許可されるため、復帰中にメニュー系
            # kind が出て owner 不明 (= buffer 解析で group 未登録) でも tavern
            # 所有とみなす。これで latch 継続判定が owner='' で取りこぼさない。
            if (_allow_recovery and not owner
                    and kind in _TAVERN_OWNER_KINDS):
                owner = "tavern"
            return (kind, owner)
        except Exception:
            return ("none", "")

    # ------------------------------------------------------------------
    # 継続判定ヘルパ
    # ------------------------------------------------------------------

    @staticmethod
    def _is_negotiation_active(ctx: SessionContext) -> bool:
        """ctx.img_name が NEGOTIATION_PROFILES 登録 IMG か。

        active 中の継続信号にのみ使う (inactive からの start には使わない)。
        """
        img = (ctx.img_name or "").upper()
        if not img:
            return False
        # 宿屋の YESNO.IMG は忍び込み確認 / 価格確認 / 結果表示と共有される。
        # 画像名だけで継続させると、会話終了後の IMG 残留で L4 から離脱
        # できなくなるため、YESNO は active_template 側の surface 判定へ委ねる。
        if img == "YESNO.IMG":
            return False
        try:
            from negotiation_reader import get_negotiation_profile
        except ImportError:
            return False
        return get_negotiation_profile(img) is not None

    # 店主会話中の L4 surface 描画中 (= panel_owner が
    # tavern 関連補助経路の所有) は L3 latch を維持する。
    # 酒を飲んだ後の "You finish the Orcgut..." 応答時に shop_state.kind=none
    # かつ template_surface_kind が空 → 3 poll で L3 離脱する症状の修正。
    _TAVERN_PANEL_OWNERS = frozenset({
        "tavern_rumor_type", # 噂タイプ サブメニュー (tavern.poll 由来)
        "negotiation",       # 価格交渉 (NEGOTBUT.IMG / YESNO.IMG)
        "active_template",   # A002/A131/A130/A132/A133/A134/A135 等
        "npc_dialog",        # 店内応答 (酒応答 / 店主挨拶 / 噂応答)
    })

    def _is_tavern_panel_owned(self, ctx: SessionContext) -> bool:
        """直近 poll で tavern 系 panel_owner が claim 中か。

        in-store 応答 (= 酒の感想 / 店主挨拶 / 噂応答) など、shop_state.kind
        からは見えないが店主会話の継続中である surface を捕捉する。
        shop_menu / shop_buy / shop_rumor_type は shop_state の実検出でのみ
        継続させ、古い panel_owner だけでは L3 を保持しない。
        テスト容易性のため ctx.extras["tavern_panel_owner"] が与えられて
        いればそれを優先する。
        """
        extras_owner = (ctx.extras.get("tavern_panel_owner")
                        if ctx.extras else None)
        if extras_owner is not None:
            return extras_owner in self._TAVERN_PANEL_OWNERS
        w = ctx.extras.get("window") if ctx.extras else None
        if w is None:
            return False
        owner = getattr(w, "_panel_owner", "") or ""
        return owner in self._TAVERN_PANEL_OWNERS

    def _is_tavern_template_surface_active(
            self, ctx: SessionContext) -> bool:
        """tavern-owned active_template surface (= L4 子画面) が
        画面上にある間は L3 latch を維持する継続信号を返す。

        対象 surface (active_template_reader.template_surface_kind):
          - tavern_stay_days   : A002 'How many days are you staying?'
          - tavern_sneak_confirm: A131 'Are you trying to sneak into a room?'
          - tavern_sneak_result : A130/A132 忍び込み結果

        これらは shop_popup_detector からは kind="none" に見えるため、
        本ヘルパが無いと L3 latch が誤って離脱してしまう。

        テスト容易性のため ctx.extras["tavern_template_surface_active"] が
        与えられていればそれを優先する。
        """
        extras_flag = (
            ctx.extras.get("tavern_template_surface_active")
            if ctx.extras else None)
        if extras_flag is not None:
            return bool(extras_flag)
        try:
            from active_template_reader import (
                read_active_template_candidates,
                template_surface_kind,
            )
        except ImportError:
            return False
        try:
            candidates = read_active_template_candidates(
                ctx.analyzer, ctx.anchor)
        except Exception:
            return False
        _tavern_surface_kinds = (
            "tavern_stay_days",
            "tavern_sneak_confirm",
            "tavern_sneak_result",
        )
        for c in candidates:
            try:
                kind = template_surface_kind(c)
            except Exception:
                continue
            if kind in _tavern_surface_kinds:
                return True
        return False

    def _is_tavern_rumor_type_continuation(self, ctx: SessionContext) -> bool:
        """店主 Rumors → Rumor Type popup の継続信号。

        ASK ABOUT buffer を借用した Rumor Type popup 中は shop_popup_detector が
        none を返すケースがある。npc_phase=ASKING かつ active sub menu が
        "Rumor Type" の時のみ継続と判定する。

        テスト容易性のため ctx.extras["tavern_rumor_type_active"] が与えられて
        いればそれを優先する。
        """
        extras_flag = (ctx.extras.get("tavern_rumor_type_active")
                       if ctx.extras else None)
        if extras_flag is not None:
            return bool(extras_flag)
        if ctx.npc_phase != NPC_PHASE_ASKING:
            return False
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import (
                parse_menu, detect_active_sub_menu_title,
            )
            from popup11_list_detector import read_active_menu_marker
        except ImportError:
            return False
        try:
            marker = read_active_menu_marker(ctx.analyzer, ctx.anchor)
            if not marker:
                return False
            raw = read_ask_about_menu(ctx.analyzer, ctx.anchor)
            parsed = parse_menu(raw)
            title = detect_active_sub_menu_title(parsed, marker)
            return title == "Rumor Type"
        except Exception:
            return False

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def _stop(self, ctx: SessionContext | None = None) -> bool:
        self._none_shop_polls = 0
        self._set_active(False)
        if ctx is not None:
            w = ctx.extras.get("window") if ctx.extras else None
            if w is not None:
                try:
                    w._tavern_rumor_key_prev = None
                    w._ui_router.clear_if_owner("tavern_rumor_type")
                except AttributeError:
                    pass
                # L3 latch 終了時に rumor flow フラグもクリア。
                w._tavern_rumor_flow_active = False
        return True

    def try_start(self, ctx: SessionContext) -> bool:
        if self._active:
            return False
        if ctx.top_level_state != "normal-play" or not ctx.in_interior:
            return False
        # Tavern context (または起動直後の unknown) のみ許可。
        # 他施設で誤 start しないよう、unknown fallback は施設情報が
        # 完全に空の場合に限定する。
        if not (self._is_tavern_context(ctx)
                or self._facility_info_unknown(ctx)):
            return False
        kind, owner = self._detect_shop_state(ctx)
        # owner_kind が "tavern" の時のみ start (他施設の shop kind は無視)
        if owner == "tavern" and kind in _TAVERN_OWNER_KINDS:
            self._none_shop_polls = 0
            self._set_active(True)
            return True
        return False

    def try_stop(self, ctx: SessionContext) -> bool:
        if not self._active:
            return False
        # 1. 即 stop 条件
        if ctx.top_level_state != "normal-play" or not ctx.in_interior:
            return self._stop(ctx)
        if self._known_non_tavern_context(ctx):
            return self._stop(ctx)

        # 2-4. 継続条件
        kind, owner = self._detect_shop_state(ctx)
        # 主メニュー (= shop_menu) に戻ったら rumor flow を解除。
        # 噂応答→主メニュー復帰の瞬間に negotiation_module の defer を解く。
        if owner == "tavern" and kind == "shop_menu":
            w = ctx.extras.get("window") if ctx.extras else None
            if w is not None and getattr(w, "_tavern_rumor_flow_active",
                                          False):
                w._tavern_rumor_flow_active = False
        # 1軸化: 単一判定 (前 poll の _tavern_view) が L4 子画面を可視と結論して
        # いる間は L3 latch を維持する。これを継続の主信号とし、個別の
        # _is_tavern_* 判定への依存を減らす (= 判定の一元化)。前 poll 値のため
        # 1 poll 遅延するが latch 継続には許容範囲。
        _w_view = ctx.extras.get("window") if ctx.extras else None
        if _w_view is not None and getattr(
                _w_view, "_tavern_view_l4_visible", False):
            self._none_shop_polls = 0
            return False
        # tavern owner の shop kind なら継続。他施設の owner は継続しない。
        if owner == "tavern" and kind in _TAVERN_OWNER_KINDS:
            self._none_shop_polls = 0
            return False
        if self._is_negotiation_active(ctx):
            self._none_shop_polls = 0
            return False
        if self._is_tavern_rumor_type_continuation(ctx):
            self._none_shop_polls = 0
            return False
        # stay_days (A002) / sneak_confirm (A131) /
        # sneak_result (A130/A132) は active_template が描画する surface だが
        # L3 親状態は tavern のまま維持する (= L3/L4 分離)。
        if self._is_tavern_template_surface_active(ctx):
            self._none_shop_polls = 0
            return False
        # panel_owner が tavern 系の補助経路
        # 所有 (= tavern_rumor_type / negotiation / active_template /
        # npc_dialog) なら L3 latch を維持する。shop_menu / shop_buy /
        # shop_rumor_type は実 shop_state 検出でのみ維持し、古い owner 残置
        # だけで会話終了後に L4 固着しないようにする。
        # 酒を飲んだ後の "You finish the Orcgut..." 応答時に shop_state.kind=
        # none かつ template_surface_kind が空 → 3 poll で L3 離脱する症状を
        # 防ぐ。in-store 応答は店主会話の継続そのもの。
        if self._is_tavern_panel_owned(ctx):
            self._none_shop_polls = 0
            return False

        # 5. ヒステリシス
        self._none_shop_polls += 1
        if self._none_shop_polls >= _TAVERN_NONE_HYSTERESIS_POLLS:
            return self._stop(ctx)
        return False

    def poll(self, ctx: SessionContext) -> None:
        """latch on 中の内部処理: tavern-owned Rumor Type 描画のみ。

        店主 ASK ABOUT? Rumor Type サブメニューが画面に出ている場合のみ、
        ASK ABOUT? buffer から Rumor Type サブメニューだけを抽出して翻訳
        タブ・パネルに描画する。

        他の surface (= 宿屋 YES/NO、宿泊交渉、店主メニュー、
        噂応答) は本セッションでは描画せず、それぞれ active_template_module /
        normal_play/negotiation_module / shop_menu_module / 経路 1 が担当する
        (= 各 surface を専用 module へ分離し、negotiation は並列動作可能)。
        """
        w = ctx.extras.get("window") if ctx.extras else None
        if w is None:
            return

        # tavern_rumor_type 所有権の release は npc_phase /
        # shop_kind による early return より前に必ず判定する。
        # release を early return 後に置くと、噂を選んだ瞬間 npc_phase が
        # ASKING を抜けたとき panel_owner='tavern_rumor_type' が残置し続け、
        # route 1 が L4 ガードで blocked されたまま噂応答が描画されない。
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import (
                parse_menu, build_display_sub,
                build_panel_display_sub,
                detect_active_sub_menu_title,
            )
            from popup11_list_detector import read_active_menu_marker
        except ImportError:
            return
        try:
            _aa_marker = read_active_menu_marker(w._analyzer, w._anchor)
            _aa_raw = read_ask_about_menu(w._analyzer, w._anchor)
            _aa_parsed = parse_menu(_aa_raw)
            _aa_active_sub = detect_active_sub_menu_title(
                _aa_parsed, _aa_marker)
        except Exception:  # noqa: BLE001
            _aa_active_sub = None

        _rumor_type_visible = (_aa_active_sub == "Rumor Type")
        if not _rumor_type_visible:
            # Rumor Type サブメニュー終了 → 所有権 release
            # (npc_phase / shop_kind に関わらず必ず判定)。
            if w._ui_router.is_owner("tavern_rumor_type"):
                w._tavern_rumor_key_prev = None
                w._ui_router.clear_if_owner("tavern_rumor_type")

        # 以降は描画判定: ASKING 以外や shop_menu/buy active 時は描画しない。
        if ctx.npc_phase != NPC_PHASE_ASKING:
            return
        # 念のため、shop_menu / shop_buy が active なら描画しない
        # (後段の shop_menu/buy 描画と競合させないため)
        kind, _ = self._detect_shop_state(ctx)
        if kind in ("shop_menu", "shop_buy", "shop_rumor_type"):
            return
        try:
            if not _rumor_type_visible:
                # rumor flow からまだ抜けていない (= 噂応答中)
                # ことを示すフラグを True に保つ。shop_menu 主メニュー復帰時
                # (= try_stop で kind=='shop_menu' 検出) に False に戻す。
                return
            # Rumor Type サブメニュー表示中 → flow フラグを立てる
            w._tavern_rumor_flow_active = True
            # 判定描画セット原則: 噂種別は本セッションが自前の ASK ABOUT
            # marker 判定で前景を確定し自身で描画する独立の判定描画セット。施設の
            # 単一判定 (前 poll の _tview.render_owner) に従属させると、1 poll 遅延と
            # 誤分類で owner が固着する (= 判定/描画のクロス境界分離)。自前の
            # marker 判定で前景を確定する (_tview ゲートは使わない)。
            _rt_key = ("tavern_rumor_type", tuple(
                s.get("title", "")
                for s in _aa_parsed.get("sub_menus", [])))
            _rt_owner_taken = (
                w._ui_router.current_owner() != "tavern_rumor_type")
            _rt_prev_key = getattr(w, "_tavern_rumor_key_prev", None)
            if _rt_key == _rt_prev_key and not _rt_owner_taken:
                return
            w._tavern_rumor_key_prev = _rt_key
            _rt_tab_en, _rt_tab_ja = build_display_sub(
                _aa_parsed, sub_title="Rumor Type")
            _rt_panel_en, _rt_panel_ja = build_panel_display_sub(
                _aa_parsed, sub_title="Rumor Type")
            w._ui_router.update_translation(
                "tavern_rumor_type",
                _rt_tab_en, _rt_tab_ja,
                panel_en=_rt_panel_en,
                panel_ja=_rt_panel_ja)
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger("RTESArenaAssist").exception(
                "tavern rumor type display failed")

    def on_other_session_started(self, ctx: SessionContext) -> None:
        """他セッション on 時の強制 off + tavern_rumor_type 所有権クリア。"""
        w = ctx.extras.get("window") if ctx.extras else None
        if w is not None:
            try:
                w._tavern_rumor_key_prev = None
                w._ui_router.clear_if_owner("tavern_rumor_type")
            except AttributeError:
                pass
        super().on_other_session_started(ctx)


__all__ = ["TavernSession"]
