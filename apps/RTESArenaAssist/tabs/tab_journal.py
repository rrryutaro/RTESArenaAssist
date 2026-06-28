from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget, QScrollArea
import i18n_helper as i18n
from tts_read_aloud import attach_read_aloud, make_speaker_button

def _journal_card_style() -> str:
    return 'QGroupBox#journalCard { border: 1px solid #3a3a4a; border-radius: 6px; border-left: 3px solid #e0af68; margin-top: 10px; background: rgba(255,255,255,0.025); }QGroupBox#journalCard::title { subcontrol-origin: margin; subcontrol-position: top left; left: 10px; top: 1px; padding: 0 5px; color: #e0af68; font-weight: bold; }'

class JournalEntryWidget(QGroupBox):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self.setObjectName('journalCard')
        self.setStyleSheet(_journal_card_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(6)
        self._body_lbl = QLabel('—')
        self._body_lbl.setObjectName('valueLabel')
        self._body_lbl.setWordWrap(True)
        self._body_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        attach_read_aloud(self._body_lbl, self._read_text)
        body_row.addWidget(self._body_lbl, 1)
        body_row.addWidget(make_speaker_button(self._read_text, self), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body_row)

    def _read_text(self) -> str:
        import reading_highlight as _rh
        return _rh.plain_of(self._body_lbl)

    def set_entry(self, date_ja: str, body_ja: str) -> None:
        nd = i18n.tr('translate.not_in_dict')
        title = date_ja or '—'
        self.setTitle(title)
        import reading_highlight as _rh
        _rh.set_plain(self._body_lbl, body_ja or nd)

    def contains_reading_probe(self, probe: str | None) -> bool:
        if not probe or not probe.strip():
            return False
        import reading_highlight as _rh
        return probe in _rh.plain_of(self._body_lbl)

    def highlight_reading(self, current_segment, prefetched_segments=None) -> None:
        import reading_highlight as _rh
        _rh.apply_reading(self._body_lbl, current_segment, prefetched_segments)

    def clear_reading_highlight(self) -> None:
        import reading_highlight as _rh
        _rh.clear_highlight(self._body_lbl)

class TabJournal(QWidget):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self._entry_widgets: list[JournalEntryWidget] = []
        self._display_active: bool = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll_inner = QWidget()
        self._inner_layout = QVBoxLayout(self._scroll_inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(10)
        self._inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._scroll_inner)
        root.addWidget(self._scroll, 1)

    def update_journal_entries(self, entries: list[dict]) -> None:
        if not getattr(self, '_display_active', True):
            return
        while len(self._entry_widgets) < len(entries):
            w = JournalEntryWidget()
            self._entry_widgets.append(w)
            self._inner_layout.addWidget(w)
        for i, w in enumerate(self._entry_widgets):
            if i < len(entries):
                w.show()
                e = entries[i]
                w.set_entry(e.get('date_ja', '') or '', e.get('body_ja', '') or '')
            else:
                w.hide()

    def set_display_active(self, active: bool) -> None:
        self._display_active = active
        if not active:
            for w in self._entry_widgets:
                w.hide()

    def highlight_reading(self, full_text, current_segment, prefetched_segments=None) -> None:
        probe = current_segment
        if probe is None and prefetched_segments:
            probe = prefetched_segments[0]
        matched = False
        for w in self._entry_widgets:
            if not w.isVisible():
                w.clear_reading_highlight()
                continue
            if not matched and w.contains_reading_probe(probe):
                w.highlight_reading(current_segment, prefetched_segments)
                matched = True
            else:
                w.clear_reading_highlight()
