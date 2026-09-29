import html
import os
from PySide6.QtCore import QStandardPaths, QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout, QWidget
import assist_settings as settings
import i18n_helper as i18n
from assist_constants import Dark
_MODE_SIMPLE = 'simple'
_MODE_FULL = 'full'
_MODE_ASSIST = 'assist'
_MODE_BUTTON_WIDTH = 56
_LINK_COLOR = Dark.ACCENT

def _link(href: str, text: str) -> str:
    return f'<a href="{href}" style="color:{_LINK_COLOR}">{html.escape(text)}</a>'

def _list_docs(mode: str) -> list[tuple[str, str]]:
    if mode == _MODE_FULL:
        from services import manual_pack
        return manual_pack.list_installed_docs(i18n.current_lang())
    from services import manual_pages
    return manual_pages.list_pages(mode)

def _language_name(code: str) -> str:
    for entry in i18n.available_languages():
        if entry.get('code') == code:
            return entry.get('display_name') or code
    return code

def _doc_label(stem: str, mode: str) -> str:
    key = f'manual.doc.{mode}.{stem}'
    label = i18n.tr(key)
    if label == key:
        key2 = f'manual.doc.{stem}'
        label2 = i18n.tr(key2)
        return stem if label2 == key2 else label2
    return label

class _PackWorker(QThread):
    progressed = Signal(str, int, int)
    finished_ok = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, lang: str, path: str | None=None, parent=None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._path = path

    def run(self) -> None:
        from services import manual_pack

        def progress(kind: str, done: int, total: int) -> None:
            self.progressed.emit(kind, done, total)
        try:
            if self._path:
                state = manual_pack.import_pack_file(self._path, self._lang, progress)
            else:
                state = manual_pack.rebuild_from_cache(self._lang, progress)
        except manual_pack.PackError as exc:
            self.failed.emit(exc.code, exc.detail)
            return
        except Exception:
            self.failed.emit('write', '')
            return
        self.finished_ok.emit(state)

class TabManual(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode: str = _MODE_SIMPLE
        self._docs: list[tuple[str, str]] = []
        self._pack_worker: _PackWorker | None = None
        self._pack_running = False
        self._matches: list[int] = []
        self._match_idx: int = 0
        self._revealed: set[str] = set()
        self._build_ui()
        self._load_docs()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)
        toolbar = QWidget()
        toolbar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(0, 0, 0, 0)
        toolbar_row.setSpacing(4)
        self._btn_simple = QPushButton(i18n.tr('manual.mode.simple'))
        self._btn_full = QPushButton(i18n.tr('manual.mode.full'))
        self._btn_assist = QPushButton(i18n.tr('manual.mode.assist'))
        self._mode_buttons = (self._btn_simple, self._btn_full, self._btn_assist)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        for btn in self._mode_buttons:
            btn.setCheckable(True)
            btn.setFixedWidth(_MODE_BUTTON_WIDTH)
            self._mode_group.addButton(btn)
        self._btn_simple.setChecked(True)
        self._btn_simple.clicked.connect(lambda: self._switch_mode(_MODE_SIMPLE))
        self._btn_full.clicked.connect(lambda: self._switch_mode(_MODE_FULL))
        self._btn_assist.clicked.connect(lambda: self._switch_mode(_MODE_ASSIST))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(i18n.tr('manual.search_placeholder'))
        self._search_edit.setMaximumWidth(180)
        self._search_edit.returnPressed.connect(self._search)
        self._prev_btn = QPushButton(i18n.tr('manual.prev'))
        self._next_btn = QPushButton(i18n.tr('manual.next'))
        self._prev_btn.setFixedWidth(60)
        self._next_btn.setFixedWidth(60)
        self._prev_btn.clicked.connect(self._prev_match)
        self._next_btn.clicked.connect(self._next_match)
        self._match_lbl = QLabel('')
        self._match_lbl.setMinimumWidth(56)
        self._match_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for btn in self._mode_buttons:
            toolbar_row.addWidget(btn)
        toolbar_row.addSpacing(8)
        toolbar_row.addWidget(self._search_edit)
        toolbar_row.addWidget(self._prev_btn)
        toolbar_row.addWidget(self._next_btn)
        toolbar_row.addWidget(self._match_lbl)
        self._guide_chk = QCheckBox(i18n.tr('manual.guide.show'))
        self._guide_chk.setChecked(bool(settings.get('manual_show_guide', False)))
        self._guide_chk.toggled.connect(self._on_guide_toggled)
        toolbar_row.addWidget(self._guide_chk)
        toolbar_row.addStretch()
        root.addWidget(toolbar)
        self._pack_note = QLabel('')
        self._pack_note.setWordWrap(True)
        self._pack_note.setTextFormat(Qt.TextFormat.RichText)
        self._pack_note.linkActivated.connect(self._on_pack_link)
        self._pack_note.hide()
        root.addWidget(self._pack_note)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._nav = QListWidget()
        self._nav.setObjectName('manualNav')
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setWordWrap(True)
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        splitter.addWidget(self._nav)
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setOpenLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        splitter.addWidget(self._browser)
        splitter.setSizes([140, 360])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)
        self._prev_btn.setEnabled(False)
        self._next_btn.setEnabled(False)

    def _fit_mode_buttons(self) -> None:
        width = max(_MODE_BUTTON_WIDTH, *(btn.sizeHint().width() for btn in self._mode_buttons))
        for btn in self._mode_buttons:
            btn.setFixedWidth(width)

    def showEvent(self, event) -> None:
        self._fit_mode_buttons()
        super().showEvent(event)

    def _switch_mode(self, mode: str):
        if self._mode == mode:
            return
        self._mode = mode
        current_row = self._nav.currentRow()
        self._load_docs()
        if current_row < self._nav.count():
            self._nav.setCurrentRow(current_row)

    def _guide_enabled(self) -> bool:
        return bool(self._mode == _MODE_SIMPLE and getattr(self, '_guide_chk', None) and self._guide_chk.isChecked())

    def _on_guide_toggled(self, on: bool) -> None:
        settings.set_val('manual_show_guide', bool(on))
        self._revealed = set()
        self._guide_place = None
        self._load_docs()

    def _on_anchor_clicked(self, url) -> None:
        import riddle_guide
        text = url.toString()
        if text.startswith('rtesaa:'):
            self._on_pack_link(text)
            return
        place = riddle_guide.parse_place(text)
        if place is not None:
            self._guide_place = None if place < 0 else place
            if self._guide_place is None:
                self._refresh_guide_cache()
            self._show_guide()
            return
        key = riddle_guide.parse_reveal(text)
        if key is None:
            return
        self._revealed.add(key)
        self._show_guide()

    def _guide_groups(self):
        import riddle_guide
        from services import riddle_store
        entries = riddle_guide.collect_entries(riddle_store.get_store().seen_entries())
        return riddle_guide.group_entries(entries)

    def _refresh_guide_cache(self) -> None:
        self._guide_cache = self._guide_groups() if self._guide_enabled() else []

    def _show_guide(self) -> None:
        import riddle_guide
        groups = getattr(self, '_guide_cache', None) or []
        place_idx = getattr(self, '_guide_place', None)
        if place_idx is None or not groups:
            self._browser.setHtml(riddle_guide.build_index_html(groups))
        else:
            idx = max(0, min(place_idx, len(groups) - 1))
            place, entries = groups[idx]
            self._browser.setHtml(riddle_guide.build_html(entries, getattr(self, '_revealed', set()), heading=place, with_back=True))
        self._matches = []
        self._match_idx = 0
        self._update_match_label()

    def _load_docs(self):
        self._docs = _list_docs(self._mode)
        self._nav.clear()
        self._update_pack_note()
        if not self._docs:
            if self._mode == _MODE_FULL:
                self._show_full_pack_page()
            else:
                self._browser.setPlainText(i18n.tr('manual.no_manual'))
            return
        for stem, _ in self._docs:
            self._nav.addItem(QListWidgetItem(_doc_label(stem, self._mode)))
        self._refresh_guide_cache()
        if self._guide_enabled():
            self._nav.addItem(QListWidgetItem(i18n.tr('manual.guide.title')))
        self._nav.setCurrentRow(0)

    def _on_nav_changed(self, row: int):
        if row < 0:
            return
        if row >= len(self._docs):
            if self._guide_enabled():
                self._guide_place = None
                self._refresh_guide_cache()
                self._show_guide()
            return
        _, rel = self._docs[row]
        if os.path.isabs(rel):
            self._browser.setSource(QUrl.fromLocalFile(rel))
        else:
            import app_resources
            self._browser.setSource(QUrl.fromLocalFile(app_resources.resource_fs_path(rel)))
        self._matches = []
        self._match_idx = 0
        self._update_match_label()

    def _pack_busy(self) -> bool:
        return self._pack_running

    def _show_full_pack_page(self, message: str='') -> None:
        from services import manual_pack
        esc = html.escape
        lang = i18n.current_lang()
        parts = [f"<h2>{esc(i18n.tr('manual.pack.title'))}</h2>"]
        if manual_pack.offers_pack(lang):
            parts.append(f"<p>{esc(i18n.tr('manual.pack.intro'))}</p>")
            if self._pack_busy():
                parts.append(f"<p><b>{esc(message or i18n.tr('manual.pack.working'))}</b></p>")
            else:
                file = manual_pack.pack_file_name(lang)
                parts.append('<p>' + _link('rtesaa:manual-open-page', i18n.tr('manual.pack.open_page')) + '</p>')
                parts.append(f"<p>{esc(i18n.tr('manual.pack.import_hint', file=file))}</p>")
                parts.append('<p>' + _link('rtesaa:manual-import', i18n.tr('manual.pack.import')) + '</p>')
                if message:
                    parts.append(f'<p><b>{esc(message)}</b></p>')
        guide, _ = manual_pack.find_docs_pdf('player_guide')
        quick, _ = manual_pack.find_docs_pdf('quick_reference')
        if guide is not None or quick is not None:
            parts.append(f"<p>{esc(i18n.tr('manual.pack.pdf_intro'))}</p><ul>")
            if guide is not None:
                parts.append('<li>' + _link('rtesaa:open-pdf:player_guide', i18n.tr('manual.pack.open_player_guide')) + '</li>')
            if quick is not None:
                parts.append('<li>' + _link('rtesaa:open-pdf:quick_reference', i18n.tr('manual.pack.open_quick_ref')) + '</li>')
            parts.append('</ul>')
        else:
            parts.append(f"<p>{esc(i18n.tr('manual.pack.no_docs'))}</p>")
        self._browser.setHtml(''.join(parts))

    def _on_pack_link(self, link: str) -> None:
        if link == 'rtesaa:manual-import':
            self._choose_and_import()
        elif link == 'rtesaa:manual-rebuild':
            self._start_pack_install(None)
        elif link == 'rtesaa:manual-open-page':
            from services.public_links import MANUAL_DOWNLOAD_URL
            QDesktopServices.openUrl(QUrl(MANUAL_DOWNLOAD_URL))
        elif link.startswith('rtesaa:open-pdf:'):
            self._open_docs_pdf(link.split(':', 2)[2])

    def _choose_and_import(self) -> None:
        if self._pack_busy():
            return
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or ''
        path, _ = QFileDialog.getOpenFileName(self, i18n.tr('manual.pack.import_title'), start, f"{i18n.tr('manual.pack.file_filter')} (*.zip)")
        if path:
            self._start_pack_install(path)

    def _open_docs_pdf(self, key: str) -> None:
        from services import manual_pack
        if key not in manual_pack.DOCS_PDFS:
            return
        path, _ = manual_pack.find_docs_pdf(key)
        if path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _start_pack_install(self, path: str | None) -> None:
        if self._pack_busy():
            return
        self._pack_running = True
        self._pack_worker = _PackWorker(i18n.current_lang(), path, self)
        self._pack_worker.progressed.connect(self._on_pack_progress)
        self._pack_worker.finished_ok.connect(self._on_pack_done)
        self._pack_worker.failed.connect(self._on_pack_failed)
        self._pack_worker.start()
        self._show_pack_message(i18n.tr('manual.pack.working'))

    def _show_pack_message(self, msg: str) -> None:
        if self._mode != _MODE_FULL:
            return
        if not self._docs:
            self._show_full_pack_page(msg)
        else:
            self._pack_note.setText(f'<b>{html.escape(msg)}</b>')
            self._pack_note.show()

    def _on_pack_progress(self, _kind: str, done: int, total: int) -> None:
        self._show_pack_message(i18n.tr('manual.pack.step_images', done=done, total=total))

    def _on_pack_done(self, _state: dict) -> None:
        self._pack_running = False
        if self._mode == _MODE_FULL:
            self._load_docs()

    def _on_pack_failed(self, code: str, detail: str) -> None:
        self._pack_running = False
        key = {'unreadable': 'manual.pack.failed_unreadable', 'invalid': 'manual.pack.failed_invalid', 'lang': 'manual.pack.failed_lang'}.get(code, 'manual.pack.failed_write')
        msg = i18n.tr(key, lang=_language_name(detail))
        if self._mode == _MODE_FULL and self._docs:
            self._update_pack_note(msg)
        else:
            self._show_pack_message(msg)

    def _update_pack_note(self, message: str='') -> None:
        if self._mode != _MODE_FULL:
            self._pack_note.hide()
            return
        from services import manual_pack
        state = manual_pack.installed_state(i18n.current_lang())
        if not state:
            self._pack_note.hide()
            return
        esc = html.escape
        lines = []
        if message:
            lines.append(f'<b>{esc(message)}</b>')
        if state.get('images') != manual_pack.IMAGES_OK:
            key = 'manual.pack.no_images_pdf' if state.get('images') == manual_pack.IMAGES_NO_PDF else 'manual.pack.no_images_mismatch'
            lines.append(f'{esc(i18n.tr(key))} ' + _link('rtesaa:manual-rebuild', i18n.tr('manual.pack.rebuild')))
        lines.append(esc(i18n.tr('manual.pack.installed', updated=state.get('updated', ''))) + ' ' + _link('rtesaa:manual-open-page', i18n.tr('manual.pack.open_page')) + ' | ' + _link('rtesaa:manual-import', i18n.tr('manual.pack.import')))
        self._pack_note.setText('<br>'.join(lines))
        self._pack_note.show()

    def _search(self):
        keyword = self._search_edit.text().strip()
        if not keyword:
            return
        doc = self._browser.document()
        cursor = doc.find(keyword)
        positions = []
        while not cursor.isNull():
            positions.append(cursor.position())
            cursor = doc.find(keyword, cursor)
        self._matches = positions
        self._match_idx = 0
        if positions:
            self._go_to_match(0)
        self._update_match_label()
        self._prev_btn.setEnabled(len(positions) > 1)
        self._next_btn.setEnabled(len(positions) > 1)

    def _prev_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx - 1) % len(self._matches)
        self._go_to_match(self._match_idx)
        self._update_match_label()

    def _next_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx + 1) % len(self._matches)
        self._go_to_match(self._match_idx)
        self._update_match_label()

    def _go_to_match(self, idx: int):
        from PySide6.QtGui import QTextCursor
        doc = self._browser.document()
        cursor = QTextCursor(doc)
        cursor.setPosition(self._matches[idx])
        self._browser.setTextCursor(cursor)
        self._browser.ensureCursorVisible()

    def _update_match_label(self):
        if not self._matches:
            kw = self._search_edit.text().strip()
            self._match_lbl.setText(i18n.tr('manual.no_match') if kw else '')
        else:
            self._match_lbl.setText(i18n.tr('manual.match_count', current=self._match_idx + 1, total=len(self._matches)))
