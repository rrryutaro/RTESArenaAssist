"""tts_read_aloud.py — 任意テキストの読み上げ補助。

テキスト表示ウィジェット（翻訳パネル／翻訳タブ／ジャーナル／ログ／呪文詳細 等）に
「その場の表示テキストを読み上げる」操作を付与する共通ヘルパー。

- 右クリックの文脈メニュー「読み上げる」（常時利用可）。
- 設定 ``tts_speaker_icon`` が ON のとき、テキスト横に小さなスピーカーボタン。

読み上げは ``TTSService.speak_now``（自動読み上げ OFF でも読む明示読み上げ）を
使う。発声テキストは ``get_text()`` で遅延取得し、その時点の表示内容を読む
（アポストロフィ除去などの整形は TTSService 側で行われる）。

読み上げ関数は起動時に ``set_speaker`` で 1 度だけ登録する（各ウィジェットへ
TTS を配線しないための単純化）。
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

import assist_settings as settings
import i18n_helper as i18n

_speak: Optional[Callable[[str], None]] = None


def set_speaker(speak: Optional[Callable[[str], None]]) -> None:
    """読み上げ関数（通常は TTSService.speak_now）を登録する。"""
    global _speak
    _speak = speak


def speaker_icon_enabled() -> bool:
    """設定でスピーカーアイコン表示が ON か。"""
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
    """ウィジェットに右クリック「読み上げる」文脈メニューを付与する。

    get_text はクリック時点の表示テキストを返すコールバック。
    """
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def _on_menu(pos) -> None:
        menu = QMenu(widget)
        act = menu.addAction(i18n.tr("tts.read_aloud", default="読み上げる"))
        act.triggered.connect(lambda: _do_speak(get_text()))
        menu.exec(widget.mapToGlobal(pos))

    widget.customContextMenuRequested.connect(_on_menu)


def make_speaker_button(get_text: Callable[[], str],
                        parent: Optional[QWidget] = None) -> QToolButton:
    """スピーカーボタンを生成して返す（呼び出し側がレイアウトへ追加する）。

    設定 ``tts_speaker_icon`` の ON/OFF に追従して表示/非表示を切替える。
    """
    btn = QToolButton(parent)
    btn.setObjectName("speakerButton")
    btn.setText("🔊")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setToolTip(i18n.tr("tts.read_aloud", default="読み上げる"))
    btn.clicked.connect(lambda: _do_speak(get_text()))
    # 親なし QToolButton を setVisible(True) するとトップレベル窓化し、生成のたびに
    # 小窓が一瞬表示される。親がある時のみ設定に従って可視化し、親が無い場合は隠した
    # まま返す（呼び出し側がレイアウト追加で reparent した後に可視化する想定）。
    btn.setVisible(parent is not None and speaker_icon_enabled())
    return btn


__all__ = [
    "set_speaker", "speaker_icon_enabled",
    "attach_read_aloud", "make_speaker_button",
]
