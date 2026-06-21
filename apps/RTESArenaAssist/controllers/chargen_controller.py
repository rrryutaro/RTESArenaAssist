"""
controllers/chargen_controller.py — chargen 検出 / 翻訳オーケストレーション

含まれるもの（11 メソッド、internal 名はアンダースコア prefix のまま維持）:
  - _reset_chargen_state_for_restart  ← chargen 再開検出時の全 state 一括リセット
  - _read_chargen_done_live           ← chargen_done フラグのライブ読み出し
  - _read_text_at                     ← NUL 終端 ASCII 読み出し
  - _read_cinematic_block             ← cinematic 全ページ一括読み出し
  - _fire_post_chargen_opening        ← post-chargen cinematic 翻訳発火
  - _read_player_name                 ← player struct +0x1AD ASCII プレイヤー名
  - _update_chargen_name_display      ← 名前入力画面のクラス名代入翻訳
  - _handle_chargen_npc_dialog        ← chargen NPC ダイアログ翻訳処理
  - _activate_class_list_for_class    ← クラス一覧画面切替 + ニューゲーム検出
  - _read_chargen_state_byte          ← chargen_state バイトのライブ読み出し
  - _try_dynamic_chargen_npc          ← 動的 chargen テキストパターンマッチ

window 側の状態（_chargen_* フラグ群、_anchor、_analyzer 等）は
AssistWindow が保持し、コントローラからは self._w.X 経由で参照する。
"""

import logging

import inf_text_lookup as itl
from controllers.chargen_helpers import (
    _CHARGEN_OPENING_HINT_ADDR, _CHARGEN_OPENING_MAXLEN,
    _CHARGEN_OPENING_FULLREAD,
    _CHARGEN_OPENING_SCAN_START, _CHARGEN_OPENING_SCAN_END,
    _CHARGEN_OPENING_PREFIXES,
    _is_garbage_npc_buffer, _looks_like_cinematic,
    _CHARGEN_NAME_RE, _CHARGEN_CLASS_JA, _CHARGEN_DYNAMIC_PATTERNS,
)

_log = logging.getLogger("chargen_controller")


class ChargenController:
    """chargen 検出 / 翻訳オーケストレーション。AssistWindow を back-reference として保持。"""

    def __init__(self, window):
        self._w = window

    # ------------------------------------------------------------------
    # state リセット
    # ------------------------------------------------------------------

    def _reset_chargen_state_for_restart(self, reason: str = "unknown") -> None:
        """chargen 再開検出時に呼び出す全 state 一括リセット。

        呼び出し元:
        - `_activate_class_list_for_class` での「前回 chargen 完了後の
          class_list 再活性化」検出時（手動選択経路の 2 回目 New Game）
        - `_update_translate_tab` の method 画面 NPC `_CHARGEN_` 検出時
          （自動・手動共通の 2 回目 New Game 開始シグナル）

        chargen_done の 1→0 遷移はトリガに使わない（Appearance Done 直後に
        誤発火するため）。
        """
        w = self._w
        w._chargen_state_streak = 0
        w._chargen_state_prev = 0
        # _chargen_q_seq_prev は現在のメモリ値で初期化する。0 で固定すると
        # 直後の poll で残骸値 (1-10) に変化したとみなして Q が誤発火する。
        try:
            from arena_bridge import CHARGEN_Q_SEQ_OFFSET as _OFF
            w._chargen_q_seq_prev = w._analyzer.read_bytes(
                w._anchor + _OFF, 1)[0]
        except (OSError, AttributeError, ImportError):
            w._chargen_q_seq_prev = 0
        w._in_chargen_name = False
        w._chargen_in_advice = False
        w._chargen_advice_state = None
        w._chargen_advice_a845 = None
        w._chargen_goyenow_displayed = False
        w._chargen_goyenow_state = None
        w._chargen_10q_displayed = False
        w._chargen_method_state = None
        w._chargen_method_a845 = None
        w._chargen_distribute_displayed = False
        w._chargen_choose_attrs_displayed = False
        w._chargen_choose_attrs_state_val = None
        w._chargen_appearance_displayed = False
        w._chargen_opening_displayed = False
        w._chargen_method_window = False
        w._chargen_race_select_displayed = False
        # chargen subscreen フラグのリセット
        w._chargen_class_accept_displayed = False
        w._chargen_race_desc_displayed = False
        w._chargen_sex_select_displayed = False
        w._chargen_complete_displayed = False
        w._chargen_class_list_active = False
        w._chargen_race_ja = None
        w._chargen_class_ja = None
        w._chargen_class_en = None
        w._goyenow_scan_budget = 0
        w._advice_capture_age = -1
        # 能力値配分以降の状態管理 latch (responsability-separated design)
        w._chargen_status_display_armed = False
        w._chargen_attrs_state_anchor = None
        w._chargen_attrs_phase_seen = False
        w._chargen_attrs_modal_active = False
        w._chargen_attrs_modal_kind = None
        w._chargen_attrs_phase_log_prev = None
        w._chargen_explanation_active = None
        w._chargen_explanation_distribute_npc_snapshot = None
        w._chargen_explanation_distribute_dlg_seen_open = False
        w._chargen_goyenow_npc_snapshot = None
        w._chargen_goyenow_b7c4_prev = None
        # 次回 cinematic でも start.mif 突入時にクリアできるよう旗を戻す
        w._dungeon_entry_cleared = False
        # chargen subscreen 追跡をリセット（新規 chargen の起点）
        w._chargen_subscreen_last = None
        # _last_class_list_activation も新規 chargen 開始時にクリア
        # (前 chargen の class list 状態が残ると新規 chargen 初回 activation
        # で skip されてしまう)。
        w._last_class_list_activation = None
        # _last_chargen_entry_key はここでクリアしない。
        # 本 reset 自体が _update_translate_tab → _handle_chargen_npc_dialog
        # 経由で呼ばれるケースがあり、ここで cache を消すと cache の意義
        # (= runaway 防止) が破綻する (cache 設定 → reset → cache クリア
        # → 次 poll で同じ entry で再 reset の無限ループ)。
        # 新規 chargen の判別は cache key (entry の inf/text) 自体の変化で
        # 自然に行われる (前 chargen と新 chargen で NPC ダイアログ内容が
        # 一致しない限り key が異なる)。
        w._set_class_list_panel_mode(False)
        _log.info("chargen: state reset for restart (%s)", reason)

    # ------------------------------------------------------------------
    # メモリ読み出し helper
    # ------------------------------------------------------------------

    def _read_chargen_done_live(self) -> int:
        """chargen_done フラグを毎回ライブで読み出す。失敗時は cached prev を返す。

        _handle_chargen_npc_dialog のガード判定で使う：cached prev は次の poll 反復まで
        更新されないため、Arena 側で先に値が変わっている場合に判定がずれるのを防ぐ。
        """
        w = self._w
        try:
            from arena_bridge import CHARGEN_DONE_OFFSET as _CDO
            return w._analyzer.read_bytes(w._anchor + _CDO, 1)[0]
        except (OSError, ImportError, AttributeError):
            return w._chargen_done_prev

    def _read_text_at(self, address: int) -> str:
        """指定アドレスから NUL 終端 ASCII を読む。read_bytes が ERROR_PARTIAL_COPY
        (299) を返すケースに備えサイズを半減しながら最大 6 段階で再試行する。
        失敗時は空文字列。"""
        w = self._w
        for size in (_CHARGEN_OPENING_MAXLEN, 512, 256, 128, 64, 32):
            try:
                data = w._analyzer.read_bytes(address, size)
            except OSError:
                continue
            if not data:
                continue
            end = data.find(b"\x00")
            if end >= 0:
                data = data[:end]
            try:
                return data.decode("ascii", errors="replace").strip()
            except Exception:
                return ""
        return ""

    def _read_cinematic_block(self, address: int) -> str:
        """cinematic 用: 大きめチャンクを読み NUL 区切りの全 ASCII 断片を連結する。

        Arena は cinematic テキストを「行ごとに NUL 終端された連続レコード」として
        メモリに格納している（hint アドレスの直読みでは最初の 1 行のみしか
        取得できないため）。
        本メソッドは 4KB 読み出して NUL 分割し、印字可能 ASCII の断片を順に
        連結することで cinematic 全ページを一括取得する。

        終端判定: 連続 NUL を 4 個以上検出 OR 印字可能率の極端に低い断片に
        遭遇したら全体終端とみなす。
        """
        w = self._w
        # サイズフォールバック付き読取
        data = b""
        for size in (_CHARGEN_OPENING_FULLREAD, 2048, 1024, 512, 256):
            try:
                data = w._analyzer.read_bytes(address, size)
                if data:
                    break
            except OSError:
                continue
        if not data:
            return ""

        parts = data.split(b"\x00")
        text_parts: list[str] = []
        empty_run = 0
        for raw in parts:
            if not raw:
                empty_run += 1
                if empty_run >= 4 and text_parts:
                    break
                continue
            empty_run = 0
            try:
                s = raw.decode("ascii", errors="replace").strip()
            except Exception:
                if text_parts:
                    break
                continue
            if not s:
                if text_parts:
                    break
                continue
            # 印字可能率チェック
            printable = sum(1 for c in s if 0x20 <= ord(c) < 0x7F)
            ratio = printable / max(len(s), 1)
            if ratio < 0.7:
                if text_parts:
                    break
                continue
            # 短すぎる断片は記号・パディング扱い
            if len(s) < 3 and text_parts:
                continue
            text_parts.append(s)
        # 行間はスペースで連結（Arena は 60 文字幅で word-wrap 済みのため）
        return " ".join(text_parts).strip()

    def _read_player_name(self) -> str:
        """player struct +0x1AD から ASCII プレイヤー名を読む（失敗時は空文字）。"""
        w = self._w
        if w._analyzer is None or not w._anchor:
            return ""
        try:
            raw = w._analyzer.read_bytes(w._anchor + 0x1AD, 26)
        except OSError:
            return ""
        return raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()

    def _read_chargen_state_byte(self) -> int | None:
        """anchor + CHARGEN_STATE_OFFSET を 1 バイト読む（失敗時 None）。"""
        w = self._w
        try:
            from arena_bridge import CHARGEN_STATE_OFFSET as _OFF
            return w._analyzer.read_bytes(w._anchor + _OFF, 1)[0]
        except (OSError, ImportError, AttributeError):
            return None

    # ------------------------------------------------------------------
    # post-chargen cinematic 発火
    # ------------------------------------------------------------------

    def _fire_post_chargen_opening(self) -> bool:
        """post-chargen cinematic 本文をメモリから一括取得して翻訳タブに表示する。

        探索戦略:
          (1) 既知 hint アドレス (_CHARGEN_OPENING_HINT_ADDR = 0x10764C10) を
              4KB ブロックで読み NUL 区切り全断片を連結。妥当な長さの cinematic
              本文が得られれば採用（高速パス）。
          (2) 失敗時は scan_string で prefix 検索 → ヒット先から同様に block 読取
              （堅牢パス、〜32MB 範囲）。
          (3) 累積モード: 一旦表示成功した後でも cinematic は次ページに更新される
              場合があるため、より長い本文が読めたら都度上書きする
              （呼び出し側でリトライ継続中の場合）。

        Arena は chargen_done=1 を立てた直後ではなく一拍遅れて cinematic 本文を
        書き込むため、表示成功時のみ True を返す。
        """
        w = self._w
        text = ""
        addr_used = 0
        # (1) hint アドレス試行（block 読取で全ページ一括）
        block = self._read_cinematic_block(_CHARGEN_OPENING_HINT_ADDR)
        if block and _looks_like_cinematic(block):
            text = block
            addr_used = _CHARGEN_OPENING_HINT_ADDR
        # (2) prefix scan フォールバック
        if not text:
            for prefix in _CHARGEN_OPENING_PREFIXES:
                try:
                    results = w._analyzer.scan_string(
                        prefix,
                        _CHARGEN_OPENING_SCAN_START,
                        _CHARGEN_OPENING_SCAN_END,
                    )
                except (OSError, RuntimeError, AttributeError) as exc:
                    _log.debug("chargen: opening scan_string error: %s", exc)
                    continue
                if not results:
                    continue
                addr_used = results[0].address
                block = self._read_cinematic_block(addr_used)
                if block and _looks_like_cinematic(block):
                    text = block
                    break
        if not text:
            _log.debug("chargen: post-chargen opening not yet written")
            return False
        # 同一テキストなら panel チカつき防止のため push を省略
        if text == w._chargen_opening_text_prev:
            return True
        w._chargen_opening_text_prev = text
        # 翻訳辞書ルックアップ。`text` フィールドの prefix で照合（_CHARGEN_OPENING_
        # は "Do not fear for it is I, Ria Silmane." を text に持ち、後続のプレイヤー
        # 名込みの本文 ("Do not fear ... [name], listen to me, ...") とマッチする）。
        entry = itl.lookup_by_text("", text)
        if entry is None:
            # 公開では cinematic の英語アンカー（照合用 text）が en-US bundle にも
            # localpack（未再生成）にも無く lookup_by_text が解けないことがある。
            # post-chargen cinematic は必ず _CHARGEN_OPENING_ なので直接引く
            # （訳は id 単位で公開 bundle から解決＝localpack 再生成不要）。
            entry = itl.lookup("_CHARGEN_OPENING_", 0)
        original = text
        translated = ""
        if entry is not None:
            # cinematic は本文中にプレイヤー名が埋め込まれる ([name] / [名前])。
            # 辞書側の整形済みテキスト + 訳文を採用し、player name で置換する。
            player_name = self._read_player_name() or ""
            disp = entry.get("text_display") or entry.get("text", "") or ""
            tr = itl.get_translation(entry)
            tr_str = tr if isinstance(tr, str) else ""
            if player_name:
                disp = disp.replace("[name]", player_name)
                tr_str = tr_str.replace("[名前]", player_name)
            # メモリ上の生原文 (Arena が表示している実テキスト) を優先しつつ、
            # 翻訳辞書から得た訳文を表示する。これにより万一辞書本文が短くても
            # 原文側は full text として表示される。
            original = text
            translated = tr_str
        w._set_chargen_ui_state(True)
        # キャラ作成後のビジョン(リア・シルメイン等)= 状況説明として読む。
        w._push_translation(original, translated, speech_role="situation")
        _log.info("chargen: post-chargen cinematic displayed "
                  "(addr=0x%X, text_len=%d, mapped=%s)",
                  addr_used, len(text), entry is not None)
        return True

    # ------------------------------------------------------------------
    # 名前入力画面 / NPC ダイアログ翻訳
    # ------------------------------------------------------------------

    def _update_chargen_name_display(self, cls_en: str) -> None:
        """名前入力画面: 実際のクラス名を代入して翻訳タブを更新する。

        3-layer スキーマ対応。タブ JA は translations_display.ja を使い補足情報
        （Enter / Backspace 説明）を含める。原文側はゲーム画面のテキストのみ。
        """
        w = self._w
        cls_ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
        if cls_en:
            w._chargen_class_en = cls_en
        if cls_ja and w._chargen_class_ja != cls_ja:
            w._chargen_class_ja = cls_ja
            w._sync_attributes_race_class()
        entry = itl.lookup("_CHARGEN_NAME_", 0)
        if entry is None:
            return
        # 3-layer: 4 軸ごとに get_*() を使用、[class]/[クラス] 置換適用
        tab_orig    = itl.get_text_display(entry).replace("[class]", cls_en)
        panel_orig  = itl.get_text_panel(entry).replace("[class]", cls_en)
        tab_disp    = itl.get_translation_display(entry) or ""
        tab_trans   = tab_disp.replace("[クラス]", cls_ja)
        panel_basic = itl.get_translation(entry) or ""
        panel_trans = panel_basic.replace("[クラス]", cls_ja)
        w._push_translation(tab_orig, tab_trans,
                             panel_original=panel_orig,
                             panel_translated=panel_trans)

    def _handle_chargen_npc_dialog(self, npc_dialog: str) -> None:
        """chargen NPC ダイアログ翻訳処理（接続時・ポーリング時共通）。

        処理順:
          1. 名前入力 regex（最優先・早期 return）
          2. 動的パターン（プレースホルダ代入が必要なエントリ）
          3. lookup_by_text フォールバック（静的エントリ）
          4. 未登録時は原文のみ表示

        2 を 3 より先に実行するのは、動的代入対象エントリの ``text`` フィールドが
        プレースホルダを含まない prefix のため、3 が先だと意図せず先にマッチして
        プレースホルダ未置換のテンプレート文字列が表示されてしまうため。

        chargen_done=1（Appearance Done 後）は chargen 専用パターン（name regex /
        class list）をスキップし、ゲーム内 NPC バッファ残留テキストが
        旧 chargen 翻訳を再発火させるのを防ぐ。
        """
        w = self._w
        if not npc_dialog:
            return

        # 既知の garbage 残留パターン（chargen 終了後にメモリに残る "RRRRR..." 等）は
        # 翻訳パネル更新で原文表示しても利用者にとって意味がないため早期 return する。
        # この判定は chargen_done フラグに依存しないので 2 回目以降の chargen でも安全。
        if _is_garbage_npc_buffer(npc_dialog):
            _log.debug("npc_dialog: ignored garbage buffer (%r)", npc_dialog[:24])
            return

        # クラス一覧画面 (Choose thy class) の決定的シグナル：
        #   NPC バッファの内容がハイライト中のクラス名そのもの（例: "Acrobat"）。
        #   Arena は Choose thy class 画面でハイライト変更ごとにバッファを書き換える
        #   想定だが、run によっては Arena 側が +0x1044 を更新せず同じクラス名
        #   (= 直前 _CHARGEN_RESULT_ の推奨クラス) を保持するケースがある。
        #   その場合、毎 poll で _activate_class_list_for_class が呼ばれ続け、
        #   ユーザーが Assist パネルで他クラスをクリック選択しても次 poll で
        #   元の (Arena 側 buffer の) クラスに巻き戻される症状となる。
        # 修正: 同一クラスの連続活性化を抑止する cache を追加。
        from class_list_panel import resolve_npc_class_name
        cls_canonical = resolve_npc_class_name(npc_dialog)
        if cls_canonical is not None:
            _last_cls = getattr(w, "_last_class_list_activation", None)
            if _last_cls != cls_canonical:
                w._last_class_list_activation = cls_canonical
                self._activate_class_list_for_class(cls_canonical)
            return

        m = _CHARGEN_NAME_RE.search(npc_dialog)
        if m:
            if not w._in_chargen_name:
                w._in_chargen_name = True
                # name_input 進入時に前段フラグをクリア
                w._chargen_class_accept_displayed = False
                w._chargen_10q_displayed = False
                w._chargen_method_window = False
                # クラス一覧 panel が残ったままになる問題対策。
                # _set_class_list_panel_mode(False) で panel mode を translate に戻す
                # （フラグだけ False にしても panel mode は class_list のままになるため）。
                if w._chargen_class_list_active:
                    w._set_class_list_panel_mode(False)
                entry = itl.lookup("_CHARGEN_NAME_", 0)
                if entry is not None:
                    w._update_translate_tab(entry)
            self._update_chargen_name_display(m.group(1))
            return
        if w._in_chargen_name:
            w._in_chargen_name = False
        if self._try_dynamic_chargen_npc(npc_dialog):
            return
        entry = itl.lookup_by_text("", npc_dialog)
        if entry is not None:
            # runaway 防止: 同一 entry の連続検出時は _update_translate_tab を
            # 呼び直さない (= chargen 状態の毎 poll 全リセットを抑止)。
            # _update_translate_tab は inf_key=="_CHARGEN_" 等で chargen 状態
            # フラグの一括リセットを伴うため、同一 npc 内容で連発させると
            # _chargen_10q_displayed 等が True にならない症状となる。
            _entry_key = (entry.get("inf") or "",
                          (entry.get("text") or "")[:40])
            _prev_key = getattr(w, "_last_chargen_entry_key", None)
            if _prev_key == _entry_key:
                return
            inf_key = (entry.get("inf") or "").upper()
            # クラス一覧（直接選択）表示中に method 画面テキスト（"How do you wish to
            # select your class?" = NPC バッファ残留）が再マッチしても、クラス一覧の
            # 翻訳（"Choose thy class..."）を method 訳で上書きしない。直接選択で
            # クラス一覧へ遷移後、下部翻訳が method 画面の訳に戻る不具合の是正。
            # バッファに method 文が無ければ本ガードは発火しない（無害）。
            if w._chargen_class_list_active and inf_key == "_CHARGEN_":
                return
            w._last_chargen_entry_key = _entry_key
            w._update_translate_tab(entry)
            # クラスアドバイス画面検出時は「in_advice モード」のフラグだけ立てる。
            # 実際の chargen_state 値の記録は _poll で「2 ポーリング連続同値で安定」
            # を確認してから行う（cycle 中の transient 値を回避するため）。
            w._track_chargen_race_class(inf_key)
            if inf_key.startswith("_CHARGEN_CLASS_ADVICE_"):
                w._chargen_in_advice = True
                w._chargen_advice_state = None
                w._chargen_advice_a845 = None
                w._chargen_goyenow_displayed = False
                w._chargen_goyenow_state = None
                w._chargen_choose_attrs_displayed = False
                w._chargen_choose_attrs_state_val = None
                # GoYeNow scan 予算を 60 poll (30 秒) にセット。
                # この期間内に hint addr 直読み or 縮小 scan で発火しなければ諦める。
                w._goyenow_scan_budget = 60
                _log.info("chargen: class_advice mode entered (%s)", inf_key)
            elif inf_key == "_CHARGEN_CHOOSE_ATTRIBUTES_":
                w._chargen_choose_attrs_state_val = w._chargen_state_prev
                w._chargen_appearance_displayed = False
                # ChooseAttributes phase に初回進入したら anchor を保持する。
                # 以降の modal (BONUS_REMAINING) や CHOOSE_ATTRIBUTES
                # 再表示では再キャプチャ・破棄しない。Appearance 検出
                # (`anchor + 0x1C`) は modal で消える
                # `_chargen_choose_attrs_state_val` ではなく本 anchor を参照する。
                if not w._chargen_attrs_phase_seen:
                    _old_anchor = w._chargen_attrs_state_anchor
                    w._chargen_attrs_state_anchor = w._chargen_state_prev
                    w._chargen_attrs_phase_seen = True
                    _log.info(
                        "chargen_latch: attrs_anchor=%s->0x%02X source=CHOOSE_ATTRIBUTES_initial",
                        ("0x%02X" % _old_anchor) if _old_anchor is not None
                        else "None",
                        w._chargen_attrs_state_anchor,
                    )
                # status latch は CHOOSE_ATTRIBUTES が唯一の arm point
                # (ステータスタブ表示の開始は能力値選択画面から)
                if not w._chargen_status_display_armed:
                    w._chargen_status_display_armed = True
                    _log.info(
                        "chargen_latch: status_armed=0->1 source=CHOOSE_ATTRIBUTES")
                # modal を閉じた状態 (ChooseAttributes に戻った) → modal off
                w._chargen_attrs_modal_active = False
                # 通常フローの判定: ClassAdvice/GoYeNow/DistributePoints のいずれかを
                # 経由していれば通常プレイ中とみなし、chargen_state の変化を待って
                # Appearance を発火する。
                # 「DistributePoints 未発火 = 再接続」とは限らない（GoYeNow fallback で
                # DistributePoints が失火しただけの可能性がある）ため、この条件だけで
                # 即時発火させると通常フロー中に誤発火する。
                normal_chargen_flow = (
                    w._chargen_advice_state is not None
                    or w._chargen_goyenow_displayed
                    or w._chargen_distribute_displayed
                )
                if normal_chargen_flow:
                    w._chargen_choose_attrs_displayed = True
                    # panel_mode の決定は chargen_state.poll の renderer に
                    # 委譲する (`_enforce_chargen_panel_mode`)。ここで
                    # `_activate_choose_attributes_panel()` を無条件に呼ぶと
                    # ボーナス警告 / Save/Reroll の翻訳表示直後にすぐ
                    # AttributesPanel に戻されて翻訳が見えなくなる症状が起きる。
                    _log.info("chargen: choose_attributes detected, state_val=0x%02X", w._chargen_state_prev)
                else:
                    # 接続時点で既に Appearance 画面にいる場合（真の再接続）のみ即時発火。
                    # MRSHIRT.IMG / 有効 bonus_pts の場合は能力値選択画面の
                    # 可能性が高いため即時 Appearance 発火を禁止する。
                    # MRSHIRT/FRSHIRT.IMG では Appearance を絶対に発火しない
                    # (FACES*.CIF や APPEARANCE NPC テキストでのみ確定)。
                    # bonus_pts は判定に使わない。
                    # 抑止した場合は choose_attrs phase を明示的に立てる。
                    try:
                        from arena_bridge import (
                            SCREEN_IMG_OFFSET as _SCR_OFF,
                            SCREEN_IMG_MAXLEN as _SCR_MAX,
                        )
                        _img_raw = w._analyzer.read_bytes(
                            w._anchor + _SCR_OFF, _SCR_MAX)
                        _img_now = _img_raw.split(b"\x00", 1)[0].decode(
                            "ascii", errors="replace").upper()
                    except (OSError, AttributeError, ImportError):
                        _img_now = ""
                    if _img_now in ("MRSHIRT.IMG", "FRSHIRT.IMG"):
                        # 能力値選択画面に居る → choose_attrs phase を明示
                        w._chargen_choose_attrs_displayed = True
                        # modal は再評価に任せる (sticky を避ける)
                        w._chargen_attrs_modal_active = False
                        w._chargen_attrs_modal_kind = None
                        _log.info(
                            "chargen: reconnect Appearance fire suppressed "
                            "(img=%s) — choose_attrs phase activated",
                            _img_now)
                    elif _img_now.startswith("FACES") and _img_now.endswith(".CIF"):
                        # 真の Appearance 再接続: FACES*.CIF 検出
                        app_entry = itl.lookup("_CHARGEN_APPEARANCE_", 0)
                        if app_entry is not None:
                            w._update_translate_tab(app_entry)
                        w._chargen_appearance_displayed = True
                        _log.info(
                            "chargen: Appearance fired immediately "
                            "(reconnect, FACES IMG detected, img=%s)",
                            _img_now)
                    else:
                        # 判別不可: choose_attrs phase を立てて保留
                        w._chargen_choose_attrs_displayed = True
                        w._chargen_attrs_modal_active = False
                        w._chargen_attrs_modal_kind = None
                        _log.info(
                            "chargen: reconnect Appearance fire suppressed "
                            "(img=%s unrecognized) — choose_attrs phase "
                            "activated as default",
                            _img_now)
            else:
                # 他の NPC ダイアログが来た = choose_attrs トラッキングは不要になる
                w._chargen_choose_attrs_displayed = False
                w._chargen_choose_attrs_state_val = None
        else:
            # 未登録 NPC ダイアログ: chargen 中は原文の生 push を抑止する。
            # chargen の正規ダイアログ (method / 10Q / Race / CLASS / GOYENOW /
            # DISTRIBUTE / CHOOSE_ATTRIBUTES / APPEARANCE / BONUS_REMAINING /
            # PROVINCE / COMPLETE / 名前入力) はいずれも辞書または動的パターンで
            # マッチする。ここに到達するのは NPC バッファに残留する Arena 内部
            # 状態テキスト / 制御バイト / ダイアログ閉幕後の断片であり、
            # 原文 push で翻訳パネルを汚染する原因となる
            # （原文側に不正な表示が出る）。直前の有効翻訳を維持するため skip する。
            return

    def _activate_class_list_for_class(self, en_name: str) -> None:
        """クラス一覧画面用パネルへ切替え、指定クラスをハイライト表示する。

        - 翻訳タブ: class_list モードに切替 + 該当クラスをハイライト
        - レイアウトパネル（翻訳パネル）: ゲームメッセージ翻訳専用のため、
          ここでは "Choose thy class..." の翻訳を表示する（class_list モードは持たない）

        ニューゲーム検出: 前回 chargen が完了済み（Appearance/cinematic 表示済み）
        にも関わらず class_list が再活性化した場合、ユーザーがメニューから新規ゲームを
        始めたと判断して chargen 状態をリセットする。chargen_done の 1→0 遷移を
        トリガにすると Appearance Done 直後に誤発火するため、より堅牢な
        class_list 再活性化シグナルを採用する。
        """
        w = self._w
        first_activation = not w._chargen_class_list_active
        if en_name:
            w._chargen_class_en = en_name
            cls_ja = _CHARGEN_CLASS_JA.get(en_name, en_name)
            if cls_ja and w._chargen_class_ja != cls_ja:
                w._chargen_class_ja = cls_ja
                w._sync_attributes_race_class()
        if (first_activation
                and (w._chargen_appearance_displayed
                     or w._chargen_opening_displayed)):
            self._reset_chargen_state_for_restart(
                reason="class_list reactivated after appearance/opening")
            # リセット直後は class_list_active が False に戻るので first_activation は維持
            first_activation = True
        if first_activation:
            # 手動経路に進んだ → 10Q 窓は閉じる
            w._chargen_method_window = False
            w._set_class_list_panel_mode(True)
            w._set_chargen_ui_state(True)
            _log.info("chargen: class list panel activated (npc=%s)", en_name)
        try:
            w._tab_translate.select_class_in_list(en_name)
        except AttributeError:
            pass

    def _try_dynamic_chargen_npc(self, npc_dialog: str) -> bool:
        """動的テキストを含む chargen NPC ダイアログをパターンマッチで処理する。マッチした場合 True を返す。"""
        w = self._w
        normalized = " ".join(npc_dialog.split())
        for item in _CHARGEN_DYNAMIC_PATTERNS:
            pattern, inf_key = item[0], item[1]
            extract_re     = item[2] if len(item) > 2 else None
            subst_fn       = item[3] if len(item) > 3 else None
            orig_suffix    = item[4] if len(item) > 4 else None
            if not pattern.search(normalized):
                continue
            # 動的 chargen NPC が出る = method 画面の窓は閉じる（10Q 誤発火防止）
            w._chargen_method_window = False
            # chargen subscreen フラグの制御。
            # 全ての non-COMPLETE 動的 NPC で _chargen_complete_displayed = False をクリア。
            # 前回 chargen の "Then thou wilt..." 残留が本回の早い段階で誤発火しても、
            # 他 NPC fire 時にクリアされるようにする戦略。
            if inf_key == "_CHARGEN_PROVINCE_":
                # "From where dost thou hail" → race_select 進入
                w._chargen_race_select_displayed = True
                # 名前入力・性別選択は完了済み → クリア
                w._in_chargen_name = False
                w._chargen_sex_select_displayed = False
                # 10Q phase / class_accept / class_list / appearance も完了済み
                w._chargen_10q_displayed = False
                w._chargen_class_accept_displayed = False
                w._chargen_class_list_active = False
                w._chargen_appearance_displayed = False
                # 残留 chargen_complete をクリア
                w._chargen_complete_displayed = False
            elif inf_key == "_CHARGEN_PROVINCE_CONFIRM_":
                # confirm dialog 表示中。race_select は維持（No 戻り対応）
                # 残留 chargen_complete をクリア
                w._chargen_complete_displayed = False
            elif inf_key == "_CHARGEN_COMPLETE_":
                # chargen_complete subscreen 進入。
                # _CHARGEN_COMPLETE_ の動的パターン本文（"Then thou wilt be known as the"）
                # に一致した時点で、追加 condition なしで発火する。
                # false positive は、他 chargen NPC 発火時の state クリア
                # （上記各ブランチの _chargen_complete_displayed = False）
                # でカバーする方針。発火時はログに記録して挙動確認可能にする。
                _log.info(
                    "chargen_complete fired (NPC match: 'Then thou wilt be known as the'); "
                    "flags before fire: appearance=%s chargen_done_prev=%s",
                    w._chargen_appearance_displayed, w._chargen_done_prev,
                )
                w._chargen_complete_displayed = True
                # 他フラグをクリア（chargen 進行の最終段階のため）
                w._chargen_race_select_displayed = False
                w._chargen_race_desc_displayed = False
                w._chargen_class_accept_displayed = False
                w._chargen_in_advice = False
                w._chargen_goyenow_displayed = False
                w._chargen_distribute_displayed = False
                w._chargen_choose_attrs_displayed = False
                w._chargen_appearance_displayed = False
                w._chargen_sex_select_displayed = False
                w._in_chargen_name = False
                w._chargen_10q_displayed = False
                w._chargen_method_window = False
                w._chargen_class_list_active = False
                # 訂正: COMPLETE は race 選択直後の status_proclamation 画面
                # ("Then thou wilt be known as...") の翻訳イベントであり、
                # 能力値選択以降の modal ではない。ステータスタブを表示
                # 開始させてはならない。
                # - `_chargen_status_display_armed` は触らない
                # - `_chargen_attrs_modal_active` も触らない (false 維持)
                # ステータスタブ表示は `_CHARGEN_CHOOSE_ATTRIBUTES_` 確定時に
                # のみ arm される。
            w._set_chargen_ui_state(True)
            entry = itl.lookup(inf_key, 0)
            # 原文側に画面外コンテンツを出さない方針:
            # 動的 NPC では原文側（tab_orig / panel_orig）に entry の text_panel /
            # text_display を使うとプレースホルダ（[name] / [class] 等）が
            # 残ったまま表示される。実際のゲーム NPC バッファ内容
            # （normalized）を使い、placeholder 置換済みの原文を表示する。
            # entry に suffix が定義されていれば付加（"\n\nYes / No" 等）。
            tab_orig = normalized + (orig_suffix or "")
            panel_orig = normalized + (orig_suffix or "")
            tab_disp = itl.get_translation_display(entry) if entry else None
            tab_trans = tab_disp if isinstance(tab_disp, str) else ""
            panel_basic = itl.get_translation(entry) if entry else None
            panel_trans = panel_basic if isinstance(panel_basic, str) else ""
            # 動的プレースホルダ置換は翻訳側のみ適用
            # （原文側は normalized が既に置換済みなので不要）
            if extract_re and subst_fn:
                m = extract_re.search(normalized)
                if m:
                    subs = subst_fn(m)
                    for placeholder, value in subs.items():
                        if tab_trans:
                            tab_trans = tab_trans.replace(placeholder, value)
                        if panel_trans:
                            panel_trans = panel_trans.replace(placeholder, value)
                    # 動的パターンから race / class を吸い上げて AttributesPanel に反映
                    new_race = subs.get("[種族]")
                    new_cls  = subs.get("[クラス]")
                    if new_race and w._chargen_race_ja != new_race:
                        w._chargen_race_ja = new_race
                    if new_cls and w._chargen_class_ja != new_cls:
                        w._chargen_class_ja = new_cls
                    if new_race or new_cls:
                        w._sync_attributes_race_class()
            # キャラ作成中のNPCダイアログ(10問の質問等)= 状況説明として読む。
            w._push_translation(tab_orig, tab_trans,
                                 panel_original=panel_orig,
                                 panel_translated=panel_trans,
                                 speech_role="situation")
            return True
        return False
