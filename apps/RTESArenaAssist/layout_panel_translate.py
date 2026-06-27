from __future__ import annotations
import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSplitter, QVBoxLayout, QWidget
import i18n_helper as i18n
import assist_settings as settings
_log = logging.getLogger('RTESArenaAssist')

class LayoutPanelTranslate(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.set_connected(False)
        self.apply_font_settings()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._no_conn = QLabel(i18n.tr('translate.no_connection'))
        self._no_conn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._no_conn)
        self._conn_widget = QWidget()
        hw = QHBoxLayout(self._conn_widget)
        hw.setContentsMargins(0, 0, 0, 0)
        hw.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 6, 10, 6)
        ll.setSpacing(0)
        self._ja_lbl = QLabel(i18n.tr('translate.no_data'))
        self._ja_lbl.setWordWrap(True)
        self._ja_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._ja_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        from tts_read_aloud import attach_read_aloud as _attach_ra
        import reading_highlight as _rh
        _attach_ra(self._ja_lbl, lambda: _rh.plain_of(self._ja_lbl))
        self._ja_scroll = QScrollArea()
        self._ja_scroll.setWidget(self._ja_lbl)
        self._ja_scroll.setWidgetResizable(True)
        self._ja_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._ja_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ll.addWidget(self._ja_scroll, 1)
        splitter.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 6, 10, 6)
        rl.setSpacing(0)
        self._en_lbl = QLabel(i18n.tr('translate.no_data'))
        self._en_lbl.setWordWrap(True)
        self._en_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._en_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        _attach_ra(self._en_lbl, self._en_lbl.text)
        self._en_scroll = QScrollArea()
        self._en_scroll.setWidget(self._en_lbl)
        self._en_scroll.setWidgetResizable(True)
        self._en_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._en_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rl.addWidget(self._en_scroll, 1)
        splitter.addWidget(right)
        hw.addWidget(splitter)
        root.addWidget(self._conn_widget)

    def set_connected(self, connected: bool) -> None:
        self._no_conn.setVisible(not connected)
        self._conn_widget.setVisible(connected)

    def update_translation(self, original: str, translated: str) -> None:
        _prev_orig = getattr(self, '_prev_orig', None)
        _prev_trans = getattr(self, '_prev_trans', None)
        if (original, translated) != (_prev_orig, _prev_trans):
            self._prev_orig = original
            self._prev_trans = translated
            _log.info('layout_panel_translate.update_translation (orig=%r trans=%r)', original[:160], translated[:160])
        nd = i18n.tr('translate.no_data')
        not_in = i18n.tr('translate.not_in_dict')
        import reading_highlight as _rh
        _rh.set_plain(self._ja_lbl, translated if translated else not_in)
        self._en_lbl.setText(original or nd)

    def highlight_reading(self, full_text, current_segment, prefetched_segments=None) -> None:
        import reading_highlight as _rh
        _rh.apply_reading(self._ja_lbl, current_segment, prefetched_segments)

    def apply_font_direct(self, family_ja: str, size_ja: int, family_en: str, size_en: int) -> None:
        for lbl, family, size in ((self._ja_lbl, family_ja, size_ja), (self._en_lbl, family_en, size_en)):
            style = f'font-size: {size}pt;'
            if family:
                style = f"font-family: '{family}'; " + style
            lbl.setStyleSheet(style)

    def apply_font_settings(self) -> None:
        sync = settings.get('panel_translate_font_sync', False)
        fam_ja = settings.get('panel_translate_font_family_ja', '') or ''
        size_ja = settings.get('panel_translate_font_size_ja', 14)
        fam_en = fam_ja if sync else settings.get('panel_translate_font_family_en', '') or ''
        size_en = size_ja if sync else settings.get('panel_translate_font_size_en', 12)
        self.apply_font_direct(fam_ja, size_ja, fam_en, size_en)
