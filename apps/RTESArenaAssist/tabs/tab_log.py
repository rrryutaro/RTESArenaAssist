from __future__ import annotations
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
import assist_settings as settings
import i18n_helper as i18n
from services.log_store import LogEntry, category_i18n_key, format_datetime, DEFAULT_LOG_DATETIME_FORMAT
from tts_read_aloud import attach_read_aloud, make_speaker_button

def _datetime_label(ts: float) -> str:
    if not settings.get('log_show_datetime', True):
        return ''
    fmt = settings.get('log_datetime_format', DEFAULT_LOG_DATETIME_FORMAT) or DEFAULT_LOG_DATETIME_FORMAT
    try:
        from datetime import datetime
        return format_datetime(datetime.fromtimestamp(ts), fmt)
    except Exception:
        return ''
_CARD_HEADER_COLOR = {'situation': '#e0af68', 'conversation': '#7ab8d4'}
_DEFAULT_HEADER_COLOR = '#9aa5ce'

def _log_card_style(category: str) -> str:
    head = _CARD_HEADER_COLOR.get(category, _DEFAULT_HEADER_COLOR)
    return f'QGroupBox#logCard {{ border: 1px solid #3a3a4a; border-radius: 6px; border-left: 3px solid {head}; margin-top: 10px; background: rgba(255,255,255,0.02); }}QGroupBox#logCard::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; top: 1px; padding: 0 5px; color: {head}; font-weight: bold; }}'

class LogCard(QGroupBox):

    def __init__(self, entry: LogEntry, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self.setObjectName('logCard')
        self.setStyleSheet(_log_card_style(entry.category))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self.setTitle(self._header(entry))
        body_text = entry.text or '—'
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body = QLabel(body_text)
        body.setObjectName('valueLabel')
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        import reading_highlight as _rh
        _rh.set_plain(body, body_text)
        self._body_lbl = body
        attach_read_aloud(body, lambda b=body: _rh.plain_of(b))
        body_row.addWidget(body, 1)
        body_row.addWidget(make_speaker_button(lambda t=entry.text: t, self), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(body_row)
        if settings.get('log_show_original', False) and entry.original:
            orig = QLabel(entry.original)
            orig.setObjectName('dimLabel')
            orig.setWordWrap(True)
            orig.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            attach_read_aloud(orig, lambda t=entry.original: t)
            layout.addWidget(orig)

    @staticmethod
    def _header(entry: LogEntry) -> str:
        cat_key = category_i18n_key(entry.category)
        cat = i18n.tr(cat_key) if cat_key else entry.category
        parts = [p for p in (_datetime_label(entry.ts), cat, entry.location) if p]
        return '  ·  '.join(parts)

class TabLog(QWidget):

    def __init__(self, parent: Optional[QWidget]=None) -> None:
        super().__init__(parent)
        self._store = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)
        bar = QHBoxLayout()
        self._sort_combo = QComboBox()
        self._sort_combo.addItem(i18n.tr('log.sort.newest', default='新しい順'), True)
        self._sort_combo.addItem(i18n.tr('log.sort.oldest', default='古い順'), False)
        self._sort_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self._sort_combo)
        self._filter_combo = QComboBox()
        self._filter_combo.addItem(i18n.tr('log.filter.all', default='すべて'), None)
        self._filter_combo.addItem(i18n.tr('log.category.situation', default='状況説明'), 'situation')
        self._filter_combo.addItem(i18n.tr('log.category.conversation', default='会話'), 'conversation')
        self._filter_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self._filter_combo)
        self._loc_combo = QComboBox()
        self._loc_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self._loc_combo)
        self._rebuild_location_filter()
        bar.addStretch()
        self._count_lbl = QLabel('')
        self._count_lbl.setObjectName('dimLabel')
        bar.addWidget(self._count_lbl)
        self._clear_btn = QPushButton(i18n.tr('log.clear', default='クリア'))
        self._clear_btn.clicked.connect(self._on_clear)
        bar.addWidget(self._clear_btn)
        outer.addLayout(bar)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._inner = QWidget()
        self._vbox = QVBoxLayout(self._inner)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(10)
        self._vbox.addStretch()
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, 1)
        self._empty_lbl = QLabel(i18n.tr('log.empty', default='ログはまだありません。'))
        self._empty_lbl.setObjectName('dimLabel')
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vbox.insertWidget(0, self._empty_lbl)

    def set_store(self, store) -> None:
        self._store = store
        if store is not None:
            store.set_observer(self._on_new_entry)
            store.set_changed_observer(self.refresh)
        self.refresh()

    def _newest_first(self) -> bool:
        return bool(self._sort_combo.currentData())

    def _filter_category(self) -> Optional[str]:
        return self._filter_combo.currentData()

    def _filter_location(self) -> Optional[str]:
        return self._loc_combo.currentData()

    def _rebuild_location_filter(self) -> None:
        prev = self._loc_combo.currentData()
        self._loc_combo.blockSignals(True)
        self._loc_combo.clear()
        self._loc_combo.addItem(i18n.tr('log.filter.location_all', default='場所：すべて'), None)
        locs = self._store.distinct_locations() if self._store else []
        for loc in locs:
            self._loc_combo.addItem(loc, loc)
        idx = self._loc_combo.findData(prev) if prev else 0
        self._loc_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._loc_combo.blockSignals(False)

    def _on_new_entry(self, entry: LogEntry) -> None:
        if entry.location and self._loc_combo.findData(entry.location) < 0:
            self._loc_combo.addItem(entry.location, entry.location)
        cat = self._filter_category()
        if cat and entry.category != cat:
            return
        loc = self._filter_location()
        if loc and entry.location != loc:
            return
        self._empty_lbl.setVisible(False)
        card = LogCard(entry)
        if self._newest_first():
            self._vbox.insertWidget(0, card)
        else:
            self._vbox.insertWidget(self._vbox.count() - 1, card)
        self._update_count()

    def _on_clear(self) -> None:
        if self._store is not None:
            self._store.clear()
        else:
            self.refresh()

    def refresh(self) -> None:
        self._rebuild_location_filter()
        for i in reversed(range(self._vbox.count())):
            w = self._vbox.itemAt(i).widget()
            if isinstance(w, LogCard):
                w.setParent(None)
        entries = []
        if self._store is not None:
            entries = self._store.entries(newest_first=self._newest_first(), category=self._filter_category(), location=self._filter_location())
        for idx, entry in enumerate(entries):
            self._vbox.insertWidget(idx, LogCard(entry))
        self._empty_lbl.setVisible(not entries)
        self._update_count()

    def highlight_reading(self, full_text, current_segment, prefetched_segments=None) -> None:
        import reading_highlight as _rh
        probe = current_segment
        if probe is None and prefetched_segments:
            probe = prefetched_segments[0]
        matched = False
        for i in range(self._vbox.count()):
            w = self._vbox.itemAt(i).widget()
            if not isinstance(w, LogCard):
                continue
            body = getattr(w, '_body_lbl', None)
            if body is None:
                continue
            if not matched and probe is not None and probe.strip() and (probe in _rh.plain_of(body)):
                _rh.apply_reading(body, current_segment, prefetched_segments)
                matched = True
            else:
                _rh.clear_highlight(body)

    def _update_count(self) -> None:
        n = len(self._store.entries()) if self._store else 0
        self._count_lbl.setText(i18n.tr('log.count', n=n))

    def showEvent(self, event) -> None:
        self.refresh()
        super().showEvent(event)
__all__ = ['TabLog']
