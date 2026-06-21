"""UI 更新を集約する薄ラッパ。

assist_window の `_tab_translate` / `_layout_translate_panel` / `_panel_owner`
を組で更新する経路を 1 つに絞り、所有権 (panel_owner) の上書きと
Rule G クリーンアップを集中管理する。

session / module は本ラッパ経由でのみ翻訳タブ・layout パネル・panel_owner を
更新する。
"""
from __future__ import annotations

from dataclasses import replace
import logging
from typing import Optional

import assist_settings as settings
import i18n_helper as i18n
from assist_log import recog as _recog
from display_intent import DisplayIntent, PollFrame
from hierarchy_state import (
    active_facility_session_name,
    facility_owners_for_session,
    CONVERSATION_PANEL_OWNERS,
)
from panel_mode_resolver import resolve_flush_mode

_log = logging.getLogger("RTESArenaAssist")

# hierarchy_state.CONVERSATION_PANEL_OWNERS と統一 (= equipment_*/mages_* も
# 含む)。施設会話の menu/list/spellmaker/placeholder を update_translation 経由で
# 描画した際に suppress_fallback=True を効かせるための owner 集合。
_CONVERSATION_TAB_OWNERS = CONVERSATION_PANEL_OWNERS

class UiRouter:
    def __init__(self, window) -> None:
        self._window = window
        self._poll_frame: Optional[PollFrame] = None
        self._pending_display: Optional[DisplayIntent] = None
        self._pending_order = 0
        self._pending_display_order = 0
        # 翻訳が実反映された時の単一オブザーバー (TTS/ログ分配)
        self._translation_observer = None
        self._obs_last_key = None

    def set_translation_observer(self, callback) -> None:
        """翻訳が実 UI に反映された時に呼ぶコールバックを設定する。
        callback(panel_owner: str, original: str, text: str) -> None。
        変化時のみ呼ばれる（同一 owner/原文/訳の連続は1回）。"""
        self._translation_observer = callback

    def begin_poll_frame(self, frame: PollFrame) -> None:
        """poll 1 周分の表示候補収集を開始する。"""
        self._poll_frame = frame
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0

    def propose_display(self, intent: DisplayIntent) -> None:
        """poll 末尾に反映する表示候補を登録する。

        priority が高い候補を優先し、同 priority では後から届いた候補を
        採用する。poll 外で呼ばれた場合は通常の即時反映として扱う。
        """
        if self._poll_frame is None:
            self.apply_display(intent)
            self._apply_flush_panel_mode(intent)
            return
        resolved = self._resolve_proposed_intent(intent)
        if resolved is None:
            return
        self._pending_order += 1
        current = self._pending_display
        merged = self._merge_compatible_intents(current, resolved)
        if merged is not None:
            self._pending_display = merged
            self._pending_display_order = self._pending_order
            self._apply_logical_display(merged)
            return
        if (current is None or
                (resolved.priority, self._pending_order) >=
                (current.priority, self._pending_display_order)):
            self._pending_display = resolved
            self._pending_display_order = self._pending_order
            self._apply_logical_display(resolved)

    def _merge_compatible_intents(
            self,
            current: Optional[DisplayIntent],
            resolved: DisplayIntent) -> Optional[DisplayIntent]:
        """同一 poll 内の mode-only と content intent を 1 件へ畳み込む。"""
        if current is None or current.priority != resolved.priority:
            return None
        if current.kind == "panel_mode" and resolved.kind == "translation":
            if (current.mode is not None
                    and (resolved.mode is None
                         or resolved.mode == current.mode)):
                return replace(resolved, mode=current.mode)
        if current.kind == "translation" and resolved.kind == "panel_mode":
            if (resolved.mode is not None
                    and (current.mode is None
                         or current.mode == resolved.mode)):
                return replace(current, mode=resolved.mode)
        if current.kind == "translation" and resolved.kind == "translation":
            if (current.mode is not None
                    and (resolved.mode is None
                         or resolved.mode == current.mode)):
                return replace(resolved, mode=current.mode)
        return None

    def pending_display(self) -> Optional[DisplayIntent]:
        return self._pending_display

    def flush_poll_display(self) -> None:
        """収集済み候補の最終 1 件だけを実 UI に反映して poll frame を閉じる。"""
        intent = self._pending_display
        frame = self._poll_frame
        self._poll_frame = None
        self._pending_display = None
        self._pending_order = 0
        self._pending_display_order = 0
        if intent is not None:
            self.apply_display(intent)
        self._apply_flush_panel_mode(intent)
        self._log_flush_winner(intent, frame)
        self._log_facility_display_invariant(frame)

    def _winner_has_content(self, intent: Optional[DisplayIntent]) -> bool:
        """勝者が空でない翻訳本文を持つか (tab_translate の no_data 判定と同義)。"""
        if intent is None or intent.kind != "translation":
            return False
        en = (intent.en or "").strip()
        try:
            nd = i18n.tr("translate.no_data")
        except Exception:  # noqa: BLE001
            nd = ""
        return bool(en) and en not in ("—", nd)

    def _apply_flush_panel_mode(self, intent: Optional[DisplayIntent]) -> None:
        """panel_mode を書く単一権威。勝者の mode を flush で1回確定する。

        勝者 intent が運ぶ mode (= 各 list/screen/panel_mode kind は .mode を保持・
        翻訳/クリア系は intent.mode か現在 mode) を ``resolve_flush_mode`` に通し、
        前景系は素通し・翻訳系は fallback 床判定で確定する。owner のみ更新する
        release_if_owner だけは mode を触らない。per-push の fallback bypass を
        本経路へ収束させる。
        """
        if intent is None or intent.kind == "release_if_owner":
            return
        w = self._window
        tab = getattr(w, "_tab_translate", None)
        if tab is None:
            return
        try:
            cur = tab.panel_mode()
        except AttributeError:
            return
        winner_mode = intent.mode if intent.mode is not None else cur
        is_tab_owner = bool(
            intent.kind == "translation"
            and (intent.panel_owner or "") in _CONVERSATION_TAB_OWNERS)
        try:
            emulate = bool(settings.get(
                "translate_tab_emulate_panel_hidden", False))
            fb = settings.get("translate_fallback_screen", "map")
        except Exception:  # noqa: BLE001
            emulate, fb = False, "map"
        target = resolve_flush_mode(
            winner_mode=winner_mode,
            top_level=getattr(w, "_top_level_state", "pregame"),
            emulate=emulate,
            winner_has_content=self._winner_has_content(intent),
            winner_is_tab_owner=is_tab_owner,
            fallback_setting=fb)
        if target is not None and target != cur:
            tab.set_panel_mode(target)

    def _log_flush_winner(self, intent: Optional[DisplayIntent],
                          frame: Optional[PollFrame]) -> None:
        """診断: poll の勝者(kind/owner/mode/priority)を変化時のみ記録。

        item_pickup 表示中に背景 push が panel_mode を奪う cross-poll 交替の
        機構をログで確認するための観測基盤 (挙動不変)。
        """
        if intent is None:
            key = ("<none>", "", "", 0)
        else:
            key = (intent.kind, intent.panel_owner or "",
                   intent.mode or "", intent.priority)
        prev = getattr(self, "_winner_key", None)
        if key == prev:
            return
        self._winner_key = key
        # idle 同士の振動 (<none> ↔ owner なし clear) は毎 poll のノイズなので
        # log しない（常時出力禁止）。実 owner/mode が勝った変化のみ記録する。
        def _idle(k) -> bool:
            return k is not None and k[0] in ("<none>", "clear") and not k[1]
        if _idle(key) and _idle(prev):
            return
        try:
            tab_mode = self._window._tab_translate.panel_mode()
        except (AttributeError, RuntimeError):
            tab_mode = "?"
        _recog(
            _log,
            "flush winner: kind=%s owner=%r mode=%r prio=%d tab_mode=%r "
            "owner_now=%r reason=%r",
            key[0], key[1], key[2], key[3], tab_mode,
            self.current_owner(),
            (intent.reason if intent is not None else ""))

    def _resolve_proposed_intent(
            self, intent: DisplayIntent) -> Optional[DisplayIntent]:
        """候補登録時点の条件を解決し、末尾反映用 intent に正規化する。"""
        current = self.current_owner()
        if (intent.allowed_current_owners is not None
                and current not in intent.allowed_current_owners):
            _log.debug(
                "ui_router.propose_display skipped "
                "(kind=%s owner=%r current=%r allowed=%r)",
                intent.kind, intent.panel_owner, current,
                intent.allowed_current_owners)
            return None
        if intent.allowed_current_owners is not None:
            intent = replace(intent, allowed_current_owners=None)
        if intent.kind == "clear":
            return intent
        if intent.kind == "clear_if_owner":
            if current != intent.panel_owner:
                return None
            return DisplayIntent.clear(
                "",
                mode=intent.mode,
                clear_place_list=intent.clear_place_list,
                priority=intent.priority,
                reason=intent.reason,
            )
        if intent.kind == "release_if_owner":
            if current != intent.panel_owner:
                return None
            return DisplayIntent.claim_owner(
                "",
                priority=intent.priority,
                reason=intent.reason,
            )
        return intent

    def _apply_logical_display(self, intent: DisplayIntent) -> None:
        """候補採用時点で owner だけ先行更新し、同 poll 内の判定を保つ。"""
        if intent.kind == "translation":
            if not intent.keep_owner:
                self._window._panel_owner = intent.panel_owner
            return
        if intent.kind in (
            "clear",
            "claim_owner",
            "shop_buy_list",
            "facility_list",
            "item_pickup_list",
            "load_screen_slots",
            "equipment_list",
            "spell_detail",
            "place_list",
        ):
            self._window._panel_owner = intent.panel_owner

    def update_translation(self, panel_owner: str, en: str, ja: str,
                           *, mode: Optional[str] = "translate",
                           panel_en: Optional[str] = None,
                           panel_ja: Optional[str] = None,
                           update_panel: bool = True,
                           update_tab: bool = True,
                           keep_owner: bool = False,
                           priority: int = 0,
                           reason: str = "",
                           speech_role: Optional[str] = None,
                           speech_text: Optional[str] = None) -> None:
        """翻訳タブ + layout パネルを同時更新し panel_owner を登録する。

        panel_en / panel_ja を渡した場合のみ layout パネルの本文を
        翻訳タブと差し替える (= 翻訳タブはインデント/ホットキー付き、
        パネルはプレーン、というケースで使う)。

        読み上げ対象の表示は speech_role(状況説明/会話)を宣言する。
        speech_text を渡すと表示訳の代わりにその本文を読む(例: 価格交渉の差分)。
        宣言しない表示(menu/list/system)は読まれない(安全側)。
        """
        self.propose_display(DisplayIntent.translation(
            panel_owner, en, ja, mode=mode,
            panel_en=panel_en, panel_ja=panel_ja,
            update_panel=update_panel, update_tab=update_tab,
            keep_owner=keep_owner,
            priority=priority, reason=reason,
            speech_role=speech_role, speech_text=speech_text))

    def propose_translation(self, panel_owner: str, en: str, ja: str,
                            *, mode: Optional[str] = "translate",
                            panel_en: Optional[str] = None,
                            panel_ja: Optional[str] = None,
                            update_panel: bool = True,
                            update_tab: bool = True,
                            keep_owner: bool = False,
                            priority: int = 0,
                            reason: str = "",
                            speech_role: Optional[str] = None,
                            speech_text: Optional[str] = None) -> None:
        """poll 内では候補化し、poll 外では即時反映する翻訳更新。"""
        self.propose_display(DisplayIntent.translation(
            panel_owner, en, ja, mode=mode,
            panel_en=panel_en, panel_ja=panel_ja,
            update_panel=update_panel, update_tab=update_tab,
            keep_owner=keep_owner,
            priority=priority,
            reason=reason,
            speech_role=speech_role, speech_text=speech_text))

    def apply_display(self, intent: DisplayIntent) -> None:
        """DisplayIntent 1 件を実 UI に反映する。

        現在は即時反映として使う。次段階では poll 内で集めた intent の
        最終 1 件だけをここへ渡す。
        """
        if intent.allowed_current_owners is not None:
            current = self.current_owner()
            if current not in intent.allowed_current_owners:
                _log.debug(
                    "ui_router.apply_display skipped "
                    "(kind=%s owner=%r current=%r allowed=%r)",
                    intent.kind, intent.panel_owner, current,
                    intent.allowed_current_owners)
                return
        w = self._window

        if intent.kind == "translation":
            self._apply_translation(intent)
            return

        if intent.kind == "clear":
            # mode は flush 末尾の単一権威 (_apply_flush_panel_mode) が確定する。
            w._tab_translate.update_translation("", "", suppress_fallback=True)
            if intent.clear_place_list:
                try:
                    w._tab_translate.update_place_list([])
                except AttributeError:
                    pass
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "clear_if_owner":
            current = self.current_owner()
            if current != intent.panel_owner:
                return
            # mode は flush 末尾の単一権威 (_apply_flush_panel_mode) が確定する。
            w._tab_translate.update_translation("", "", suppress_fallback=True)
            if intent.clear_place_list:
                try:
                    w._tab_translate.update_place_list([])
                except AttributeError:
                    pass
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = ""
            return

        if intent.kind == "release_if_owner":
            if self.current_owner() == intent.panel_owner:
                w._panel_owner = ""
            return

        if intent.kind == "claim_owner":
            # mode は flush 末尾の単一権威 (_apply_flush_panel_mode) が確定する。
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "panel_mode":
            # mode は flush 末尾の単一権威 (_apply_flush_panel_mode) が確定する。
            # owner も payload も触らない (mode-only intent)。
            return

        if intent.kind == "shop_buy_list":
            # mode (= "shop_buy") は flush 末尾の単一権威が確定する。
            w._tab_translate.update_shop_buy_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "facility_list":
            # 施設専用 L4 一覧。mode="facility_list" (= 宿屋 shop_buy とは別
            # identity)、TabTranslate 側も別ページ。共有は純粋な行描画 helper のみ。
            # mode は flush 末尾の単一権威が確定する。
            try:
                w._tab_translate.set_facility_list_title(
                    intent.panel_ja or intent.panel_en or "")
            except AttributeError:
                pass
            w._tab_translate.update_facility_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "item_pickup_list":
            # mode (= "item_pickup") は flush 末尾の単一権威が確定する。
            w._tab_translate.update_item_pickup_list(
                intent.items, intent.remaining or 0)
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "load_screen_slots":
            # mode (= "load_screen") は flush 末尾の単一権威が確定する。
            w._tab_translate.update_load_screen_slots(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation("", "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "equipment_list":
            w._tab_translate.set_equipment_panel_title(intent.title)
            # mode (= "equipment") は flush 末尾の単一権威が確定する。
            w._tab_translate.update_equipment_list(intent.items)
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "spell_detail":
            # mode (= "spell_detail") は flush 末尾の単一権威が確定する。
            w._tab_translate.update_spell_detail(intent.items)
            if (w._layout_translate_panel is not None
                    and (intent.panel_en or intent.panel_ja)):
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        if intent.kind == "place_list":
            # mode (= "place_list") は flush 末尾の単一権威が確定する。
            w._tab_translate.set_place_list_title(intent.title)
            w._tab_translate.update_place_list(intent.items)
            if w._layout_translate_panel is not None:
                w._layout_translate_panel.update_translation(
                    intent.panel_en or "", intent.panel_ja or "")
            w._panel_owner = intent.panel_owner
            return

        raise ValueError(f"unknown display intent kind: {intent.kind!r}")

    def _apply_translation(self, intent: DisplayIntent) -> None:
        w = self._window
        # 観測ログ: UiRouter 経由の panel_owner / en / ja の変化を追跡する。
        _prev_key = getattr(self, "_applied_prev_key", None)
        _mode = intent.mode
        _mode_key = _mode if _mode is not None else "<keep>"
        _now_key = (intent.panel_owner, _mode_key, intent.en[:160], intent.ja[:160])
        if _prev_key != _now_key:
            self._applied_prev_key = _now_key
            # 分離内の判断結果 = panel に実際に適用された owner/本文 (応答表示等)。
            # 遷移時のみ RECOG で記録し、画面に何が出たかを判断できるようにする。
            _recog(
                _log,
                "panel applied: owner=%r mode=%r en=%r ja=%r",
                intent.panel_owner, _mode_key,
                intent.en[:120], intent.ja[:120])
        # mode は flush 末尾の単一権威 (_apply_flush_panel_mode) が確定する。
        # ここでは翻訳本文の描画のみを担う。
        if intent.update_tab:
            # fallback 判定は flush 末尾の単一権威 (_apply_flush_panel_mode)
            # へ集約する。ここでは描画専念 (常時 suppress)。会話/非会話の別は
            # flush で winner_is_tab_owner に反映する。
            w._tab_translate.update_translation(
                intent.en, intent.ja, suppress_fallback=True)
        if intent.update_panel and w._layout_translate_panel is not None:
            _pen = intent.panel_en if intent.panel_en is not None else intent.en
            _pja = intent.panel_ja if intent.panel_ja is not None else intent.ja
            w._layout_translate_panel.update_translation(_pen, _pja)
        if not intent.keep_owner:
            w._panel_owner = intent.panel_owner

        # 翻訳反映を単一オブザーバーへ通知（変化時のみ・TTS/ログ分配）。
        # en=原文 / ja=現在言語の訳。タブ本文が空(panel-only 表示)のときは
        # パネル本文を採用。owner はパネル限定更新では現 owner を補う。
        # 発生源が宣言した読み上げ役割/本文(speech_role/speech_text)を相乗りで渡す。
        # 受け手は宣言を消費するだけ(再判定なし)。
        if self._translation_observer is not None:
            _obs_en = intent.en or (intent.panel_en or "")
            _obs_ja = intent.ja or (intent.panel_ja or "")
            _obs_owner = intent.panel_owner or self.current_owner()
            _obs_key = (_obs_owner, _obs_en, _obs_ja)
            if self._obs_last_key != _obs_key:
                self._obs_last_key = _obs_key
                try:
                    self._translation_observer(
                        _obs_owner, _obs_en, _obs_ja,
                        intent.speech_role, intent.speech_text)
                except Exception:  # noqa: BLE001
                    _log.exception("translation_observer failed")

    def _log_facility_display_invariant(
            self, frame: Optional[PollFrame]) -> None:
        """L3 施設会話中に L4 owner が空 / 非施設 owner に奪われた場合に診断する。

        owner が空のときだけでなく、status 等の非施設 owner に flush で奪われた
        場合も警告する (= 会話表示が背景 panel に上書きされた取りこぼしを検出)。
        """
        w = self._window
        session_name = active_facility_session_name(w)
        if not session_name:
            return
        owner = self.current_owner()
        if owner and owner in facility_owners_for_session(session_name):
            return  # 正常: 施設会話 owner が表示中
        key = (
            session_name, owner,
            getattr(w, "_screen_id_prev", None),
            getattr(w, "_img_name_prev", "") or "",
            frame.top_level if frame is not None else "",
        )
        if key == getattr(self, "_facility_empty_owner_key", None):
            return
        self._facility_empty_owner_key = key
        _log.warning(
            "facility display invariant warning: active L3 session L4 owner "
            "is %s (session=%s screen=%r img=%r frame_top=%r)",
            ("empty" if not owner else f"non-facility {owner!r}"),
            session_name, getattr(w, "_screen_id_prev", None),
            getattr(w, "_img_name_prev", "") or "",
            frame.top_level if frame is not None else "")

    def current_owner(self) -> str:
        return getattr(self._window, "_panel_owner", "") or ""

    def is_owner(self, panel_owner: str) -> bool:
        return self.current_owner() == panel_owner

    def clear_if_owner(self, panel_owner: str,
                       *, mode: Optional[str] = None,
                       clear_place_list: bool = False) -> None:
        """所有権が一致する場合のみ翻訳表示と panel_owner をクリアする。"""
        self.propose_display(
            DisplayIntent.clear_if_owner(
                panel_owner, mode=mode,
                clear_place_list=clear_place_list))

    def clear_display(self, panel_owner: str = "",
                      *, mode: Optional[str] = "translate",
                      clear_place_list: bool = False,
                      allowed_current_owners:
                          Optional[tuple] = None) -> None:
        """翻訳表示をクリアする。

        既定 (allowed_current_owners=None) は所有者判定なしの無条件クリア。
        allowed_current_owners を渡すと、現在 owner がその集合に含まれる poll
        でのみクリアする (= 自単位/無所有のみクリアし他単位を温存する。共通層が
        foreign owner を逆算/preserve せずに分離化を保つための宣言的ゲート)。
        """
        self.propose_display(
            DisplayIntent.clear(
                panel_owner, mode=mode,
                clear_place_list=clear_place_list,
                allowed_current_owners=allowed_current_owners))

    def update_panel_translation(self, panel_en: str, panel_ja: str,
                                 *, speech_role: Optional[str] = None,
                                 speech_text: Optional[str] = None,
                                 priority: int = 0) -> None:
        """翻訳パネルのみ更新し、panel_owner は維持する。

        パネル限定の表示も読み上げ対象なら speech_role を宣言する
        (店内の単発台詞・会話応答など。観測側は panel_en/panel_ja を本文に採る)。

        priority は同 poll の panel_mode 候補と merge させたいとき用に指定する
        (propose_display は同 priority の panel_mode＋translation のみ 1 件へ畳み込む)。
        """
        self.propose_display(
            DisplayIntent.panel_translation(
                panel_en, panel_ja, priority=priority,
                speech_role=speech_role, speech_text=speech_text))

    def release_if_owner(self, panel_owner: str) -> None:
        """所有権が一致する場合のみ panel_owner を解放する。"""
        self.propose_display(DisplayIntent.release_if_owner(panel_owner))

    def claim_owner(self, panel_owner: str,
                    *, mode: Optional[str] = None) -> None:
        """既存 payload を触らずに mode / panel_owner だけを再主張する。"""
        self.propose_display(
            DisplayIntent.claim_owner(panel_owner, mode=mode))

    def set_panel_mode(self, mode: str, *, priority: int = 0,
                       reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.panel_mode(mode, priority=priority, reason=reason))

    def update_shop_buy_list(self, panel_owner: str, items: list,
                             panel_en: str, panel_ja: str) -> None:
        """shop_buy 系のリスト表示を owner と一緒に確定する。"""
        self.propose_display(
            DisplayIntent.shop_buy_list(panel_owner, items, panel_en, panel_ja))

    def update_facility_list(self, panel_owner: str, items: list,
                             panel_en: str, panel_ja: str,
                             *, priority: int = 0,
                             reason: str = "") -> None:
        """施設専用 L4 一覧を owner と一緒に確定する (宿屋 shop_buy とは別
        intent/mode)。武具店/魔術師ギルド等が自施設 owner で呼ぶ。"""
        self.propose_display(
            DisplayIntent.facility_list(
                panel_owner, items, panel_en, panel_ja,
                priority=priority, reason=reason))

    def update_item_pickup_list(self, panel_owner: str, items: list,
                                remaining: int) -> None:
        """NEWPOP item_pickup リスト表示を owner と一緒に確定する。"""
        self.propose_display(
            DisplayIntent.item_pickup_list(panel_owner, items, remaining))

    def update_load_screen_slots(self, panel_owner: str,
                                 slot_data: list) -> None:
        """ロード画面のセーブスロット一覧を owner と一緒に確定する。"""
        self.propose_display(
            DisplayIntent.load_screen_slots(panel_owner, slot_data))

    def propose_load_screen_slots(self, panel_owner: str,
                                  slot_data: list,
                                  *, priority: int = 0,
                                  reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.load_screen_slots(
                panel_owner, slot_data,
                priority=priority, reason=reason))

    def update_equipment_list(self, panel_owner: str, title: str,
                              items: list) -> None:
        """装備/呪文一覧を owner と一緒に確定する。"""
        self.propose_display(
            DisplayIntent.equipment_list(panel_owner, title, items))

    def propose_equipment_list(self, panel_owner: str, title: str,
                               items: list,
                               *, priority: int = 0,
                               reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.equipment_list(
                panel_owner, title, items,
                priority=priority, reason=reason))

    def update_spell_detail(self, panel_owner: str, data: dict,
                            *, panel_en: str = "",
                            panel_ja: str = "") -> None:
        """呪文詳細表示を owner と一緒に確定する。"""
        self.propose_display(DisplayIntent.spell_detail(
            panel_owner, data, panel_en=panel_en, panel_ja=panel_ja))

    def propose_spell_detail(self, panel_owner: str, data: dict,
                             *, panel_en: str = "", panel_ja: str = "",
                             priority: int = 0,
                             reason: str = "") -> None:
        self.propose_display(
            DisplayIntent.spell_detail(
                panel_owner, data, panel_en=panel_en, panel_ja=panel_ja,
                priority=priority, reason=reason))

    def update_place_list(self, panel_owner: str, items: list,
                          *, title: str = "", panel_en: str = "",
                          panel_ja: str = "") -> None:
        """場所一覧系表示を owner と一緒に確定する。"""
        self.propose_display(DisplayIntent.place_list(
            panel_owner, items, title=title,
            panel_en=panel_en, panel_ja=panel_ja))


__all__ = ["UiRouter"]
