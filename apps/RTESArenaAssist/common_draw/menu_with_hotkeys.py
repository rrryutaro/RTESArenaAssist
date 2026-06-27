from __future__ import annotations

def render(title_en: str, title_ja: str, items: list[tuple[str, str, str]]) -> tuple[str, str, str, str]:
    tab_en_lines: list[str] = []
    tab_ja_lines: list[str] = []
    panel_en_lines: list[str] = []
    panel_ja_lines: list[str] = []
    if title_en:
        tab_en_lines.extend([title_en, ''])
        tab_ja_lines.extend([title_ja or title_en, ''])
        panel_en_lines.extend([title_en, ''])
        panel_ja_lines.extend([title_ja or title_en, ''])
    for en, ja, hk in items:
        ja_disp = ja or en
        prefix = f'[{hk}] ' if hk else ''
        tab_en_lines.append(f'  {prefix}{en}')
        tab_ja_lines.append(f'  {prefix}{ja_disp}')
        panel_en_lines.append(en)
        panel_ja_lines.append(ja_disp)
    return ('\n'.join(tab_en_lines), '\n'.join(tab_ja_lines), '\n'.join(panel_en_lines), '\n'.join(panel_ja_lines))
__all__ = ['render']
