from __future__ import annotations
from typing import Sequence

def build_menu_display(menu_tr: Sequence[tuple[str, str]], menu_hotkeys: Sequence[str], title_en: str, title_ja: str) -> tuple[str, str, str, str]:
    tab_en_lines: list[str] = []
    tab_ja_lines: list[str] = []
    panel_en_lines: list[str] = []
    panel_ja_lines: list[str] = []
    if title_en:
        tab_en_lines.extend([title_en, ''])
        tab_ja_lines.extend([title_ja, ''])
        panel_en_lines.extend([title_en, ''])
        panel_ja_lines.extend([title_ja, ''])
    for _i, (_en, _ja) in enumerate(menu_tr):
        _hk = menu_hotkeys[_i] if _i < len(menu_hotkeys) else ''
        _ja_disp = _ja or _en
        _prefix = f'[{_hk}] ' if _hk else ''
        tab_en_lines.append(f'  {_prefix}{_en}')
        tab_ja_lines.append(f'  {_prefix}{_ja_disp}')
        panel_en_lines.append(_en)
        panel_ja_lines.append(_ja_disp)
    return ('\n'.join(tab_en_lines), '\n'.join(tab_ja_lines), '\n'.join(panel_en_lines), '\n'.join(panel_ja_lines))
__all__ = ['build_menu_display']
