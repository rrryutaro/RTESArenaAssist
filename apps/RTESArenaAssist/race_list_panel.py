"""
race_list_panel.py — 出身地（種族）一覧パネル

chargen の "From where dost thou hail" 画面（race_select subscreen）で
表示する補助パネル。9 プロヴィンス × 種族の対応関係を 9 行 × 1 列で
表示し、クリックでマニュアルの種族解説を表示する。

レイアウト:
- 各行: 原文プロヴィンス名 / 翻訳プロヴィンス名 / 原文種族名 / 翻訳種族名
- Imperial Province (Cyrodiil) は非選択（disabled 表示）
  - クリック時は「マニュアル原典に種族記載がなく、本作では選択できません。」を表示
  - マニュアル本体（04_races.html）には Imperial 解説を追加しない
"""

from __future__ import annotations

import os
import re
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QSplitter,
    QTextBrowser, QVBoxLayout, QWidget,
)

import i18n_helper as i18n


_MANUAL_SIMPLE = os.path.join(os.path.dirname(__file__), "manual", "simple")
_MANUAL_FULL   = os.path.join(os.path.dirname(__file__), "manual", "full")
_RACE_DOC      = "04_races.html"
# 旧名互換（_read_base_html / 既存呼び出し用）
_MANUAL_BASE   = _MANUAL_SIMPLE

# Imperial 行のクリック時に表示するメッセージのキー（i18n）
_IMPERIAL_TITLE_KEY = "race.imperial_unavailable.title"
_IMPERIAL_BODY_KEY  = "race.imperial_unavailable.body"


# 種族選択の表示順。
# (race_id, province_en, province_ja, race_en, race_ja, disabled)
RACE_LIST_ORDER: list[tuple[str, str, str, str, str, bool]] = [
    # 種族・地名の訳語は公式日本語版の用語に統一。
    ("nord",      "Skyrim",         "スカイリム",         "Nords",       "ノルド",         False),
    ("redguard",  "Hammerfell",     "ハンマーフェル",     "Redguards",   "レッドガード",   False),
    ("breton",    "High Rock",      "ハイロック",         "Bretons",     "ブレトン",       False),
    ("dark_elf",  "Morrowind",      "モロウウィンド",     "Dark Elves",  "ダークエルフ",   False),
    ("imperial",  "Cyrodiil",       "シロディール",       "Imperials",   "インペリアル",   True),   # 非選択
    ("wood_elf",  "Valenwood",      "ヴァレンウッド",     "Wood Elves",  "ウッドエルフ",   False),
    ("khajiit",   "Elsweyr",        "エルスウェア",       "Khajiit",     "カジート",       False),
    ("argonian",  "Black Marsh",    "ブラックマーシュ",   "Argonians",   "アルゴニアン",   False),
    ("high_elf",  "Summerset Isle", "サマーセット",       "High Elves",  "ハイエルフ",     False),
]


class _RaceRow(QFrame):
    """1 種族分の行ウィジェット。4 列レイアウトで原文/翻訳の地名・種族名を表示。"""

    clicked = Signal(str)  # race_id

    def __init__(self, race_id: str, province_en: str, province_ja: str,
                 race_en: str, race_ja: str, disabled: bool = False, parent=None):
        super().__init__(parent)
        self._race_id   = race_id
        self._disabled  = disabled
        self._highlighted = False
        self.setObjectName("raceRow")
        self.setFrameShape(QFrame.Shape.NoFrame)
        # disabled 行は cursor を非ポインターにする
        self.setCursor(Qt.CursorShape.ArrowCursor if disabled
                       else Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(8)

        # 4 列のラベル
        self._province_en_lbl = QLabel(province_en)
        self._province_en_lbl.setMinimumWidth(120)
        self._province_en_lbl.setMaximumWidth(140)
        self._province_en_lbl.setObjectName("raceRowProvinceEn")

        self._province_ja_lbl = QLabel(province_ja)
        self._province_ja_lbl.setMinimumWidth(140)
        self._province_ja_lbl.setWordWrap(True)
        self._province_ja_lbl.setObjectName("raceRowProvinceJa")

        self._race_en_lbl = QLabel(race_en)
        self._race_en_lbl.setMinimumWidth(96)
        self._race_en_lbl.setMaximumWidth(120)
        self._race_en_lbl.setObjectName("raceRowRaceEn")

        self._race_ja_lbl = QLabel(race_ja)
        self._race_ja_lbl.setObjectName("raceRowRaceJa")

        for lbl in (self._province_en_lbl, self._province_ja_lbl,
                    self._race_en_lbl, self._race_ja_lbl):
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(lbl)
        layout.addStretch(1)

        self._apply_style()

    def race_id(self) -> str:
        return self._race_id

    def is_disabled(self) -> bool:
        return self._disabled

    def is_highlighted(self) -> bool:
        return self._highlighted

    def set_highlighted(self, on: bool) -> None:
        if self._highlighted == on:
            return
        self._highlighted = on
        self._apply_style()

    def _apply_style(self) -> None:
        """class_list_panel.py のスタイルに揃える。disabled 行は薄表示。"""
        if self._disabled:
            # disabled スタイル（薄いグレー、ホバー無効）
            self.setStyleSheet(
                "QFrame#raceRow {"
                "  background: #1c2e3f;"
                "  border: 1px solid #2a3a48;"
                "  border-radius: 4px;"
                "}"
                "QFrame#raceRow QLabel {"
                "  color: #66707a;"  # 薄いグレー
                "  background: transparent;"
                "  border: none;"
                "}"
            )
        elif self._highlighted:
            self.setStyleSheet(
                "QFrame#raceRow {"
                "  background: #2a4a6a;"
                "  border: 1px solid #5bc0de;"
                "  border-radius: 4px;"
                "}"
                "QFrame#raceRow QLabel {"
                "  color: #ffe680;"
                "  font-weight: bold;"
                "  background: transparent;"
                "  border: none;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame#raceRow {"
                "  background: #1c2e3f;"
                "  border: 1px solid #2a4258;"
                "  border-radius: 4px;"
                "}"
                "QFrame#raceRow:hover {"
                "  background: #233b52;"
                "  border-color: #5bc0de;"
                "}"
                "QFrame#raceRow QLabel {"
                "  background: transparent;"
                "  border: none;"
                "}"
                "QFrame#raceRow QLabel#raceRowProvinceEn,"
                "QFrame#raceRow QLabel#raceRowRaceEn {"
                "  color: #c9d1e0;"
                "}"
                "QFrame#raceRow QLabel#raceRowProvinceJa,"
                "QFrame#raceRow QLabel#raceRowRaceJa {"
                "  color: #a0c4d8;"
                "}"
            )

    def mousePressEvent(self, event):
        # disabled 行もクリックは受け付ける（説明は表示する）
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._race_id)
        super().mousePressEvent(event)


# マニュアル表記の英語種族名 → race_id の逆引きテーブル。
# RACE_LIST_ORDER の race_en（"Nords" など）と単数形（"Nord" 等）の両方を登録。
_RACE_EN_TO_ID: dict[str, str] = {}
for _race_id, _pen, _pja, _ren, _rja, _dis in RACE_LIST_ORDER:
    _key = _ren.lower()
    _RACE_EN_TO_ID[_key] = _race_id
    # 末尾 "s" を削った単数形（簡易マニュアル "Nord" 等に対応）
    if _key.endswith("s"):
        _RACE_EN_TO_ID[_key[:-1]] = _race_id
# 不規則形対応
_RACE_EN_TO_ID.update({
    "wood elf":   "wood_elf",
    "high elf":   "high_elf",
    "dark elf":   "dark_elf",
    "wood elves": "wood_elf",
    "high elves": "high_elf",
    "dark elves": "dark_elf",
    "khajiit":    "khajiit",  # singular = plural
})


def _resolve_race_id_from_heading(heading_text: str) -> Optional[str]:
    """見出しテキストから race_id を解決する。

    簡易マニュアル: <h2>ノルド（Nord）→ スカイリム...</h2>
      1) カッコ内の英名（singular / plural 両対応）→ race_id
      2) カタカナ種族名 → race_id（フォールバック）
    """
    plain = re.sub(r"<[^>]+>", "", heading_text).strip()
    if not plain:
        return None
    m = re.search(r"[（(]([A-Za-z][A-Za-z ]*)[）)]", plain)
    if m:
        en_in = m.group(1).strip().lower()
        if en_in in _RACE_EN_TO_ID:
            return _RACE_EN_TO_ID[en_in]
    candidates: list[tuple[int, str]] = []
    for race_id, _pen, _pja, _ren, race_ja, _dis in RACE_LIST_ORDER:
        if race_ja and race_ja in plain:
            candidates.append((len(race_ja), race_id))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _parse_race_sections_simple(html_text: str) -> dict[str, str]:
    """簡易マニュアル: <h2>ノルド（Nord）→ ...</h2> ベース"""
    result: dict[str, str] = {}
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_text,
                           re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text

    h2_re = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile(r'<h[12][^>]*>', re.IGNORECASE)

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

        race_id = _resolve_race_id_from_heading(heading_inner)
        if race_id and race_id not in result:
            result[race_id] = section
        pos = m.end()
    return result


def _parse_race_sections_full(html_text: str) -> dict[str, str]:
    """詳細マニュアル: <h3>ノルド（Nords）：</h3> ベース

    結合表示時に簡易版の <h2>種族名</h2> が既にあるため、詳細版セクションは
    見出しを含めず本文のみを抽出して重複を避ける。
    """
    result: dict[str, str] = {}
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_text,
                           re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text

    h3_re = re.compile(r"<h3[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile(r'<h[123][^>]*>', re.IGNORECASE)

    pos = 0
    while True:
        m = h3_re.search(body, pos)
        if not m:
            break
        # 見出しは含めず、<h3> 直後から次の境界までを本文として抽出
        start = m.end()
        heading_inner = m.group(1)
        end_search = next_boundary_re.search(body, m.end())
        end = end_search.start() if end_search else len(body)
        section = body[start:end].strip()

        race_id = _resolve_race_id_from_heading(heading_inner)
        if race_id and race_id not in result:
            result[race_id] = section
        pos = m.end()
    return result


# 旧名互換
_parse_race_sections = _parse_race_sections_simple


def _read_manual_html(mode: str, lang: str) -> str:
    """manual/<mode>/<lang>/<RACE_DOC> を読む（無ければ ja・それも無ければ ""）。

    公開版は manual を実行ファイル内の seed から読む。
    """
    import app_resources
    for L in (lang, "ja"):
        txt = app_resources.read_text(f"manual/{mode}/{L}/{_RACE_DOC}")
        if txt is not None:
            return txt
    return ""


def _read_base_html(lang: str) -> str:
    return _read_manual_html("simple", lang)


# QTextBrowser での折り返し時の余分な行間を抑える上書き CSS
_OVERRIDE_CSS = """
<style>
  body { line-height: 1.0; }
  p    { line-height: 1.0; margin: 0 0 6px 0; }
  div  { line-height: 1.0; }
  h2   { line-height: 1.0; }
  h3   { line-height: 1.0; }
</style>
"""


def _wrap_html_fragment(fragment: str, base_html: str) -> str:
    """マニュアルの <style> ブロックを引き継いで断片を表示用 HTML に包む。
    後段に _OVERRIDE_CSS を置いて折り返し行間を引き締める。
    """
    style_match = re.search(r"<style[^>]*>(.*?)</style>", base_html,
                            re.IGNORECASE | re.DOTALL)
    style = style_match.group(0) if style_match else ""
    return (
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">{style}{_OVERRIDE_CSS}</head>'
        f'<body>{fragment}</body></html>'
    )


class RaceListPanel(QWidget):
    """chargen 種族（出身地）選択画面用パネル。

    上部: 9 行を 1 列で配置。各行に 4 情報（原文/翻訳の地名・種族名）。
    下部: 選択した種族のマニュアル解説。Imperial 行は disabled 表示で、
          クリック時はマニュアルに記載がない旨のみ表示する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: dict[str, str] = {}
        self._base_html: str = ""
        self._rows: list[_RaceRow] = []
        self._rows_by_id: dict[str, _RaceRow] = {}
        self._current_id: Optional[str] = None
        self._build_ui()
        self._reload_descriptions()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # 上部: 9 種族を 1 列 9 行で表示
        top = QWidget()
        grid = QGridLayout(top)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        for idx, (race_id, province_en, province_ja, race_en, race_ja,
                  disabled) in enumerate(RACE_LIST_ORDER):
            row_widget = _RaceRow(race_id, province_en, province_ja,
                                  race_en, race_ja, disabled=disabled)
            row_widget.clicked.connect(self._on_row_clicked)
            grid.addWidget(row_widget, idx, 0)
            self._rows.append(row_widget)
            self._rows_by_id[race_id] = row_widget
        grid.setColumnStretch(0, 1)
        splitter.addWidget(top)

        # 下部: 種族説明
        self._desc = QTextBrowser()
        self._desc.setOpenExternalLinks(False)
        self._desc.setHtml("")
        splitter.addWidget(self._desc)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 320])
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------

    def reload_for_language(self) -> None:
        """言語切替時に呼ぶ。マニュアル読み直しと現在表示の更新を行う。"""
        self._reload_descriptions()
        if self._current_id:
            self._show_description(self._current_id)

    def _reload_descriptions(self) -> None:
        """簡易版（要約）+ 詳細版（マニュアル原文）を結合して読み出す。"""
        lang = i18n.current_lang() or "ja"
        self._base_html = _read_base_html(lang)  # style 取得用は簡易版を維持

        # 簡易版 / 詳細版（公開版は実行ファイル内の seed から読む）
        simple_html = _read_manual_html("simple", lang)
        full_html = _read_manual_html("full", lang)

        simple_sections = _parse_race_sections_simple(simple_html) if simple_html else {}
        full_sections   = _parse_race_sections_full(full_html)     if full_html else {}

        combined: dict[str, str] = {}
        for race_id in set(simple_sections) | set(full_sections):
            s = simple_sections.get(race_id, "")
            f = full_sections.get(race_id, "")
            if s and f:
                combined[race_id] = s + '\n<h3>詳細解説</h3>\n' + f
            else:
                combined[race_id] = s or f
        self._sections = combined

    def reset_selection(self) -> None:
        """選択を解除し、説明欄をクリアする。"""
        for row in self._rows:
            row.set_highlighted(False)
        self._current_id = None
        self._desc.setHtml("")

    # ------------------------------------------------------------------

    def _on_row_clicked(self, race_id: str) -> None:
        if race_id == self._current_id:
            return
        for rid, row in self._rows_by_id.items():
            # disabled 行はハイライトしない
            row.set_highlighted(rid == race_id and not row.is_disabled())
        self._current_id = race_id
        self._show_description(race_id)

    def _show_description(self, race_id: str) -> None:
        row = self._rows_by_id.get(race_id)
        if row and row.is_disabled():
            # Imperial Province の取扱
            title = i18n.tr(_IMPERIAL_TITLE_KEY)
            body = i18n.tr(_IMPERIAL_BODY_KEY)
            html = (
                f'<!DOCTYPE html><html><head><meta charset="UTF-8">'
                f'<style>body{{font-family:"メイリオ",sans-serif;'
                f'font-size:13px;background:#0d1b2a;color:#c9d1e0;'
                f'margin:0;padding:16px;line-height:1.7;}}'
                f'h1{{font-size:15px;color:#7ec8e3;}}</style></head>'
                f'<body><h1>{title}</h1><p>{body}</p></body></html>'
            )
            self._desc.setHtml(html)
            return
        fragment = self._sections.get(race_id, "")
        if not fragment:
            self._desc.setHtml(f"<p>{race_id} の説明が見つかりませんでした。</p>")
            return
        html = _wrap_html_fragment(fragment, self._base_html)
        self._desc.setHtml(html)
