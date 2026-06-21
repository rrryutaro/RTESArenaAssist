"""
tabs/tab_screen_judge.py — screen_judge デバッグタブ

DOSBox クライアント領域のライブキャプチャ表示・
クリックで RGB 値と Arena 座標を確認し、観測点として登録する。
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

if TYPE_CHECKING:
    from controllers.screen_judge_controller import ScreenJudgeController

_LIVE_INTERVAL_MS = 1500
_DOT_RADIUS = 4


class _ClickableLabel(QLabel):
    """クリック位置を親に通知する QLabel サブクラス。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._click_cb = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_click_callback(self, cb):
        self._click_cb = cb

    def mousePressEvent(self, ev):
        if self._click_cb and ev.button() == Qt.MouseButton.LeftButton:
            self._click_cb(ev.pos())
        super().mousePressEvent(ev)


class TabScreenJudge(QWidget):
    """screen_judge デバッグ / 観測点可視化タブ。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(_LIVE_INTERVAL_MS)
        self._live_timer.timeout.connect(self._do_capture)
        self._last_pixmap: Optional[QPixmap] = None
        self._obs_points: list[dict] = []
        self._pending_point: Optional[dict] = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ─ ツールバー ─
        toolbar = QHBoxLayout()
        self._cap_btn = QPushButton("キャプチャ")
        self._cap_btn.clicked.connect(self._do_capture)
        toolbar.addWidget(self._cap_btn)

        self._live_chk = QCheckBox("ライブ")
        self._live_chk.toggled.connect(self._on_live_toggled)
        toolbar.addWidget(self._live_chk)

        toolbar.addStretch()

        self._info_lbl = QLabel("—")
        self._info_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        toolbar.addWidget(self._info_lbl)

        root.addLayout(toolbar)

        # ─ スプリッター（画像 | 観測点リスト）─
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 画像表示エリア
        img_widget = QWidget()
        img_layout = QVBoxLayout(img_widget)
        img_layout.setContentsMargins(0, 0, 0, 0)

        self._img_lbl = _ClickableLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._img_lbl.setMinimumSize(200, 100)
        self._img_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._img_lbl.set_click_callback(self._on_image_click)
        img_layout.addWidget(self._img_lbl)

        # 観測点保存ボタン
        self._save_obs_btn = QPushButton("観測点として保存")
        self._save_obs_btn.setEnabled(False)
        self._save_obs_btn.clicked.connect(self._save_pending_point)
        img_layout.addWidget(self._save_obs_btn)

        splitter.addWidget(img_widget)

        # 観測点リスト
        obs_group = QGroupBox("観測点リスト")
        obs_layout = QVBoxLayout(obs_group)

        self._obs_table = QTableWidget(0, 4)
        self._obs_table.setHorizontalHeaderLabels(["名前", "Arena座標", "RGB", "許容"])
        self._obs_table.horizontalHeader().setStretchLastSection(True)
        self._obs_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._obs_table.itemSelectionChanged.connect(self._on_obs_selection)
        obs_layout.addWidget(self._obs_table)

        obs_btn_row = QHBoxLayout()
        self._del_obs_btn = QPushButton("削除")
        self._del_obs_btn.setEnabled(False)
        self._del_obs_btn.clicked.connect(self._delete_selected_obs)
        obs_btn_row.addWidget(self._del_obs_btn)
        obs_btn_row.addStretch()
        obs_layout.addLayout(obs_btn_row)

        splitter.addWidget(obs_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, 1)

        self._set_placeholder()

    # ------------------------------------------------------------------
    # キャプチャ
    # ------------------------------------------------------------------

    def _controller(self) -> Optional["ScreenJudgeController"]:
        return getattr(self._window, "_screen_judge", None)

    def _do_capture(self) -> None:
        ctrl = self._controller()
        if ctrl is None:
            self._info_lbl.setText("screen_judge 無効")
            return
        img = ctrl.capture_now()
        if img is None:
            self._info_lbl.setText("キャプチャ失敗（DOSBox が見つかりません）")
            return

        # PIL Image → QPixmap
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qimg = QImage.fromData(buf.getvalue())
        pix = QPixmap.fromImage(qimg)
        self._last_pixmap = pix
        self._pending_point = None
        self._save_obs_btn.setEnabled(False)
        self._refresh_image()
        self._info_lbl.setText(f"{img.width}×{img.height} px")

    def _refresh_image(self) -> None:
        if self._last_pixmap is None:
            return
        pix = self._last_pixmap.copy()

        # 選択中観測点のハイライト
        selected = self._selected_obs()
        ctrl = self._controller()
        if ctrl and selected:
            mapper = ctrl.get_last_mapper()
            if mapper:
                painter = QPainter(pix)
                for obs in selected:
                    ax, ay = obs["arena_xy"]
                    cx, cy = mapper.arena_to_client(ax, ay)
                    painter.setPen(QPen(QColor(255, 255, 0), 2))
                    painter.drawEllipse(
                        QPoint(cx, cy), _DOT_RADIUS, _DOT_RADIUS
                    )
                    painter.drawText(cx + _DOT_RADIUS + 2, cy, obs.get("name", ""))
                painter.end()

        # pending 観測点（クリック位置）
        if self._pending_point:
            ctrl = self._controller()
            if ctrl:
                mapper = ctrl.get_last_mapper()
                if mapper:
                    ax, ay = self._pending_point["arena_xy"]
                    cx, cy = mapper.arena_to_client(ax, ay)
                    painter = QPainter(pix)
                    painter.setPen(QPen(QColor(255, 100, 100), 2))
                    painter.drawEllipse(
                        QPoint(cx, cy), _DOT_RADIUS, _DOT_RADIUS
                    )
                    painter.end()

        scaled = pix.scaled(
            self._img_lbl.width(),
            self._img_lbl.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_lbl.setPixmap(scaled)

    def _set_placeholder(self) -> None:
        self._img_lbl.setText("「キャプチャ」ボタンを押すと画像が表示されます")

    # ------------------------------------------------------------------
    # クリック処理
    # ------------------------------------------------------------------

    def _on_image_click(self, label_pos: QPoint) -> None:
        if self._last_pixmap is None:
            return
        ctrl = self._controller()
        if ctrl is None:
            return
        mapper = ctrl.get_last_mapper()
        if mapper is None:
            return

        # label 上の座標 → 実ピクセル座標に変換
        pix = self._last_pixmap
        lw = self._img_lbl.width()
        lh = self._img_lbl.height()
        pw = pix.width()
        ph = pix.height()
        aspect = pw / ph if ph else 1.0
        if lw / lh > aspect:
            disp_h = lh
            disp_w = int(disp_h * aspect)
        else:
            disp_w = lw
            disp_h = int(disp_w / aspect) if aspect else lh
        ox = (lw - disp_w) // 2
        oy = (lh - disp_h) // 2
        rx = label_pos.x() - ox
        ry = label_pos.y() - oy
        if rx < 0 or ry < 0 or rx >= disp_w or ry >= disp_h:
            return
        cx = round(rx * pw / disp_w)
        cy = round(ry * ph / disp_h)

        # RGB 取得
        img = ctrl.get_last_capture()
        if img is None:
            return
        r, g, b = img.getpixel((min(cx, pw - 1), min(cy, ph - 1)))

        # Arena 座標換算
        ax, ay = mapper.client_to_arena(cx, cy)

        existing_names = {p.get("name", "") for p in self._obs_points}
        i = len(self._obs_points) + 1
        while f"obs_{i}" in existing_names:
            i += 1
        self._pending_point = {
            "name": f"obs_{i}",
            "arena_xy": [ax, ay],
            "expected_rgb": [r, g, b],
            "tolerance": 20,
            "purpose": "",
        }
        self._save_obs_btn.setEnabled(True)
        self._info_lbl.setText(
            f"Arena({ax},{ay})  RGB({r},{g},{b})  クライアント({cx},{cy})"
        )
        self._refresh_image()

    # ------------------------------------------------------------------
    # 観測点操作
    # ------------------------------------------------------------------

    def _save_pending_point(self) -> None:
        if self._pending_point is None:
            return
        ctrl = self._controller()
        if ctrl is None:
            return
        ok = ctrl.get_registry().upsert(self._pending_point)
        if not ok:
            return
        self._obs_points = ctrl.get_registry().all()
        self._rebuild_obs_table()
        self._pending_point = None
        self._save_obs_btn.setEnabled(False)
        self._refresh_image()

    def _rebuild_obs_table(self) -> None:
        self._obs_table.setRowCount(0)
        for obs in self._obs_points:
            row = self._obs_table.rowCount()
            self._obs_table.insertRow(row)
            ax, ay = obs["arena_xy"]
            r, g, b = obs["expected_rgb"]
            self._obs_table.setItem(row, 0, QTableWidgetItem(obs.get("name", "")))
            self._obs_table.setItem(row, 1, QTableWidgetItem(f"({ax},{ay})"))
            self._obs_table.setItem(row, 2, QTableWidgetItem(f"({r},{g},{b})"))
            self._obs_table.setItem(row, 3, QTableWidgetItem(str(obs.get("tolerance", 20))))

    def _selected_obs(self) -> list[dict]:
        rows = {idx.row() for idx in self._obs_table.selectedIndexes()}
        return [self._obs_points[r] for r in rows if r < len(self._obs_points)]

    def _on_obs_selection(self) -> None:
        has_sel = bool(self._obs_table.selectedIndexes())
        self._del_obs_btn.setEnabled(has_sel)
        self._refresh_image()

    def _delete_selected_obs(self) -> None:
        ctrl = self._controller()
        if ctrl is None:
            return
        rows = sorted(
            {idx.row() for idx in self._obs_table.selectedIndexes()}, reverse=True
        )
        for r in rows:
            if r < len(self._obs_points):
                name = self._obs_points[r].get("name", "")
                ctrl.get_registry().delete(name)
        self._obs_points = ctrl.get_registry().all()
        self._rebuild_obs_table()
        self._refresh_image()

    # ------------------------------------------------------------------
    # ライブモード
    # ------------------------------------------------------------------

    def _on_live_toggled(self, checked: bool) -> None:
        if checked:
            self._live_timer.start()
            self._do_capture()
        else:
            self._live_timer.stop()

    # ------------------------------------------------------------------
    # リサイズ時に画像を再スケール
    # ------------------------------------------------------------------

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self._last_pixmap is not None:
            self._refresh_image()

    # ------------------------------------------------------------------
    # 公開 API（Phase C 以降から呼ばれる）
    # ------------------------------------------------------------------

    def get_obs_points(self) -> list[dict]:
        """現在登録中の観測点リストを返す。"""
        return list(self._obs_points)

    def set_obs_points(self, points: list[dict]) -> None:
        """外部（registry）から観測点リストを上書きする。"""
        self._obs_points = list(points)
        self._rebuild_obs_table()
        self._refresh_image()

    def load_from_registry(self) -> None:
        """ScreenJudgeController.get_registry() から観測点をロードして表示する。"""
        ctrl = self._controller()
        if ctrl is None:
            return
        self._obs_points = ctrl.get_registry().all()
        self._rebuild_obs_table()
        self._refresh_image()
