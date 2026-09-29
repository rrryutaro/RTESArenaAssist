from __future__ import annotations
import os
import app_resources
import i18n_helper as i18n
FALLBACK_LANGS = ('en', 'ja')

def page_langs(lang: str | None=None) -> tuple[str, ...]:
    order = [code for code in (lang or i18n.current_lang(),) if code]
    order += [code for code in FALLBACK_LANGS if code not in order]
    return tuple(order)

def list_pages(mode: str, lang: str | None=None) -> list[tuple[str, str]]:
    pages: dict[str, str] = {}
    for code in page_langs(lang):
        rel = f'manual/{mode}/{code}'
        if not app_resources.is_dir(rel):
            continue
        for name in app_resources.listdir(rel):
            if name.lower().endswith('.html'):
                pages.setdefault(os.path.splitext(name)[0], f'{rel}/{name}')
    return sorted(pages.items())

def read_page(mode: str, name: str, lang: str | None=None) -> str:
    for code in page_langs(lang):
        text = app_resources.read_text(f'manual/{mode}/{code}/{name}')
        if text is not None:
            return text
    return ''
__all__ = ['FALLBACK_LANGS', 'page_langs', 'list_pages', 'read_page']
