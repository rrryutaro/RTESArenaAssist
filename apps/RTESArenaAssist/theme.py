
import sys

from assist_constants import Dark, Light


def detect_os_theme() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "light" if val == 1 else "dark"
        except Exception:
            pass
    return "dark"


def resolve_theme(mode: str) -> str:
    if mode in ("system", "auto"):
        return detect_os_theme()
    return "light" if mode == "light" else "dark"


def _build_stylesheet(c) -> str:
    return f"""
QWidget {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    font-family: "Meiryo", "Yu Gothic UI", "Segoe UI", sans-serif;
    font-size: 10pt;
}}
QMainWindow, QDialog {{
    background-color: {c.BG};
}}
QLabel {{
    background-color: transparent;
    color: {c.TEXT};
}}
QPushButton {{
    background-color: {c.SEP};
    color: {c.TEXT};
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
}}
QPushButton:hover {{
    background-color: {c.ACCENT};
    color: white;
}}
QPushButton:disabled {{
    background-color: {c.PANEL};
    color: {c.TEXT_SUB};
}}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {c.SEP};
    color: {c.TEXT};
    border: 1px solid {c.SEP};
    border-radius: 3px;
    padding: 3px 5px;
    selection-background-color: {c.ACCENT};
}}
QComboBox {{
    background-color: {c.SEP};
    color: {c.TEXT};
    border: 1px solid {c.SEP};
    border-radius: 3px;
    padding: 3px 6px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    selection-background-color: {c.ACCENT};
    selection-color: white;
    border: 1px solid {c.SEP};
}}
QTabWidget::pane {{
    border: 1px solid {c.SEP};
    background: {c.BG};
    top: -1px;
}}
QTabBar::tab {{
    background: {c.SEP};
    color: {c.TEXT_SUB};
    padding: 6px 14px;
    border: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {c.ACCENT};
    color: white;
}}
QTabBar::tab:hover:!selected {{
    background: {c.HEADER};
    color: {c.TEXT};
}}
QTableWidget, QTreeWidget {{
    background-color: {c.ROW_ODD};
    color: {c.TEXT};
    gridline-color: {c.SEP};
    border: 1px solid {c.SEP};
    alternate-background-color: {c.ROW_EVEN};
}}
QTableWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {c.ACCENT};
    color: white;
}}
QListWidget#manualNav {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    border: none;
    border-right: 1px solid {c.SEP};
    outline: none;
}}
QListWidget#manualNav::item {{
    padding: 6px 10px;
    border-bottom: 1px solid {c.SEP};
}}
QListWidget#manualNav::item:selected {{
    background-color: {c.ACCENT};
    color: white;
}}
QListWidget#manualNav::item:hover:!selected {{
    background-color: {c.HEADER};
}}
QListWidget#saveList {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    border: 1px solid {c.SEP};
    outline: none;
}}
QListWidget#saveList::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {c.SEP};
}}
QListWidget#saveList::item:selected {{
    background-color: {c.ACCENT};
    color: white;
}}
QListWidget#saveList::item:hover:!selected {{
    background-color: {c.HEADER};
}}
QListWidget#saveLeftList {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    border: none;
    border-right: 1px solid {c.SEP};
    outline: none;
}}
QListWidget#saveLeftList::item {{
    padding: 5px 8px;
    border-bottom: 1px solid {c.SEP};
    font-size: 9pt;
}}
QListWidget#saveLeftList::item:selected {{
    background-color: {c.ACCENT};
    color: white;
}}
QListWidget#saveLeftList::item:hover:!selected {{
    background-color: {c.HEADER};
}}
QPushButton#viewToggleBtn {{
    background-color: {c.SEP};
    color: {c.TEXT_SUB};
    border: 1px solid {c.SEP};
    border-radius: 3px;
    padding: 4px 12px;
}}
QPushButton#viewToggleBtn:checked {{
    background-color: {c.ACCENT};
    color: white;
    border-color: {c.ACCENT};
}}
QPushButton#viewToggleBtn:hover:!checked {{
    background-color: {c.HEADER};
    color: {c.TEXT};
}}
QLabel#detailHeader {{
    font-size: 12pt;
    font-weight: bold;
    padding-bottom: 6px;
    border-bottom: 2px solid {c.ACCENT};
    color: {c.TEXT};
}}
QHeaderView::section {{
    background-color: {c.HEADER};
    color: {c.TEXT};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {c.SEP};
    font-weight: bold;
}}
QScrollBar:vertical {{
    width: 8px;
    background: {c.PANEL};
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {c.SEP};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    height: 8px;
    background: {c.PANEL};
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {c.SEP};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QSplitter::handle {{ background: {c.SEP}; }}
QStatusBar {{
    background-color: {c.PANEL};
    color: {c.TEXT_SUB};
    font-size: 9pt;
}}
QMenuBar {{
    background-color: {c.HEADER};
    color: {c.TEXT};
}}
QMenuBar::item:selected {{ background-color: {c.ACCENT}; color: white; }}
QMenu {{
    background-color: {c.PANEL};
    color: {c.TEXT};
    border: 1px solid {c.SEP};
}}
QMenu::item:selected {{ background-color: {c.ACCENT}; color: white; }}
QToolTip {{
    background-color: {c.SEP};
    color: {c.TEXT};
    border: 1px solid {c.TEXT_SUB};
    padding: 3px 5px;
}}
QTextBrowser {{
    background-color: {c.BG};
    color: {c.TEXT};
    border: none;
    font-size: 10pt;
    line-height: 1.6;
}}
QPushButton#winCtrlBtn {{
    background: transparent;
    color: {c.TEXT_SUB};
    border-radius: 3px;
    padding: 0;
    font-size: 11pt;
}}
QPushButton#winCtrlBtn:hover {{
    background: {c.SEP};
    color: {c.TEXT};
}}
QPushButton#winCloseBtn {{
    background: transparent;
    color: {c.TEXT_SUB};
    border-radius: 3px;
    padding: 0;
    font-size: 11pt;
}}
QPushButton#winCloseBtn:hover {{
    background: {c.ERROR};
    color: white;
}}
"""


def get_stylesheet(mode: str) -> str:
    effective = resolve_theme(mode)
    return _build_stylesheet(Light if effective == "light" else Dark)
