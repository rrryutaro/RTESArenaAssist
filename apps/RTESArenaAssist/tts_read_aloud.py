from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

import assist_settings as settings
import i18n_helper as i18n

_speak: Optional[Callable[[str], None]] = None


def set_speaker(speak: Optional[Callable[[str], None]]) -> None:
    global _speak
    _speak = speak


def speaker_icon_enabled() -> bool:
    return bool(settings.get("tts_speaker_icon", False))


def _do_speak(text: str) -> None:
    t = (text or "").strip()
    if not t or _speak is None:
        return
    try:
        _speak(t)
    except Exception:  # noqa: BLE001
        pass


def attach_read_aloud(widget: QWidget,
                      get_text: Callable[[], str]) -> None:
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _on_menu(pos) -> None:
        menu = QMenu(widget)
        act = menu.addAction(i18n.tr("tts.read_aloud", default="読み上げる"))
        act.triggered.connect(lambda: _do_speak(get_text()))
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(_on_menu)


def make_speaker_button(get_text: Callable[[], str],
                        parent: Optional[QWidget] = None) -> QToolButton:
    btn = QToolButton(parent)
    btn.setObjectName("speakerButton")
    btn.setText("🔊")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(i18n.tr("tts.read_aloud", default="読み上げる"))
    btn.clicked.connect(lambda: _do_speak(get_text()))
    btn.setVisible(parent is not None and speaker_icon_enabled())
    return btn


__all__ = [
    "set_speaker", "speaker_icon_enabled",
    "attach_read_aloud", "make_speaker_button",
]
