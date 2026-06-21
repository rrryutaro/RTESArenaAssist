"""
controllers/layout_controller.py — レイアウト UI ハンドラ + enter/exit 制御

UI ハンドラ群とレイアウトモード enter/exit 制御 + moveEvent を分離して保持する。

含まれるもの（19 メソッド）:
  UI ハンドラ:
    - 追従モード設定: on_track_none / on_track_afd / on_track_dfa / set_track_mode
    - DOSBox コーナー設定: on_corner_tl/tr/bl/br / set_layout_corner
    - 配置形式: set_layout_form
    - DOSBox 最前面: toggle_dosbox_topmost
    - レイアウト設定メニュー: open_layout_settings_menu
    - 一発配置 / 診断 / カーソル解除: arrange_layout / diagnose_layout / unlock_cursor
  レイアウトモード制御:
    - レイアウトモード切替: toggle_layout_mode
    - setMask 方式 enter/exit: enter_layout_mode / exit_layout_mode
    - 埋め込み方式 enter/exit: enter_embed_layout_mode / exit_embed_layout_mode
    - レイアウトモード時の DOSBox 同期追従: handle_move_event
      （AssistWindow.moveEvent からの委譲先）

window 側の状態（_layout_mgr / _layout_corner / _layout_form / _is_layout_active /
_layout_btn / _layout_dpr / _layout_dos_offset / _layout_dos_size 等）は
依然 AssistWindow が保持し、コントローラからは self._w.X 経由で参照する。
"""

import logging

from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget

import i18n_helper as i18n
import assist_settings as settings
from assist_constants import WIN_MIN_W
from layout_manager import TrackMode, LayoutCorner, LayoutForm, calc_layout_zones
from layout_panel_translate import LayoutPanelTranslate

_log = logging.getLogger("layout_controller")


class LayoutController:
    """レイアウト UI ハンドラ。AssistWindow を back-reference として保持する。"""

    def __init__(self, window):
        self._w = window

    # ------------------------------------------------------------------
    # 追従モード アクションハンドラ（lambda を使わず直接接続）
    # ------------------------------------------------------------------

    def on_track_none(self):
        self.set_track_mode(TrackMode.NONE)

    def on_track_afd(self):
        self.set_track_mode(TrackMode.ASSIST_FOLLOWS_DOSBOX)

    def on_track_dfa(self):
        self.set_track_mode(TrackMode.DOSBOX_FOLLOWS_ASSIST)

    def on_corner_tl(self):
        self.set_layout_corner(LayoutCorner.TOP_LEFT)

    def on_corner_tr(self):
        self.set_layout_corner(LayoutCorner.TOP_RIGHT)

    def on_corner_bl(self):
        self.set_layout_corner(LayoutCorner.BOTTOM_LEFT)

    def on_corner_br(self):
        self.set_layout_corner(LayoutCorner.BOTTOM_RIGHT)

    # ------------------------------------------------------------------
    # レイアウト設定メニュー（_layout_btn 右クリックから呼ばれる）
    # ------------------------------------------------------------------

    def open_layout_settings_menu(self, pos=None):
        """レイアウト設定メニュー（右クリック）。ON/OFFトグルは含まない。"""
        _log.info("open_layout_settings_menu called")
        w = self._w
        menu = QMenu(w)

        # ── 追従モード ─────────────────────────────────────────────
        lbl_track = menu.addAction(i18n.tr("layout.track_label"))
        lbl_track.setEnabled(False)

        cur_track = w._layout_mgr.get_track_mode()

        act_tn = menu.addAction("  " + i18n.tr("layout.track_none"))
        act_tn.setCheckable(True)
        act_tn.setChecked(cur_track == TrackMode.NONE)
        act_tn.triggered.connect(self.on_track_none)

        act_afd = menu.addAction("  " + i18n.tr("layout.track_assist_follows_dosbox"))
        act_afd.setCheckable(True)
        act_afd.setChecked(cur_track == TrackMode.ASSIST_FOLLOWS_DOSBOX)
        act_afd.triggered.connect(self.on_track_afd)

        act_dfa = menu.addAction("  " + i18n.tr("layout.track_dosbox_follows_assist"))
        act_dfa.setCheckable(True)
        act_dfa.setChecked(cur_track == TrackMode.DOSBOX_FOLLOWS_ASSIST)
        act_dfa.triggered.connect(self.on_track_dfa)

        menu.addSeparator()

        # ── DOSBox コーナー選択 ─────────────────────────────────────
        lbl_corner = menu.addAction(i18n.tr("layout.corner_label"))
        lbl_corner.setEnabled(False)

        _CORNER_DATA = [
            (LayoutCorner.TOP_LEFT,     "layout.corner_tl", self.on_corner_tl),
            (LayoutCorner.TOP_RIGHT,    "layout.corner_tr", self.on_corner_tr),
            (LayoutCorner.BOTTOM_LEFT,  "layout.corner_bl", self.on_corner_bl),
            (LayoutCorner.BOTTOM_RIGHT, "layout.corner_br", self.on_corner_br),
        ]
        for corner, key, handler in _CORNER_DATA:
            act = menu.addAction("  " + i18n.tr(key))
            act.setCheckable(True)
            act.setChecked(w._layout_corner == corner)
            act.triggered.connect(handler)

        menu.addSeparator()

        # ── 配置形式 ────────────────────────────────────────────────
        lbl_form = menu.addAction(i18n.tr("layout.form_label"))
        lbl_form.setEnabled(False)

        _FORM_DATA = [
            (LayoutForm.FORM_1, "layout.form_1"),
            (LayoutForm.FORM_2, "layout.form_2"),
            (LayoutForm.FORM_3, "layout.form_3"),
        ]
        for form, key in _FORM_DATA:
            act = menu.addAction("  " + i18n.tr(key))
            act.setCheckable(True)
            act.setChecked(w._layout_form == form)
            act.triggered.connect(lambda _checked, f=form: self.set_layout_form(f))

        menu.addSeparator()

        # ── 一発配置 ───────────────────────────────────────────────
        act_arrange = menu.addAction(i18n.tr("layout.arrange_once"))
        act_arrange.triggered.connect(self.arrange_layout)

        menu.addSeparator()

        # ── DOSBox 最前面表示 ──────────────────────────────────────
        act_dos_top = menu.addAction("  DOSBox を最前面表示")
        act_dos_top.setCheckable(True)
        act_dos_top.setChecked(settings.get("dosbox_always_on_top", False))
        act_dos_top.triggered.connect(self.toggle_dosbox_topmost)

        menu.addSeparator()

        # ── 診断 ───────────────────────────────────────────────────
        act_diag = menu.addAction("  [診断] DOSBox を検索")
        act_diag.triggered.connect(self.diagnose_layout)

        if pos is not None:
            menu.exec(w._layout_btn.mapToGlobal(pos))
        else:
            menu.exec(w._layout_btn.mapToGlobal(w._layout_btn.rect().bottomLeft()))

    # ------------------------------------------------------------------
    # 設定変更
    # ------------------------------------------------------------------

    def set_track_mode(self, mode: TrackMode):
        _log.info("set_track_mode: %s", mode.value)
        w = self._w
        w._layout_mgr.set_track_mode(mode, w)
        settings.set_val("layout_track_mode", mode.value)
        if mode == TrackMode.NONE:
            w._sb.showMessage(i18n.tr("layout.track_stopped"), 4000)
        elif mode == TrackMode.ASSIST_FOLLOWS_DOSBOX:
            w._sb.showMessage(i18n.tr("layout.track_started_afd"), 4000)
        else:
            w._sb.showMessage(i18n.tr("layout.track_started_dfa"), 4000)

    def toggle_dosbox_topmost(self, checked: bool):
        w = self._w
        settings.set_val("dosbox_always_on_top", checked)
        w._layout_mgr.set_dosbox_topmost(checked)
        w._sb.showMessage(
            "DOSBox 最前面表示: ON" if checked else "DOSBox 最前面表示: OFF", 3000
        )

    def set_layout_corner(self, corner: LayoutCorner):
        w = self._w
        w._layout_corner = corner
        settings.set_val("layout_corner", corner.value)
        w._sb.showMessage(f"Corner: {corner.value}", 2000)

    def set_layout_form(self, form: LayoutForm):
        w = self._w
        w._layout_form = form
        settings.set_val("layout_form", form.value)
        if w._is_layout_active:
            self.exit_layout_mode()
            self.enter_layout_mode()
        else:
            w._sb.showMessage(f"配置形式: {form.value}", 2000)

    # ------------------------------------------------------------------
    # ユーティリティ（カーソル解除 / 一発配置 / 診断）
    # ------------------------------------------------------------------

    def unlock_cursor(self):
        """レイアウトモード中、DOSBox の ClipCursor によるカーソルロックを解除する。"""
        import ctypes
        ctypes.windll.user32.ClipCursor(None)

    def arrange_layout(self):
        """一発配置（通常モード用: レイアウトモードは変えない）。"""
        _log.info("arrange_layout called")
        w = self._w
        dos_w, dos_h = w._get_dosbox_window_resolution()
        QApplication.processEvents()
        ok = w._layout_mgr.arrange(dos_w, dos_h, w, corner=w._layout_corner)
        if not ok:
            QMessageBox.warning(w, i18n.tr("common.warning"),
                                i18n.tr("layout.dosbox_not_found"))
            return
        w._sb.showMessage(
            f"配置完了: DOSBox {dos_w}×{dos_h}  [{w._layout_corner.value}]", 5000
        )

    def diagnose_layout(self):
        """DOSBox ウィンドウ検索の診断情報をダイアログに表示する。"""
        import screen_capture as sc
        import ctypes, ctypes.wintypes
        w = self._w

        lines = ["== DOSBox 診断 ==\n"]

        # "DOSBox" プレフィックスで検索
        hwnds = sc.find_hwnds_by_prefix("DOSBox")
        lines.append(f'find_hwnds_by_prefix("DOSBox"): {len(hwnds)} 件')
        for h in hwnds:
            r = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(h, ctypes.byref(r))
            n = ctypes.windll.user32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            ctypes.windll.user32.GetWindowTextW(h, buf, n + 1)
            lines.append(f"  HWND={h}  pos=({r.left},{r.top}) size={r.right-r.left}x{r.bottom-r.top}  title={buf.value!r}")

        # 全ウィンドウを列挙して "dos" を含むものを表示
        all_hwnds: list = []
        _Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(h, _):
            if ctypes.windll.user32.IsWindowVisible(h):
                ln = ctypes.windll.user32.GetWindowTextLengthW(h)
                if ln > 0:
                    b = ctypes.create_unicode_buffer(ln + 1)
                    ctypes.windll.user32.GetWindowTextW(h, b, ln + 1)
                    if "dos" in b.value.lower() or "arena" in b.value.lower():
                        all_hwnds.append((h, b.value))
            return True
        ctypes.windll.user32.EnumWindows(_Proc(_cb), None)

        lines.append(f'\n"dos"/"arena" を含む可視ウィンドウ: {len(all_hwnds)} 件')
        for h, title in all_hwnds:
            lines.append(f"  HWND={h}  title={title!r}")

        # 現在の設定
        lines.append(f"\n現在のコーナー: {w._layout_corner.value}")
        lines.append(f"追従モード: {w._layout_mgr.get_track_mode().value}")
        lines.append(f"DOSBox解像度: {w._get_dosbox_window_resolution()}")

        QMessageBox.information(w, "Layout 診断", "\n".join(lines))

    # ------------------------------------------------------------------
    # レイアウトモード切替
    # ------------------------------------------------------------------

    def toggle_layout_mode(self):
        w = self._w
        _log.info("toggle_layout_mode called (active=%s)", w._is_layout_active)
        if w._is_layout_active:
            self.exit_layout_mode()
        else:
            self.enter_layout_mode()

    # ------------------------------------------------------------------
    # setMask 方式 レイアウトモード enter/exit
    # ------------------------------------------------------------------

    def enter_layout_mode(self):
        """レイアウトモード開始:
        setMask 方式。setGeometry 後に GetWindowRect で物理座標を確定し、
        DOSBox を物理座標で配置することで DPI 倍率の影響を排除する。
        """
        import ctypes
        import ctypes.wintypes
        from PySide6.QtGui import QRegion
        w = self._w
        _log.info("enter_layout_mode")

        # DOSBox 検索（見つからない場合は 1 秒後に再試行）
        if not w._layout_mgr.is_dosbox_found():
            w._sb.showMessage("DOSBox を検索中…", 1500)
            QApplication.processEvents()
            from PySide6.QtCore import QThread
            QThread.msleep(1000)
            if not w._layout_mgr.is_dosbox_found():
                w._sb.showMessage(i18n.tr("layout.dosbox_not_found"), 5000)
                return

        hwnd = w._layout_mgr.get_dosbox_hwnd()

        if ctypes.windll.user32.IsIconic(hwnd):
            _log.info("DOSBox is minimized — restoring")
            ctypes.windll.user32.ShowWindow(hwnd, 9)
            QApplication.processEvents()

        # DOSBox 現在位置を保存（exit 時に復元）
        from layout_manager import _get_rect
        _rect = _get_rect(hwnd) if hwnd else None
        w._layout_dosbox_saved_rect = _rect
        _log.info("dosbox saved rect: %s", _rect)

        # DOSBox を NOTOPMOST に（TOPMOST のまま置くと z-order が狂う）
        w._layout_mgr.set_dosbox_topmost(False)

        # DOSBox サイズ（物理px）: 実ウィンドウサイズ優先、フォールバック: 設定値
        if _rect and (_rect[2] - _rect[0]) > 0 and (_rect[3] - _rect[1]) > 0:
            dos_w_phys = _rect[2] - _rect[0]
            dos_h_phys = _rect[3] - _rect[1]
        else:
            dos_w_phys, dos_h_phys = w._get_dosbox_window_resolution()
        corner = w._layout_corner

        # 現在の AssistWindow の論理/物理比率を計測（DPR を自前で確定する）
        try:
            screen_dpr = (w.screen() or QApplication.primaryScreen()).devicePixelRatio()
        except Exception:
            screen_dpr = 1.0
        _pre_phys = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(int(w.winId()), ctypes.byref(_pre_phys))
        _pre_log_w = w.width()  # 現在の論理幅
        _pre_phys_w = _pre_phys.right - _pre_phys.left
        meas_dpr = _pre_phys_w / _pre_log_w if _pre_log_w > 0 else screen_dpr
        _log.info("pre-layout: logical_w=%d  phys_w=%d  screen_dpr=%.3f  meas_dpr=%.4f",
                  _pre_log_w, _pre_phys_w, screen_dpr, meas_dpr)

        # DOSBox サイズを論理pxに変換（QRegion / Qt レイアウト計算用）
        dos_w_log = max(1, round(dos_w_phys / meas_dpr))
        dos_h_log = max(1, round(dos_h_phys / meas_dpr))

        # レイアウトコンテナサイズ: 設定値の固定コンテナ。
        # panel_w_log + dos_w_log の自動計算方式ではなく、1920×1080 などの
        # 固定コンテナにすることで setMask 穴あけ方式が正しく機能する
        screen = (w.screen() or QApplication.primaryScreen()).geometry()
        sx, sy = w.x(), w.y()   # 現在のウィンドウ位置を維持
        lw_log = settings.get("layout_size_w", 1920)
        lh_log = settings.get("layout_size_h", 1080)
        panel_w_log = max(WIN_MIN_W, lw_log - dos_w_log)

        if corner in (LayoutCorner.TOP_LEFT, LayoutCorner.BOTTOM_LEFT):
            dos_x_log, dos_y_log, panel_x_log = 0, 0, dos_w_log
        else:
            dos_x_log, dos_y_log, panel_x_log = lw_log - dos_w_log, 0, 0

        _log.info("layout(log): %dx%d  dos=(%d,%d)%dx%d  panel=(%d,0)%dx%d",
                  lw_log, lh_log, dos_x_log, dos_y_log, dos_w_log, dos_h_log,
                  panel_x_log, panel_w_log, lh_log)

        w._layout_saved_geo = w.geometry()
        w.statusBar().hide()
        w.setGeometry(sx, sy, lw_log, lh_log)
        QApplication.processEvents()

        # setGeometry 後に AssistWindow の実物理座標を取得
        # Qt の論理座標系と Win32 物理座標系のズレをここで吸収する
        _assist_phys = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(int(w.winId()), ctypes.byref(_assist_phys))
        assist_phys_x = _assist_phys.left
        assist_phys_y = _assist_phys.top
        _phys_w = _assist_phys.right - _assist_phys.left
        actual_dpr = _phys_w / lw_log if lw_log > 0 else meas_dpr
        w._layout_dpr = actual_dpr
        _log.info("assist phys: (%d,%d) %dx%d  actual_dpr=%.4f",
                  assist_phys_x, assist_phys_y, _phys_w,
                  _assist_phys.bottom - _assist_phys.top, actual_dpr)

        old_central = w.takeCentralWidget()
        w._layout_old_central = old_central

        container = QWidget()
        container.setObjectName("layoutContainer")
        container.setStyleSheet("QWidget#layoutContainer { background: #111111; }")

        # ゾーン計算（配置形式に応じてゾーン0=主パネル、1以降=副ゾーン）
        zones = calc_layout_zones(
            w._layout_form, corner, dos_w_log, dos_h_log, lw_log, lh_log
        )
        old_central.setParent(container)
        old_central.setGeometry(*zones[0])
        old_central.show()

        w._layout_zone_widgets.clear()
        w._layout_translate_panel = None
        for i, (zx, zy, zw, zh) in enumerate(zones[1:]):
            if w._layout_form == LayoutForm.FORM_2 and i == 0:
                sub = LayoutPanelTranslate(container)
                sub.set_connected(w._analyzer is not None)
                w._layout_translate_panel = sub
            else:
                sub = QWidget(container)
                sub.setStyleSheet("background: #0d1117; border: 1px solid #2a2a2a;")
            sub.setGeometry(zx, zy, zw, zh)
            sub.show()
            w._layout_zone_widgets.append(sub)

        w.setCentralWidget(container)

        # setMask は論理px で指定（Qt が内部で actual_dpr 変換）
        dos_region  = QRegion(dos_x_log, dos_y_log, dos_w_log, dos_h_log)
        full_region = QRegion(0, 0, lw_log, lh_log)
        w.setMask(full_region.subtracted(dos_region))

        # DOSBox は物理px で配置（Win32 SetWindowPos は物理px）
        dos_phys_x = assist_phys_x + round(dos_x_log * actual_dpr)
        dos_phys_y = assist_phys_y + round(dos_y_log * actual_dpr)
        _log.info("place_dosbox(phys): (%d,%d) size=%dx%d", dos_phys_x, dos_phys_y, dos_w_phys, dos_h_phys)
        ok = w._layout_mgr.place_dosbox(dos_phys_x, dos_phys_y, dos_w_phys, dos_h_phys)
        if not ok:
            w.clearMask()
            old_central.setParent(None)
            w.setCentralWidget(old_central)
            old_central.show()
            w.statusBar().show()
            w._is_layout_active = False
            w.setGeometry(w._layout_saved_geo)
            w._layout_saved_geo = None
            w._layout_old_central = None
            w._layout_dosbox_saved_rect = None
            QMessageBox.warning(w, i18n.tr("common.warning"),
                                "DOSBox の配置に失敗しました。\n"
                                "DOSBox が起動中か確認して再試行してください。")
            return

        # DOSBox を Assist ウィンドウ直下の z-order に配置して表示
        # (setMask の「穴」から透過表示されるために Assist より下に置く)
        _dos_hwnd    = w._layout_mgr.get_dosbox_hwnd()
        _assist_hwnd = int(w.winId())
        ctypes.windll.user32.ShowWindow(_dos_hwnd, 4)       # SW_SHOWNOACTIVATE
        ctypes.windll.user32.SetWindowPos(
            _dos_hwnd, _assist_hwnd, 0, 0, 0, 0,
            0x0013,  # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        )
        ctypes.windll.user32.BringWindowToTop(_assist_hwnd)

        w._layout_dos_offset = (dos_x_log, dos_y_log)  # 論理px
        w._layout_dos_size   = (dos_w_phys, dos_h_phys)  # 物理px
        w._is_layout_active = True
        w._layout_btn.setChecked(True)
        w._cursor_unlock_timer.start()
        _log.info("layout mode active: window(log)=(%d,%d)%dx%d  dosbox(phys)=(%d,%d)%dx%d  dpr=%.4f",
                  sx, sy, lw_log, lh_log, dos_phys_x, dos_phys_y, dos_w_phys, dos_h_phys, actual_dpr)
        w._sb.showMessage(
            f"レイアウトモード: {lw_log}×{lh_log}(log)  DOSBox {dos_w_phys}×{dos_h_phys}(phys)  [{corner.value}]",
            5000,
        )

    def exit_layout_mode(self):
        """レイアウトモード終了: マスクを解除し元のウィンドウ構成に戻す。"""
        import ctypes
        w = self._w
        _log.info("exit_layout_mode")
        if not w._is_layout_active:
            return

        w._is_layout_active = False  # moveEvent を先に抑止
        w._layout_btn.setChecked(False)
        w._cursor_unlock_timer.stop()
        ctypes.windll.user32.ClipCursor(None)

        # ウィンドウマスクを解除
        w.clearMask()

        # 副ゾーンをクリア（containerごとQtが削除するが参照を手放す）
        w._layout_translate_panel = None
        w._layout_zone_widgets.clear()

        # 元の中央ウィジェット (conn_bar + タブ) を復元
        if w._layout_old_central is not None:
            old = w._layout_old_central
            old.setParent(None)
            w.setCentralWidget(old)
            old.show()
            w._layout_old_central = None

        # ステータスバーを復元
        w.statusBar().show()

        # DOSBox の TOPMOST を設定値に従って復元し、元位置に戻す
        _dos_hwnd = w._layout_mgr.get_dosbox_hwnd()
        if _dos_hwnd:
            w._layout_mgr.set_dosbox_topmost(settings.get("dosbox_always_on_top", False))
            if w._layout_dosbox_saved_rect is not None:
                r = w._layout_dosbox_saved_rect
                ret = ctypes.windll.user32.SetWindowPos(
                    _dos_hwnd, None,
                    r[0], r[1], r[2] - r[0], r[3] - r[1],
                    0x0010,  # SWP_NOACTIVATE
                )
                _log.info("restored dosbox pos: (%d,%d) %dx%d ret=%s",
                          r[0], r[1], r[2]-r[0], r[3]-r[1], ret)
        w._layout_dosbox_saved_rect = None

        # AssistWindow ジオメトリを復元
        if w._layout_saved_geo is not None:
            w.setGeometry(w._layout_saved_geo)
            w._layout_saved_geo = None

        w._sb.showMessage(i18n.tr("layout.mode_off_msg"), 3000)

    # ------------------------------------------------------------------
    # 埋め込み方式 レイアウトモード enter/exit
    # ------------------------------------------------------------------

    def enter_embed_layout_mode(self):
        """埋め込みレイアウトモード開始:
        DOSBox を QWindow.fromWinId + createWindowContainer で Qt ウィジェット化し、
        レイアウトコンテナ内の DOSBox エリアに直接配置する。
        DOSBox output=surface モードのみ対応。
        """
        w = self._w
        _log.info("enter_embed_layout_mode")

        if w._is_layout_active or w._is_embed_active:
            return

        if not w._layout_mgr.is_dosbox_found():
            QMessageBox.warning(w, i18n.tr("common.warning"),
                                i18n.tr("layout.dosbox_not_found"))
            return

        # surface モード確認
        import dosbox_conf as dc
        conf_path = settings.get("dosbox_conf_path", "") or dc.DEFAULT_CONF_PATH
        output_mode = dc.get_output_mode(conf_path) or ""
        if output_mode.lower() != "surface":
            QMessageBox.warning(
                w, "埋め込みレイアウトモード",
                f"DOSBox の出力モードが surface ではありません（現在: {output_mode or '不明'}）。\n\n"
                "埋め込みモードは surface モードのみ対応しています。\n"
                "DOSBox タブで output を surface に変更して DOSBox を再起動してください。",
            )
            return

        corner = w._layout_corner

        screen = (w.screen() or QApplication.primaryScreen()).geometry()
        sx, sy = screen.x(), screen.y()
        try:
            dpr = (w.screen() or QApplication.primaryScreen()).devicePixelRatio()
        except Exception:
            dpr = 1.0

        from layout_manager import _get_rect
        _embed_hwnd = w._layout_mgr.get_dosbox_hwnd()
        _rect = _get_rect(_embed_hwnd) if _embed_hwnd else None
        if _rect:
            dos_w_phys = _rect[2] - _rect[0]
            dos_h_phys = _rect[3] - _rect[1]
            if dos_w_phys <= 0 or dos_h_phys <= 0:
                dos_w_phys, dos_h_phys = w._get_dosbox_window_resolution()
        else:
            dos_w_phys, dos_h_phys = w._get_dosbox_window_resolution()

        dos_w = max(1, round(dos_w_phys / dpr))
        dos_h = max(1, round(dos_h_phys / dpr))

        panel_w = max(WIN_MIN_W, w.width())
        lw = min(dos_w + panel_w, screen.width())
        lh = min(max(dos_h, w.height()), screen.height())
        panel_w = max(WIN_MIN_W, lw - dos_w)

        if corner == LayoutCorner.TOP_LEFT:
            dos_x, dos_y, panel_x = 0, 0, dos_w
        elif corner == LayoutCorner.TOP_RIGHT:
            dos_x, dos_y, panel_x = lw - dos_w, 0, 0
        elif corner == LayoutCorner.BOTTOM_LEFT:
            dos_x, dos_y, panel_x = 0, lh - dos_h, dos_w
        else:
            dos_x, dos_y, panel_x = lw - dos_w, lh - dos_h, 0

        w._embed_saved_geo = w.geometry()
        w.statusBar().hide()
        w.setGeometry(sx, sy, lw, lh)
        QApplication.processEvents()

        old_central = w.takeCentralWidget()
        w._embed_old_central = old_central

        container = QWidget()
        container.setObjectName("layoutContainer")
        container.setStyleSheet("QWidget#layoutContainer { background: #111111; }")

        old_central.setParent(container)
        old_central.setGeometry(panel_x, 0, panel_w, lh)
        old_central.show()

        w.setCentralWidget(container)

        embed_widget = w._layout_mgr.enter_embed_mode(container, dos_x, dos_y, dos_w, dos_h)
        if embed_widget is None:
            old_central.setParent(None)
            w.setCentralWidget(old_central)
            w.statusBar().show()
            w.setGeometry(w._embed_saved_geo)
            w._embed_saved_geo = None
            w._embed_old_central = None
            QMessageBox.warning(w, i18n.tr("common.warning"),
                                "DOSBox の埋め込みに失敗しました。")
            return

        w._is_embed_active = True
        w._cursor_unlock_timer.start()
        _log.info("embed layout mode active: %dx%d  dosbox=(%d,%d)%dx%d",
                  lw, lh, dos_x, dos_y, dos_w, dos_h)
        w._sb.showMessage(
            f"埋め込みレイアウトモード: {lw}×{lh}  DOSBox {dos_w}×{dos_h}  [{corner.value}]",
            5000,
        )

    def exit_embed_layout_mode(self):
        """埋め込みレイアウトモード終了: DOSBox を独立ウィンドウに戻す。"""
        w = self._w
        _log.info("exit_embed_layout_mode")
        if not w._is_embed_active:
            return

        w._layout_mgr.exit_embed_mode()

        if w._embed_old_central is not None:
            old = w._embed_old_central
            old.setParent(None)
            w.setCentralWidget(old)
            old.show()
            w._embed_old_central = None

        w.statusBar().show()
        if w._embed_saved_geo is not None:
            w.setGeometry(w._embed_saved_geo)
            w._embed_saved_geo = None

        w._cursor_unlock_timer.stop()
        import ctypes
        ctypes.windll.user32.ClipCursor(None)
        w._is_embed_active = False
        w._sb.showMessage("埋め込みレイアウトモード終了", 3000)

    # ------------------------------------------------------------------
    # 移動イベント（レイアウトモード時の DOSBox 同期追従）
    # ------------------------------------------------------------------

    def handle_move_event(self):
        """AssistWindow.moveEvent から呼ばれる。レイアウトモード時に DOSBox を追従させる。"""
        w = self._w
        if not w._is_layout_active:
            return
        import ctypes
        import ctypes.wintypes
        _r = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(int(w.winId()), ctypes.byref(_r))
        dpr = w._layout_dpr
        dos_x_log, dos_y_log = w._layout_dos_offset
        phys_x = _r.left + round(dos_x_log * dpr)
        phys_y = _r.top  + round(dos_y_log * dpr)
        dos_w, dos_h = w._layout_dos_size  # physical
        w._layout_mgr.place_dosbox(phys_x, phys_y, dos_w, dos_h)
