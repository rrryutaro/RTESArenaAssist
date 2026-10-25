from __future__ import annotations
import i18n_helper as i18n
_FONT_CSS = '"Segoe UI", "Yu Gothic UI", "Meiryo", "Microsoft YaHei UI", "Microsoft JhengHei UI", "Malgun Gothic", sans-serif'
_ELLIPSIS = '…'

def text_width(text: str, px: int, bold: bool=False) -> float:
    from html import escape
    from PySide6.QtGui import QTextDocument
    from charsheet.view import with_language_fonts
    weight = 'bold' if bold else 'normal'
    html = f'<body style="font-family: {_FONT_CSS}; font-size: {px}px;"><span style="font-weight: {weight}; white-space: nowrap;">{escape(text)}</span></body>'
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setHtml(with_language_fonts(html, i18n.ui_font_families()))
    return doc.idealWidth()

def elide(text: str, px: int, width: float, bold: bool=False) -> str:
    if text_width(text, px, bold) <= width:
        return text
    low, high = (0, len(text))
    while low < high:
        mid = (low + high + 1) // 2
        if text_width(text[:mid].rstrip() + _ELLIPSIS, px, bold) <= width:
            low = mid
        else:
            high = mid - 1
    return text[:low].rstrip() + _ELLIPSIS

def can_measure() -> bool:
    try:
        from PySide6.QtGui import QGuiApplication
    except ImportError:
        return False
    return QGuiApplication.instance() is not None
