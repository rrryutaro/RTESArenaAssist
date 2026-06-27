from __future__ import annotations
import html as _html
import threading
from PySide6.QtCore import QObject, Qt, Signal
import assist_settings as settings
_HL_COLOR_CURRENT = '#ffd479'
_HL_COLOR_PREFETCH = '#82aaff'

def set_plain(label, text: str) -> None:
    text = text or ''
    if getattr(label, '_ra_plain', None) == text and (getattr(label, '_ra_highlighted', False) or label.text() == text):
        return
    label._ra_plain = text
    label._ra_highlighted = False
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(text)

def plain_of(label) -> str:
    if getattr(label, '_ra_highlighted', False):
        return getattr(label, '_ra_plain', '') or ''
    return label.text()

def clear_highlight(label) -> None:
    if not getattr(label, '_ra_highlighted', False):
        return
    label._ra_highlighted = False
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setText(getattr(label, '_ra_plain', '') or '')

def _esc(s: str) -> str:
    return _html.escape(s).replace('\n', '<br>')

def highlight_segment(label, segment: str, color: str=_HL_COLOR_CURRENT) -> bool:
    return highlight_marked(label, [(segment, color)])

def highlight_marked(label, marks) -> bool:
    plain = plain_of(label)
    if not plain or not marks:
        clear_highlight(label)
        return False
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for text, color in marks:
        seg = (text or '').strip()
        if not seg:
            continue
        pos = plain.find(seg, cursor)
        if pos < 0:
            pos = plain.find(seg)
        if pos < 0:
            continue
        spans.append((pos, pos + len(seg), color))
        cursor = pos + len(seg)
    if not spans:
        clear_highlight(label)
        return False
    spans.sort()
    out: list[str] = []
    last = 0
    for start, end, color in spans:
        if start < last:
            continue
        out.append(_esc(plain[last:start]))
        out.append(f'<span style="color:{color}">' + _esc(plain[start:end]) + '</span>')
        last = end
    out.append(_esc(plain[last:]))
    label._ra_plain = plain
    label._ra_highlighted = True
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setText(''.join(out))
    return True

def apply_reading(label, current_segment, prefetched_segments) -> None:
    marks: list = []
    if current_segment is not None:
        marks.append((current_segment, _HL_COLOR_CURRENT))
    marks += [(p, _HL_COLOR_PREFETCH) for p in prefetched_segments or []]
    if not marks:
        clear_highlight(label)
        return
    if not highlight_marked(label, marks):
        clear_highlight(label)

class ReadingHighlighter(QObject):
    _sig = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._targets: list = []
        self._latest: tuple = (None, None, [])
        self._lock = threading.Lock()
        self._sig.connect(self._apply, Qt.ConnectionType.QueuedConnection)

    def register(self, target) -> None:
        if target not in self._targets:
            self._targets.append(target)

    def on_segment(self, full_text, current_segment, prefetched_segments=None):
        with self._lock:
            self._latest = (full_text, current_segment, list(prefetched_segments or []))
        self._sig.emit()

    def _apply(self) -> None:
        with self._lock:
            full_text, current_segment, prefetched_segments = self._latest
        on = bool(settings.get('tts_highlight_reading', False))
        for target in list(self._targets):
            try:
                if on:
                    target(full_text, current_segment, list(prefetched_segments))
                else:
                    target(None, None, [])
            except Exception:
                pass
__all__ = ['ReadingHighlighter', 'set_plain', 'plain_of', 'clear_highlight', 'highlight_segment', 'highlight_marked', 'apply_reading', '_HL_COLOR_CURRENT', '_HL_COLOR_PREFETCH']
