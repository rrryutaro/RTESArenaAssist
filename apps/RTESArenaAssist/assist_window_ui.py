"""
assist_window_ui.py — AssistWindow UI ビルダー

assist_window.py の _build_ui 相当をモジュールレベル関数として保持する。
ロジック・スロット・スタック・シグナルハンドラはすべて assist_window.py 本体に残す。

循環回避: build_ui は assist_window._build_ui からの関数ローカル遅延 import で
のみ呼ばれるため、assist_window 完全ロード後にこのモジュールが import される。
条件付き Tab 可用性フラグ(TabMap/TabJournal/TabScreenJudge)のみ assist_window の
単一住所から import する(二重住所回避)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assist_window import AssistWindow

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import i18n_helper as i18n
import assist_settings as settings
from assist_constants import WIN_W, WIN_H, WIN_MIN_W, WIN_MIN_H
from version import version_string
from layout_manager import TrackMode
from attributes_panel import AttributesPanel
from tabs.tab_translate import TabTranslate
from tabs.tab_status import TabStatus
from tabs.tab_dict import TabDict
from tabs.tab_save import TabSave
from tabs.tab_manual import TabManual
from tabs.tab_capture import TabCapture

# 条件付き Tab 可用性フラグ/クラス(TabMap/TabJournal/TabScreenJudge)は
# 本体 assist_window の単一住所を参照する(try/except 複製による二重住所を避ける)。
# build_ui は assist_window._build_ui からの関数ローカル遅延 import でのみ
# 呼ばれるため、この import 時点で assist_window は完全ロード済=循環しない。
from assist_window import (  # noqa: E402
    TabMap, _TAB_MAP_AVAILABLE,
    TabJournal, _TAB_JOURNAL_AVAILABLE,
    TabScreenJudge, _SCREEN_JUDGE_AVAILABLE,
)


def build_ui(win: "AssistWindow") -> None:
    """
    AssistWindow の UI を構築し、ウィジェット参照を win に設定する。
    assist_window.py の _build_ui から cut-paste（self → win リネーム・インデント調整のみ）。
    """
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    win.setWindowTitle(i18n.tr("app.title"))
    win.setMinimumSize(WIN_MIN_W, WIN_MIN_H)
    win.resize(WIN_W, WIN_H)

    central = QWidget()
    win.setCentralWidget(central)
    root = QVBoxLayout(central)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    # ── 接続バー（ドラッグ領域兼） ──────────────────────────────
    conn_bar = QWidget()
    conn_bar.setObjectName("connBar")
    conn_layout = QHBoxLayout(conn_bar)
    conn_layout.setContentsMargins(8, 4, 8, 4)

    win._status_lbl = QLabel(i18n.tr("connection.status_disconnected"))
    win._status_lbl.setObjectName("connStatus")
    conn_layout.addWidget(win._status_lbl)

    win._img_name_lbl = QLabel("")
    win._img_name_lbl.setObjectName("dimLabel")
    conn_layout.addWidget(win._img_name_lbl)
    conn_layout.addStretch(1)

    win._anchor_lbl = QLabel("")
    win._anchor_lbl.setObjectName("connAnchor")
    conn_layout.addWidget(win._anchor_lbl)

    win._conn_ver_lbl = QLabel(version_string())
    win._conn_ver_lbl.setObjectName("dimLabel")
    conn_layout.addWidget(win._conn_ver_lbl)

    win._conn_btn = QPushButton(i18n.tr("connection.connect"))
    win._conn_btn.setMinimumWidth(80)
    win._conn_btn.clicked.connect(win._on_connect_clicked)
    conn_layout.addWidget(win._conn_btn)

    # ⊞ レイアウトボタン（左クリック=ON/OFFトグル、右クリック=設定）
    win._layout_btn = QPushButton("⊞")
    win._layout_btn.setFixedSize(28, 28)
    win._layout_btn.setObjectName("winCtrlBtn")
    win._layout_btn.setCheckable(True)
    win._layout_btn.setToolTip(i18n.tr("layout.btn_tooltip"))
    win._layout_btn.clicked.connect(win._layout.toggle_layout_mode)
    win._layout_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    win._layout_btn.customContextMenuRequested.connect(win._layout.open_layout_settings_menu)
    conn_layout.addWidget(win._layout_btn)

    # 📷 キャプチャボタン
    win._cap_btn = QPushButton("📷")
    win._cap_btn.setFixedSize(28, 28)
    win._cap_btn.setObjectName("winCtrlBtn")
    win._cap_btn.setToolTip(i18n.tr("capture.btn_tooltip"))
    win._cap_btn.clicked.connect(win._capture)
    conn_layout.addWidget(win._cap_btn)

    # ⚙ 設定ボタン
    win._settings_btn = QPushButton("⚙")
    win._settings_btn.setFixedSize(28, 28)
    win._settings_btn.setObjectName("winCtrlBtn")
    win._settings_btn.setToolTip(i18n.tr("menu.settings_open"))
    win._settings_btn.clicked.connect(win._open_settings)
    conn_layout.addWidget(win._settings_btn)

    # 最小化・閉じる
    win._min_btn = QPushButton("─")
    win._min_btn.setFixedSize(24, 24)
    win._min_btn.setObjectName("winCtrlBtn")
    win._min_btn.clicked.connect(win.showMinimized)
    conn_layout.addWidget(win._min_btn)

    win._close_btn = QPushButton("✕")
    win._close_btn.setFixedSize(24, 24)
    win._close_btn.setObjectName("winCloseBtn")
    win._close_btn.clicked.connect(win.close)
    conn_layout.addWidget(win._close_btn)

    root.addWidget(conn_bar)

    # ── タブ ──────────────────────────────────────────────────
    win._tabs = QTabWidget()
    # AttributesPanel は翻訳タブ / ステータスタブで 1 インスタンスを共有し、
    # アクティブなタブ側へ reparent して表示する (二重管理の解消)。
    win._attributes_panel = AttributesPanel()
    win._tab_translate = TabTranslate(win._attributes_panel)
    win._tab_status    = TabStatus(win._attributes_panel)
    win._tab_dict      = TabDict()
    win._tab_save      = TabSave()
    win._tab_manual    = TabManual()
    win._tab_capture      = TabCapture()
    # 翻訳ログタブ。ジャーナルの右隣に配置する。
    from tabs.tab_log import TabLog
    win._tab_log = TabLog()
    if getattr(win, "_log_store", None) is not None:
        win._tab_log.set_store(win._log_store)
    if _TAB_MAP_AVAILABLE and TabMap is not None:
        win._tab_map = TabMap(name="map_tab")
    else:
        win._tab_map = None
    if _TAB_JOURNAL_AVAILABLE and TabJournal is not None:
        win._tab_journal = TabJournal()
    else:
        win._tab_journal = None
    if _SCREEN_JUDGE_AVAILABLE and TabScreenJudge is not None:
        win._tab_screen_judge = TabScreenJudge(win, win)
        win._tab_screen_judge.load_from_registry()
    else:
        win._tab_screen_judge = None

    win._tabs.addTab(win._tab_translate, i18n.tr("tab.translate"))
    win._tabs.addTab(win._tab_status,    i18n.tr("tab.status"))
    if win._tab_map is not None:
        win._tabs.addTab(win._tab_map,   i18n.tr("tab.map"))
    if win._tab_journal is not None:
        win._tabs.addTab(win._tab_journal,
                          i18n.tr("tab.journal", default="ジャーナル"))
    # 翻訳ログ（ジャーナルの右隣）
    win._tabs.addTab(win._tab_log, i18n.tr("tab.log", default="ログ"))
    # タブ並び順最終確定
    # [翻訳][ステータス][マップ][ジャーナル][ログ][セーブ][キャプチャ][辞書][マニュアル]
    win._tabs.addTab(win._tab_save,      i18n.tr("tab.save"))
    win._tabs.addTab(win._tab_capture,   i18n.tr("tab.capture"))
    win._tabs.addTab(win._tab_dict,      i18n.tr("tab.dict"))
    win._tabs.addTab(win._tab_manual,    i18n.tr("tab.manual"))
    # ScreenJudge タブは現状未使用のため非表示。設定で再表示可能。
    if (win._tab_screen_judge is not None
            and settings.get("screen_judge_tab_visible", False)):
        win._tabs.addTab(win._tab_screen_judge, i18n.tr("tab.screen_judge"))
    elif win._tab_screen_judge is not None:
        win._tab_screen_judge.hide()
    root.addWidget(win._tabs)

    # 共有 AttributesPanel をアクティブなタブ側へ付け替える。タブ切替と
    # 翻訳タブのパネルモード変化を契機に再評価する。
    win._tabs.currentChanged.connect(
        lambda *_: win._update_attr_panel_placement())
    win._tab_translate.panel_mode_changed.connect(
        lambda *_: win._update_attr_panel_placement())
    win._update_attr_panel_placement()

    win._sb = QStatusBar()
    win.setStatusBar(win._sb)
    win._sb.showMessage(i18n.tr("status.ready"))
    win._sb_ver_lbl = QLabel(version_string())
    win._sb_ver_lbl.setObjectName("statusVersion")
    win._sb.addPermanentWidget(win._sb_ver_lbl)
    win._tab_save.status_message.connect(win._sb.showMessage)

    # 接続バー / ステータスバー表示設定の初期反映
    win._apply_view_settings()

    # キャプチャタブの初期ディレクトリ設定
    win._tab_capture.set_cap_dir(win._get_cap_dir())

    # DOSBox 設定タブは廃止。arena.conf 編集 UI は設定ダイアログへ移行。

    # 追従モードを設定から復元（DOSBox が起動していない場合は NONE のまま）
    saved_track = settings.get("layout_track_mode", TrackMode.NONE.value)
    try:
        restored_mode = TrackMode(saved_track)
    except ValueError:
        restored_mode = TrackMode.NONE
    if restored_mode != TrackMode.NONE:
        win._layout_mgr.set_track_mode(restored_mode, win)
