from PySide6.QtCore import Qt

class ObsOverlayWindow:

    def init_obs_window(self, title: str) -> None:
        self._obs_title = title
        self._obs_mode = None
        self.set_obs_mode(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    @property
    def obs_mode(self) -> bool:
        return bool(self._obs_mode)

    def set_obs_mode(self, on: bool) -> None:
        on = bool(on)
        if self._obs_mode == on:
            return
        self._obs_mode = on
        if self.isVisible():
            self.hide()
        self.setWindowFlags((Qt.WindowType.Window if on else Qt.WindowType.Tool) | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        self.setWindowTitle(self._obs_title)

    def show_for_game(self, *, foreground: bool) -> None:
        self.setWindowOpacity(1.0 if foreground else 0.01)
        self.show()
        if foreground:
            self.raise_()

    def show_blank_or_hide(self, *, ready: bool) -> None:
        if self.obs_mode and ready:
            self.setWindowOpacity(0.01)
            self.show()
            self.update()
        else:
            self.hide()
