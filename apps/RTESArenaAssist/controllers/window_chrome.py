
from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMenu, QWidget

import i18n_helper as i18n
import assist_settings as settings
from assist_constants import WIN_MIN_W, WIN_MIN_H


_INTERACTIVE_TYPES: tuple | None = None


def _is_interactive(widget) -> bool:
    global _INTERACTIVE_TYPES
    if _INTERACTIVE_TYPES is None:
        from PySide6.QtWidgets import (
            QAbstractButton, QAbstractScrollArea, QAbstractSlider,
            QLineEdit, QComboBox, QTabBar, QAbstractItemView, QSplitterHandle,
        )
        _INTERACTIVE_TYPES = (
            QAbstractButton, QAbstractScrollArea, QAbstractSlider,
            QLineEdit, QComboBox, QTabBar, QAbstractItemView, QSplitterHandle,
        )
    _NAMED_INTERACTIVE = frozenset({"AssistMapCanvas"})
    w = widget
    while w is not None:
        if isinstance(w, _INTERACTIVE_TYPES):
            return True
        if w.objectName() in _NAMED_INTERACTIVE:
            return True
        p = w.parent()
        if p is None or not isinstance(p, QWidget):
            break
        w = p
    return False


class WindowChrome:

    def __init__(self, window):
        self._w = window

        self._drag_start_pos: QPoint | None = None

        self._resize_dir: str = ""
        self._resize_start_geo: QRect | None = None
        self._resize_start_mouse: QPoint | None = None

        self._cursor_overridden: bool = False

        self._edge_cursors = {
            "n":  QCursor(Qt.CursorShape.SizeVerCursor),
            "s":  QCursor(Qt.CursorShape.SizeVerCursor),
            "e":  QCursor(Qt.CursorShape.SizeHorCursor),
            "w":  QCursor(Qt.CursorShape.SizeHorCursor),
            "nw": QCursor(Qt.CursorShape.SizeFDiagCursor),
            "se": QCursor(Qt.CursorShape.SizeFDiagCursor),
            "ne": QCursor(Qt.CursorShape.SizeBDiagCursor),
            "sw": QCursor(Qt.CursorShape.SizeBDiagCursor),
        }

        self._resize_border = 6


    def show_context_menu(self, global_pos: QPoint):
        w = self._w
        menu = QMenu(w)
        menu.addAction("⚙  " + i18n.tr("menu.settings_open"), w._open_settings)
        menu.addSeparator()
        aot = menu.addAction(i18n.tr("menu.always_on_top"))
        aot.setCheckable(True)
        aot.setChecked(settings.get("always_on_top", False))
        aot.triggered.connect(w._toggle_always_on_top)
        menu.addSeparator()
        menu.addAction(i18n.tr("menu.quit"), w.close)
        menu.exec(global_pos)


    def edge_at(self, local_pos: QPoint) -> str:
        x, y = local_pos.x(), local_pos.y()
        w, h = self._w.width(), self._w.height()
        b    = self._resize_border
        top    = y < b
        bottom = y > h - b
        left   = x < b
        right  = x > w - b
        if top    and left:  return "nw"
        if top    and right: return "ne"
        if bottom and left:  return "sw"
        if bottom and right: return "se"
        if top:    return "n"
        if bottom: return "s"
        if left:   return "w"
        if right:  return "e"
        return ""

    def do_resize(self, gpos: QPoint):
        if self._resize_start_geo is None or self._resize_start_mouse is None:
            return
        delta = gpos - self._resize_start_mouse
        geo   = QRect(self._resize_start_geo)
        d     = self._resize_dir
        dx, dy = delta.x(), delta.y()

        if "e" in d:
            geo.setRight(self._resize_start_geo.right() + dx)
        if "s" in d:
            geo.setBottom(self._resize_start_geo.bottom() + dy)
        if "w" in d:
            new_left = self._resize_start_geo.left() + dx
            if self._resize_start_geo.right() - new_left >= WIN_MIN_W:
                geo.setLeft(new_left)
        if "n" in d:
            new_top = self._resize_start_geo.top() + dy
            if self._resize_start_geo.bottom() - new_top >= WIN_MIN_H:
                geo.setTop(new_top)

        if geo.width()  < WIN_MIN_W:
            if "w" in d: geo.setLeft(geo.right()   - WIN_MIN_W)
            else:         geo.setRight(geo.left()   + WIN_MIN_W)
        if geo.height() < WIN_MIN_H:
            if "n" in d: geo.setTop(geo.bottom()   - WIN_MIN_H)
            else:         geo.setBottom(geo.top()   + WIN_MIN_H)

        self._w.setGeometry(geo)

    def set_edge_cursor(self, edge: str):
        cursor = self._edge_cursors.get(edge)
        if cursor is None:
            return
        if not self._cursor_overridden:
            QApplication.setOverrideCursor(cursor)
            self._cursor_overridden = True
        else:
            QApplication.changeOverrideCursor(cursor)

    def clear_edge_cursor(self):
        if self._cursor_overridden:
            QApplication.restoreOverrideCursor()
            self._cursor_overridden = False


    def handle_event(self, obj, event) -> bool:
        w = self._w
        if not isinstance(obj, QWidget):
            return False
        if obj is not w and not w.isAncestorOf(obj):
            return False

        et   = event.type()
        gpos = (event.globalPosition().toPoint()
                if hasattr(event, "globalPosition") else None)

        if self._resize_dir:
            if et == QEvent.Type.MouseMove and gpos:
                self.do_resize(gpos)
                return True
            if (et == QEvent.Type.MouseButtonRelease
                    and event.button() == Qt.MouseButton.LeftButton):
                self._resize_dir = ""
                self.clear_edge_cursor()
                return False

        if gpos:
            lpos = w.mapFromGlobal(gpos)
            edge = self.edge_at(lpos)
        else:
            edge = ""

        if et == QEvent.Type.MouseMove and gpos and not event.buttons():
            if edge and not _is_interactive(obj):
                self.set_edge_cursor(edge)
            else:
                self.clear_edge_cursor()

        if et == QEvent.Type.MouseButtonPress and gpos:
            btn = event.button()

            if btn == Qt.MouseButton.RightButton and not _is_interactive(obj):
                self.show_context_menu(gpos)
                return True

            if btn == Qt.MouseButton.LeftButton:
                if edge and not _is_interactive(obj):
                    self._resize_dir           = edge
                    self._resize_start_geo     = w.geometry()
                    self._resize_start_mouse   = gpos
                    self.set_edge_cursor(edge)
                    return True
                elif not _is_interactive(obj):
                    self._drag_start_pos = gpos - w.frameGeometry().topLeft()

        if (et == QEvent.Type.MouseMove
                and event.buttons() == Qt.MouseButton.LeftButton
                and self._drag_start_pos is not None
                and not self._resize_dir
                and gpos):
            w.move(gpos - self._drag_start_pos)
            return True

        if et == QEvent.Type.MouseButtonRelease:
            self._drag_start_pos = None

        return False
