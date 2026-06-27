from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from assist_window import AssistWindow
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStatusBar, QTabWidget, QVBoxLayout, QWidget
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
from assist_window import TabMap, _TAB_MAP_AVAILABLE, TabJournal, _TAB_JOURNAL_AVAILABLE, TabScreenJudge, _SCREEN_JUDGE_AVAILABLE

def build_ui(win: 'AssistWindow') -> None:
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
    win.setWindowTitle(i18n.tr('app.title'))
    win.setMinimumSize(WIN_MIN_W, WIN_MIN_H)
    win.resize(WIN_W, WIN_H)
    central = QWidget()
    win.setCentralWidget(central)
    root = QVBoxLayout(central)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    conn_bar = QWidget()
    conn_bar.setObjectName('connBar')
    conn_layout = QHBoxLayout(conn_bar)
    conn_layout.setContentsMargins(8, 4, 8, 4)
    win._status_lbl = QLabel(i18n.tr('connection.status_disconnected'))
    win._status_lbl.setObjectName('connStatus')
    conn_layout.addWidget(win._status_lbl)
    win._img_name_lbl = QLabel('')
    win._img_name_lbl.setObjectName('dimLabel')
    conn_layout.addWidget(win._img_name_lbl)
    conn_layout.addStretch(1)
    win._anchor_lbl = QLabel('')
    win._anchor_lbl.setObjectName('connAnchor')
    conn_layout.addWidget(win._anchor_lbl)
    win._conn_ver_lbl = QLabel(version_string())
    win._conn_ver_lbl.setObjectName('dimLabel')
    conn_layout.addWidget(win._conn_ver_lbl)
    win._conn_btn = QPushButton(i18n.tr('connection.connect'))
    win._conn_btn.setMinimumWidth(80)
    win._conn_btn.clicked.connect(win._on_connect_clicked)
    conn_layout.addWidget(win._conn_btn)
    win._tts_pause_btn = QPushButton('⏸')
    win._tts_pause_btn.setFixedSize(28, 28)
    win._tts_pause_btn.setObjectName('winCtrlBtn')
    win._tts_pause_btn.setToolTip(i18n.tr('tts.pause_tooltip'))
    win._tts_pause_btn.clicked.connect(win._on_tts_pause_clicked)
    conn_layout.addWidget(win._tts_pause_btn)
    win._tts_resume_btn = QPushButton('▶')
    win._tts_resume_btn.setFixedSize(28, 28)
    win._tts_resume_btn.setObjectName('winCtrlBtn')
    win._tts_resume_btn.setToolTip(i18n.tr('tts.resume_tooltip'))
    win._tts_resume_btn.clicked.connect(win._on_tts_resume_clicked)
    conn_layout.addWidget(win._tts_resume_btn)
    win._tts_stop_btn = QPushButton('■')
    win._tts_stop_btn.setFixedSize(28, 28)
    win._tts_stop_btn.setObjectName('winCtrlBtn')
    win._tts_stop_btn.setToolTip(i18n.tr('tts.stop_tooltip'))
    win._tts_stop_btn.clicked.connect(win._on_tts_stop_clicked)
    conn_layout.addWidget(win._tts_stop_btn)
    win._layout_btn = QPushButton('⊞')
    win._layout_btn.setFixedSize(28, 28)
    win._layout_btn.setObjectName('winCtrlBtn')
    win._layout_btn.setCheckable(True)
    win._layout_btn.setToolTip(i18n.tr('layout.btn_tooltip'))
    win._layout_btn.clicked.connect(win._layout.toggle_layout_mode)
    win._layout_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    win._layout_btn.customContextMenuRequested.connect(win._layout.open_layout_settings_menu)
    conn_layout.addWidget(win._layout_btn)
    win._cap_btn = QPushButton('📷')
    win._cap_btn.setFixedSize(28, 28)
    win._cap_btn.setObjectName('winCtrlBtn')
    win._cap_btn.setToolTip(i18n.tr('capture.btn_tooltip'))
    win._cap_btn.clicked.connect(win._capture)
    conn_layout.addWidget(win._cap_btn)
    win._settings_btn = QPushButton('⚙')
    win._settings_btn.setFixedSize(28, 28)
    win._settings_btn.setObjectName('winCtrlBtn')
    win._settings_btn.setToolTip(i18n.tr('menu.settings_open'))
    win._settings_btn.clicked.connect(win._open_settings)
    conn_layout.addWidget(win._settings_btn)
    win._min_btn = QPushButton('─')
    win._min_btn.setFixedSize(24, 24)
    win._min_btn.setObjectName('winCtrlBtn')
    win._min_btn.clicked.connect(win.showMinimized)
    conn_layout.addWidget(win._min_btn)
    win._close_btn = QPushButton('✕')
    win._close_btn.setFixedSize(24, 24)
    win._close_btn.setObjectName('winCloseBtn')
    win._close_btn.clicked.connect(win.close)
    conn_layout.addWidget(win._close_btn)
    root.addWidget(conn_bar)
    win._tabs = QTabWidget()
    win._attributes_panel = AttributesPanel()
    win._tab_translate = TabTranslate(win._attributes_panel)
    win._tab_status = TabStatus(win._attributes_panel)
    win._tab_dict = TabDict()
    win._tab_save = TabSave()
    win._tab_manual = TabManual()
    win._tab_capture = TabCapture()
    from tabs.tab_log import TabLog
    win._tab_log = TabLog()
    if getattr(win, '_log_store', None) is not None:
        win._tab_log.set_store(win._log_store)
    if _TAB_MAP_AVAILABLE and TabMap is not None:
        win._tab_map = TabMap(name='map_tab')
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
    win._tabs.addTab(win._tab_translate, i18n.tr('tab.translate'))
    win._tabs.addTab(win._tab_status, i18n.tr('tab.status'))
    if win._tab_map is not None:
        win._tabs.addTab(win._tab_map, i18n.tr('tab.map'))
    if win._tab_journal is not None:
        win._tabs.addTab(win._tab_journal, i18n.tr('tab.journal', default='ジャーナル'))
    win._tabs.addTab(win._tab_log, i18n.tr('tab.log', default='ログ'))
    win._tabs.addTab(win._tab_save, i18n.tr('tab.save'))
    win._tabs.addTab(win._tab_capture, i18n.tr('tab.capture'))
    win._tabs.addTab(win._tab_dict, i18n.tr('tab.dict'))
    win._tabs.addTab(win._tab_manual, i18n.tr('tab.manual'))
    if win._tab_screen_judge is not None and settings.get('screen_judge_tab_visible', False):
        win._tabs.addTab(win._tab_screen_judge, i18n.tr('tab.screen_judge'))
    elif win._tab_screen_judge is not None:
        win._tab_screen_judge.hide()
    root.addWidget(win._tabs)
    win._tabs.currentChanged.connect(lambda *_: win._update_attr_panel_placement())
    win._tab_translate.panel_mode_changed.connect(lambda *_: win._update_attr_panel_placement())
    win._update_attr_panel_placement()
    win._sb = QStatusBar()
    win.setStatusBar(win._sb)
    win._sb.showMessage(i18n.tr('status.ready'))
    win._sb_ver_lbl = QLabel(version_string())
    win._sb_ver_lbl.setObjectName('statusVersion')
    win._sb.addPermanentWidget(win._sb_ver_lbl)
    win._tab_save.status_message.connect(win._sb.showMessage)
    win._apply_view_settings()
    win._tab_capture.set_cap_dir(win._get_cap_dir())
    saved_track = settings.get('layout_track_mode', TrackMode.NONE.value)
    try:
        restored_mode = TrackMode(saved_track)
    except ValueError:
        restored_mode = TrackMode.NONE
    if restored_mode != TrackMode.NONE:
        win._layout_mgr.set_track_mode(restored_mode, win)
