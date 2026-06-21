
from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

import i18n_helper as i18n
import inf_text_lookup as itl

_I18N_DIR = os.path.join(os.path.dirname(__file__), "..", "i18n")
_UNTRANSLATED_STYLE = "background: #3a2a00; border-radius: 4px; padding: 4px;"
_TRANSLATED_STYLE = ""

_SEGMENT_QSS = """
QPushButton[segment="true"] {
    padding: 6px 18px;
    border: 1px solid palette(mid);
    background: palette(button);
    color: palette(button-text);
}
QPushButton[segment="true"]:checked {
    background: palette(highlight);
    color: palette(highlighted-text);
    border: 1px solid palette(highlight);
    font-weight: bold;
}
QPushButton[segment-left="true"] {
    border-top-left-radius: 4px;
    border-bottom-left-radius: 4px;
    border-right: none;
}
QPushButton[segment-right="true"] {
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}
"""


_DICT_VIEW_SKIP = {"inf_text", "ui", "ui_app", "glossary"}


def _load_dict_entries() -> tuple[list, list]:
    entries: list = []
    categories: list = []
    lang = i18n.current_lang()

    cat_ids = i18n.original_categories()
    if not cat_ids:
        cat_ids = i18n.v2_bundle_categories()

    for cat_id in cat_ids:
        if cat_id in _DICT_VIEW_SKIP:
            continue
        label = _cat_label(cat_id)
        rows = _category_dict_rows(cat_id, label)
        if rows:
            entries.extend(rows)
            categories.append({"id": cat_id, "display": label})

    ui_entries, ui_cat = _load_assist_ui_entries(lang)
    if ui_entries and ui_cat is not None:
        entries.extend(ui_entries)
        categories.append(ui_cat)

    return entries, categories


def _cat_label(cat_id: str) -> str:
    key = f"dict.cat.{cat_id}"
    label = i18n.tr(key)
    return cat_id if (not label or label == key) else label


def _category_dict_rows(cat_id: str, cat_display: str) -> list:
    rows: list = []
    src = i18n.originals(cat_id)
    if src:
        for id_, e in src.items():
            if not isinstance(e, dict):
                continue
            eng = e.get("original") or ""
            if not eng:
                continue
            rows.append({
                "eng": eng,
                "jpn": i18n.lang_only(id_) or "",
                "cat_id": cat_id,
                "cat_display": cat_display,
            })
        return rows
    for e in i18n.v2_category_entries(cat_id):
        eng = e.get("original") or ""
        if not eng:
            continue
        rows.append({
            "eng": eng,
            "jpn": e.get("text") or "",
            "cat_id": cat_id,
            "cat_display": cat_display,
        })
    return rows


def _read_strings(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data.get("strings"), dict):
        return {
            k: v for k, v in data["strings"].items()
            if isinstance(v, str)
        }
    return {
        k: v for k, v in data.items()
        if not k.startswith("_") and isinstance(v, str)
    }


def _load_assist_ui_entries(lang: str) -> tuple[list, dict | None]:
    en_strings = _read_strings(os.path.join(_I18N_DIR, "en.json"))
    if not en_strings:
        return [], None

    if lang == "en":
        cur_strings = en_strings
    else:
        cur_strings = _read_strings(os.path.join(_I18N_DIR, f"{lang}.json"))

    cat_id = "assist_ui"
    cat_display = i18n.tr("dict.cat.assist_ui")
    entries: list = []
    for key, en_val in en_strings.items():
        if not isinstance(en_val, str) or not en_val:
            continue
        cur_val = cur_strings.get(key, "")
        if not isinstance(cur_val, str):
            cur_val = ""
        entries.append({
            "eng": en_val,
            "jpn": cur_val,
            "cat_id": cat_id,
            "cat_display": cat_display,
        })

    if not entries:
        return [], None
    return entries, {"id": cat_id, "display": cat_display}


class TabDict(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dict_entries: list = []
        self._dict_categories: list = []
        itl.load()
        self._inf_entries: list = []

        self._build_ui()
        self._load_dict()
        self._populate_inf_files()


    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self._btn_mode_dict = QPushButton(i18n.tr("dict.mode_dictionary"))
        self._btn_mode_inf = QPushButton(i18n.tr("dict.mode_inf_text"))
        for i, btn in enumerate((self._btn_mode_dict, self._btn_mode_inf)):
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setProperty("segment", "true")
            btn.setProperty("segment-left" if i == 0 else "segment-right", "true")
        self._btn_mode_dict.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._btn_mode_dict, 0)
        self._mode_group.addButton(self._btn_mode_inf, 1)
        self._mode_group.idClicked.connect(self._on_mode_changed)
        self.setStyleSheet(self.styleSheet() + _SEGMENT_QSS)
        mode_row.addWidget(self._btn_mode_dict)
        mode_row.addWidget(self._btn_mode_inf)
        mode_row.addStretch()
        root.addLayout(mode_row)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_dict_page())
        self._stack.addWidget(self._build_inf_page())
        root.addWidget(self._stack, 1)

    def _build_dict_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self._dict_search_edit = QLineEdit()
        self._dict_search_edit.setPlaceholderText(i18n.tr("dict.search_placeholder"))
        self._dict_search_edit.returnPressed.connect(self._search_dict)

        self._dict_cat_combo = QComboBox()
        self._dict_cat_combo.setMinimumWidth(140)

        self._dict_search_btn = QPushButton(i18n.tr("dict.search_btn"))
        self._dict_search_btn.clicked.connect(self._search_dict)

        top.addWidget(self._dict_search_edit, 1)
        top.addWidget(self._dict_cat_combo)
        top.addWidget(self._dict_search_btn)
        layout.addLayout(top)

        self._dict_result_lbl = QLabel(i18n.tr("dict.loading"))
        layout.addWidget(self._dict_result_lbl)

        self._dict_table = QTableWidget(0, 3)
        self._dict_table.setHorizontalHeaderLabels([
            i18n.tr("dict.col_eng"),
            i18n.tr("dict.col_jpn"),
            i18n.tr("dict.col_category"),
        ])
        hdr = self._dict_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._dict_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dict_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._dict_table.setAlternatingRowColors(True)
        self._dict_table.verticalHeader().setVisible(False)
        layout.addWidget(self._dict_table)

        return page

    def _build_inf_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        lbl_inf = QLabel(i18n.tr("inf_text.inf_file") + ":")
        self._inf_combo = QComboBox()
        self._inf_combo.setMinimumWidth(160)
        self._inf_combo.currentIndexChanged.connect(self._on_inf_changed)

        lbl_type = QLabel(i18n.tr("inf_text.type_filter") + ":")
        self._inf_type_combo = QComboBox()
        for key, label in [
            ("all", i18n.tr("inf_text.type_all")),
            ("lore", "lore"),
            ("lore_once", "lore_once"),
            ("riddle", "riddle"),
            ("key", "key"),
            ("key_lore", "key_lore"),
        ]:
            self._inf_type_combo.addItem(label, key)
        self._inf_type_combo.currentIndexChanged.connect(self._on_inf_filter_changed)

        lbl_search = QLabel(i18n.tr("inf_text.search") + ":")
        self._inf_search_edit = QLineEdit()
        self._inf_search_edit.setPlaceholderText(i18n.tr("inf_text.search_placeholder"))
        self._inf_search_edit.textChanged.connect(self._on_inf_filter_changed)

        filter_row.addWidget(lbl_inf)
        filter_row.addWidget(self._inf_combo)
        filter_row.addWidget(lbl_type)
        filter_row.addWidget(self._inf_type_combo)
        filter_row.addWidget(lbl_search)
        filter_row.addWidget(self._inf_search_edit, 1)
        layout.addLayout(filter_row)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self._inf_list = QListWidget()
        self._inf_list.setAlternatingRowColors(True)
        self._inf_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._inf_list.currentItemChanged.connect(self._on_inf_item_selected)
        splitter.addWidget(self._inf_list)

        detail = QWidget()
        d_lay = QVBoxLayout(detail)
        d_lay.setContentsMargins(0, 4, 0, 0)
        d_lay.setSpacing(4)

        self._inf_orig_lbl = QLabel(i18n.tr("inf_text.original") + ":")
        self._inf_orig_lbl.setObjectName("subLabel")
        self._inf_orig = QTextEdit()
        self._inf_orig.setReadOnly(True)
        self._inf_orig.setMaximumHeight(100)
        self._inf_orig.setObjectName("dimLabel")
        self._inf_orig.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)

        self._inf_trans_lbl = QLabel(i18n.tr("inf_text.translation") + " (JA):")
        self._inf_trans_lbl.setObjectName("subLabel")
        self._inf_trans = QTextEdit()
        self._inf_trans.setReadOnly(True)
        self._inf_trans.setMinimumHeight(60)
        self._inf_trans.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        d_lay.addWidget(self._inf_orig_lbl)
        d_lay.addWidget(self._inf_orig)
        d_lay.addWidget(sep)
        d_lay.addWidget(self._inf_trans_lbl)
        d_lay.addWidget(self._inf_trans, 1)

        splitter.addWidget(detail)
        splitter.setSizes([200, 140])
        layout.addWidget(splitter, 1)

        return page


    def _load_dict(self) -> None:
        self._dict_entries, self._dict_categories = _load_dict_entries()

        self._dict_cat_combo.clear()
        self._dict_cat_combo.addItem(i18n.tr("dict.category_all"), "")
        for cat in self._dict_categories:
            self._dict_cat_combo.addItem(cat["display"], cat["id"])

        self._show_dict_entries(self._dict_entries)

    def _search_dict(self) -> None:
        keyword = self._dict_search_edit.text().strip().lower()
        cat_id = self._dict_cat_combo.currentData()

        filtered = self._dict_entries
        if cat_id:
            filtered = [e for e in filtered if e["cat_id"] == cat_id]
        if keyword:
            filtered = [
                e for e in filtered
                if keyword in e["eng"].lower() or keyword in e["jpn"].lower()
            ]
        self._show_dict_entries(filtered)

    def _show_dict_entries(self, entries: list) -> None:
        self._dict_table.setRowCount(0)
        for row_idx, e in enumerate(entries):
            self._dict_table.insertRow(row_idx)
            self._dict_table.setItem(row_idx, 0, _item(e["eng"]))
            self._dict_table.setItem(row_idx, 1, _item(e["jpn"]))
            self._dict_table.setItem(row_idx, 2, _item(e["cat_display"]))

        if entries:
            self._dict_result_lbl.setText(
                i18n.tr("dict.results", count=len(entries)))
        else:
            kw = self._dict_search_edit.text().strip()
            self._dict_result_lbl.setText(
                i18n.tr("dict.no_results") if kw
                else i18n.tr("dict.results", count=0)
            )

    def lookup(self, english: str) -> str | None:
        for e in self._dict_entries:
            if e["eng"].lower() == english.lower():
                return e["jpn"]
        return None


    def _populate_inf_files(self) -> None:
        self._inf_combo.blockSignals(True)
        self._inf_combo.clear()
        self._inf_combo.addItem(i18n.tr("inf_text.all_files"), "")
        for name in itl.all_inf_names():
            self._inf_combo.addItem(name, name)
        self._inf_combo.blockSignals(False)
        self._on_inf_changed()

    def _on_inf_changed(self) -> None:
        inf_name = self._inf_combo.currentData() or ""
        if inf_name:
            self._inf_entries = itl.all_entries_for_inf(inf_name)
        else:
            itl._ensure_loaded()
            self._inf_entries = sorted(
                itl._index.values(),
                key=lambda e: (e["inf"], e["idx"]),
            )
        self._on_inf_filter_changed()

    def _on_inf_filter_changed(self) -> None:
        type_key = self._inf_type_combo.currentData() or "all"
        query = self._inf_search_edit.text().strip().lower()

        self._inf_list.blockSignals(True)
        self._inf_list.clear()

        for e in self._inf_entries:
            if type_key != "all" and e.get("type") != type_key:
                continue
            text_body = e.get("text") or e.get("question") or ""
            trans_body = ""
            t = itl.get_translation(e)
            if isinstance(t, dict):
                trans_body = " ".join(v for v in t.values() if v)
            elif t:
                trans_body = t
            if query and query not in text_body.lower() and query not in trans_body.lower():
                continue

            label = (
                f"[{e['idx']:3d}] {e['type']:10s}  "
                f"{text_body[:40].replace(chr(10), ' ')}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, e)
            self._inf_list.addItem(item)

        self._inf_list.blockSignals(False)

    def _on_inf_item_selected(
        self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None
    ) -> None:
        if cur is None:
            return
        e = cur.data(Qt.ItemDataRole.UserRole)
        self._show_inf_entry(e)

    def _show_inf_entry(self, entry: dict) -> None:
        t = entry.get("type", "")
        if t == "riddle":
            orig_text = (
                f"[問] {entry.get('question', '')}\n"
                f"[正] {entry.get('correct', '')}\n"
                f"[誤] {entry.get('wrong', '')}"
            )
            trans = itl.get_translation(entry)
            if isinstance(trans, dict):
                trans_text = (
                    f"[問] {trans.get('question', '')}\n"
                    f"[正] {trans.get('correct', '')}\n"
                    f"[誤] {trans.get('wrong', '')}"
                )
            else:
                trans_text = ""
        else:
            orig_text = entry.get("text", "")
            trans = itl.get_translation(entry)
            trans_text = trans if isinstance(trans, str) else ""

        self._inf_orig.setPlainText(orig_text)
        self._inf_trans.setPlainText(trans_text)
        self._inf_trans.setStyleSheet(
            _TRANSLATED_STYLE if trans_text else _UNTRANSLATED_STYLE
        )


    def _on_mode_changed(self, mode_id: int) -> None:
        self._stack.setCurrentIndex(mode_id)


def _item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item
