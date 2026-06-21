"""
controllers/img_screen_controller.py — IMG ベース画面検出ハンドラ

`SCREEN_IMG_OFFSET`（anchor + 0x9176）が変化したときに `_poll` から呼ばれて、
画面 IMG 名（"MENU.IMG" / "LOADSAVE.IMG" / "INTRO01.IMG" / 等）に応じて
適切な翻訳・パネル表示を行う。

含まれるもの:
  - on_img_name_changed(img_name)  ← 公開エントリポイント
  - _show_startup_intro / _show_menu_screen / _show_load_screen /
    _show_newgame_slide  ← pregame L1 node 所有の top_level/pregame_render
    へ委譲する thin delegator (描画所有の node 化)

window 側の状態（_startup_layout_pushed / _newgame_layout_pushed フラグ）は
従来通り AssistWindow が保持し、pregame_render からは w.X 経由で参照する。
"""

import logging

import assist_settings as settings
from top_level.top_level_dispatcher import current_state as _current_top_level
from top_level import pregame_render as _pregame_render
from normal_play.npc_conversation_module import NPC_CONVERSATION_OWNER

_log = logging.getLogger("img_screen_controller")


class ImgScreenController:
    """IMG ベース画面検出のハンドラ。AssistWindow を back-reference として保持する。"""

    def __init__(self, window):
        self._w = window

    def _set_panel_mode(self, mode: str) -> None:
        self._w._ui_router.set_panel_mode(mode)

    # ------------------------------------------------------------------
    # 公開エントリポイント
    # ------------------------------------------------------------------

    def on_img_name_changed(self, img_name: str) -> None:
        """img_name が変化したときに呼ばれる。画面種別に応じて表示を切り替える。

        5 トリガー設計:
          本メソッド内では以下の 2 トリガーのみでトップレベル遷移を発火する。
          それ以外の信号ではトップレベル状態を維持する (層境界の厳格分離)。
          #2 非タイトル中 → タイトル中: MENU.IMG / PERCNTRO.XMI 検知
              システムメニューだけでなく、死亡後タイトル復帰もここで扱う。
          #3 タイトル中 → キャラクター作成中: EVLINTRO.XMI 検知
          #4 (タイトル中 → 通常プレイ中) のフラグ記録: LOADSAVE.IMG 検知時に
              _pregame_loadsave_seen を立てる (実際の遷移は poll_controller 側)
          #5 (キャラクター作成中 → 通常プレイ中) は poll_controller 側で発火
        """
        _log.info("img_name changed: %r", img_name)
        img_upper = (img_name or "").upper()
        top = _current_top_level(self._w)
        prev_screen = getattr(self._w, "_screen_id_prev", None)

        # ── トップレベル遷移 (5 トリガー設計) ──────────
        # IMG駆動の L1 遷移判定 (T1/T2/T5) を単一 classifier
        # classify_top_level へ集約する。reason 文字列は
        # 本箇所で構築する (via 付き)。
        from top_level.top_level_node import classify_top_level
        _l1_next, _ = classify_top_level(top, img_upper)
        # トリガー #2/#5: 非タイトル中 → タイトル中
        if _l1_next == "pregame" and top != "pregame":
            try:
                via = "system_menu" if prev_screen == "system_menu" else top
                self._w._transition_top_level(
                    "pregame", f"{via} → {img_upper}")
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass

        # トリガー #3: タイトル中 → キャラクター作成中
        elif _l1_next == "chargen" and top == "pregame":
            try:
                self._w._transition_top_level("chargen", "EVLINTRO.XMI")
                self._w._pregame_loadsave_seen = False
            except AttributeError:
                pass

        # トリガー #4 のフラグ記録: タイトル中の LOADSAVE.IMG 検知。
        # 実際の通常プレイ中遷移は poll_controller 側で
        #   _pregame_loadsave_seen + タイトル中固有以外への遷移
        # の組合せで発火する。
        if img_upper == "LOADSAVE.IMG" \
                and _current_top_level(self._w) == "pregame":
            try:
                self._w._pregame_loadsave_seen = True
            except AttributeError:
                pass

        # ── サブ状態の表示処理 (トップレベル遷移には影響しない) ─────
        if img_upper.endswith(".XMI"):
            # XMI 拡張子は表示クリア。キャラクター作成中の旅立ち XMI
            # (VISION.XMI) では post-chargen opening 再 push 用に
            # _chargen_opening_text_prev をリセットする。
            if _current_top_level(self._w) == "chargen":
                self._w._chargen_opening_text_prev = ""
            try:
                self._w._ui_router.clear_display("")
            except AttributeError:
                pass
            return

        if img_name == "MENU.IMG":
            self._show_menu_screen()
        elif img_name == "LOADSAVE.IMG":
            self._show_load_screen()
        elif (img_name.startswith("INTRO") and img_name.endswith(".IMG")):
            self._show_newgame_slide(img_name)
        elif img_name == "PARCH.CIF":
            # キャラクター作成中の羊皮紙背景。表示処理のみ実行し、
            # トップレベル遷移は行わない (本案ではキャラクター作成中
            # への入口は EVLINTRO.XMI のみ)。
            self._w._set_chargen_ui_state(True)
        elif img_name in ("QUOTE.IMG", "SCROLL01.IMG", "SCROLL02.IMG"):
            # タイトル中のオープニング演出。表示処理のみ。
            self._show_startup_intro(img_name)
        elif img_name == "MRSHIRT.IMG":
            # 装備/呪文画面 (equipment / spellbook / spell_detail) の再描画は
            # poll_controller の確定 _screen_id_stable resync が担う
            # (装備 ON/OFF や Next/Previous Spell をメモリ marker 変化で検出)。
            # ここでは MRSHIRT.IMG を通常ゲーム画面の else 分岐 (表示クリア) から
            # 除外し、現在のパネルモードを維持するためだけに return する。
            return
        elif img_name in ("EQUIP.IMG", "MPANTS.IMG"):
            # 装備 ON/OFF 時の一時 IMG。
            # 装備/呪文画面表示中はパネルモードを維持するため else 分岐の reset を回避。
            return
        elif img_name == "POPUP11.IMG":
            # POPUP11.IMG の下位状態判別 / dispatch は poll_controller 側で
            # detect_popup11_list_state() を介して where_is_list / dynamic_place_list /
            # npc_response に振り分ける。
            # ここで直接 _show_npc_dialog() を呼ぶと過渡的に誤表示が発生するため呼ばない。
            return
        elif img_name.startswith("CHARBK") and img_name.endswith(".IMG"):
            # 呪文詳細画面 IMG（CHARBK00.IMG など）。
            # screen_id="spell_detail" の on_screen_id_changed 経由で
            # _show_spell_detail_screen が呼ばれるため、ここでは何もしない。
            return
        else:
            # 通常ゲームプレイ画面: プリプレイモードを解除する
            # MRSHIRT.IMG（装備/呪文画面）は MRSHIRT.IMG 分岐で処理する
            self._w._newgame_layout_pushed = False
            self._w._startup_layout_pushed = False
            try:
                # equipment は screen_id 管理に寄せたため else の reset 対象から除外。
                # load_screen のみ reset 維持。
                if self._w._tab_translate.panel_mode() == "load_screen":
                    self._set_panel_mode("translate")
            except AttributeError:
                pass
            self._w._set_chargen_ui_state(False)

    # NPC 会話関連の翻訳表示が継続する screen_id のセット。
    # これら以外への遷移時は ASK ABOUT? / POPUP11 系の翻訳表示状態を strict に
    # リセットして、前画面の翻訳残置を防ぐ。
    _NPC_DIALOG_RELATED_SCREENS = frozenset({"npc_dialog"})

    def on_screen_id_changed(self, screen_id: str) -> None:
        """screen_id が変化したときに呼ばれる。

        画面遷移時クリアポリシー:
          - NPC 会話系以外の画面に遷移した場合、ASK ABOUT? / POPUP11 系の
            翻訳表示状態 (タブ・パネルの内容、内部 prev フラグ) を全てリセット
            する。前画面の翻訳残置を防止する不変条件。
          - 個別画面ハンドラ (equipment / spellbook / spell_detail) が定義されて
            いる screen_id では、そのハンドラを呼出して画面固有の翻訳表示を行う。
        """
        _log.info("screen_id changed: %r", screen_id)

        # NPC 会話関連と無関係な画面遷移 → 翻訳表示状態を strict にクリア。
        # クリア対象は NPC 会話系 (ASK ABOUT? / POPUP11) の翻訳表示なので、責務は
        # normal-play に閉じる。pregame の MENU / SCROLL 等や chargen の subscreen
        # は専用ハンドラがその場面の翻訳を表示しており、ここで空クリアすると
        # 正規表示まで消してしまう。
        if (_current_top_level(self._w) == "normal-play"
                and screen_id not in self._NPC_DIALOG_RELATED_SCREENS):
            self._reset_npc_dialog_display(clear_display=False)

        if screen_id == "equipment":
            self._show_equipment_screen()
        elif screen_id == "spellbook":
            self._show_spellbook_screen()
        elif screen_id == "spell_detail":
            # 呪文詳細画面（SPELLBOOK パーチメント）— 専用パネルで呪文名・効果テキストを表示
            self._show_spell_detail_screen()

    def _reset_npc_dialog_display(self, *, clear_display: bool = True) -> None:
        """NPC 会話関連 (ASK ABOUT? / POPUP11 系) の翻訳表示状態をクリアする。

        NPC 会話表示単位の終了時は表示と内部状態を同時に整理する。
        screen_id 変化時は表示単位外の横断 clear にならないよう、
        clear_display=False で内部状態だけをリセットする。

        ただしクリア対象は NPC 会話系の表示。他系統 (item_pickup / red_text /
        gold_drop / trigger / level_up) が翻訳タブ・パネルの内容を所有して
        いる場合は、その表示は各 owner のライフサイクルで管理されるため、
        ここでは表示を維持して内部 NPC 会話状態フラグだけリセットする。
        """
        try:
            # NPC 会話表示単位は「自単位 (npc_dialog) または無所有 ("") が
            # panel を所有する poll」でのみ自表示をクリアし、他単位
            # (item_pickup / red_text / gold_drop / trigger / level_up 等)
            # が所有している場合はそのまま温存する (item_pickup 等は mode 自体が
            # 表示実体のため奪うと見えなくなる)。現在表示所有者の集合ゲート
            # (allowed_current_owners) で宣言的に表現する。clear → owner=''
            # 復帰 + mode/place_list 復帰を行う。place_list 行データの明示
            # クリアも維持する。
            if clear_display:
                clear_mode = self._npc_clear_panel_mode()
                if self._w._tab_translate is not None:
                    # NPC 応答表示は npc_conversation owner で push されるため、
                    # 自単位クリアの許可集合に含める (npc_dialog と同等扱い)。
                    self._w._ui_router.clear_display(
                        "", mode=clear_mode, clear_place_list=True,
                        allowed_current_owners=(
                            "", "npc_dialog", NPC_CONVERSATION_OWNER,
                            "npc_message"))
            # 内部 NPC 会話状態フラグは owner と無関係に常にリセットする
            # (次回 NPC 会話進入時の状態誤判定を防ぐため)。
            self._w._ask_about_menu_active_prev = False
            self._w._ask_about_current_ptr_prev = -1
            self._w._popup11_list_state_prev = ""
            self._w._popup11_exit_pending_ask_about = False
            self._w._npc_dialog_text_prev = ""
        except (AttributeError, RuntimeError) as exc:
            _log.debug("_reset_npc_dialog_display skipped: %s", exc)

    def _npc_clear_panel_mode(self) -> str | None:
        """NPC 会話表示を閉じた後の panel mode。

        NPC 会話 L4 の終了時は表示クリアと mode 復帰を 1 intent にまとめる。
        poll frame 内で set_panel_mode と clear を別々に出すと、後着の clear が
        mode 復帰を落として place_list 等が残るため。
        """
        try:
            mode = self._w._tab_translate.panel_mode()
            img_name_now = (
                getattr(self._w, "_img_name_prev", "") or "").upper()
            if mode == "load_screen" and img_name_now == "LOADSAVE.IMG":
                return None
            screen_id_now = getattr(self._w, "_screen_id_prev", "") or ""
            if (mode == "choose_attributes"
                    and screen_id_now in ("status_page", "bonus_screen")):
                return "choose_attributes"
            if _current_top_level(self._w) == "normal-play":
                fallback = settings.get("translate_fallback_screen", "map")
                if fallback == "map":
                    return "fallback_map"
                if fallback == "status":
                    return "fallback_status"
            return "translate"
        except AttributeError:
            return "translate"

    # ------------------------------------------------------------------
    # 個別画面ハンドラ
    # ------------------------------------------------------------------

    def _show_startup_intro(self, img_name: str) -> None:
        """起動イントロの翻訳を表示する (pregame_render へ委譲・描画所有 node 化)。"""
        _pregame_render.show_startup_intro(self._w, img_name)

    def _show_menu_screen(self) -> None:
        """タイトルメニューの翻訳を表示する (pregame_render へ委譲)。"""
        _pregame_render.show_menu_screen(self._w)

    def _show_load_screen(self) -> None:
        """ロード画面の一覧を表示する (pregame_render へ委譲)。"""
        _pregame_render.show_load_screen(self._w)

    def _show_equipment_screen(self) -> None:
        """装備品一覧（MRSHIRT.IMG equipment タブ）を翻訳タブに表示する。

        知見:
          - slotID → weaponNames[slotID] (hands=1/2) or armorNames[slotID] (hands=0)
          - 防具素材は param1 範囲 40-50=Plate / 29-39=Chain / 18-28=Leather で判定
          - equipped/weight/condition/effect を detail 行として追加表示。
          - 5色スキーム（装備可否・未鑑定）で着色する。
        """
        item_data: list = []
        title = "装備品一覧"
        try:
            import arena_data
            import assist_settings as settings
            from inventory_reader import read_equipment_items
            import dungeon_msg_lookup as dml

            # 通常プレイ時クラス ID（anchor+0x1A9）から装備可否チェック用 classes.json id を取得
            json_class_id: int | None = None
            is_hypothesis = True
            try:
                play_cls_id = self._w._analyzer.read_bytes(self._w._anchor + 0x1A9, 1)[0]
                play_cls_map = settings.get("arena_play_class_id_map", {}) or {}
                class_en = play_cls_map.get(str(play_cls_id))
                if class_en:
                    cls_data = arena_data.get_class_by_name(class_en)
                    if cls_data:
                        json_class_id = cls_data["id"]
                        is_hypothesis = bool(cls_data.get("_hypothesis_note"))
            except Exception:
                pass

            def _can_equip(it: dict) -> bool | None:
                if json_class_id is None:
                    return None
                t = it["item_type"]
                if t == "weapon":
                    return arena_data.can_class_use_weapon(json_class_id, it["slot_id"])
                if t == "armor":
                    return arena_data.can_class_use_armor(json_class_id, it["armor_material_id"])
                if t == "shield":
                    return arena_data.can_class_use_shield(json_class_id, it["slot_id"])
                return True  # accessory / spellcasting: クラス制限なし

            items_raw = read_equipment_items(self._w._analyzer, self._w._anchor)
            item_data = [
                {
                    "en":              it["en"],
                    "ja":              dml.lookup_item(it["en"]),
                    "equipped":        it["equipped"],
                    "is_unidentified": it["is_unidentified"],
                    "can_equip":       _can_equip(it),
                    "slot_label":      it["slot_label"],
                    "weight":          it["weight"],
                    "condition":       it["condition"],
                    "effect":          it["effect"],
                }
                for it in items_raw
            ]
            title = "装備品一覧"
        except Exception:
            _log.exception("equipment read failed")

        self._w._ui_router.propose_equipment_list(
            "equipment", title, item_data,
            priority=30, reason="screen:equipment")

    def _show_spell_detail_screen(self) -> None:
        """呪文詳細画面（MRSHIRT.IMG SPELLBOOK パーチメント）を翻訳タブに表示する。

        ゲーム内 SPELLBOOK 詳細画面のレイアウトに合わせて以下を表示:
          - プレイヤー情報: Name / Level / Balance / Spell Cost
          - 呪文名 (EN/JA), Save Vs. (element), Target, Casting Cost
          - Effects: 効果種別名 + 効果テキスト本文

        メモリ構造（仮説）:
          anchor+0x57E6  = 現在表示中 SpellData レコード（85 bytes）
            +0x24 (=0x580A) targetType u8
            +0x26 (=0x580C) element u8
            +0x29 (=0x580F) effects[0] u8
            +0x32 (=0x5818) cost u16 LE
            +0x34 (=0x581A) name[33]
          anchor+0x1044  = 効果テキストバッファ
        効果種別/属性/対象の英→和訳は spell_reader 内のテーブルで行う。
        """
        try:
            from spell_reader import read_spell_detail
            import dungeon_msg_lookup as dml
            data = read_spell_detail(self._w._analyzer, self._w._anchor)
            # 呪文名の和訳ルックアップを追加
            data["name_ja"] = dml.lookup_spell(data.get("name", "")) or ""
        except Exception:
            _log.exception("spell_detail read failed")
            data = {}
        # effect text バッファの ready 判定:
        #   1) text_en が空 → 未書込み
        #   2) text_en == spell_name → 呪文名そのものが残留
        #   3) 呪文名は変化したのに text_en が前回受理値と同一 → 前回呪文の stale text
        # 上記いずれかに該当する場合、effect text は無効とみなして空で表示する
        # (誤った前回値を見せるより空で出す方が安全)。
        text_en = (data.get("text_en") or "").strip()
        spell_name = (data.get("name") or "").strip()
        last_name = getattr(self._w, "_spell_detail_last_accepted_name", "")
        last_text = getattr(self._w, "_spell_detail_last_accepted_text", "")
        text_is_stale_prev = (
            bool(text_en)
            and spell_name
            and spell_name != last_name
            and text_en == last_text
        )
        text_is_name_residue = bool(text_en) and text_en == spell_name
        text_is_invalid = (not text_en) or text_is_name_residue or text_is_stale_prev
        if text_is_invalid:
            data["text_en"] = ""
            data["text_ja"] = ""
            self._w._spell_detail_text_ready = False
        else:
            self._w._spell_detail_text_ready = True
            self._w._spell_detail_last_accepted_name = spell_name
            self._w._spell_detail_last_accepted_text = text_en
        self._w._ui_router.propose_spell_detail(
            "spell_detail", data,
            priority=30, reason="screen:spell_detail")

    def _show_spellbook_screen(self) -> None:
        """習得呪文一覧（MRSHIRT.IMG spellbook タブ）を翻訳タブに表示する。

        呪文 ID: anchor+0x50A (knownSpellCount) / anchor+0x50B (knownSpellIDs)
        呪文名: save_dir の SPELLSG.NN ファイルから取得（SpellData.name @ +0x34）
        """
        try:
            from spell_reader import read_spellbook_items
            import dungeon_msg_lookup as dml
            items_raw = read_spellbook_items(self._w._analyzer, self._w._anchor)
            item_data = [
                {"en": it["en"], "ja": dml.lookup_spell(it["en"])}
                for it in items_raw
            ]
        except Exception:
            _log.exception("spellbook read failed")
            item_data = []
        self._w._ui_router.propose_equipment_list(
            "spellbook", "習得呪文一覧", item_data,
            priority=30, reason="screen:spellbook")

    def _show_newgame_slide(self, img_name: str) -> None:
        """ニューゲームイントロの現在スライド翻訳を表示する (pregame_render へ委譲)。"""
        _pregame_render.show_newgame_slide(self._w, img_name)

    def _restore_translate_mode(self) -> None:
        """panel_mode が他モード（place_list 等）になっている場合に translate に戻す。

        LOADSAVE.IMG 表示中は load_screen mode を維持する。
        screen_id 遷移時に _reset_npc_dialog_display 経由で本関数が呼ばれ
        load_screen → translate にリセットされ、続く _maybe_apply_fallback
        で fallback_map に切り替わり、ロード画面のセーブスロット一覧が
        翻訳タブで見えなくなる症状を防ぐ。
        """
        try:
            mode = self._w._tab_translate.panel_mode()
            if mode == "translate":
                return
            # LOADSAVE.IMG 表示中の load_screen は維持する
            img_name_now = (
                getattr(self._w, "_img_name_prev", "") or "").upper()
            if mode == "load_screen" and img_name_now == "LOADSAVE.IMG":
                return
            screen_id_now = getattr(self._w, "_screen_id_prev", "") or ""
            if (mode == "choose_attributes"
                    and screen_id_now in ("status_page", "bonus_screen")):
                return
            self._set_panel_mode("translate")
        except AttributeError:
            pass

    def _show_npc_dialog(self, text_override: str | None = None) -> None:
        """NPC 会話テキストを読み出して翻訳を push する。

        読み出し順:
          1. anchor + 0x1044 (NPC_DIALOG_OFFSET): Who are you? 応答
          2. anchor + 0x9A9E: Where is 応答 / イベントバッファ
        両方に有効テキストがある場合は 0x1044 を優先する。
        read_live_buffer を使用して先頭の制御バイトを除去してから lookup に渡す。
        マッチしない場合は空 push（既存翻訳をクリア）。

        店主会話など施設 UI session active 中は no-op。
        """
        try:
            # facility session (tavern / temple) active 中は no-op
            _tav = getattr(self._w, "_tavern_session", None)
            _tem = getattr(self._w, "_temple_session", None)
            if ((_tav is not None and _tav.is_active())
                    or (_tem is not None and _tem.is_active())):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            import npc_dialog_lookup as ndl

            self._restore_translate_mode()

            # text_override が与えられればそれを使う（poll 側で lookup ヒット優先で
            # 選ばれた応答候補をそのまま表示）。stale な再読みを避ける。
            text = (text_override or "").strip()
            if not text:
                # 呼出元が直接呼ぶ場合（_overrideなし）は popup11_response_reader 経由で
                # 最良の候補を取得する。0x929E / 0x1044 / 0x9A9E を全て見て lookup
                # ヒットを優先採用する。
                from popup11_response_reader import read_response_candidate
                cand = read_response_candidate(self._w._analyzer, self._w._anchor)
                text = cand.text if cand else ""

            if not text:
                # text 空でクリアする場合は所有権も解放する。
                self._w._ui_router.clear_if_owner(
                    NPC_CONVERSATION_OWNER,
                    mode=self._npc_clear_panel_mode(),
                    clear_place_list=True)
                return

            result = ndl.lookup(text)
            if result:
                ja_template, placeholders = result
                ja_text = ndl.format_japanese(ja_template, placeholders)
            else:
                ja_text = ""

            # 表示所有権を NPC 応答に明示する (= 同 poll 内で他経路が上書きする
            # 判断材料になる)。専用 owner npc_conversation を使う。
            # 街中NPCの応答 = 会話として読み上げを宣言する。
            self._w._ui_router.update_translation(
                NPC_CONVERSATION_OWNER, text, ja_text,
                speech_role="conversation")

        except Exception:
            _log.exception("_show_npc_dialog failed")

    def _show_ask_about_menu(self) -> None:
        """ASK ABOUT? メニュー表示時の翻訳を push する。

        店主会話など施設 UI session active 中は no-op。
        """
        try:
            # facility session (tavern / temple) active 中は no-op
            _tav = getattr(self._w, "_tavern_session", None)
            _tem = getattr(self._w, "_temple_session", None)
            if ((_tav is not None and _tav.is_active())
                    or (_tem is not None and _tem.is_active())):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            from arena_bridge import read_ask_about_menu
            from ask_about_menu_parser import (
                build_display, build_display_sub,
                build_panel_display, build_panel_display_sub,
                parse_menu,
            )

            self._restore_translate_mode()

            raw = read_ask_about_menu(self._w._analyzer, self._w._anchor)
            parsed = parse_menu(raw)

            # サブメニュー選択中かをタブ・パネル共通で判定する
            active_sub_title = self._detect_active_sub_menu_title(parsed)
            _log.info(
                "_show_ask_about_menu: active_sub_title=%r", active_sub_title)

            # 翻訳タブ: サブメニュー選択中はそのサブのみ、メイン表示中はメインのみ
            if active_sub_title:
                en_tab, ja_tab = build_display_sub(
                    parsed, sub_title=active_sub_title)
            else:
                en_tab, ja_tab = build_display(parsed, include_sub=False)
            # 翻訳パネル: サブメニューを推定して切り替え
            en_panel = ja_panel = ""
            if self._w._layout_translate_panel is not None:
                if active_sub_title:
                    en_panel, ja_panel = build_panel_display_sub(
                        parsed, sub_title=active_sub_title)
                else:
                    en_panel, ja_panel = build_panel_display(parsed)
            # ASK ABOUT? は NPC 応答と同じ owner を共有するが、メニュー
            # (システム)なので読み上げ役割は宣言しない(=読まない)。応答を組む
            # _show_npc_dialog 側だけが speech_role="conversation" を宣言する。
            self._w._ui_router.update_translation(
                NPC_CONVERSATION_OWNER, en_tab, ja_tab,
                panel_en=en_panel, panel_ja=ja_panel)

        except Exception:
            _log.exception("_show_ask_about_menu failed")

    def _detect_active_sub_menu_title(self, parsed: dict) -> str:
        """ASK ABOUT? 表示中のサブメニュータイトルを返す。メイン表示時は空文字。

        判定機構: anchor + 0xA844 (u16 LE) が「現在表示中項目テキストへの
        anchor 相対ポインタ」を保持し、popup11_list_detector.
        read_active_menu_marker がポインタの指し先テキストを返す。テキスト
        と parse_menu 結果の main/sub_menus 項目を照合するロジックは
        ask_about_menu_parser.detect_active_sub_menu_title に委譲する
        (= サブメニュー内のどの項目を指してもタイトルを正しく特定できる)。
        """
        try:
            from popup11_list_detector import read_active_menu_marker
            from ask_about_menu_parser import detect_active_sub_menu_title
            marker = read_active_menu_marker(self._w._analyzer, self._w._anchor)
            title = detect_active_sub_menu_title(parsed, marker)
            _log.info(
                "_detect_active_sub_menu_title: marker=%r title=%r",
                marker, title)
            return title
        except Exception:
            _log.exception("_detect_active_sub_menu_title failed")
            return ""

    def _show_where_is_list(self) -> None:
        """場所一覧（ASK ABOUT? → Where is... 選択直後）表示時の翻訳を push する。

        翻訳タブ: アイテム一覧と同じ ItemRow ベースの一覧表示。
        翻訳パネル: タイトル「どこにある？」のみ表示。一覧項目は出さない
                    （クラス一覧/種族選択と同じ扱い）。

        店主会話など施設 UI session active 中は no-op。
        """
        try:
            # facility session (tavern / temple) active 中は no-op
            _tav = getattr(self._w, "_tavern_session", None)
            _tem = getattr(self._w, "_temple_session", None)
            if ((_tav is not None and _tav.is_active())
                    or (_tem is not None and _tem.is_active())):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
            from popup11_list_parser import parse_where_is_list
            from ask_about_menu_parser import translate

            item_count = _read_u8(self._w._analyzer,
                                  self._w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
            items_en = parse_where_is_list(self._w._analyzer, self._w._anchor, item_count)
            if not items_en:
                return

            # 翻訳タブ: アイテム一覧と同じ ItemRow ベース表示。
            # 静的メニュー項目 (Inn/Temple 等) は ask_about_menu.json、メイン
            # ストーリーの固有ダンジョン名 (Fang Lair 等) は location.json で翻訳する。
            item_data = [
                {"en": opt_en, "ja": self._translate_where_is_item(opt_en, translate)}
                for opt_en in items_en
            ]
            # 翻訳パネル: タイトルのみ（一覧は出さない）
            title_en = "Where is..."
            title_ja = translate(title_en)
            self._w._ui_router.update_place_list(
                NPC_CONVERSATION_OWNER, item_data,
                title="", panel_en=title_en, panel_ja=title_ja)

        except Exception:
            _log.exception("_show_where_is_list failed")

    @staticmethod
    def _translate_where_is_item(opt_en: str, translate) -> str:
        """場所一覧 1 項目の JA を返す。

        ask_about_menu.json の固定項目 (Inn/Temple/Mages Guild 等) を優先し、
        ヒットしない (= メインストーリーの固有ダンジョン名等) 場合は
        location.json を引く。どちらにも無ければ原文を返す。
        """
        ja = translate(opt_en)
        if ja and ja != opt_en:
            return ja
        try:
            from location_lookup import lookup as _loc_lookup
            loc = _loc_lookup(opt_en)
            if loc:
                return loc
        except Exception:  # noqa: BLE001
            pass
        return ja

    def _show_dynamic_place_list(self) -> None:
        """詳細場所一覧（場所一覧 → カテゴリ選択後の動的固有名一覧）表示時の翻訳を push する。

        翻訳タブ: アイテム一覧と同じ ItemRow ベースの一覧表示。JA 列は固有名のため空（"—" 表示）
        翻訳パネル: 場所一覧と同じく「どこにある？」のみ。一覧項目は出さない

        店主会話など施設 UI session active 中は no-op。
        """
        try:
            # facility session (tavern / temple) active 中は no-op
            _tav = getattr(self._w, "_tavern_session", None)
            _tem = getattr(self._w, "_temple_session", None)
            if ((_tav is not None and _tav.is_active())
                    or (_tem is not None and _tem.is_active())):
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            from popup11_list_detector import POPUP11_ITEM_COUNT_OFFSET, _read_u8
            from popup11_list_parser import parse_dynamic_place_list
            from ask_about_menu_parser import translate

            item_count = _read_u8(self._w._analyzer,
                                  self._w._anchor + POPUP11_ITEM_COUNT_OFFSET) or 0
            items_en = parse_dynamic_place_list(
                self._w._analyzer, self._w._anchor, item_count)
            if not items_en:
                return

            # 翻訳タブ: ItemRow ベース表示。JA 列は分解合成ルックアップ、
            # 未翻訳は空文字（ItemRow が "—" プレースホルダで表示）。
            import dynamic_place_lookup as dpl
            category = dpl.detect_category(items_en[0]) if items_en else None
            item_data = [
                {"en": opt_en, "ja": dpl.lookup(opt_en, category)} for opt_en in items_en
            ]
            # 翻訳パネル: 場所一覧と同じくタイトルのみ
            title_en = "Where is..."
            title_ja = translate(title_en)
            self._w._ui_router.update_place_list(
                NPC_CONVERSATION_OWNER, item_data,
                title="", panel_en=title_en, panel_ja=title_ja)

        except Exception:
            _log.exception("_show_dynamic_place_list failed")
