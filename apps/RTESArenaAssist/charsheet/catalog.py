from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import app_resources
import i18n_helper as i18n
from charsheet.template_engine import title_of
BUILTIN_DIR = 'assets/charsheet'
USER_DIR_NAME = 'character_sheets'
_SUFFIX = '.html'

@dataclass(frozen=True)
class TemplateEntry:
    id: str
    file_name: str
    is_user: bool
    name: str

def user_dir() -> Optional[Path]:
    from services.manual_pack import user_dir as settings_dir
    base = settings_dir()
    return base / USER_DIR_NAME if base is not None else None

def _builtin_name(file_name: str, text: Optional[str]) -> str:
    stem = file_name[:-len(_SUFFIX)]
    return i18n.text_opt(f'charsheet.template.{stem}') or title_of(text or '') or stem

def builtin_templates() -> list[TemplateEntry]:
    out: list[TemplateEntry] = []
    for file_name in app_resources.listdir(BUILTIN_DIR):
        if not file_name.lower().endswith(_SUFFIX):
            continue
        text = app_resources.read_text(f'{BUILTIN_DIR}/{file_name}')
        out.append(TemplateEntry(id=f'builtin:{file_name}', file_name=file_name, is_user=False, name=_builtin_name(file_name, text)))
    return out

def _read_user_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError):
        return None

def user_templates() -> list[TemplateEntry]:
    folder = user_dir()
    if folder is None or not folder.is_dir():
        return []
    out: list[TemplateEntry] = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
        if not (path.is_file() and path.name.lower().endswith(_SUFFIX)):
            continue
        text = _read_user_file(path)
        base = title_of(text or '') or path.name[:-len(_SUFFIX)]
        out.append(TemplateEntry(id=f'user:{path.name}', file_name=path.name, is_user=True, name=i18n.tr('status.view.user_template', name=base)))
    return out

def all_templates() -> list[TemplateEntry]:
    return builtin_templates() + user_templates()

def find(template_id: str) -> Optional[TemplateEntry]:
    for entry in all_templates():
        if entry.id == template_id:
            return entry
    return None

def load(entry: TemplateEntry) -> Optional[str]:
    if entry.is_user:
        folder = user_dir()
        return _read_user_file(folder / entry.file_name) if folder else None
    return app_resources.read_text(f'{BUILTIN_DIR}/{entry.file_name}')

def base_dir(entry: TemplateEntry) -> Optional[str]:
    if not entry.is_user:
        return None
    folder = user_dir()
    return str(folder) if folder is not None else None

def ensure_user_dir() -> Optional[Path]:
    folder = user_dir()
    if folder is None:
        return None
    if folder.is_dir():
        return folder
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    for entry in builtin_templates():
        text = load(entry)
        if text is None:
            continue
        target = folder / entry.file_name
        if target.exists():
            continue
        try:
            with open(target, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
        except OSError:
            continue
    return folder
__all__ = ['BUILTIN_DIR', 'USER_DIR_NAME', 'TemplateEntry', 'user_dir', 'builtin_templates', 'user_templates', 'all_templates', 'find', 'load', 'base_dir', 'ensure_user_dir']
