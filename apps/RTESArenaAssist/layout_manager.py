
import ctypes
import ctypes.wintypes
import logging
from enum import Enum

from PySide6.QtCore import QObject, QTimer

_log = logging.getLogger("layout_manager")


class TrackMode(Enum):
    NONE                  = "none"
    ASSIST_FOLLOWS_DOSBOX = "assist_follows_dosbox"
    DOSBOX_FOLLOWS_ASSIST = "dosbox_follows_assist"


class LayoutCorner(Enum):
    TOP_LEFT     = "top_left"
    TOP_RIGHT    = "top_right"
    BOTTOM_LEFT  = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"


class LayoutForm(Enum):
    FORM_1 = "form_1"
    FORM_2 = "form_2"
    FORM_3 = "form_3"


def calc_layout_zones(
    form: "LayoutForm",
    corner: "LayoutCorner",
    dos_w: int, dos_h: int,
    lw: int, lh: int,
) -> list[tuple[int, int, int, int]]:
    if corner == LayoutCorner.TOP_LEFT:
        dx, dy = 0, 0
    elif corner == LayoutCorner.TOP_RIGHT:
        dx, dy = lw - dos_w, 0
    elif corner == LayoutCorner.BOTTOM_LEFT:
        dx, dy = 0, lh - dos_h
    else:
        dx, dy = lw - dos_w, lh - dos_h

    col_x = dos_w if dx == 0 else 0
    col_w = lw - dos_w
    row_y = dos_h if dy == 0 else 0
    row_h = lh - dos_h

    if form == LayoutForm.FORM_1:
        return [(col_x, 0, col_w, lh), (dx, row_y, dos_w, row_h)]
    elif form == LayoutForm.FORM_2:
        return [(col_x, dy, col_w, dos_h), (0, row_y, lw, row_h)]
    else:
        return [(col_x, dy, col_w, dos_h), (dx, row_y, dos_w, row_h), (col_x, row_y, col_w, row_h)]


_TRACK_MS          = 100
_SWP_NOSIZE        = 0x0001
_SWP_NOMOVE        = 0x0002
_SWP_NOZORD        = 0x0004
_SWP_NOACT         = 0x0010
_SWP_FRAMECHANGED  = 0x0020
_HWND_TOPMOST      = -1
_HWND_NOTOPMOST    = -2
_TICK_LOG_INTERVAL = 50

_RDW_INVALIDATE  = 0x0001
_RDW_UPDATENOW   = 0x0100
_RDW_ALLCHILDREN = 0x0080

_GWL_STYLE    = -16
_WS_CAPTION   = 0x00C00000
_WS_THICKFRAME = 0x00040000



def _get_rect(hwnd: int):
    r = ctypes.wintypes.RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return r.left, r.top, r.right, r.bottom
    return None


def _screen_of(widget) -> "QRect":
    from PySide6.QtWidgets import QApplication
    sc = widget.screen() if hasattr(widget, "screen") and widget.screen() else None
    if sc is None:
        sc = QApplication.screenAt(widget.geometry().center())
    if sc is None:
        sc = QApplication.primaryScreen()
    geo = sc.geometry()
    _log.debug("_screen_of: screen=%s geo=(%d,%d) %dx%d",
               sc.name(), geo.x(), geo.y(), geo.width(), geo.height())
    return geo


def _get_title(hwnd: int) -> str:
    n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _move_win(hwnd: int, x: int, y: int) -> bool:
    ret = ctypes.windll.user32.SetWindowPos(
        hwnd, None, x, y, 0, 0, _SWP_NOSIZE | _SWP_NOZORD | _SWP_NOACT
    )
    return bool(ret)


def _resize_win(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    ctypes.windll.kernel32.SetLastError(0)
    ret = ctypes.windll.user32.SetWindowPos(
        hwnd, None, x, y, w, h, _SWP_NOZORD | _SWP_NOACT
    )
    if not ret:
        err = ctypes.windll.kernel32.GetLastError()
        _log.warning("SetWindowPos failed: hwnd=%s pos=(%d,%d) size=%dx%d err=%d",
                     hwnd, x, y, w, h, err)
    return bool(ret)



class LayoutManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dosbox_hwnd: int       = 0
        self._dosbox_pid:  int       = 0
        self._track_mode: TrackMode  = TrackMode.NONE
        self._assist_win             = None

        self._last_dos: tuple | None = None
        self._last_ast: tuple | None = None
        self._tick_count             = 0

        self._embed_container        = None
        self._embed_qwin             = None
        self._embed_original_style: int | None = None

        self._layout_original_style: int | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(_TRACK_MS)
        self._timer.timeout.connect(self._tick)


    def set_dosbox_pid(self, pid: int) -> None:
        _log.info("set_dosbox_pid: %s", pid)
        self._dosbox_pid = pid
        self._dosbox_hwnd = 0

    def find_dosbox_hwnd(self) -> int:
        try:
            from screen_capture import find_hwnds_by_pid, find_hwnds_by_prefix

            if self._dosbox_pid:
                hwnds = find_hwnds_by_pid(self._dosbox_pid)
                _log.debug("find_dosbox_hwnd by PID=%s: %s", self._dosbox_pid, hwnds)
                if hwnds:
                    title = _get_title(hwnds[0])
                    rect  = _get_rect(hwnds[0])
                    _log.info("DOSBox (by PID) HWND=%s  title=%r  rect=%s",
                              hwnds[0], title, rect)
                    self._dosbox_hwnd = hwnds[0]
                    return self._dosbox_hwnd

            hwnds = find_hwnds_by_prefix("DOSBox")
            _log.debug("find_dosbox_hwnd by prefix='DOSBox': %s", hwnds)
            if hwnds:
                title = _get_title(hwnds[0])
                rect  = _get_rect(hwnds[0])
                _log.info("DOSBox (by prefix) HWND=%s  title=%r  rect=%s",
                          hwnds[0], title, rect)
                self._dosbox_hwnd = hwnds[0]
            else:
                _log.warning("DOSBox window not found (pid=%s, prefix='DOSBox')",
                             self._dosbox_pid)
                self._dosbox_hwnd = 0
        except Exception:
            _log.exception("find_dosbox_hwnd failed")
            self._dosbox_hwnd = 0
        return self._dosbox_hwnd

    def _valid(self) -> bool:
        return bool(self._dosbox_hwnd
                    and ctypes.windll.user32.IsWindow(self._dosbox_hwnd))

    def is_dosbox_found(self) -> bool:
        if not self._valid():
            self.find_dosbox_hwnd()
        return self._valid()

    def get_dosbox_hwnd(self) -> int:
        return self._dosbox_hwnd


    def place_dosbox(self, x: int, y: int, w: int, h: int) -> bool:
        if not self._valid():
            _log.warning("place_dosbox: invalid HWND — trying re-find")
            self.find_dosbox_hwnd()
        if not self._valid():
            _log.warning("place_dosbox: HWND still invalid after re-find")
            return False
        ret = _resize_win(self._dosbox_hwnd, x, y, w, h)
        _log.info("place_dosbox: pos=(%d,%d) size=%dx%d result=%s", x, y, w, h, ret)
        return ret


    def strip_dosbox_chrome(self) -> bool:
        if not self._valid():
            return False
        hwnd = self._dosbox_hwnd
        style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_STYLE)
        self._layout_original_style = style
        ctypes.windll.user32.SetWindowLongW(
            hwnd, _GWL_STYLE, style & ~(_WS_CAPTION | _WS_THICKFRAME)
        )
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORD | _SWP_NOACT | _SWP_FRAMECHANGED,
        )
        _log.info("strip_dosbox_chrome: hwnd=%s  old_style=0x%08X", hwnd, style)
        return True

    def restore_dosbox_chrome(self) -> None:
        if self._layout_original_style is None:
            return
        if self._valid():
            ctypes.windll.user32.SetWindowLongW(
                self._dosbox_hwnd, _GWL_STYLE, self._layout_original_style
            )
            ctypes.windll.user32.SetWindowPos(
                self._dosbox_hwnd, None, 0, 0, 0, 0,
                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORD | _SWP_NOACT | _SWP_FRAMECHANGED,
            )
            _log.info("restore_dosbox_chrome: hwnd=%s  style=0x%08X",
                      self._dosbox_hwnd, self._layout_original_style)
        self._layout_original_style = None

    def set_dosbox_topmost(self, enable: bool) -> None:
        if not self._valid():
            return
        insert_after = ctypes.c_void_p(_HWND_TOPMOST if enable else _HWND_NOTOPMOST)
        ctypes.windll.user32.SetWindowPos(
            self._dosbox_hwnd, insert_after, 0, 0, 0, 0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACT,
        )
        _log.info("set_dosbox_topmost: %s", enable)


    def enter_embed_mode(self, parent_widget, x: int, y: int, w: int, h: int):
        from PySide6.QtGui import QWindow
        from PySide6.QtWidgets import QWidget

        if not self._valid():
            self.find_dosbox_hwnd()
        if not self._valid():
            _log.warning("enter_embed_mode: invalid HWND")
            return None

        hwnd = self._dosbox_hwnd

        style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_STYLE)
        self._embed_original_style = style
        ctypes.windll.user32.SetWindowLongW(
            hwnd, _GWL_STYLE, style & ~(_WS_CAPTION | _WS_THICKFRAME)
        )
        ctypes.windll.user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            _SWP_NOSIZE | _SWP_NOZORD | _SWP_NOACT | _SWP_FRAMECHANGED,
        )

        self._embed_qwin = QWindow.fromWinId(hwnd)
        container = QWidget.createWindowContainer(self._embed_qwin, parent_widget)
        container.setGeometry(x, y, w, h)
        container.show()
        self._embed_container = container
        _log.info("enter_embed_mode: hwnd=%s pos=(%d,%d) size=%dx%d", hwnd, x, y, w, h)

        from PySide6.QtCore import QTimer
        def _repaint(h=hwnd, c=container):
            ctypes.windll.user32.RedrawWindow(
                h, None, None, _RDW_INVALIDATE | _RDW_UPDATENOW | _RDW_ALLCHILDREN
            )
            c.repaint()
        QTimer.singleShot(200, _repaint)

        return container

    def exit_embed_mode(self) -> None:
        if self._embed_container is not None:
            self._embed_container.hide()
            self._embed_container.setParent(None)
            self._embed_container = None
        self._embed_qwin = None

        if self._valid() and self._embed_original_style is not None:
            ctypes.windll.user32.SetWindowLongW(
                self._dosbox_hwnd, _GWL_STYLE, self._embed_original_style
            )
            ctypes.windll.user32.SetWindowPos(
                self._dosbox_hwnd, None, 0, 0, 0, 0,
                _SWP_NOSIZE | _SWP_NOZORD | _SWP_NOACT | _SWP_FRAMECHANGED,
            )
            self._embed_original_style = None
        _log.info("exit_embed_mode done")

    def nudge_dosbox(self, dx: int, dy: int) -> None:
        if not self._valid() or (dx == 0 and dy == 0):
            return
        r = _get_rect(self._dosbox_hwnd)
        if r:
            _move_win(self._dosbox_hwnd, r[0] + dx, r[1] + dy)


    def get_track_mode(self) -> TrackMode:
        return self._track_mode

    def set_track_mode(self, mode: TrackMode, assist_win):
        _log.info("set_track_mode: %s -> %s", self._track_mode.value, mode.value)
        self._track_mode = mode
        self._assist_win = assist_win
        self._reset_cache()

        if mode == TrackMode.NONE:
            self._timer.stop()
            _log.debug("track timer stopped")
            return

        if not self._valid():
            self.find_dosbox_hwnd()
        self._timer.start()
        _log.debug("track timer started (dosbox_hwnd=%s)", self._dosbox_hwnd)


    def arrange(self, dos_w: int, dos_h: int, assist_win,
                corner: LayoutCorner = LayoutCorner.TOP_LEFT) -> bool:
        _log.info("arrange: dos=%dx%d corner=%s", dos_w, dos_h, corner.value)
        try:
            if not self._valid():
                self.find_dosbox_hwnd()
            if not self._valid():
                _log.warning("arrange: DOSBox not found, aborting")
                return False

            screen = _screen_of(assist_win)
            sx, sy = screen.x(), screen.y()
            sw, sh = screen.width(), screen.height()
            _log.debug("screen: origin=(%d,%d) size=%dx%d", sx, sy, sw, sh)

            if corner == LayoutCorner.TOP_LEFT:
                dos_x, dos_y = sx, sy
            elif corner == LayoutCorner.TOP_RIGHT:
                dos_x, dos_y = sx + sw - dos_w, sy
            elif corner == LayoutCorner.BOTTOM_LEFT:
                dos_x, dos_y = sx, sy + sh - dos_h
            else:
                dos_x, dos_y = sx + sw - dos_w, sy + sh - dos_h

            _log.info("SetWindowPos DOSBox: pos=(%d,%d) size=%dx%d",
                      dos_x, dos_y, dos_w, dos_h)
            ret = _resize_win(self._dosbox_hwnd, dos_x, dos_y, dos_w, dos_h)
            after = _get_rect(self._dosbox_hwnd)
            _log.info("SetWindowPos result: %s  after=%s", ret, after)
            if not ret:
                _log.warning("arrange: SetWindowPos failed (hwnd=%s)", self._dosbox_hwnd)
                return False

            try:
                dpr = assist_win.screen().devicePixelRatio()
            except Exception:
                dpr = 1.0
            dos_w_l = max(1, int(dos_w / dpr))

            if corner in (LayoutCorner.TOP_LEFT, LayoutCorner.BOTTOM_LEFT):
                ast_x = sx + dos_w_l
            else:
                ast_x = sx
            ast_y = sy

            _log.info("move Assist: (%d,%d)  dpr=%.2f  dos_w_l=%d", ast_x, ast_y, dpr, dos_w_l)
            assist_win.move(ast_x, ast_y)

            assist_win.raise_()
            assist_win.activateWindow()
            self._reset_cache()
            return True

        except Exception:
            _log.exception("arrange failed")
            return False


    def _tick(self):
        try:
            self._tick_count += 1
            if self._track_mode != TrackMode.NONE:
                self._tick_track()
            else:
                self._timer.stop()
        except Exception:
            _log.exception("_tick failed at tick#%d", self._tick_count)

    def _tick_track(self):
        if self._assist_win is None:
            return
        if not self._valid():
            self.find_dosbox_hwnd()
            if not self._valid():
                if self._tick_count % _TICK_LOG_INTERVAL == 1:
                    _log.debug("tick#%d: DOSBox not found", self._tick_count)
                return

        r = _get_rect(self._dosbox_hwnd)
        if r is None:
            return
        dos_x, dos_y = r[0], r[1]

        if self._track_mode == TrackMode.ASSIST_FOLLOWS_DOSBOX:
            if self._last_dos is not None and (dos_x, dos_y) != self._last_dos:
                dx = dos_x - self._last_dos[0]
                dy = dos_y - self._last_dos[1]
                g  = self._assist_win.geometry()
                _log.debug("tick#%d AFD: dosbox moved (%+d,%+d)", self._tick_count, dx, dy)
                self._assist_win.move(g.left() + dx, g.top() + dy)
            elif self._tick_count % _TICK_LOG_INTERVAL == 1:
                _log.debug("tick#%d AFD: no change", self._tick_count)
            self._last_dos = (dos_x, dos_y)

        elif self._track_mode == TrackMode.DOSBOX_FOLLOWS_ASSIST:
            ast_pos = (self._assist_win.x(), self._assist_win.y())
            if self._last_ast is not None and ast_pos != self._last_ast:
                dx = ast_pos[0] - self._last_ast[0]
                dy = ast_pos[1] - self._last_ast[1]
                _log.debug("tick#%d DFA: Assist moved (%+d,%+d)", self._tick_count, dx, dy)
                _move_win(self._dosbox_hwnd, dos_x + dx, dos_y + dy)
            elif self._tick_count % _TICK_LOG_INTERVAL == 1:
                _log.debug("tick#%d DFA: no change", self._tick_count)
            self._last_ast = ast_pos

    def _reset_cache(self):
        self._last_dos = None
        self._last_ast = None


    def stop(self):
        _log.info("LayoutManager.stop()")
        self._timer.stop()
        self._track_mode = TrackMode.NONE
        self._assist_win = None
