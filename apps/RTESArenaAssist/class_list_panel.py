from __future__ import annotations
import os
import re
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout, QWidget
import i18n_helper as i18n
_MANUAL_SIMPLE = os.path.join(os.path.dirname(__file__), 'manual', 'simple')
_MANUAL_FULL = os.path.join(os.path.dirname(__file__), 'manual', 'full')
_CLASS_DOC = '05_classes.html'
_MANUAL_BASE = _MANUAL_SIMPLE
CLASS_LIST_ORDER: list[str] = ['Acrobat', 'Archer', 'Assassin', 'Barbarian', 'Bard', 'Battlemage', 'Burglar', 'Healer', 'Knight', 'Mage', 'Monk', 'Nightblade', 'Ranger', 'Rogue', 'Sorceror', 'Spellsword', 'Thief', 'Warrior']

def _gloss_key(canonical: str) -> str:
    return f'class.gloss.{canonical.lower()}'

def class_display_name(canonical: str) -> str:
    name = i18n.value('classes', canonical) or canonical
    gloss = i18n.text_opt(_gloss_key(canonical)) or ''
    if gloss:
        return i18n.text('class_list.name_with_gloss_format').replace('{name}', name).replace('{gloss}', gloss)
    return name

def _class_name_candidates(canonical: str) -> list[str]:
    out: list[str] = []
    for name in (i18n.value('classes', canonical), i18n.value_in('classes', canonical, 'ja')):
        if name and name not in out:
            out.append(name)
    gloss = i18n.lang_value_in(_gloss_key(canonical), 'ja')
    if gloss and gloss not in out:
        out.append(gloss)
    return out
_NAME_GLOSS_RE = re.compile('^(.*?)\\s*[（(]([^（）()]+)[）)]$')

def resolve_class_from_display_name(text: str) -> Optional[str]:
    cleaned = (text or '').strip()
    if not cleaned:
        return None
    base = gloss = None
    m = _NAME_GLOSS_RE.match(cleaned)
    if m:
        base = m.group(1).strip()
        gloss = m.group(2).strip()
    for canonical in CLASS_LIST_ORDER:
        names = _class_name_candidates(canonical)
        if cleaned in names:
            return canonical
        if base and base in names:
            return canonical
        if gloss and gloss in names:
            return canonical
    return None

class _ClassRow(QFrame):
    clicked = Signal(str)

    def __init__(self, en: str, display_name: str, parent=None):
        super().__init__(parent)
        self._en = en
        self._highlighted = False
        self.setObjectName('classRow')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)
        self._en_lbl = QLabel(en)
        self._en_lbl.setMinimumWidth(96)
        self._en_lbl.setMaximumWidth(96)
        self._en_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._en_lbl.setObjectName('classRowEn')
        layout.addWidget(self._en_lbl)
        self._name_lbl = QLabel(display_name)
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._name_lbl.setObjectName('classRowJa')
        layout.addWidget(self._name_lbl, 1)
        self._apply_style()

    def class_en(self) -> str:
        return self._en

    def set_display_name(self, display_name: str) -> None:
        self._name_lbl.setText(display_name)

    def is_highlighted(self) -> bool:
        return self._highlighted

    def set_highlighted(self, on: bool) -> None:
        if self._highlighted == on:
            return
        self._highlighted = on
        self._apply_style()

    def _apply_style(self) -> None:
        if self._highlighted:
            self.setStyleSheet('QFrame#classRow {  background: #2a4a6a;  border: 1px solid #5bc0de;  border-radius: 4px;}QFrame#classRow QLabel {  color: #ffe680;  font-weight: bold;  background: transparent;  border: none;}')
        else:
            self.setStyleSheet('QFrame#classRow {  background: #1c2e3f;  border: 1px solid #2a4258;  border-radius: 4px;}QFrame#classRow:hover {  background: #233b52;  border-color: #5bc0de;}QFrame#classRow QLabel {  background: transparent;  border: none;}QFrame#classRow QLabel#classRowEn {  color: #c9d1e0;}QFrame#classRow QLabel#classRowJa {  color: #a0c4d8;}')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._en)
        super().mousePressEvent(event)
_NPC_CLASS_NAME_LOOKUP: dict[str, str] = {name.lower(): name for name in CLASS_LIST_ORDER}
_NPC_CLASS_NAME_LOOKUP.update({'battle mage': 'Battlemage', 'sorcerer': 'Sorceror'})

def resolve_npc_class_name(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    return _NPC_CLASS_NAME_LOOKUP.get(cleaned.lower())
_CLASS_NAME_ALIASES: dict[str, str] = {'battle mage': 'Battlemage', 'sorcerer': 'Sorceror'}
for _canonical in CLASS_LIST_ORDER:
    _CLASS_NAME_ALIASES[_canonical.lower() + 's'] = _canonical
_CLASS_NAME_ALIASES.update({'thieves': 'Thief', 'sorcerors': 'Sorceror', 'sorcerers': 'Sorceror'})

def _extract_english_from_heading(heading_text: str) -> str | None:
    plain = re.sub('<[^>]+>', '', heading_text).strip()
    m = re.search('[（(]([A-Za-z][A-Za-z ]*)[）)]', plain)
    if m:
        return m.group(1).strip()
    if re.fullmatch('[A-Za-z][A-Za-z ]*', plain):
        return plain
    return None

def _resolve_canonical_class(name: str) -> str | None:
    key = name.lower()
    if key in _CLASS_NAME_ALIASES:
        return _CLASS_NAME_ALIASES[key]
    for canonical in CLASS_LIST_ORDER:
        if canonical.lower() == key:
            return canonical
    return None

def _resolve_class_from_heading(heading_text: str) -> Optional[str]:
    plain = re.sub('<[^>]+>', '', heading_text).strip()
    if not plain:
        return None
    en_in = _extract_english_from_heading(heading_text)
    if en_in:
        canonical = _resolve_canonical_class(en_in)
        if canonical:
            return canonical
    candidates: list[tuple[int, str]] = []
    for canonical in CLASS_LIST_ORDER:
        for cand in _class_name_candidates(canonical):
            if cand in plain:
                candidates.append((len(cand), canonical))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]

def _parse_class_sections_simple(html_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    body_match = re.search('<body[^>]*>(.*?)</body>', html_text, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text
    h2_re = re.compile('<h2[^>]*>(.*?)</h2>', re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile('<h[12][^>]*>|<div\\s+class="section-header"[^>]*>', re.IGNORECASE)
    pos = 0
    while True:
        m = h2_re.search(body, pos)
        if not m:
            break
        start = m.start()
        heading_inner = m.group(1)
        end_search = next_boundary_re.search(body, m.end())
        end = end_search.start() if end_search else len(body)
        section = body[start:end].strip()
        canonical = _resolve_class_from_heading(heading_inner)
        if canonical and canonical not in result:
            result[canonical] = section
        pos = m.end()
    return result
_FULL_STATS_P_PATTERNS = (re.compile('^使用可能武器[:：]'), re.compile('^武器[:：]'), re.compile('^防具[:：]'), re.compile('^盾[:：]'), re.compile('^初期体力[:：]'))

def _strip_stats_paragraphs(section_html: str) -> str:

    def _is_stats_p(p_text: str) -> bool:
        plain = re.sub('<[^>]+>', '', p_text).strip()
        return any((pat.match(plain) for pat in _FULL_STATS_P_PATTERNS))

    def _replace(m: re.Match) -> str:
        return '' if _is_stats_p(m.group(1)) else m.group(0)
    return re.sub('<p[^>]*>(.*?)</p>', _replace, section_html, flags=re.DOTALL)

def _parse_class_sections_full(html_text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    body_match = re.search('<body[^>]*>(.*?)</body>', html_text, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text
    h3_re = re.compile('<h3[^>]*>(.*?)</h3>', re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile('<h[123][^>]*>|<div\\s+class="section-header"[^>]*>', re.IGNORECASE)
    pos = 0
    while True:
        m = h3_re.search(body, pos)
        if not m:
            break
        start = m.end()
        heading_inner = m.group(1)
        end_search = next_boundary_re.search(body, m.end())
        end = end_search.start() if end_search else len(body)
        section = body[start:end].strip()
        section = _strip_stats_paragraphs(section)
        canonical = _resolve_class_from_heading(heading_inner)
        if canonical and canonical not in result:
            result[canonical] = section
        pos = m.end()
    return result
_parse_class_sections = _parse_class_sections_simple

def _read_manual_html(mode: str, lang: str) -> str:
    import app_resources
    for L in (lang, 'ja'):
        txt = app_resources.read_text(f'manual/{mode}/{L}/{_CLASS_DOC}')
        if txt is not None:
            return txt
    return ''

def _load_html_or_empty(base_dir: str, lang: str) -> str:
    mode = 'full' if base_dir == _MANUAL_FULL else 'simple'
    return _read_manual_html(mode, lang)

def _load_class_descriptions(lang: str) -> dict[str, str]:
    simple_html = _load_html_or_empty(_MANUAL_SIMPLE, lang)
    full_html = _load_html_or_empty(_MANUAL_FULL, lang)
    simple_sections = _parse_class_sections_simple(simple_html) if simple_html else {}
    full_sections = _parse_class_sections_full(full_html) if full_html else {}
    combined: dict[str, str] = {}
    detail_title = i18n.text('manual.detail_section_title')
    for canonical in set(simple_sections) | set(full_sections):
        s = simple_sections.get(canonical, '')
        f = full_sections.get(canonical, '')
        if s and f:
            combined[canonical] = s + f'\n<h3>{detail_title}</h3>\n' + f
        else:
            combined[canonical] = s or f
    return combined
_OVERRIDE_CSS = '\n<style>\n  body { line-height: 1.0; }\n  p    { line-height: 1.0; margin: 0 0 6px 0; }\n  div  { line-height: 1.0; }\n  h2   { line-height: 1.0; }\n  h3   { line-height: 1.0; }\n</style>\n'

def _wrap_html_fragment(fragment: str, base_html: str) -> str:
    style_match = re.search('<style[^>]*>(.*?)</style>', base_html, re.IGNORECASE | re.DOTALL)
    style = style_match.group(0) if style_match else ''
    return f'<!DOCTYPE html><html><head><meta charset="UTF-8">{style}{_OVERRIDE_CSS}</head><body>{fragment}</body></html>'

def _read_base_html(lang: str) -> str:
    return _read_manual_html('simple', lang)

class ClassListPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: dict[str, str] = {}
        self._base_html: str = ''
        self._rows: list[_ClassRow] = []
        self._rows_by_en: dict[str, _ClassRow] = {}
        self._current_en: Optional[str] = None
        self._build_ui()
        self._reload_descriptions()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        top = QWidget()
        grid = QGridLayout(top)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)
        for idx, en in enumerate(CLASS_LIST_ORDER):
            row = idx % 9
            col = idx // 9
            row_widget = _ClassRow(en, class_display_name(en))
            row_widget.clicked.connect(self._on_row_clicked)
            grid.addWidget(row_widget, row, col)
            self._rows.append(row_widget)
            self._rows_by_en[en] = row_widget
        for c in (0, 1):
            grid.setColumnStretch(c, 1)
        splitter.addWidget(top)
        self._desc = QTextBrowser()
        self._desc.setOpenExternalLinks(False)
        self._desc.setHtml('')
        splitter.addWidget(self._desc)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 320])
        root.addWidget(splitter, 1)

    def reload_for_language(self) -> None:
        self._reload_descriptions()
        for en, row in self._rows_by_en.items():
            row.set_display_name(class_display_name(en))
        if self._current_en:
            self._show_description(self._current_en)

    def _reload_descriptions(self) -> None:
        lang = i18n.current_lang() or 'ja'
        self._base_html = _read_base_html(lang)
        self._sections = _load_class_descriptions(lang)

    def reset_selection(self) -> None:
        for row in self._rows:
            row.set_highlighted(False)
        self._current_en = None
        self._desc.setHtml('')

    def select_class(self, en_name: str) -> None:
        if en_name == self._current_en:
            return
        for en, row in self._rows_by_en.items():
            row.set_highlighted(en == en_name)
        self._current_en = en_name
        self._show_description(en_name)

    def _on_row_clicked(self, en_name: str) -> None:
        self.select_class(en_name)

    def _show_description(self, en_name: str) -> None:
        fragment = self._sections.get(en_name, '')
        if not fragment:
            msg = i18n.text('common.description_not_found').replace('{name}', en_name)
            self._desc.setHtml(f'<p>{msg}</p>')
            return
        html = _wrap_html_fragment(fragment, self._base_html)
        self._desc.setHtml(html)
