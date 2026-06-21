"""
class_list_panel.py — クラス一覧パネル

chargen のクラス選択方法で「I will pick my own class」を選んだ後に
表示される 18 クラス一覧画面用の補助パネル。
上部: 18 クラスを 2 列 9 行で表示、各行は「英名 | カタカナ（漢字）」を
       縦に揃えた列レイアウトで表示する。
下部: 選択したクラスのマニュアル説明。
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
_CLASS_DOC     = "05_classes.html"
# 旧名互換（_read_base_html / _load_class_descriptions の base ファイル参照用）
_MANUAL_BASE   = _MANUAL_SIMPLE


# クラス一覧の表示順（Arena ゲーム内 "Choose thy class" 画面のアルファベット順）。
# 1-9 が左列、10-18 が右列。
# (英名, カタカナ, 漢字 or None)
CLASS_LIST_ORDER: list[tuple[str, str, Optional[str]]] = [
    # 左列 1-9
    ("Acrobat",    "アクロバット",   "軽業師"),
    ("Archer",     "アーチャー",     "弓使い"),
    ("Assassin",   "アサシン",       "暗殺者"),
    ("Barbarian",  "バーバリアン",   "野蛮人"),
    ("Bard",       "バード",         "吟遊詩人"),
    ("Battlemage", "バトルメイジ",   "戦闘魔術師"),
    ("Burglar",    "バーグラー",     "侵入者"),
    ("Healer",     "ヒーラー",       "治癒師"),
    ("Knight",     "ナイト",         "騎士"),
    # 右列 10-18
    ("Mage",       "メイジ",         "魔法使い"),
    ("Monk",       "モンク",         "修道士"),
    ("Nightblade", "ナイトブレード", "夜刃使い"),
    ("Ranger",     "レンジャー",     "放浪戦士"),
    ("Rogue",      "ローグ",         "無法者"),
    ("Sorceror",   "ソーサラー",     "妖術師"),
    ("Spellsword", "スペルソード",   "呪文剣士"),
    ("Thief",      "シーフ",         "盗賊"),
    ("Warrior",    "ウォーリアー",   "戦士"),
]


def _format_ja(kana: str, kanji: Optional[str]) -> str:
    return f"{kana}（{kanji}）" if kanji else kana


class _ClassRow(QFrame):
    """1 クラス分の行ウィジェット。英名と日本語名を列で揃えて表示する。"""

    clicked = Signal(str)

    def __init__(self, en: str, kana: str, kanji: Optional[str], parent=None):
        super().__init__(parent)
        self._en = en
        self._highlighted = False
        self.setObjectName("classRow")
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
        self._en_lbl.setObjectName("classRowEn")
        layout.addWidget(self._en_lbl)

        self._ja_lbl = QLabel(_format_ja(kana, kanji))
        self._ja_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._ja_lbl.setObjectName("classRowJa")
        layout.addWidget(self._ja_lbl, 1)

        self._apply_style()

    def class_en(self) -> str:
        return self._en

    def is_highlighted(self) -> bool:
        return self._highlighted

    def set_highlighted(self, on: bool) -> None:
        if self._highlighted == on:
            return
        self._highlighted = on
        self._apply_style()

    def _apply_style(self) -> None:
        # ボタン見栄えに揃える: 通常時はボタン枠/グラデ、hover でハイライト風、
        # 選択中はアクセント色で枠+背景を強調する。
        if self._highlighted:
            self.setStyleSheet(
                "QFrame#classRow {"
                "  background: #2a4a6a;"
                "  border: 1px solid #5bc0de;"
                "  border-radius: 4px;"
                "}"
                "QFrame#classRow QLabel {"
                "  color: #ffe680;"
                "  font-weight: bold;"
                "  background: transparent;"
                "  border: none;"
                "}"
            )
        else:
            self.setStyleSheet(
                "QFrame#classRow {"
                "  background: #1c2e3f;"
                "  border: 1px solid #2a4258;"
                "  border-radius: 4px;"
                "}"
                "QFrame#classRow:hover {"
                "  background: #233b52;"
                "  border-color: #5bc0de;"
                "}"
                "QFrame#classRow QLabel {"
                "  background: transparent;"
                "  border: none;"
                "}"
                "QFrame#classRow QLabel#classRowEn {"
                "  color: #c9d1e0;"
                "}"
                "QFrame#classRow QLabel#classRowJa {"
                "  color: #a0c4d8;"
                "}"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._en)
        super().mousePressEvent(event)


# ゲーム内 NPC バッファに書き込まれるクラス名 → カノニカル名 の解決テーブル
_NPC_CLASS_NAME_LOOKUP: dict[str, str] = {
    name.lower(): name for name, _, _ in CLASS_LIST_ORDER
}
# 表記ゆれ（マニュアル側 / Arena 側で異なる場合の予備マッピング）
_NPC_CLASS_NAME_LOOKUP.update({
    "battle mage": "Battlemage",
    "sorcerer":    "Sorceror",
})


def resolve_npc_class_name(text: str) -> Optional[str]:
    """NPC ダイアログテキストがクラス名そのもの（例: "Acrobat"）の場合に
    カノニカル名を返す。一致しない場合は None。
    """
    if not text:
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    return _NPC_CLASS_NAME_LOOKUP.get(cleaned.lower())


# 英語クラス名のマニュアル表記ゆれ（マニュアル中の別表記 → カノニカル名）。
# 単複両形（plural / singular）を吸収するため、現マニュアルの plural 表記を
# すべて登録しておく。Sorceror のような綴り揺れも併せて吸収。
_CLASS_NAME_ALIASES: dict[str, str] = {
    "battle mage": "Battlemage",
    "sorcerer":    "Sorceror",
}
# 全クラスの plural 形を自動登録（"Thieves" → "Thief" 等の不規則形は個別に上書き）
for _canonical, _, _ in CLASS_LIST_ORDER:
    _CLASS_NAME_ALIASES[_canonical.lower() + "s"] = _canonical
_CLASS_NAME_ALIASES.update({
    "thieves":   "Thief",
    "sorcerors": "Sorceror",
    "sorcerers": "Sorceror",
})


def _extract_english_from_heading(heading_text: str) -> str | None:
    """見出しテキストからマニュアル表記の英語クラス名を抽出する。

    現マニュアルの想定: 「シーフ（Thieves）」「バトルメイジ（Battlemages）」
    旧マニュアル互換: 英名のみ「Thief」/ 「Battle Mage」 もそのまま返す。
    """
    plain = re.sub(r"<[^>]+>", "", heading_text).strip()
    # 全角・半角どちらの括弧でも拾う
    m = re.search(r"[（(]([A-Za-z][A-Za-z ]*)[）)]", plain)
    if m:
        return m.group(1).strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z ]*", plain):
        return plain
    return None


def _resolve_canonical_class(name: str) -> str | None:
    """マニュアル表記の英語名を、CLASS_LIST_ORDER のカノニカル名に解決する。"""
    key = name.lower()
    if key in _CLASS_NAME_ALIASES:
        return _CLASS_NAME_ALIASES[key]
    for canonical, _, _ in CLASS_LIST_ORDER:
        if canonical.lower() == key:
            return canonical
    return None


def _resolve_class_from_heading(heading_text: str) -> Optional[str]:
    """見出し内のテキストから、英名・カタカナ・漢字のいずれかでカノニカル名を解決する。

    優先順位:
      1) 英名（カッコ内 or 見出し全体）→ _resolve_canonical_class
      2) カタカナ・漢字のうち、最も長い完全一致を取る（短い名前の部分一致を回避）
    """
    plain = re.sub(r"<[^>]+>", "", heading_text).strip()
    if not plain:
        return None
    en_in = _extract_english_from_heading(heading_text)
    if en_in:
        canonical = _resolve_canonical_class(en_in)
        if canonical:
            return canonical
    candidates: list[tuple[int, str]] = []
    for canonical, kana, kanji in CLASS_LIST_ORDER:
        if kana and kana in plain:
            candidates.append((len(kana), canonical))
        if kanji and kanji in plain:
            candidates.append((len(kanji), canonical))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _parse_class_sections_simple(html_text: str) -> dict[str, str]:
    """簡易マニュアル（manual/simple/）から英語クラス名ごとの HTML 断片を返す。

    構造: <h2>シーフ（盗賊）</h2> → <p>...</p> → <div class="ability">...</div>
          → <table>...</table> → 次の <h2>
    """
    result: dict[str, str] = {}
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_text, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text

    h2_re = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile(
        r'<h[12][^>]*>|<div\s+class="section-header"[^>]*>',
        re.IGNORECASE,
    )

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


# 詳細版から除外する装備系 <p> パターン
# （簡易版の表に同じ情報が既にあるため重複表示を避ける）
_FULL_STATS_P_PATTERNS = (
    re.compile(r"^使用可能武器[:：]"),
    re.compile(r"^武器[:：]"),
    re.compile(r"^防具[:：]"),
    re.compile(r"^盾[:：]"),
    re.compile(r"^初期体力[:：]"),
)


def _strip_stats_paragraphs(section_html: str) -> str:
    """詳細版セクションから装備情報の <p>...</p> を除去する。"""
    def _is_stats_p(p_text: str) -> bool:
        plain = re.sub(r"<[^>]+>", "", p_text).strip()
        return any(pat.match(plain) for pat in _FULL_STATS_P_PATTERNS)

    def _replace(m: re.Match) -> str:
        return "" if _is_stats_p(m.group(1)) else m.group(0)

    return re.sub(r"<p[^>]*>(.*?)</p>", _replace, section_html, flags=re.DOTALL)


def _parse_class_sections_full(html_text: str) -> dict[str, str]:
    """詳細マニュアル（manual/full/）から英語クラス名ごとの HTML 断片を返す。

    構造: <h2>盗賊系クラス</h2>（カテゴリ）→ <h3>シーフ（Thieves）</h3> → <p>...</p>...
    各 <h3> の開始から、次の <h3> / <h2> / <h1> / <div class="section-header"> / </body>
    までを 1 セクションとして抽出する。装備情報 <p>（武器/防具/盾/初期体力）は
    簡易版の表と重複するため除去する。
    """
    result: dict[str, str] = {}
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html_text, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html_text

    h3_re = re.compile(r"<h3[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
    next_boundary_re = re.compile(
        r'<h[123][^>]*>|<div\s+class="section-header"[^>]*>',
        re.IGNORECASE,
    )

    pos = 0
    while True:
        m = h3_re.search(body, pos)
        if not m:
            break
        # 詳細版セクションは見出し（<h3>クラス名</h3>）を含めず本文のみ抽出する。
        # 結合表示時に簡易版の <h2>クラス名</h2> が既にあるため重複を避ける。
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


# 旧名互換（外部から呼ばれる場合のため）
_parse_class_sections = _parse_class_sections_simple


def _read_manual_html(mode: str, lang: str) -> str:
    """manual/<mode>/<lang>/<CLASS_DOC> を読む（無ければ ja・それも無ければ ""）。

    公開版は manual を _internal に置かず exe 内 seed から読む。dev はディスク。
    """
    import app_resources
    for L in (lang, "ja"):
        txt = app_resources.read_text(f"manual/{mode}/{L}/{_CLASS_DOC}")
        if txt is not None:
            return txt
    return ""


def _load_html_or_empty(base_dir: str, lang: str) -> str:
    mode = "full" if base_dir == _MANUAL_FULL else "simple"
    return _read_manual_html(mode, lang)


def _load_class_descriptions(lang: str) -> dict[str, str]:
    """簡易版（要約）+ 詳細版（マニュアル原文）を結合した HTML 断片を返す。

    表示順:
      1. 簡易版（kana・概要・★能力・装備テーブル）
      2. 区切り <h3>詳細解説</h3>
      3. 詳細版（マニュアル原文の段落）
    詳細版が無い場合は簡易版のみ返す（後方互換）。
    """
    simple_html = _load_html_or_empty(_MANUAL_SIMPLE, lang)
    full_html   = _load_html_or_empty(_MANUAL_FULL, lang)
    simple_sections = _parse_class_sections_simple(simple_html) if simple_html else {}
    full_sections   = _parse_class_sections_full(full_html)     if full_html else {}

    combined: dict[str, str] = {}
    for canonical in set(simple_sections) | set(full_sections):
        s = simple_sections.get(canonical, "")
        f = full_sections.get(canonical, "")
        if s and f:
            combined[canonical] = s + '\n<h3>詳細解説</h3>\n' + f
        else:
            combined[canonical] = s or f
    return combined


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
    """マニュアルの <style> ブロックを引き継いで断片を表示用の完全 HTML に包む。
    後段に _OVERRIDE_CSS を置いて折り返し行間を引き締める。
    """
    style_match = re.search(r"<style[^>]*>(.*?)</style>", base_html, re.IGNORECASE | re.DOTALL)
    style = style_match.group(0) if style_match else ""
    return (
        f'<!DOCTYPE html><html><head><meta charset="UTF-8">{style}{_OVERRIDE_CSS}</head>'
        f'<body>{fragment}</body></html>'
    )


def _read_base_html(lang: str) -> str:
    return _read_manual_html("simple", lang)


class ClassListPanel(QWidget):
    """chargen クラス一覧画面用パネル。

    上部: 18 クラスのボタンを 2 列 9 行で配置（左 1-9、右 10-18）。
    下部: 選択したクラスのマニュアル説明を表示。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections: dict[str, str] = {}
        self._base_html: str = ""
        self._rows: list[_ClassRow] = []
        self._rows_by_en: dict[str, _ClassRow] = {}
        self._current_en: Optional[str] = None
        self._build_ui()
        self._reload_descriptions()

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        # 上部: 18 クラスを 2 列 9 行で表示
        top = QWidget()
        grid = QGridLayout(top)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(2)

        for idx, (en, kana, kanji) in enumerate(CLASS_LIST_ORDER):
            row = idx % 9
            col = idx // 9
            row_widget = _ClassRow(en, kana, kanji)
            row_widget.clicked.connect(self._on_row_clicked)
            grid.addWidget(row_widget, row, col)
            self._rows.append(row_widget)
            self._rows_by_en[en] = row_widget
        for c in (0, 1):
            grid.setColumnStretch(c, 1)
        splitter.addWidget(top)

        # 下部: クラス説明
        self._desc = QTextBrowser()
        self._desc.setOpenExternalLinks(False)
        self._desc.setHtml("")
        splitter.addWidget(self._desc)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 320])
        root.addWidget(splitter, 1)

    # ------------------------------------------------------------------

    def reload_for_language(self) -> None:
        """言語切替時に呼ぶ。マニュアル読み直しと現在表示の更新を行う。"""
        self._reload_descriptions()
        if self._current_en:
            self._show_description(self._current_en)

    def _reload_descriptions(self) -> None:
        """簡易版（要約）+ 詳細版（マニュアル原文）を結合した HTML を読み出す。"""
        lang = i18n.current_lang() or "ja"
        self._base_html = _read_base_html(lang)
        self._sections = _load_class_descriptions(lang)

    def reset_selection(self) -> None:
        """選択を解除し、説明欄をクリアする。"""
        for row in self._rows:
            row.set_highlighted(False)
        self._current_en = None
        self._desc.setHtml("")

    def select_class(self, en_name: str) -> None:
        """指定クラスをハイライトし、説明を表示する。

        NPC バッファ追従からの呼び出しと、ユーザーのパネルクリックの
        両方からこのメソッドを使う。
        """
        if en_name == self._current_en:
            return
        for en, row in self._rows_by_en.items():
            row.set_highlighted(en == en_name)
        self._current_en = en_name
        self._show_description(en_name)

    # ------------------------------------------------------------------

    def _on_row_clicked(self, en_name: str) -> None:
        # ユーザーがパネル上のクラスをクリックした場合もハイライト＋説明表示。
        self.select_class(en_name)

    def _show_description(self, en_name: str) -> None:
        fragment = self._sections.get(en_name, "")
        if not fragment:
            self._desc.setHtml(f"<p>{en_name} の説明が見つかりませんでした。</p>")
            return
        html = _wrap_html_fragment(fragment, self._base_html)
        self._desc.setHtml(html)
