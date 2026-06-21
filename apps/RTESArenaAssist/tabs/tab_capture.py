"""
tab_capture.py — スクリーンキャプチャビューアタブ
"""

import datetime
import json
import os

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

import assist_settings as settings
import i18n_helper as i18n


class _ZoomableImage(QGraphicsView):
    """ホイールズーム・ドラッグパン対応の画像ビュー。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMinimumHeight(80)
        self._has_image = False

    def set_pixmap(self, pix: QPixmap) -> None:
        self._scene.clear()
        self._has_image = False
        if pix and not pix.isNull():
            self._scene.addPixmap(pix)
            self._scene.setSceneRect(pix.rect().toRectF())
            self._has_image = True
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        else:
            self._scene.setSceneRect(0, 0, 1, 1)

    def set_text(self, text: str) -> None:
        self._scene.clear()
        self._has_image = False
        item = self._scene.addText(text)
        self._scene.setSceneRect(item.boundingRect())

    def showEvent(self, event):
        super().showEvent(event)
        if self._has_image:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, factor)


class TabCapture(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cap_dir = ""
        self._caps: list[int] = []
        self._locks: set[int] = set()
        self._build_ui()

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── ディレクトリバー ──────────────────────────────────
        bar = QHBoxLayout()
        self._dir_lbl = QLabel("—")
        self._dir_lbl.setObjectName("dimLabel")
        bar.addWidget(self._dir_lbl, 1)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setFixedSize(28, 28)
        btn_refresh.setObjectName("winCtrlBtn")
        btn_refresh.setToolTip(i18n.tr("capture.refresh"))
        btn_refresh.clicked.connect(self.refresh)
        bar.addWidget(btn_refresh)
        root.addLayout(bar)

        # ── スプリッター（リスト + プレビュー） ───────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左: リスト + ロック/削除ボタン
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(2)

        self._list = QListWidget()
        self._list.setMinimumWidth(140)
        self._list.setMaximumWidth(200)
        self._list.currentRowChanged.connect(self._on_select)
        self._list.installEventFilter(self)
        ll.addWidget(self._list, 1)

        # ボタン行はキャプチャ無し時に非表示にする（_set_empty で制御）
        self._btn_row_w = QWidget()
        btn_row = QHBoxLayout(self._btn_row_w)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(2)
        self._lock_btn = QPushButton("🔒")
        self._lock_btn.setFixedHeight(26)
        self._lock_btn.setToolTip("ロック")
        self._lock_btn.setEnabled(False)
        self._lock_btn.clicked.connect(self._toggle_lock)
        self._del_btn = QPushButton("🗑")
        self._del_btn.setFixedHeight(26)
        self._del_btn.setToolTip("削除")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._delete_cap)
        self._del_all_btn = QPushButton("🗑全")
        self._del_all_btn.setFixedHeight(26)
        self._del_all_btn.setToolTip("ロックされていないキャプチャをすべて削除")
        self._del_all_btn.setEnabled(False)
        self._del_all_btn.clicked.connect(self._delete_all_unlocked)
        btn_row.addWidget(self._lock_btn)
        btn_row.addWidget(self._del_btn)
        btn_row.addWidget(self._del_all_btn)
        ll.addWidget(self._btn_row_w)

        splitter.addWidget(left)

        # 右: タイムスタンプ + 画像
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(2)

        self._ts_lbl = QLabel("")
        self._ts_lbl.setObjectName("dimLabel")
        rl.addWidget(self._ts_lbl)

        img_splitter = QSplitter(Qt.Orientation.Vertical)
        img_splitter.setChildrenCollapsible(False)

        game_pane = QWidget()
        gpl = QVBoxLayout(game_pane)
        gpl.setContentsMargins(0, 0, 0, 0)
        gpl.setSpacing(1)
        lbl_game = QLabel(i18n.tr("capture.preview_game"))
        lbl_game.setObjectName("subLabel")
        self._img_game = _ZoomableImage()
        gpl.addWidget(lbl_game)
        gpl.addWidget(self._img_game, 1)
        img_splitter.addWidget(game_pane)

        viewer_pane = QWidget()
        vpl = QVBoxLayout(viewer_pane)
        vpl.setContentsMargins(0, 0, 0, 0)
        vpl.setSpacing(1)
        lbl_viewer = QLabel(i18n.tr("capture.preview_viewer"))
        lbl_viewer.setObjectName("subLabel")
        self._img_viewer = _ZoomableImage()
        vpl.addWidget(lbl_viewer)
        vpl.addWidget(self._img_viewer, 1)
        img_splitter.addWidget(viewer_pane)

        self._viewer_pane = viewer_pane
        rl.addWidget(img_splitter, 1)

        splitter.addWidget(right)
        splitter.setSizes([160, 500])

        root.addWidget(splitter, 1)

        # キャプチャなしメッセージ
        self._empty_lbl = QLabel(i18n.tr("capture.no_captures"))
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setObjectName("dimLabel")
        root.addWidget(self._empty_lbl)

        self._set_empty(True)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def set_cap_dir(self, cap_dir: str) -> None:
        self._cap_dir = cap_dir
        self._dir_lbl.setText(cap_dir or "—")
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        self._caps = []
        self._img_game.set_text(i18n.tr("capture.no_image"))
        self._img_viewer.set_text(i18n.tr("capture.no_image"))
        self._ts_lbl.setText("")
        self._lock_btn.setEnabled(False)
        self._del_btn.setEnabled(False)
        self._del_all_btn.setEnabled(False)

        if not self._cap_dir or not os.path.isdir(self._cap_dir):
            self._set_empty(True)
            return

        self._load_locks()

        nums: set[int] = set()
        try:
            for name in os.listdir(self._cap_dir):
                if name.startswith("cap_") and name.endswith(".png"):
                    part = name[4:].split("_")[0]
                    try:
                        nums.add(int(part))
                    except ValueError:
                        pass
        except OSError:
            pass

        self._caps = sorted(nums, reverse=True)
        if not self._caps:
            self._set_empty(True)
            return

        self._set_empty(False)
        for n in self._caps:
            self._list.addItem(self._make_item(n))
        self._list.setCurrentRow(0)
        # 一括削除はロックされていないキャプチャが 1 件以上あれば有効
        self._del_all_btn.setEnabled(any(n not in self._locks for n in self._caps))

    # ------------------------------------------------------------------
    # ロック管理
    # ------------------------------------------------------------------

    def _locks_path(self) -> str:
        return os.path.join(self._cap_dir, "cap_locks.json")

    def _load_locks(self) -> None:
        try:
            with open(self._locks_path(), encoding="utf-8") as f:
                data = json.load(f)
            self._locks = set(data.get("locked", []))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._locks = set()

    def _save_locks(self) -> None:
        if not self._cap_dir:
            return
        try:
            with open(self._locks_path(), "w", encoding="utf-8") as f:
                json.dump({"locked": sorted(self._locks)}, f)
        except OSError:
            pass

    def _toggle_lock(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._caps):
            return
        n = self._caps[row]
        if n in self._locks:
            self._locks.discard(n)
        else:
            self._locks.add(n)
        self._save_locks()
        self._list.takeItem(row)
        self._list.insertItem(row, self._make_item(n))
        self._list.setCurrentRow(row)
        self._update_buttons(n)

    # ------------------------------------------------------------------
    # 削除
    # ------------------------------------------------------------------

    def _delete_cap(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._caps):
            return
        n = self._caps[row]
        if n in self._locks:
            return

        if settings.get("capture_delete_confirm", True):
            msg = QMessageBox(self)
            msg.setWindowTitle("削除確認")
            msg.setText(f"Cap #{n:03d} を削除しますか？\nこの操作は元に戻せません。")
            msg.setIcon(QMessageBox.Icon.Question)
            yes_btn = msg.addButton(QMessageBox.StandardButton.Yes)
            no_btn  = msg.addButton(QMessageBox.StandardButton.No)
            msg.setDefaultButton(yes_btn)
            msg.setEscapeButton(no_btn)
            no_confirm_cb = QCheckBox("次回から確認しない")
            msg.setCheckBox(no_confirm_cb)
            msg.exec()
            if msg.clickedButton() is not yes_btn:
                return
            if no_confirm_cb.isChecked():
                settings.set_val("capture_delete_confirm", False)

        for suffix in ("_layout.png", "_game.png", "_viewer.png"):
            path = os.path.join(self._cap_dir, f"cap_{n:03d}{suffix}")
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._locks.discard(n)
        self._save_locks()
        self.refresh()

    def _delete_all_unlocked(self) -> None:
        """ロックされていないキャプチャを一括削除する。

        確認ダイアログは設定 capture_delete_confirm に関わらず必ず表示する
        （取り返しのつかない一括操作のため）。ロック中のキャプチャは保持する。
        """
        if not self._cap_dir or not self._caps:
            return
        targets = [n for n in self._caps if n not in self._locks]
        if not targets:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("一括削除確認")
        locked = len(self._caps) - len(targets)
        text = (f"ロックされていないキャプチャ {len(targets)} 件を削除しますか？\n"
                f"ロック中: {locked} 件は保持されます。\n"
                f"この操作は元に戻せません。")
        msg.setText(text)
        msg.setIcon(QMessageBox.Icon.Warning)
        yes_btn = msg.addButton("削除", QMessageBox.ButtonRole.DestructiveRole)
        no_btn  = msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(no_btn)
        msg.setEscapeButton(no_btn)
        msg.exec()
        if msg.clickedButton() is not yes_btn:
            return

        deleted = 0
        for n in targets:
            ok = True
            for suffix in ("_layout.png", "_game.png", "_viewer.png"):
                path = os.path.join(self._cap_dir, f"cap_{n:03d}{suffix}")
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        ok = False
            if ok:
                deleted += 1
                self._locks.discard(n)
        self._save_locks()
        self.refresh()
        # 完了メッセージ（ステータスバーがあれば、なければダイアログで省略）
        try:
            self.window().statusBar().showMessage(
                f"キャプチャを {deleted} 件削除しました（ロック {locked} 件保持）", 5000)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _cap_timestamp(self, n: int) -> str:
        for suffix in ("_layout.png", "_game.png", "_viewer.png"):
            path = os.path.join(self._cap_dir, f"cap_{n:03d}{suffix}")
            if os.path.isfile(path):
                try:
                    mtime = os.path.getmtime(path)
                    dt = datetime.datetime.fromtimestamp(mtime)
                    return dt.strftime("%Y-%m-%d %H:%M")
                except OSError:
                    pass
        return ""

    def _make_item(self, n: int) -> QListWidgetItem:
        lock = "🔒 " if n in self._locks else ""
        item = QListWidgetItem(f"{lock}#{n:03d}")
        item.setData(Qt.ItemDataRole.UserRole, n)
        return item

    def eventFilter(self, obj, event):
        if obj is self._list and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Delete:
                self._delete_cap()
                return True
            if key == Qt.Key.Key_Space:
                self._toggle_lock()
                return True
        return super().eventFilter(obj, event)

    def _set_empty(self, empty: bool) -> None:
        self._empty_lbl.setVisible(empty)
        self._list.setVisible(not empty)
        # ロック/削除/一括削除のボタン列はキャプチャがある時だけ表示する
        # （無いと中央に浮いて見えるのを避けるため）
        self._btn_row_w.setVisible(not empty)

    def _update_buttons(self, n: int) -> None:
        locked = n in self._locks
        self._lock_btn.setText("🔓" if locked else "🔒")
        self._lock_btn.setToolTip("ロック解除" if locked else "ロック")
        self._del_btn.setEnabled(not locked)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._caps):
            self._img_game.set_text(i18n.tr("capture.no_image"))
            self._img_viewer.set_text(i18n.tr("capture.no_image"))
            self._ts_lbl.setText("")
            self._lock_btn.setEnabled(False)
            self._del_btn.setEnabled(False)
            return

        n = self._caps[row]
        ts = self._cap_timestamp(n)
        self._ts_lbl.setText(f"Cap #{n:03d}  {ts}" if ts else f"Cap #{n:03d}")
        self._lock_btn.setEnabled(True)
        self._update_buttons(n)

        layout_path = os.path.join(self._cap_dir, f"cap_{n:03d}_layout.png")
        if os.path.isfile(layout_path):
            pix = QPixmap(layout_path)
            self._img_game.set_pixmap(pix)
            self._viewer_pane.setVisible(False)
        else:
            self._viewer_pane.setVisible(True)
            self._load_image(self._img_game,
                             os.path.join(self._cap_dir, f"cap_{n:03d}_game.png"))
            self._load_image(self._img_viewer,
                             os.path.join(self._cap_dir, f"cap_{n:03d}_viewer.png"))

    def _load_image(self, view: _ZoomableImage, path: str) -> None:
        if not os.path.isfile(path):
            view.set_text(i18n.tr("capture.no_image"))
            return
        pix = QPixmap(path)
        if pix.isNull():
            view.set_text(i18n.tr("capture.no_image"))
            return
        view.set_pixmap(pix)
