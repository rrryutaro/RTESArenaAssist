"""controllers/connect_flow_controller.py — 接続シーケンス。

DOSBox 接続完了後の初期化 (辞書再読込・MIF ディレクトリ解決・L1 初期判定)
を assist_window から純抽出 (挙動不変)。window 状態は win 経由で参照する
(本体側の委譲は関数ローカル import で循環回避)。
"""
from __future__ import annotations

import logging
import os

import i18n_helper as i18n
import assist_settings as settings
import inf_text_lookup as itl
from controllers.chargen_helpers import _CHARGEN_CLASS_JA
from ui_router import UiRouter

_log = logging.getLogger("assist_window")


def _app_dir() -> str:
    from assist_window import _APP_DIR
    return _APP_DIR


def on_connect_done(win, pid: int, anchor: int):
    win._analyzer = win._worker.analyzer
    win._anchor   = anchor
    win._npc_dialog_prev = ""       # NPC会話キャッシュをリセット
    win._npc_dialog_text_prev = ""  # POPUP11 テキストキャッシュをリセット
    win._interior_facility_kind = ""  # L3 施設識別の永続値をリセット(再接続の stale 防止)
    itl.load()                  # 辞書を最新ファイルから再読み込み
    win._conn_btn.setEnabled(True)
    win._conn_btn.setText(i18n.tr("connection.disconnect"))
    # 接続バーは画面名 + IMG 名表示。初期値はプレースホルダ、_poll で上書きされる
    # 認識画面表示の ON/OFF を反映
    if settings.get("show_recognition_screen", True):
        win._status_lbl.setText(
            i18n.tr("connection.status_connected", screen="—"))
    else:
        win._status_lbl.setText(
            i18n.tr("connection.status_connected_no_screen"))
    win._anchor_lbl.setText(i18n.tr("connection.img_info", img="—"))
    # 中央の独立 IMG ラベルは右側へ統合したため非表示
    win._img_name_lbl.setVisible(False)
    win._tab_translate.set_connected(True)
    # 共有 AttributesPanel に memory target を渡す (翻訳 / ステータス両用)。
    win._tab_status.set_memory_target(win._analyzer, win._anchor)
    # Appearance faces パネル: memory target と AssistWindow 参照を渡す
    # (window 参照はゲームウィンドウサイズ追従用)
    try:
        win._tab_translate.appearance_faces_panel().set_memory_target(
            win._analyzer, win._anchor)
        win._tab_translate.appearance_faces_panel().set_window(win)
    except AttributeError:
        pass
    if win._layout_translate_panel is not None:
        win._layout_translate_panel.set_connected(True)

    # MIF照合器を初期化（ゲームフォルダの MAPS/ を自動検出）
    try:
        from arena_bridge import MifTriggerMatcher
        from runtime_paths import resolve_arena_data_dir
        import json as _json

        def _usable_mif_dir(path: str) -> str:
            if not path or not os.path.isdir(path):
                return ""
            try:
                for name in os.listdir(path):
                    if name.upper().endswith(".MIF"):
                        return path
            except OSError:
                return ""
            return ""

        save_dir = settings.get("save_dir", "")
        explicit_mif_dir = settings.get("mif_dir", "")
        mif_dir = _usable_mif_dir(explicit_mif_dir)
        if not mif_dir and save_dir:
            maps_path = os.path.join(save_dir, "MAPS")
            mif_dir = _usable_mif_dir(maps_path)
            if not mif_dir:
                mif_dir = _usable_mif_dir(save_dir)
        if not mif_dir:
            mif_dir = _usable_mif_dir(os.fspath(
                resolve_arena_data_dir() / "MIF"))
        win._mif_matcher = MifTriggerMatcher(mif_dir=mif_dir)
        _log.info("MifTriggerMatcher initialized: mif_dir=%s", mif_dir or "(none)")
    except Exception:
        win._mif_matcher = None

    win._trigger_flag_prev  = 0
    win._trigger_indices    = []
    win._cached_trig_idx    = 0
    win._cached_rt_x = win._cached_rt_z = None
    # 翻訳パネル owner 追跡。clear ハンドラが他系統の表示を破壊しないよう、
    # 自分が表示したものだけ消せる仲裁構造を最小限で導入する。
    # 値: "trigger" | "red_text" | "npc_dialog" | "gold_drop" | "level_up"
    #     | "status" | "item_pickup" | "" (なし/clear 済み)
    win._panel_owner: str = ""
    win._ui_router = UiRouter(win)
    # 翻訳反映を読み上げ/ログ分配へ接続
    _feed = getattr(win, "_translation_feed", None)
    if _feed is not None:
        win._ui_router.set_translation_observer(_feed.on_translation)
    # NEWPOP popup 経路（chest / corpse）追跡
    win._b32_was_corpse: bool = False
    win._img_name_prev = ""
    win._screen_id_prev: str | None = None
    # screen_id デバウンス用（撤去済み、互換のため残す）
    win._screen_id_pending: str | None = None
    win._screen_id_stable_count: int = 0
    win._menu_active_prev: int = 0xFFFF  # system_menu 連続観測用
    win._flag_detail_skip_n: int = 0   # spell_detail bounce 保護カウンタ
    win._spell_detail_text_ready: bool = True  # effect text 書込み完了フラグ
    win._spell_detail_text_marker = None  # effect text buffer 変化検出用
    win._equipment_marker: bytes | None = None  # 装備変化検出用
    win._newgame_layout_pushed = False
    win._startup_layout_pushed = False
    win._chargen_state_prev = 0
    win._chargen_q_seq_prev = 0
    win._in_chargen_name    = False
    win._chargen_state_streak = 0
    win._chargen_in_advice = False
    win._chargen_advice_state = None
    win._chargen_goyenow_displayed = False
    win._chargen_goyenow_state = None
    win._chargen_goyenow_b7c4_prev = None
    win._chargen_10q_displayed = False
    win._chargen_method_state = None
    win._chargen_distribute_displayed = False
    win._chargen_choose_attrs_displayed = False
    win._chargen_choose_attrs_state_val = None
    win._chargen_appearance_displayed = False
    win._chargen_done_prev = 0
    win._chargen_opening_displayed = False
    win._chargen_method_window = False
    win._chargen_race_select_displayed = False
    # 新設フラグのリセット
    win._chargen_class_accept_displayed = False
    win._chargen_race_desc_displayed = False
    win._chargen_sex_select_displayed = False
    win._chargen_complete_displayed = False
    win._chargen_class_list_active = False
    win._is_in_chargen = False
    win._goyenow_scan_budget = 0
    win._advice_capture_age = -1
    win._chargen_race_ja = None
    win._chargen_class_ja = None
    win._chargen_class_en = None
    win._top_level_state = "pregame"
    win._chargen_subscreen_last = None
    win._pregame_loadsave_seen = False
    win._set_class_list_panel_mode(False)
    win._set_chargen_ui_state(False)

    # 接続時の現在値で prev を初期化し、初回ポーリングでの誤検出を防ぐ
    try:
        from arena_bridge import (
            CHARGEN_STATE_OFFSET, CHARGEN_Q_SEQ_OFFSET,
            CHARGEN_DONE_OFFSET,
            NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN, read_live_buffer,
        )
        win._chargen_state_prev = win._analyzer.read_bytes(
            win._anchor + CHARGEN_STATE_OFFSET, 1)[0]
        win._chargen_q_seq_prev = win._analyzer.read_bytes(
            win._anchor + CHARGEN_Q_SEQ_OFFSET, 1)[0]
        win._chargen_done_prev = win._analyzer.read_bytes(
            win._anchor + CHARGEN_DONE_OFFSET, 1)[0]
        npc_init = read_live_buffer(
            win._analyzer, win._anchor + NPC_DIALOG_OFFSET, NPC_DIALOG_MAXLEN)
        win._chargen._handle_chargen_npc_dialog(npc_init)
        win._npc_dialog_prev = npc_init
    except (OSError, ImportError):
        pass

    win._sb.showMessage(i18n.tr("status.ready"))
    win._layout_mgr.set_dosbox_pid(pid)
    # 途中接続時のトップレベル状態識別。
    # 「トップレベル状態は信号内容のみで判定する」原則に従い、
    # 信号内容 (画面 IMG) ベースで判定する。auto 活性化処理は本判定の
    # 後に gate されて実行される (信号内容に反するメモリ内容を根拠とした
    # 状態フラグ設定の混入を防ぐ)。
    win._detect_top_level_at_connect()

    # 中途接続の階層初期化 (L1→L2 push)。
    # L1=normal-play なら現在信号から親 L2 を resolve_attach_path で解決し、
    # 親保持 area (_last_non_interior_area) へ seed する。屋内中の中途接続
    # でも mif_name (= 街マップ MIF。interior MIF とは別) から親 L2 が
    # 決まるため、「親未取得の屋内は暫定で街扱い」の fallback ではなく
    # 実際の親 L2 で階層認識・area 確定を開始できる。L3 施設の latch /
    # L4 会話は以降の poll で各 session/node が信号から自然に attach する。
    if win._top_level_state == "normal-play":
        try:
            from session.hierarchy_attach import resolve_attach_path
            from normal_play.base_location.base_location_view import (
                area_name,
            )
            from arena_bridge import (
                read_game_state, read_interior_flag,
            )
            from play_area_classifier import (
                resolve_in_interior, _WILDERNESS_FLAG_OFFSET,
            )
            _gs_attach = read_game_state(win._analyzer, win._anchor)
            _mif_attach = (_gs_attach.get("LiveMifName")
                           or _gs_attach.get("MifName") or "")
            # 屋内判定は場所種別byte(+0x4BD0)を権威に（夜間の 0xBC8E 汚染を抑止）。
            try:
                _place_attach = win._analyzer.read_bytes(
                    win._anchor + _WILDERNESS_FLAG_OFFSET, 1)[0]
            except (OSError, IndexError, AttributeError):
                _place_attach = None
            _in_interior_attach = resolve_in_interior(
                read_interior_flag(win._analyzer, win._anchor),
                _place_attach, _mif_attach)
            _attach = resolve_attach_path(
                win,
                mif_name=_mif_attach,
                in_interior=_in_interior_attach,
            )
            _seed_area = area_name(_attach.get("l2", ""))
            if _seed_area:
                win._last_non_interior_area = _seed_area
            _log.info(
                "hierarchy attach: l1=%s l2=%s l3=%s "
                "(mif=%r in_interior=%s seed_area=%r)",
                _attach.get("l1"), _attach.get("l2"), _attach.get("l3"),
                _mif_attach, _in_interior_attach, _seed_area)
        except Exception:  # noqa: BLE001
            _log.exception("hierarchy attach failed")

    # 再起動・再接続時の復帰: トップレベル判定が chargen の場合のみ、
    # player struct のメモリ内容から能力値画面 (ChooseAttributes) の
    # UI 復帰を試みる。タイトル中 (pregame) では Arena のメモリに前回
    # プレイのキャラデータが残っているが、信号内容ベース判定で pregame
    # と確定しているのでこの auto 活性化は走らない。
    if win._top_level_state == "chargen":
        try:
            attrs = win._analyzer.read_bytes(win._anchor + 0x1CD, 8)
            name_raw = win._analyzer.read_bytes(win._anchor + 0x1AD, 26)
            name_str = name_raw.split(b"\x00", 1)[0].decode("ascii", errors="ignore").strip()
            is_named = bool(name_str) and all(0x20 <= b <= 0x7E for b in name_raw[:len(name_str)])
            attrs_ok = sum(attrs) > 0 and all(b < 200 for b in attrs)
            if is_named and attrs_ok:
                # race / class を memory から復帰 (UI 表示補助)
                try:
                    race_idx = win._analyzer.read_bytes(win._anchor + 0x214, 1)[0]
                    if 0 <= race_idx < 8:
                        race_jas = ["ブレトン", "レッドガード", "ノルド", "ダークエルフ",
                                    "ハイエルフ", "ウッドエルフ", "カジート", "アルゴニアン"]
                        win._chargen_race_ja = race_jas[race_idx]
                except OSError:
                    pass
                try:
                    cls_id = win._analyzer.read_bytes(win._anchor + 0x217, 1)[0]
                    cls_map = settings.get("arena_class_id_map", {}) or {}
                    cls_en = cls_map.get(str(cls_id))
                    if cls_en:
                        win._chargen_class_en = cls_en
                        win._chargen_class_ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
                except OSError:
                    pass
                win._sync_attributes_race_class()
                # 翻訳タブを choose_attributes モードに切替（UI 復帰の補助）
                win._activate_choose_attributes_panel()
                # 内部状態フラグ (_chargen_choose_attrs_displayed 等) は
                # 設定しない (検出マーカーは信号内容で立てる経路に委譲する)。
                _log.info("connect: ChooseAttributes panel auto-activated "
                          "(name=%r race=%s class=%s)",
                          name_str, win._chargen_race_ja, win._chargen_class_ja)
        except OSError:
            pass

    # 接続時の chargen モードを AttributesPanel に反映（detect の結果に依存）
    win._sync_attributes_chargen_mode()
    # 接続時のステータス/マップ/ジャーナル表示の有効/無効を同期
    win._apply_display_active_for_state()
    win._poll_timer.start()


def detect_top_level_at_connect(win) -> None:
    """途中接続時の top-level 状態識別。

    現在の screen_img と chargen_done を読んで _top_level_state を設定する。
    """
    try:
        from arena_bridge import (
            SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN, CHARGEN_DONE_OFFSET)
        raw = win._analyzer.read_bytes(
            win._anchor + SCREEN_IMG_OFFSET, SCREEN_IMG_MAXLEN)
        img = raw.split(b"\x00", 1)[0].decode("ascii", errors="replace").upper()
    except (OSError, ImportError, AttributeError):
        img = ""

    img_upper = img.upper()

    # chargen フラグを最優先で確認する。
    # _handle_chargen_npc_dialog が _on_connect_done で接続時に呼ばれており、
    # _CHARGEN_ NPC が検出済みなら _chargen_method_window 等が立っている。
    # chargen_done の値に関わらず chargen と判定する（2回目 chargen では
    # chargen_done == 1 のまま残留するため chargen_done 判定は不可）。
    try:
        from screen_detector import get_chargen_subscreen
        if get_chargen_subscreen(win) is not None:
            win._top_level_state = "chargen"
            _log.info("top_level: connect-time detect → chargen (chargen flags, img=%r)", img)
            return
    except ImportError:
        pass

    # 接続時判定:
    #   タイトル中固有信号 / キャラクター作成中固有信号で先に確定。
    #   残った曖昧 IMG は経験値 == 0 でキャラクター作成中、それ以外は通常
    #   プレイ中。経験値 == 0 だけで判定し chargen_done は使わない (ロード
    #   後 0 のまま戻らない事例が観測されたため、単独信号として使えない)。

    # 確定 pregame IMG (タイトル中固有信号)
    if img_upper in ("QUOTE.IMG", "SCROLL01.IMG", "SCROLL02.IMG",
                     "MENU.IMG", "LOADSAVE.IMG", "PERCNTRO.XMI"):
        state = "pregame"
        if img_upper == "LOADSAVE.IMG":
            win._pregame_loadsave_seen = True
    # VISION.XMI は chargen 旅立ちだけでなく、normal-play の死亡 /
    # 休憩時メインクエスト啓示でも使われる。IMG 単独では確定扱いしない。
    elif img_upper == "VISION.XMI":
        try:
            hp_raw = win._analyzer.read_bytes(win._anchor + 0x1FD, 2)
            hp = hp_raw[0] | (hp_raw[1] << 8)
        except (OSError, AttributeError, IndexError):
            hp = None
        if hp == 0:
            state = "normal-play"
        else:
            try:
                exp_raw = win._analyzer.read_bytes(win._anchor + 0x5AD, 4)
                exp = exp_raw[0] | (exp_raw[1] << 8) | (exp_raw[2] << 16) | (exp_raw[3] << 24)
                state = "chargen" if exp == 0 else "normal-play"
            except (OSError, AttributeError, IndexError):
                state = "normal-play"
    # 確定 chargen IMG (キャラクター作成中固有信号)
    elif (img_upper.startswith("INTRO") and img_upper.endswith(".IMG")) \
            or img_upper in ("EVLINTRO.XMI",
                             "NOEXIT.IMG", "BONUS.IMG", "PARCH.CIF"):
        state = "chargen"
    # 確定 normal-play IMG (通常プレイ専用画面)
    elif img_upper in ("PAGE2.IMG", "OP.IMG",
                       "LOGBOOK.IMG", "AUTOMAP.IMG", "POINTER.IMG",
                       "NEWPOP.IMG"):
        state = "normal-play"
    else:
        # 曖昧 IMG (TERRAIN.IMG / MRSHIRT.IMG / FRSHIRT.IMG / MSSHIRT.IMG /
        # FACES*.CIF / CHARBK*.IMG / POPUP2.IMG / 不明 XMI 等)。
        # 経験値 == 0 → キャラクター作成中、それ以外は通常プレイ中。
        try:
            exp_raw = win._analyzer.read_bytes(win._anchor + 0x5AD, 4)
            exp = exp_raw[0] | (exp_raw[1] << 8) | (exp_raw[2] << 16) | (exp_raw[3] << 24)
            state = "chargen" if exp == 0 else "normal-play"
        except (OSError, AttributeError):
            # 読出失敗時は安全側で通常プレイ中
            state = "normal-play"

    win._top_level_state = state
    _log.info("top_level: connect-time detect → %s (img=%r)", state, img)
    # 翻訳タブへの top_level 同期は廃止 (fallback 床は flush の
    # 単一権威 resolver が window._top_level_state を直接読む)。接続時に通常
    # プレイ中なら床落ちを funnel へ提案する (poll 外なので即時 resolver 確定)。
    if state == "normal-play":
        try:
            win._ui_router.set_panel_mode(
                "translate", reason="connect_normal_play")
        except (AttributeError, RuntimeError):
            pass


__all__ = ["on_connect_done", "detect_top_level_at_connect"]
