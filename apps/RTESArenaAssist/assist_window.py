"""
assist_window.py — RTESArenaAssist メインウィンドウ

■ 変更点
  - メニューバー廃止 → 接続バーに ⚙ ボタン
  - 設定ダイアログ (_SettingsDialog): ゲームフォルダ/バックアップ先/テーマ/最前面
  - 8方向リサイズ: eventFilter で実装 (QApplication.setOverrideCursor 使用)
  - コンテキストメニュー: 非インタラクティブ領域の右クリックで表示
"""

import os
import re
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QThread, QTimer, Signal, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox,
    QStatusBar, QTabWidget, QVBoxLayout, QWidget,
)

import struct
import time

import logging

import i18n_helper as i18n
import assist_log
import assist_settings as settings
import theme as theme_mod
from assist_constants import APP_NAME, WIN_W, WIN_H, WIN_MIN_W, WIN_MIN_H
from version import version_string
from layout_manager import LayoutManager, TrackMode, LayoutCorner, LayoutForm, calc_layout_zones
from layout_panel_translate import LayoutPanelTranslate

_log = logging.getLogger("assist_window")
from tabs.tab_translate import TabTranslate
from tabs.tab_status import TabStatus
from attributes_panel import AttributesPanel
from tabs.tab_dict import TabDict
from tabs.tab_save import TabSave
from tabs.tab_manual import TabManual
from tabs.tab_capture import TabCapture
try:
    from tabs.tab_map import TabMap
    _TAB_MAP_AVAILABLE = True
except Exception:  # noqa: BLE001
    TabMap = None  # type: ignore
    _TAB_MAP_AVAILABLE = False
try:
    from tabs.tab_journal import TabJournal
    _TAB_JOURNAL_AVAILABLE = True
except Exception:  # noqa: BLE001
    TabJournal = None  # type: ignore
    _TAB_JOURNAL_AVAILABLE = False
from windows.settings_dialog import _SettingsDialog  # Phase 1: 分離
from controllers.img_screen_controller import ImgScreenController  # Phase 3: 分離
from controllers.poll_controller import PollController              # 分離
from controllers.window_chrome import WindowChrome  # Phase 4: 分離
from controllers.layout_controller import LayoutController  # Phase 5a: 分離
from controllers.chargen_controller import ChargenController  # Phase 2b: 分離

# screen_judge subsystem は設定 screen_judge_enabled=True のときのみロード
if settings.get("screen_judge_enabled", True):
    try:
        from controllers.screen_judge_controller import ScreenJudgeController
        from tabs.tab_screen_judge import TabScreenJudge
        _SCREEN_JUDGE_AVAILABLE = True
    except ImportError as _sj_exc:
        _log.warning("screen_judge unavailable: %s", _sj_exc)
        ScreenJudgeController = None
        TabScreenJudge = None
        _SCREEN_JUDGE_AVAILABLE = False
else:
    ScreenJudgeController = None
    TabScreenJudge = None
    _SCREEN_JUDGE_AVAILABLE = False

_POLL_MS       = 100
_RESIZE_BORDER = 6   # リサイズ判定幅 (px)
_APP_DIR       = os.path.dirname(os.path.abspath(__file__))
_USER_DIR      = (os.path.dirname(os.path.abspath(sys.executable))
                  if getattr(sys, "frozen", False) else _APP_DIR)

# chargen 検出用の定数 + 純粋関数は controllers/chargen_helpers.py に分離（Phase 2a）
from controllers.chargen_helpers import (
    _CHARGEN_OPENING_HINT_ADDR, _CHARGEN_OPENING_MAXLEN,
    _CHARGEN_OPENING_FULLREAD,
    _CHARGEN_OPENING_SCAN_START, _CHARGEN_OPENING_SCAN_END,
    _CHARGEN_OPENING_PREFIXES,
    _CHARGEN_GOYENOW_HINT_ADDR, _CHARGEN_GOYENOW_HINT_CHECKLEN,
    _CHARGEN_GOYENOW_PREFIX,
    _CHARGEN_GOYENOW_SCAN_START, _CHARGEN_GOYENOW_SCAN_END,
    _GARBAGE_NPC_PATTERNS, _is_garbage_npc_buffer, _looks_like_cinematic,
    _CHARGEN_NAME_RE,
    _CHARGEN_CLASS_JA, _CHARGEN_PEOPLE_JA,
    _CHARGEN_RACE_INF_TO_JA,
    _CHARGEN_DYNAMIC_PATTERNS,
)

# ドラッグ対象外ウィジェット型（遅延初期化）
class _ConnectWorker(QThread):
    done   = Signal(int, int)  # pid, anchor_addr
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.analyzer = None

    def run(self):
        try:
            from arena_bridge import ArenaMemoryAnalyzer, find_anchor
            self.analyzer = ArenaMemoryAnalyzer()
            self.analyzer.attach()
            anchor = find_anchor(self.analyzer)
            if anchor is None:
                self.analyzer.detach()
                self.analyzer = None
                self.failed.emit("Anchor not found — is Arena running in DOSBox?")
                return
            self.done.emit(self.analyzer.pid, anchor)
        except Exception as exc:
            if self.analyzer:
                try:
                    self.analyzer.detach()
                except Exception:
                    pass
                self.analyzer = None
            self.failed.emit(str(exc))


class AssistWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._analyzer = None
        self._anchor: int = 0
        self._worker: _ConnectWorker | None = None

        # ドラッグ・リサイズ・カーソル状態は controllers/window_chrome.py に分離（Phase 4）

        self._poll_timer = QTimer(self)
        self._poll_ms = settings.get("poll_interval_ms", _POLL_MS)
        self._poll_timer.setInterval(self._poll_ms)
        self._poll_timer.timeout.connect(self._poll)

        # IMG 画面検出ハンドラ（Phase 3 で分離）
        self._img_screen = ImgScreenController(self)

        # ポーリングループ（分離）
        self._poll_ctrl = PollController(self)

        # ウィンドウクロム（ドラッグ・8方向リサイズ・コンテキストメニュー、Phase 4 で分離）
        self._chrome = WindowChrome(self)

        # レイアウト UI ハンドラ（メニュー・トグル・設定、Phase 5a で分離）
        self._layout = LayoutController(self)

        # chargen 検出 / 翻訳オーケストレーション（Phase 2b で分離）
        self._chargen = ChargenController(self)

        # 読み上げ(TTS) サービス + 翻訳分配（Phase1）＋翻訳ログ(Phase2-A)
        from tts_service import TTSService
        from controllers.translation_feed import TranslationFeed
        from services.log_store import LogStore
        self._tts = TTSService()
        # Phase3: 任意テキスト読み上げ（右クリック/スピーカーアイコン）の
        # 読み上げ関数を登録（master OFF でも読む明示読み上げ）。
        try:
            from tts_read_aloud import set_speaker as _set_speaker
            _set_speaker(self._tts.speak_now)
        except Exception:  # noqa: BLE001
            pass
        self._log_store = LogStore(
            max_entries=int(settings.get("log_max_entries", 2000)))
        self._translation_feed = TranslationFeed(
            self._tts, self, log_store=self._log_store)
        # Phase2-B: ログをセーブ/ロード契機(map と同じ)で駆動する。
        # ロードで未保存分を破棄しロード先スロットの保存ログへ差し替える。
        try:
            from controllers.map_ext_lifecycle import get_lifecycle
            get_lifecycle().add_store(self._log_store)
            # ロード時に読み上げの重複ガードもクリアする（ロード後に同一テキストが
            # 再び出ても読むため）。
            get_lifecycle().add_on_load(self._translation_feed.reset_spoken)
        except Exception:  # noqa: BLE001
            pass
        self._apply_tts_settings()

        # screen_judge subsystem（Phase A 以降、設定で ON/OFF）
        if _SCREEN_JUDGE_AVAILABLE and ScreenJudgeController is not None:
            self._screen_judge = ScreenJudgeController(self)
            _log.info("screen_judge: enabled")
        else:
            self._screen_judge = None
            _log.info("screen_judge: disabled (setting or import failed)")

        # レイアウト管理
        self._layout_mgr = LayoutManager(self)
        self._layout_corner = LayoutCorner(
            settings.get("layout_corner", LayoutCorner.TOP_LEFT.value)
        )
        try:
            self._layout_form = LayoutForm(settings.get("layout_form", LayoutForm.FORM_2.value))
        except ValueError:
            self._layout_form = LayoutForm.FORM_2
        # レイアウトモード状態（setMask 方式）
        self._is_layout_active:   bool             = False
        self._layout_old_central                   = None   # 元の centralWidget
        self._layout_saved_geo                     = None   # 元のジオメトリ
        self._layout_dos_offset: tuple[int, int]   = (0, 0) # DOSBox局所オフセット(論理px)
        self._layout_dos_size:   tuple[int, int]   = (0, 0) # DOSBoxサイズ(物理px)
        self._layout_dosbox_saved_rect             = None   # DOSBox 元位置 (l,t,r,b)
        self._layout_dpr:        float             = 1.0    # 物理px/論理px（moveEvent用）
        self._layout_zone_widgets:  list           = []     # 副ゾーンのプレースホルダー
        self._layout_translate_panel               = None   # FORM_2 翻訳パネル

        # 埋め込みレイアウトモード状態（createWindowContainer 方式）
        self._is_embed_active:    bool             = False
        self._embed_old_central                    = None
        self._embed_saved_geo                      = None

        # レイアウトモード中の DOSBox カーソルロック解除タイマー
        self._cursor_unlock_timer = QTimer(self)
        self._cursor_unlock_timer.setInterval(100)
        self._cursor_unlock_timer.timeout.connect(self._layout.unlock_cursor)

        # img_name 検出状態（MENU.IMG / LOADSAVE.IMG / INTRO*.IMG 等）
        self._img_name_prev:         str  = ""
        self._newgame_layout_pushed: bool = False
        self._startup_layout_pushed: bool = False

        # トリガー状態
        self._trigger_flag_prev: int       = 0
        self._trigger_indices:   list      = []
        self._cached_trig_idx:   int       = 0
        self._cached_rt_x:       int | None = None
        self._cached_rt_z:       int | None = None
        self._mif_matcher                  = None

        # NPC会話バッファ状態（キャラ作成等のダイアログ検出用）
        self._npc_dialog_prev: str         = ""
        # POPUP11.IMG 表示中の NPC 会話テキストキャッシュ（テキスト変化検出用）
        self._npc_dialog_text_prev: str    = ""
        # ASK ABOUT? メニュー表示中フラグ（状態遷移検出用）
        self._ask_about_menu_active_prev: bool = False
        # ASK_ABOUT_MAIN 復帰中フラグ (メモリ残留対応)
        # 応答 (npc_response) → ASK_ABOUT_MAIN 復帰時に True、ユーザー次操作で
        # item_count/dyn_count が変化したら False に戻す。
        self._popup11_ask_recovery: bool   = False
        self._popup11_item_dyn_prev: tuple = (-1, -1)

        # NPC会話状態
        # NPC会話判定信号 (+0xA845) を読み、0x85 観測で True / 0x00 観測で False に
        # 更新する。0x10 観測時は現状値を保持（NPC応答中と死体クリック中を
        # NPC会話状態で区別する）。
        self._npc_phase: int | None        = None
        self._npc_conversation_active: bool = False
        # NPC会話判定信号の未知値ログ重複抑止
        self._npc_phase_unknown_prev: int | None = None
        # 会話・対話セッション統括 (通常 NPC 会話 / 施設会話)。
        # 通常 NPC 会話と施設会話 (宿屋 / 神殿 等) を相互排他 latch として
        # 管理し、一方が active な間は他方の判定を抑止する。
        from session import (
            SessionManager, NpcChatSession, TavernSession, TempleSession,
            EquipmentSession, MagesGuildSession,
        )
        self._session_manager: SessionManager = SessionManager()
        self._npc_chat_session: NpcChatSession = NpcChatSession()
        self._tavern_session: TavernSession = TavernSession()
        # 神殿神官会話セッション (TavernSession と同設計、TEMPLE*.MIF +
        # owner_kind="temple" で active)。
        self._temple_session: TempleSession = TempleSession()
        # 武具店 / 魔術師ギルド会話セッション (TempleSession と同設計、
        # owner_kind="equipment" / "mages_guild" で active)。完全分離:
        # 各施設の latch は自施設の owner_kind でのみ start/継続し他施設に干渉しない。
        self._equipment_session: EquipmentSession = EquipmentSession()
        self._mages_guild_session: MagesGuildSession = MagesGuildSession()
        # 交渉ダイアログは module 化 (normal_play/negotiation_module.py)。
        # 旧 NegotiationSession は session_manager 排他で tavern_session/
        # temple_session active 中に try_start が呼ばれず描画不能だったため、
        # L4 module として並列動作するよう移行 (L3/L4 分離)。
        # 登録順 = 優先順位。施設会話 (Temple/Tavern) を先に試して相互排他を
        # 担保する。
        self._session_manager.register(self._temple_session)
        self._session_manager.register(self._equipment_session)
        self._session_manager.register(self._mages_guild_session)
        self._session_manager.register(self._tavern_session)
        self._session_manager.register(self._npc_chat_session)
        # 直前 poll の tavern / temple active 状態 (= 新規 on の検出用)
        self._tavern_active_prev: bool = False
        self._temple_active_prev: bool = False
        # 武具店 / 魔術師ギルドの直前 poll active 状態
        self._equipment_active_prev: bool = False
        self._mages_guild_active_prev: bool = False
        # 神殿 owner キーの前 poll 値 (= IMG 遷移時の reset 判定用)
        self._temple_menu_key_prev: tuple | None = None
        self._temple_active_template_key_prev: tuple | None = None
        self._temple_negot_key_prev: tuple | None = None
        # 神殿セッションの直前 IMG (= YESNO.IMG → MENU_RT.IMG 遷移検出)
        self._temple_last_img_prev: str = ""
        # ロードデータ選択中 / ロード中状態
        # LOADSAVE.IMG 表示中 = ロードデータ選択中（判定抑止なし、画面認識状態は
        #   「ロードデータ選択」を表示）
        # LOADSAVE.IMG → OP.IMG 以外への遷移 = ロード中状態（判定抑止あり、画面認識
        #   状態は「ロード中」を表示）
        # LOADSAVE.IMG → OP.IMG への遷移 = キャンセル（両状態を解除）
        # 両状態は相互排他で同時に True にならない。
        self._loading_data_select_active: bool   = False
        self._loading_state_active: bool         = False
        self._loading_loadsave_seen_prev: bool   = False
        self._loading_state_post_remaining: int  = 0

        # chargen フェーズ状態（0x2E 固定判定を撤去、method_state 相対値に移行）
        self._chargen_state_prev: int      = 0
        # chargen 設問シーケンス番号（1-10、変化時に翻訳表示）
        self._chargen_q_seq_prev: int      = 0
        # 名前入力画面中フラグ（NPC ダイアログ上書き防止用）
        self._in_chargen_name: bool        = False
        # chargen_state 遷移検出（複数回再現確認済み）
        # 観測根拠:
        #   - chargen_state は画面遷移時に〜1秒 cycle し、画面安定時は stable
        #   - ProvinceConfirmed1-4 (完了/種族/助言/GoYeNow) の各 stable 値は +28 ずつ
        # 「2 ポーリング連続同値で安定」を確認してから記録/発火する（cycle中の transient 値を回避）
        self._chargen_state_streak: int        = 0   # 同値連続ポーリング数
        self._chargen_in_advice: bool          = False  # クラスアドバイス画面中
        self._chargen_advice_state: int | None = None
        self._chargen_goyenow_displayed: bool  = False
        self._chargen_goyenow_state: int | None = None  # GoYeNow 発火時の実測 chargen_state
        self._chargen_10q_displayed: bool      = False  # 10Q intro 一度発火フラグ
        # method 画面（_CHARGEN_ NPC）の安定 chargen_state を保持。10Q intro は
        # method_state + 0x1C で発火する仮説。
        # 過去の 0x2E 固定判定は run ごとに値が異なる（A1=0xA0, B1=0xEE 観測）
        # ため破綻していた。
        self._chargen_method_state: int | None = None
        # Distribute Points ダイアログ（ChooseAttributes 画面開始時）の発火フラグ。
        # NPC バッファには載らないため chargen_state の +28 規則
        # (advice_state + 0x1C * 2) で検出する。
        self._chargen_distribute_displayed: bool = False
        # Appearance 画面検出用。
        # _CHARGEN_CHOOSE_ATTRIBUTES_ NPC 発火後、chargen_state が別の安定値に変化した
        # タイミングで発火する（外観選択テキストは NPC バッファに書かれないため）。
        self._chargen_choose_attrs_displayed: bool = False
        self._chargen_choose_attrs_state_val: int | None = None
        self._chargen_appearance_displayed: bool = False
        # chargen 完了フラグ（anchor+4760）: 0→1 の遷移でオープニングを発火する。
        # memdump diff (2026-05-04) で 2 回再現確認済み。
        self._chargen_done_prev: int = 0
        self._chargen_opening_displayed: bool = False
        # cinematic テキストは chargen_done=1 の数秒後に書き込まれるため、
        # 0→1 検出時にリトライカウンタを起動して以降の poll で再試行する。
        self._chargen_opening_retry: int = 0
        # 直前 push したテキスト（同一の場合 push 省略 = 翻訳タブをチカつかせない）
        self._chargen_opening_text_prev: str = ""
        # ダンジョン突入 (live_mif=start.mif) で cinematic を 1 度だけクリアする
        # ためのフラグ。ダンジョンを離れたらリセットされる。
        self._dungeon_entry_cleared: bool = False
        # GoYeNow scan の予算カウンタ。
        # ClassAdvice 検出時に 60（30 秒分）にセット、各 poll で 1 消費。
        # 0 になると scan を停止し、後続フェーズで誤発火するのを防ぐ。
        # 旧来の「5 秒間隔で永久に scan_string」を撤廃。
        self._goyenow_scan_budget: int = 0
        # advice_state capture 後の経過 poll カウンタ。
        # capture 直後の同 poll で hint addr direct が誤発火するバグ
        # 対策として、capture 後 N poll 経過するまで fallback ブロックを保留する。
        # -1 = 未 capture、0 以上 = capture 後の poll 数。
        # advice_state capture 時に 0 にセット、各 poll で increment。
        self._advice_capture_age: int = -1
        # method 画面 (_CHARGEN_) → 10Q intro の窓だけ True。
        # 任意の他 chargen 進行（NPC マッチ・class list 活性化）でクリアされる。
        # これにより Select 経路の name 入力画面で 0x2E が安定しても 10Q intro が
        # 誤発火しなくなる。
        self._chargen_method_window: bool      = False
        # 出身地（種族）選択画面表示中フラグ。
        # _CHARGEN_PROVINCE_ 検出時に True、_CHARGEN_PROVINCE_CONFIRM_ Yes 確定後の
        # 次 chargen NPC（_CHARGEN_RACE_* 等）検出時に False。
        # race_list panel 表示判定に使用。
        self._chargen_race_select_displayed: bool = False
        # 新設フラグ群:
        # それぞれ対応する chargen NPC 検出時に True、後続 NPC 検出時に False。
        self._chargen_class_accept_displayed: bool = False    # _CHARGEN_RESULT_*
        self._chargen_race_desc_displayed: bool    = False    # _CHARGEN_RACE_*
        self._chargen_sex_select_displayed: bool   = False    # "Choose thy gender"
        self._chargen_complete_displayed: bool     = False    # "Then thou wilt be known as"
        # 翻訳キャッシュ:
        # chargen subscreen 中は前回 push を覚えて、空文字 push を無視する。
        self._last_chargen_subscreen: str | None   = None
        # クラス一覧画面 (Choose thy class) のパネル表示中フラグ。
        # 検出は NPC バッファ内容（クラス名そのものが書き込まれる）で行う。
        self._chargen_class_list_active: bool  = False
        # chargen 中かどうか。位置・座標などのゲーム状態行を隠すために使う。
        self._is_in_chargen: bool              = False
        # AttributesPanel 表示用に chargen 進行で判明した種族・クラス名（日本語）
        self._chargen_race_ja: str | None      = None
        self._chargen_class_ja: str | None     = None
        self._chargen_class_en: str | None     = None

        # chargen 後半の状態管理 latch (能力値配分以降の責務分離設計)
        #
        # ステータスタブ表示の単調 latch。distribute / choose_attrs /
        # complete / appearance / opening 到達で True。top-level 離脱 /
        # 新規 chargen reset でのみ False。個別フラグの OR 判定だと
        # COMPLETE → 次 NPC で一時的にフラグがクリアされる経路で
        # チラツキが発生するため latch 化する。
        self._chargen_status_display_armed: bool = False

        # ChooseAttributes phase の chargen_state anchor 値。初回進入時に
        # だけ stable state を保持し、BONUS_REMAINING / COMPLETE /
        # CHOOSE_ATTRIBUTES 再表示で再キャプチャ・破棄しない。Appearance /
        # opening / reset で破棄する。Appearance 検出 (`anchor + 0x1C`) は
        # modal で消える既存 `_chargen_choose_attrs_state_val` の代わりに
        # 本 anchor を参照する。
        self._chargen_attrs_state_anchor: int | None = None
        self._chargen_attrs_phase_seen: bool         = False

        # 能力値配分中の modal (BONUS_REMAINING / Save/Reroll 確認 等) 検出。
        # 毎 poll でメモリから再評価する (sticky latch にしない)。
        # CHOOSE_ATTRIBUTES 再表示 (modal 閉) / appearance / opening / reset
        # でクリア。renderer の panel_mode 判定に使う。
        self._chargen_attrs_modal_active: bool = False
        # modal の種別。None | "bonus_required" | "stat_save_confirm"
        # 診断ログでの判別と将来の専用処理用。
        self._chargen_attrs_modal_kind: str | None = None
        # 診断ログ用: 直前 poll の attrs_phase 観測値 hash (変化時のみ log 出力)
        self._chargen_attrs_phase_log_prev: tuple | None = None
        # キャラクター作成中の説明ダイアログ表示中フラグ。
        # 翻訳パネル表示時も翻訳タブ側に説明翻訳を表示するため、renderer の
        # panel_mode 優先判断に使う。
        # 値: None | "distribute" (能力値配分説明) | "appearance" (外見選択説明)
        self._chargen_explanation_active: str | None = None
        # DistributePoints 説明の閉幕検出用スナップショット (汎用バッファ、レガシー)。
        # 現行は dlg_flag 遷移ベースで閉幕判定するため未使用 (互換のため保持)。
        self._chargen_explanation_distribute_npc_snapshot: bytes | None = None
        # DistributePoints 説明 popup の dlg_flag 開幕観測 latch。
        # 説明 fire 後 dlg_flag=0x01 を 1 回以上観測してから 0x00 へ戻った時点で閉幕。
        self._chargen_explanation_distribute_dlg_seen_open: bool = False
        # GoYeNow → DistributePoints 安全措置用: GoYeNow 検出時の汎用バッファ
        # 内容スナップショット。後の poll で異なる内容に変化したら
        # DistributePoints 進入とみなす。
        self._chargen_goyenow_npc_snapshot: bytes | None = None
        # GoYeNow → DistributePoints 検出 (ダイアログ開幕ゲート版) 用:
        # goyenow サブ状態中の +0xB7C4 直前値。0x00→非0 のエッジで発火する。
        self._chargen_goyenow_b7c4_prev: int | None = None

        self._theme_mode = settings.get("theme", "dark")

        # top-level 状態: "pregame" | "chargen" | "normal-play"
        # on_img_name_changed() / _poll() の遷移検出で明示的に切り替える。
        self._top_level_state: str = "pregame"
        # 最後に検出した chargen subscreen ID（subscreen 間の隙間 fallback 用）
        self._chargen_subscreen_last: str | None = None
        # _handle_chargen_npc_dialog の runaway 防止 cache。
        # 同一 NPC entry の連続検出時に _update_translate_tab を呼び直さず、
        # chargen 状態フラグの全リセットを抑止する。
        self._last_chargen_entry_key: tuple | None = None
        # クラス一覧画面で同一クラスの連続活性化を抑止する cache。
        # Arena 側 NPC バッファが同じクラス名を保持し続けた場合に、
        # _activate_class_list_for_class の毎 poll 呼出でユーザーの
        # Assist パネル操作が上書きされる問題への対策。
        self._last_class_list_activation: str | None = None
        # pregame 中に LOADSAVE.IMG を経由したか（pregame+mif ガード用）
        # True のときのみ pregame → normal-play（MIF 出現）遷移を許可する。
        # New Game（PARCH.CIF 直行）では False のまま → 誤遷移を防ぐ。
        self._pregame_loadsave_seen: bool = False

        # レベルアップ全工程の状態追跡
        # +0x1AA = Level - 1, +0x129C = BONUS PTS（status 画面のみ有意）, +0x5AD = Experience
        self._player_level_prev:    int | None = None  # 前回 poll の Level
        self._player_bonus_prev:    int | None = None  # 前回 poll の BONUS PTS（status 中）
        self._level_up_active:      bool       = False # レベルアップ進行中（ダイアログ→ボーナス完了）
        self._level_up_from:        int | None = None  # レベルアップ前 Level
        self._level_up_to:          int | None = None  # レベルアップ後 Level
        self._level_up_saw_bonus:   bool       = False # レベルアップ中にボーナス画面へ入ったか
        # ボーナス割り振り画面の保持フラグ。CHARSTAT.IMG 検出で突入し、
        # 画面を閉じる (flag_status==0) まで保持する（内部の UPDOWN/MRSHIRT 循環で
        # 他のキャラクター画面へ倒れないようにする単一所有保持）。
        self._bonus_screen_hold:    bool       = False
        # キャラクター画面 (ステータス画面) を開いた直後の page 過渡吸収用。
        # 開く瞬間に紙人形 img が equipment と一瞬検出されるのを抑える。
        self._char_screen_flag_prev: int        = 0
        self._char_screen_settling:  bool       = False
        self._char_screen_budget:    int        = 0
        # 魔法画面 (spellbook family) の 一覧/詳細 判別用。突入時 (=一覧) の
        # SPELL_VIEW 値を base に捕捉し、base からの差で詳細を判別する。
        self._spell_screen_active:   bool       = False
        self._spell_view_base:       int | None = None

        self._build_ui()
        self._restore_geometry()
        self._apply_theme()

        # スクリーンショット時のシャッターSE（短い WAV を winsound で非同期再生）。
        # Qt の QSoundEffect は SAPI5 読み上げと同時再生で native クラッシュするため
        # 使わない（winsound は SAPI5 と共存可）。WAV バイト列を保持し再生時に渡す。
        # 設定で 5 つのフィルムカメラ風候補から選択 + ON/OFF・音量変更可。
        # ファイル不在等で失敗しても機能停止しない。
        self._shutter_se_wav = None
        self._shutter_se_kind = None
        self._reload_shutter_se()

        if settings.get("always_on_top", False):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        from assist_window_ui import build_ui
        build_ui(self)

    # ------------------------------------------------------------------
    # 設定
    # ------------------------------------------------------------------

    def _open_settings(self):
        dlg = _SettingsDialog(self, self._theme_mode, self._layout_translate_panel)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        settings.set_val("save_dir",               dlg.game_dir)
        settings.set_val("backup_dir",             dlg.backup_dir)
        settings.set_val("capture_dir",            dlg.capture_dir)
        settings.set_val("capture_delete_confirm", dlg.delete_confirm)
        settings.set_val("capture_se_enabled",     dlg.capture_se_enabled)
        settings.set_val("capture_se_volume",      dlg.capture_se_volume)
        settings.set_val("capture_se_kind",        dlg.capture_se_kind)
        # 次回 _capture 時に新しい WAV をロードする
        self._reload_shutter_se()

        settings.set_val("equipment_mark_equipped",     dlg.equipment_mark_equipped)
        settings.set_val("equipment_mark_equippable",   dlg.equipment_mark_equippable)
        settings.set_val("equipment_mark_unequippable", dlg.equipment_mark_unequippable)

        old_aot = settings.get("always_on_top", False)
        new_aot = dlg.always_on_top
        settings.set_val("always_on_top", new_aot)
        if new_aot != old_aot:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, new_aot)
            self.show()

        if dlg.theme != self._theme_mode:
            self._set_theme(dlg.theme)

        # 表示言語: 変更時のみ保存し、再起動で全体へ反映する旨を案内する。
        # （即時反映は全パネルの language_changed 購読対応後に切替予定。
        #   signal 配線は i18n コア側に用意済みのため後日無改修で拡張可能。）
        if dlg.ui_language != settings.get("ui_language", ""):
            settings.set_val("ui_language", dlg.ui_language)
            QMessageBox.information(
                self,
                i18n.tr("settings.language_restart_title"),
                i18n.tr("settings.language_restart_msg"))

        # 翻訳パネルフォント設定を保存
        settings.set_val("keep_trigger_on_panel", dlg.keep_trigger_on_panel)

        settings.set_val("panel_translate_font_family_ja", dlg.font_family_ja)
        settings.set_val("panel_translate_font_size_ja",   dlg.font_size_ja)
        settings.set_val("panel_translate_font_family_en", dlg.font_family_en)
        settings.set_val("panel_translate_font_size_en",   dlg.font_size_en)
        settings.set_val("panel_translate_font_sync",      dlg.font_sync)
        if self._layout_translate_panel is not None:
            self._layout_translate_panel.apply_font_settings()

        # レイアウト設定
        # レイアウト関連が未変更のときは set_track_mode / set_layout_*
        # を呼ばない (LayoutManager が DOSBox/Assist を再配置するのを抑止)。
        if dlg.layout_dirty:
            try:
                self._layout.set_track_mode(TrackMode(dlg.layout_track_mode))
            except ValueError:
                pass
            try:
                self._layout.set_layout_corner(LayoutCorner(dlg.layout_corner))
            except ValueError:
                pass
            try:
                self._layout.set_layout_form(LayoutForm(dlg.layout_form))
            except ValueError:
                pass
            settings.set_val("layout_size_w", dlg.layout_size_w)
            settings.set_val("layout_size_h", dlg.layout_size_h)
            old_dos_top = settings.get("dosbox_always_on_top", False)
            if dlg.dosbox_always_on_top != old_dos_top:
                self._layout.toggle_dosbox_topmost(dlg.dosbox_always_on_top)

        # ポーリング間隔
        new_poll_ms = max(100, min(5000, dlg.poll_interval_ms))
        settings.set_val("poll_interval_ms", new_poll_ms)
        if new_poll_ms != self._poll_ms:
            self._poll_ms = new_poll_ms
            self._poll_timer.setInterval(self._poll_ms)

        # チート設定 (UI は設定ダイアログのチートタブへ移動)
        # TabStatus と TabTranslate の AttributesPanel は別インスタンスで、
        #       両方に反映しないとステータス画面のスピン編集ロックが解除されない
        settings.set_val("cheat_enabled", dlg.cheat_enabled)
        settings.set_val("cheat_status_change", dlg.cheat_status_change)
        settings.set_val("cheat_reveal_map", dlg.cheat_reveal_map)
        settings.set_val("cheat_health_max", dlg.cheat_health_max)
        settings.set_val("cheat_fatigue_max", dlg.cheat_fatigue_max)
        settings.set_val("cheat_spell_max", dlg.cheat_spell_max)
        try:
            # 共有 AttributesPanel への反映 (翻訳 / ステータス両タブに作用)。
            self._tab_status.apply_cheat_settings()
        except AttributeError:
            pass

        # マップタブ表示設定
        settings.set_val("map_wall_line_of_sight", dlg.map_wall_line_of_sight)
        settings.set_val("map_show_unexplored_floor",
                         dlg.map_show_unexplored_floor)
        settings.set_val("map_center_on_player", dlg.map_center_on_player)
        settings.set_val("map_show_grid", dlg.map_show_grid)
        settings.set_val("map_show_chunk_grid", dlg.map_show_chunk_grid)
        settings.set_val("map_show_chunk_coords", dlg.map_show_chunk_coords)
        settings.set_val("map_show_recenter_lines",
                         dlg.map_show_recenter_lines)
        settings.set_val("map_chunk_coord_font_size",
                         dlg.map_chunk_coord_font_size)
        settings.set_val("map_extended_display", dlg.map_extended_display)
        settings.set_val("wild_distinguish_road", dlg.wild_distinguish_road)
        settings.set_val("wild_show_edge", dlg.wild_show_edge)
        settings.set_val("wild_distinguish_edge", dlg.wild_distinguish_edge)
        settings.set_val("wild_show_crops", dlg.wild_show_crops)
        settings.set_val("wild_show_all_entrances",
                         dlg.wild_show_all_entrances)
        settings.set_val("wild_show_static_flats",
                         dlg.wild_show_static_flats)
        settings.set_val("translate_fallback_screen",
                         dlg.translate_fallback_screen)
        try:
            self._tab_map.apply_settings()
        except AttributeError:
            pass
        try:
            self._tab_translate.apply_map_settings()
        except AttributeError:
            pass

        # 接続バー表示制御
        settings.set_val("show_recognition_screen", dlg.show_recognition_screen)
        settings.set_val("show_img_info", dlg.show_img_info)
        settings.set_val("show_version", dlg.show_version)
        self._apply_view_settings()

        # 読み上げ(TTS) 設定 (Phase1)
        settings.set_val("tts_enabled", dlg.tts_enabled)
        settings.set_val("tts_engine", dlg.tts_engine)
        settings.set_val("tts_voice", dlg.tts_voice)
        settings.set_val("tts_vv_speaker", dlg.tts_vv_speaker)
        settings.set_val("tts_rate", dlg.tts_rate)
        settings.set_val("tts_volume", dlg.tts_volume)
        settings.set_val("tts_interrupt", dlg.tts_interrupt)
        settings.set_val("tts_target_situation", dlg.tts_target_situation)
        settings.set_val("tts_target_conversation",
                         dlg.tts_target_conversation)
        settings.set_val("tts_speaker_icon", dlg.tts_speaker_icon)
        settings.set_val("log_show_original", dlg.log_show_original)
        settings.set_val("log_show_datetime", dlg.log_show_datetime)
        _fmt = dlg.log_datetime_format
        if _fmt:
            settings.set_val("log_datetime_format", _fmt)
        settings.set_val("tts_name_reading", dlg.tts_name_reading)
        settings.set_val("log_max_entries", dlg.log_max_entries)
        # 保存上限の変更を即時反映（両層を新上限へ切り詰め）。
        try:
            self._log_store.set_max_entries(dlg.log_max_entries)
        except Exception:  # noqa: BLE001
            pass
        # 設定変更をログタブへ即反映（日時/原文表示の切替）。
        try:
            if getattr(self, "_tab_log", None) is not None:
                self._tab_log.refresh()
        except Exception:  # noqa: BLE001
            pass
        self._apply_tts_settings()

        # 翻訳タブ拡張設定 (ハードコード解消)
        settings.set_val("translate_tab_emulate_panel_hidden",
                         dlg.translate_tab_emulate_panel_hidden)

        # 各タブに変更通知
        self._tab_save.on_settings_changed()
        self._tab_capture.set_cap_dir(self._get_cap_dir())
        # arena.conf path 変更はダイアログ側で reload 済み。保存先パスのみ反映。
        settings.set_val("dosbox_conf_path", dlg.dosbox_conf_path)

    def _toggle_always_on_top(self, checked: bool):
        settings.set_val("always_on_top", checked)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    # ------------------------------------------------------------------
    # 接続
    # ------------------------------------------------------------------

    def _on_connect_clicked(self):
        if self._analyzer is not None:
            self._disconnect()
        else:
            self._start_connect()

    def _start_connect(self):
        self._conn_btn.setEnabled(False)
        self._status_lbl.setText(i18n.tr("status.loading"))
        self._sb.showMessage(i18n.tr("status.loading"))
        self._worker = _ConnectWorker(self)
        self._worker.done.connect(self._on_connect_done)
        self._worker.failed.connect(self._on_connect_failed)
        self._worker.start()

    def _on_connect_done(self, pid: int, anchor: int):
        from controllers.connect_flow_controller import on_connect_done
        on_connect_done(self, pid, anchor)

    def _on_connect_failed(self, msg: str):
        self._conn_btn.setEnabled(True)
        self._conn_btn.setText(i18n.tr("connection.connect"))
        self._status_lbl.setText(i18n.tr("connection.status_disconnected"))
        self._sb.showMessage(f"{i18n.tr('common.error')}: {msg}")

    def _disconnect(self):
        self._poll_timer.stop()
        if self._analyzer:
            try:
                self._analyzer.detach()
            except Exception:
                pass
            self._analyzer = None
        self._anchor = 0
        self._conn_btn.setText(i18n.tr("connection.connect"))
        self._status_lbl.setText(i18n.tr("connection.status_disconnected"))
        self._anchor_lbl.setText("")
        self._img_name_lbl.setText("")
        self._img_name_prev = ""
        self._screen_id_prev = None
        self._screen_id_pending = None
        self._screen_id_stable_count = 0
        self._spell_detail_marker = None  # spell_detail 内の呪文切替検出用
        self._menu_active_prev = 0xFFFF   # system_menu 連続観測用
        self._flag_detail_skip_n = 0      # spell_detail bounce 保護カウンタ
        self._spell_detail_text_ready = True  # effect text 書込み完了フラグ
        self._spell_detail_text_marker = None  # effect text buffer 変化検出用
        self._equipment_marker = None     # 装備変化検出用
        try:
            from template_parser import reset_cache
            reset_cache()
        except (ImportError, Exception):
            pass
        self._newgame_layout_pushed = False
        self._startup_layout_pushed = False
        self._tab_translate.set_connected(False)
        # 共有 AttributesPanel をクリア (翻訳 / ステータス両用)。
        self._tab_status.clear_memory_target()
        try:
            self._tab_translate.appearance_faces_panel().clear_memory_target()
        except AttributeError:
            pass
        if self._layout_translate_panel is not None:
            self._layout_translate_panel.set_connected(False)
        # 切断時はクラス一覧モードと chargen UI 状態を解除する
        self._is_in_chargen = False
        self._set_class_list_panel_mode(False)
        self._set_chargen_ui_state(False)
        self._mif_matcher = None
        self._top_level_state = "pregame"
        # 翻訳タブへの top_level 同期は廃止 (fallback 床は flush の
        # 単一権威 resolver が _top_level_state を直接読む)。
        self._chargen_subscreen_last = None
        self._pregame_loadsave_seen = False
        self._layout_mgr.set_dosbox_pid(0)
        self._sb.showMessage(i18n.tr("status.ready"))

    # ------------------------------------------------------------------
    # top-level 状態管理
    # ------------------------------------------------------------------

    def _transition_top_level(self, new_state: str, reason: str) -> None:
        """top-level 状態を遷移させる。

        遷移時は INFO ログを出力する。同一状態への遷移は無視する。
        """
        if self._top_level_state == new_state:
            return
        _log.info("top_level: %s → %s (reason: %s)",
                  self._top_level_state, new_state, reason)
        self._top_level_state = new_state
        # 翻訳タブへの top_level 同期は廃止 (fallback 床は flush の
        # 単一権威 resolver が window._top_level_state を直接読む)。
        # P0-1: load_screen owner の解放は UiRouter 経由で行う（共通層が
        # panel_owner を直書きしない＝分離原則）。release_if_owner は現 owner が
        # "load_screen" の場合のみ解放する（旧直書きの条件と等価）。
        if new_state == "normal-play":
            # 通常プレイ突入時の床落ちを funnel へ提案する (旧
            # tab.set_top_level_state→_maybe_apply_fallback の rogue 軸を置換)。
            # mode=translate を提案→単一権威 resolver が map/status へ床落ち。
            # 前景 list/screen 提案が同 poll にあればそちらが優先される。
            try:
                self._ui_router.set_panel_mode("translate", reason="enter_normal_play")
            except (AttributeError, RuntimeError):
                pass
            try:
                self._ui_router.release_if_owner("load_screen")
            except (AttributeError, RuntimeError):
                pass
        # chargen → normal-play 遷移時は last subscreen をリセット
        if new_state == "normal-play":
            self._chargen_subscreen_last = None
            try:
                self._save_play_class_id_mapping(
                    getattr(self, "_chargen_class_en", None))
            except AttributeError:
                pass
            try:
                self._reset_map_marker_for_normal_play_entry()
            except AttributeError:
                pass
        # 能力値配分以降の latch は chargen を離脱したらクリア
        if new_state != "chargen":
            self._chargen_status_display_armed = False
            self._chargen_attrs_state_anchor = None
            self._chargen_attrs_phase_seen = False
            self._chargen_attrs_modal_active = False
            self._chargen_attrs_modal_kind = None
            self._chargen_attrs_phase_log_prev = None
            self._chargen_explanation_active = None
            self._chargen_explanation_distribute_npc_snapshot = None
            self._chargen_explanation_distribute_dlg_seen_open = False
            self._chargen_goyenow_npc_snapshot = None
            self._chargen_goyenow_b7c4_prev = None
            # ステータス表示の更新凍結（chargen の外見/能力値確定中のゴミ値
            # 保護）も chargen 専用ライフサイクル。chargen 検出 poll は
            # top-level 離脱で no-op するため凍結を自力で解除できない。
            # latch 群と同じこの単一テアダウン地点で解除し、凍結が通常プレイへ
            # stale 持ち越しされ経験値等が古い値で固着する事象を防ぐ。
            try:
                if self._tab_status is not None:
                    self._tab_status.set_freeze_updates(False)
            except (AttributeError, RuntimeError):
                pass
        # AttributesPanel の chargen モードを同期
        self._sync_attributes_chargen_mode()
        # ステータス / マップ / ジャーナル表示の有効/無効を同期
        self._apply_display_active_for_state()

    def _update_attr_panel_placement(self) -> None:
        """共有 AttributesPanel をアクティブなタブ側へ付け替える。

        翻訳タブが choose_attributes / fallback_status を表示中のときだけ
        翻訳タブへ、それ以外はステータスタブへマウントする。1 インスタンスを
        両タブで共有するための reparent (実体 2 つの二重管理を解消)。
        """
        try:
            want_translate = (
                self._tabs.currentWidget() is self._tab_translate
                and self._tab_translate.panel_mode()
                in ("choose_attributes", "fallback_status")
            )
            if want_translate:
                self._tab_translate.mount_attributes_panel()
            else:
                self._tab_status.mount_attributes_panel()
        except (AttributeError, RuntimeError):
            pass

    def _apply_display_active_for_state(self) -> None:
        """top-level 状態に応じてステータス/マップ/ジャーナルの有効/無効を設定する。

        - タイトル中 (pregame): 全てクリア (前回プレイの残置防止)
        - キャラクター作成中 (chargen): マップ/ジャーナルはクリアのまま、
          ステータスは能力値配分画面 (DistributePoints) 以降で有効化
        - 通常プレイ中 (normal-play): 全て有効
        """
        state = self._top_level_state
        if state == "normal-play":
            status_active = True
            map_active = True
            journal_active = True
        elif state == "chargen":
            # ステータスは能力値配分以降で有効。個別フラグの OR 判定だと
            # COMPLETE → 次 NPC でフラグが一時 False になりチラツキが起きる
            # ため、単調 latch `_chargen_status_display_armed` を参照する。
            # latch は distribute / choose_attrs / complete / appearance /
            # opening 到達で True、top-level 離脱 / reset で False。
            status_active = self._chargen_status_display_armed
            map_active = False
            journal_active = False
        else:  # pregame
            status_active = False
            map_active = False
            journal_active = False
        try:
            self._tab_status.set_display_active(status_active)
        except AttributeError:
            pass
        try:
            self._tab_map.set_display_active(map_active)
        except AttributeError:
            pass
        try:
            self._tab_journal.set_display_active(journal_active)
        except AttributeError:
            pass

    def _reset_map_marker_for_normal_play_entry(self) -> None:
        """通常プレイ突入時に前回 run の player marker seed だけ切る。

        探索状態は map session の責務として保持する。ここで reset_progress()
        すると、B -> C 突入直後に地図そのものが消えるため触らない。
        """
        self._map_rt_x_last = None
        self._map_rt_z_last = None
        self._map_angle_last = None

    def _sync_attributes_chargen_mode(self) -> None:
        """AttributesPanel (status タブ / translate タブ) の chargen モードを同期する。"""
        mode = (self._top_level_state == "chargen")
        try:
            # 共有 AttributesPanel への反映 (翻訳 / ステータス両タブに作用)。
            self._tab_status.set_chargen_mode(mode)
        except AttributeError:
            pass

    def _detect_top_level_at_connect(self) -> None:
        from controllers.connect_flow_controller import (
            detect_top_level_at_connect)
        detect_top_level_at_connect(self)

    # ------------------------------------------------------------------
    # ポーリング
    # ------------------------------------------------------------------

    # フリーズ調査用: 1 poll が重いと判断する閾値 (ms)。これを超えた poll だけ
    # 既定 (WARNING) でも内訳を出力し、通常の軽い poll では出力しない (= 過剰
    # ログ回避)。詳細を全 poll で追う場合は環境変数でログを INFO 以上にする。
    _POLL_SLOW_MS = 50.0

    def _poll(self):
        # poll loop の本体は controllers/poll_controller.py に分離。
        _t0 = time.perf_counter()
        self._poll_ctrl.poll()
        _elapsed_ms = (time.perf_counter() - _t0) * 1000.0
        # poll timing は毎 poll 発生する常時大量の診断 → DEBUG (既定では出さない)。
        # 詳細が要る時だけ環境変数で DEBUG に下げて出力する。
        phases = getattr(self, "_poll_phase_times", None) or {}
        checkpoints = getattr(self, "_poll_checkpoints", None) or []
        if _log.isEnabledFor(logging.DEBUG):
            breakdown = " ".join(
                f"{name}={ms:.1f}ms" for name, ms in phases.items())
            # チェックポイントは poll 開始からの累積 (ms)。隣接差分が区間所要。
            ckline = " ".join(
                f"{name}@{cum:.1f}" for name, cum in checkpoints)
            _log.debug(
                "poll timing: total=%.1fms%s%s",
                _elapsed_ms,
                f" [{breakdown}]" if breakdown else "",
                f" ck[{ckline}]" if ckline else "")

    def _update_translate_tab(self, entry: dict) -> None:
        from controllers.translation_update_controller import (
            update_translate_tab)
        update_translate_tab(self, entry)

    def _set_class_list_panel_mode(self, active: bool) -> None:
        """翻訳タブのモードを class_list / translate に切り替える。

        レイアウトパネル側はゲームメッセージ翻訳専用なのでモード切替しない。

        class_list アクティブ時に _CHARGEN_CHOOSE_CLASS_ の翻訳を
        layout_panel_translate へ push し、画面の "Choose thy class..." を表示する。
        タブは class_list panel UI のままで、底辺の翻訳パネルが画面テキスト翻訳を表示。
        """
        mode = "class_list" if active else "translate"
        try:
            self._ui_router.set_panel_mode(mode)
        except AttributeError:
            pass
        self._chargen_class_list_active = active
        # クラス一覧アクティブ時は "Choose thy class..." の翻訳を翻訳パネルへ push する。
        # 旧実装は `_layout_translate_panel is not None` を条件にしていたが、埋め込み
        # レイアウト等で同参照が None の構成では push がスキップされ、前画面（クラス
        # 選択方法）の訳が残留する不具合があった。実 push は UiRouter 経由で
        # アクティブなパネルへ届くため、参照の有無に依存させず active なら常に push する。
        if active:
            try:
                import inf_text_lookup as itl_local
                entry = itl_local.lookup("_CHARGEN_CHOOSE_CLASS_", 0)
                if entry is not None:
                    p_orig = itl_local.get_text_panel(entry)
                    p_basic = itl_local.get_translation(entry) or ""
                    self._ui_router.update_panel_translation(
                        p_orig, p_basic)
            except (ImportError, AttributeError) as exc:
                _log.debug("class_list panel translate push skipped: %s", exc)

    def _activate_choose_attributes_panel(self, *, priority: int = 0) -> None:
        """翻訳タブを ChooseAttributes パネルに切替える。

        Distribute Points ダイアログ後の能力値割り振り画面で使う。
        ステータスタブと同じ AttributesPanel を翻訳タブ内に表示する
        （クラス一覧パネルと同じ要領）。

        chargen renderer から呼ぶ際は priority を渡し、background
        翻訳 push に勝つ高優先で提案する (イベント駆動の呼出は既定 0)。
        """
        # クラス一覧モードを抜けてから choose_attributes へ
        if self._chargen_class_list_active:
            self._set_class_list_panel_mode(False)
        try:
            self._ui_router.set_panel_mode(
                "choose_attributes", priority=priority)
        except AttributeError:
            pass
        self._set_chargen_ui_state(True)
        self._sync_attributes_race_class()

    def _sync_attributes_race_class(self) -> None:
        """chargen 進行で得た race / class 表示名を AttributesPanel 群に反映。"""
        try:
            # 共有 AttributesPanel への反映 (翻訳 / ステータス両タブに作用)。
            self._tab_status.set_race_class(self._chargen_race_ja, self._chargen_class_ja)
        except AttributeError:
            pass

    def _track_chargen_race_class(self, inf_key: str) -> None:
        """chargen NPC エントリの inf キーから race / class 表示名を抽出して保持。

        合わせて memory の +0x217 (class id) と canonical 英名のマッピングを
        settings.arena_class_id_map に蓄積する（次回起動時の表示復帰用）。
        """
        if inf_key.startswith("_CHARGEN_RACE_"):
            race_key = inf_key[len("_CHARGEN_RACE_"):].rstrip("_")
            ja = _CHARGEN_RACE_INF_TO_JA.get(race_key)
            if ja:
                self._chargen_race_ja = ja
                self._sync_attributes_race_class()
        elif inf_key.startswith("_CHARGEN_CLASS_ADVICE_") or inf_key.startswith("_CHARGEN_RESULT_"):
            prefix = "_CHARGEN_CLASS_ADVICE_" if inf_key.startswith("_CHARGEN_CLASS_ADVICE_") else "_CHARGEN_RESULT_"
            cls_key = inf_key[len(prefix):].rstrip("_")
            cls_en = cls_key.replace("_", " ").title().replace(" ", "")
            self._chargen_class_en = cls_en
            ja = _CHARGEN_CLASS_JA.get(cls_en, cls_en)
            if ja:
                self._chargen_class_ja = ja
                self._sync_attributes_race_class()
            self._save_class_id_mapping(cls_en)

    def _save_class_id_mapping(self, cls_en: str) -> None:
        """memory の +0x217 を読み、class id → 英名 のマッピングを settings に保存。

        chargen を進めるたびに自動で蓄積されるため、次回 Assist 再起動時に
        +0x217 から英名→日本語表記への解決ができるようになる。
        """
        if self._analyzer is None or not cls_en:
            return
        try:
            cls_id = self._analyzer.read_bytes(self._anchor + 0x217, 1)[0]
        except OSError:
            return
        mapping = dict(settings.get("arena_class_id_map", {}) or {})
        if mapping.get(str(cls_id)) != cls_en:
            mapping[str(cls_id)] = cls_en
            settings.set_val("arena_class_id_map", mapping)
            _log.info("chargen: arena_class_id_map updated: %d → %s",
                      cls_id, cls_en)

    def _save_play_class_id_mapping(self, cls_en: str | None) -> None:
        """通常プレイ時 class id (+0x1A9) と chargen で確定したクラス名を対応付ける。"""
        if not cls_en and getattr(self, "_chargen_class_ja", None):
            for en_name, ja_name in _CHARGEN_CLASS_JA.items():
                if ja_name == self._chargen_class_ja:
                    cls_en = en_name
                    break
        if self._analyzer is None or not cls_en:
            return
        try:
            cls_id = self._analyzer.read_bytes(self._anchor + 0x1A9, 1)[0]
        except OSError:
            return
        mapping = dict(settings.get("arena_play_class_id_map", {}) or {})
        if mapping.get(str(cls_id)) != cls_en:
            mapping[str(cls_id)] = cls_en
            settings.set_val("arena_play_class_id_map", mapping)
            _log.info("normal-play: arena_play_class_id_map updated: %d → %s",
                      cls_id, cls_en)

    def _set_chargen_ui_state(self, in_chargen: bool) -> None:
        """chargen 中は翻訳タブのゲーム状態行を隠す。"""
        if self._is_in_chargen == in_chargen:
            return
        self._is_in_chargen = in_chargen
        try:
            self._tab_translate.set_chargen_active(in_chargen)
        except AttributeError:
            pass

    # ------------------------------------------------------------------
    # img_name ベース画面検出 — controllers/img_screen_controller.py に分離（Phase 3）
    # ------------------------------------------------------------------

    def _push_translation(self, original: str, translated: str,
                          panel_original: str | None = None,
                          panel_translated: str | None = None,
                          speech_role: str | None = None) -> None:
        from controllers.translation_update_controller import (
            push_translation)
        push_translation(self, original, translated,
                         panel_original=panel_original,
                         panel_translated=panel_translated,
                         speech_role=speech_role)
    # ------------------------------------------------------------------
    # chargen 検出 / 翻訳 — controllers/chargen_controller.py に分離（Phase 2b）
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # キャプチャ
    # ------------------------------------------------------------------
    # レイアウト管理 — controllers/layout_controller.py に分離（Phase 5a）
    # （_toggle_layout_mode と _enter/_exit/_embed_*_layout_mode は Phase 5b で対応予定）
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # レイアウトモード enter/exit — controllers/layout_controller.py に分離
    # （Phase 5b）
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # キャプチャ
    # ------------------------------------------------------------------

    def _get_cap_dir(self) -> str:
        """キャプチャ保存先を返す。未設定時はユーザー側 captures/ を使用。"""
        return (settings.get("capture_dir", "")
                or settings.get("backup_dir", "")
                or os.path.join(_USER_DIR, "captures"))

    def _get_dosbox_window_resolution(self) -> tuple[int, int]:
        """arena.conf の windowresolution を (w, h) で返す。

        旧 _tab_dosbox.get_window_resolution() の代替。tab_dosbox 廃止に伴い
        AssistWindow 側で arena.conf を直接参照する。読み取れない場合は
        1024x768 を返す。
        """
        import dosbox_conf as dc
        path = settings.get("dosbox_conf_path", "") or dc.DEFAULT_CONF_PATH
        size = dc.get_window_size(path)
        if size:
            return size
        return 1024, 768

    def _apply_tts_settings(self) -> None:
        """設定値を TTSService へ反映する（Phase1）。"""
        tts = getattr(self, "_tts", None)
        if tts is None:
            return
        tts.set_enabled(bool(settings.get("tts_enabled", False)))
        tts.set_interrupt(bool(settings.get("tts_interrupt", True)))
        tts.set_rate(int(settings.get("tts_rate", 0)))
        tts.set_volume(int(settings.get("tts_volume", 100)))
        tts.set_voice(settings.get("tts_voice", "") or "")
        tts.set_engine(settings.get("tts_engine", "sapi5") or "sapi5")
        tts.set_vv_speaker(int(settings.get("tts_vv_speaker", 0) or 0))

    def _apply_view_settings(self) -> None:
        """接続バー / ステータスバーの表示要素の ON/OFF を設定から反映する。

        - show_recognition_screen: 接続中ラベルに認識画面名を含めるか
          (False のとき poll_controller 側で screen 部分を空にする)
        - show_img_info: 接続バー右の IMG: {img} ラベル表示
        - show_version: 接続バー右のバージョン + ステータスバーのバージョン表示
        """
        show_img = bool(settings.get("show_img_info", True))
        show_ver = bool(settings.get("show_version", True))
        if hasattr(self, "_anchor_lbl"):
            self._anchor_lbl.setVisible(show_img)
        if hasattr(self, "_conn_ver_lbl"):
            self._conn_ver_lbl.setVisible(show_ver)
        if hasattr(self, "_sb_ver_lbl"):
            self._sb_ver_lbl.setVisible(show_ver)
        # 認識画面名の表示は poll_controller 側で settings を参照するため
        # ここでは特に何もしない (次回 poll で反映)。

    def _reload_shutter_se(self) -> None:
        """設定 capture_se_kind に応じて assets/se_<kind>.wav の WAV バイト列を読む。

        再生は winsound(Windows 標準)で行う。Qt の QSoundEffect は SAPI5 読み上げと
        同時再生で native クラッシュするため使わない。
        """
        kind = settings.get("capture_se_kind", "phone_camera")
        if self._shutter_se_kind == kind and self._shutter_se_wav is not None:
            return
        self._shutter_se_wav = None
        self._shutter_se_kind = kind
        try:
            # 公開版は assets を _internal に置かず exe 内 seed から読む。開発時はディスク。
            import app_resources
            wav = app_resources.read_bytes(f"assets/se_{kind}.wav")
            if wav is None:  # フォールバック: 既定の phone_camera
                wav = app_resources.read_bytes("assets/se_phone_camera.wav")
            self._shutter_se_wav = wav
        except Exception:
            self._shutter_se_wav = None

    def _capture(self):
        # シャッターSE は処理開始前に再生（クリック反応のフィードバック目的）。
        # 設定 capture_se_enabled=False または SE 初期化失敗時はスキップする。
        if settings.get("capture_se_enabled", True):
            self._reload_shutter_se()
            if self._shutter_se_wav is not None:
                try:
                    from services.sound_effect import play_wav_async
                    vol = float(settings.get("capture_se_volume", 0.3))
                    play_wav_async(self._shutter_se_wav, vol)
                except Exception:
                    pass
        try:
            import screen_capture as sc
            if not sc.is_available():
                self._sb.showMessage(i18n.tr("capture.no_pillow"), 5000)
                return

            out_dir = self._get_cap_dir()
            os.makedirs(out_dir, exist_ok=True)
            cap_no = sc.next_cap_no(out_dir)

            # レイアウトモード: ウィンドウ全体をスクリーン領域 BitBlt（自然合成）
            if self._is_layout_active:
                import ctypes
                import ctypes.wintypes
                r = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(int(self.winId()), ctypes.byref(r))
                img = sc.capture_screen_region(
                    r.left, r.top, r.right - r.left, r.bottom - r.top)
                if img:
                    path = os.path.join(out_dir, f"cap_{cap_no:03d}_layout.png")
                    img.save(path)
                    self._sb.showMessage(
                        i18n.tr("capture.saved", no=cap_no, count=1), 4000)
                    self._tab_capture.set_cap_dir(out_dir)
                else:
                    self._sb.showMessage(i18n.tr("capture.nothing"), 4000)
                return

            # 通常モード: ゲーム + ビューア別々に保存
            game_pid = self._analyzer.pid if self._analyzer else 0
            game_path, viewer_path = sc.save_screenshots(
                out_dir     = out_dir,
                cap_no      = cap_no,
                widget      = self,
                game_pid    = game_pid,
                game_prefix = "DOSBox",
            )
            saved = [p for p in (game_path, viewer_path) if p]
            if saved:
                self._sb.showMessage(
                    i18n.tr("capture.saved", no=cap_no, count=len(saved)), 4000)
                self._tab_capture.set_cap_dir(out_dir)
            else:
                self._sb.showMessage(i18n.tr("capture.nothing"), 4000)
        except Exception as exc:
            self._sb.showMessage(f"{i18n.tr('capture.error')}: {exc}", 5000)

    # ------------------------------------------------------------------
    # テーマ
    # ------------------------------------------------------------------

    def _apply_theme(self):
        self.setStyleSheet(theme_mod.get_stylesheet(self._theme_mode))

    def _set_theme(self, mode: str):
        self._theme_mode = mode
        settings.set_val("theme", mode)
        self._apply_theme()

    # ------------------------------------------------------------------
    # ジオメトリ
    # ------------------------------------------------------------------

    def _restore_geometry(self):
        geo = settings.get("window_geometry", "")
        if geo:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))

    # ------------------------------------------------------------------
    # イベントフィルタ（ドラッグ / リサイズ / コンテキストメニュー）
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        return self._chrome.handle_event(obj, event)


    # ------------------------------------------------------------------
    # 移動イベント（レイアウトモード: DOSBox 同期追従）
    # ------------------------------------------------------------------

    def moveEvent(self, event):
        super().moveEvent(event)
        self._layout.handle_move_event()

    # ------------------------------------------------------------------
    # 終了
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        QApplication.instance().removeEventFilter(self)
        try:
            self._tts.shutdown()
        except (AttributeError, RuntimeError):
            pass
        self._chrome.clear_edge_cursor()
        if self._is_layout_active:
            self._layout.exit_layout_mode()
        if self._is_embed_active:
            self._layout.exit_embed_layout_mode()
        self._layout_mgr.stop()
        geo_b64 = self.saveGeometry().toBase64().data().decode()
        settings.set_val("window_geometry", geo_b64)
        self._disconnect()
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


# ------------------------------------------------------------------
# 設定ダイアログ — windows/settings_dialog.py に分離（Phase 1）
# ------------------------------------------------------------------
