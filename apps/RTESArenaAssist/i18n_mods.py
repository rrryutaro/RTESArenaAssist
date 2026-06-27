from __future__ import annotations
import glob
import json
import os
SCHEMA = 'rtesaa.translation_mod'

class TranslationMod:

    def __init__(self, *, filename: str, locale: str, priority: int, texts: dict[int, str], registry_hash: str):
        self.filename = filename
        self.locale = locale
        self.priority = priority
        self.texts = texts
        self.registry_hash = registry_hash

def _load_one(path: str, warnings: list[str]) -> TranslationMod | None:
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        warnings.append(f'mod unreadable: {os.path.basename(path)}: {exc}')
        return None
    if raw.get('schema') != SCHEMA:
        warnings.append(f'mod skipped (bad schema): {os.path.basename(path)}')
        return None
    locale = raw.get('locale')
    if not locale:
        warnings.append(f'mod missing locale: {os.path.basename(path)}')
        return None
    texts: dict[int, str] = {}
    for t in raw.get('texts') or []:
        try:
            texts[int(t['id'])] = str(t['text'])
        except (KeyError, ValueError, TypeError):
            warnings.append(f'mod bad text entry in {os.path.basename(path)}: {t!r}')
    try:
        priority = int(raw.get('priority', 0))
    except (ValueError, TypeError):
        priority = 0
    return TranslationMod(filename=os.path.basename(path), locale=locale, priority=priority, texts=texts, registry_hash=str(raw.get('registry_hash', '')))

class ModSet:

    def __init__(self, mods: list[TranslationMod], warnings: list[str]):
        self.mods = mods
        self.warnings = warnings
        self._merged: dict[str, dict[int, str]] = {}
        ordered = sorted(mods, key=lambda m: (m.priority, m.filename.lower()))
        for mod in ordered:
            table = self._merged.setdefault(mod.locale, {})
            table.update(mod.texts)

    def text(self, id: int, locale: str) -> str | None:
        table = self._merged.get(locale)
        if table is None:
            return None
        return table.get(int(id))

    def has_locale(self, locale: str) -> bool:
        return locale in self._merged

def load_mods(mods_dir: str) -> ModSet:
    warnings: list[str] = []
    mods: list[TranslationMod] = []
    if mods_dir and os.path.isdir(mods_dir):
        for path in sorted(glob.glob(os.path.join(mods_dir, '*.json'))):
            mod = _load_one(path, warnings)
            if mod is not None:
                mods.append(mod)
    return ModSet(mods, warnings)
__all__ = ['TranslationMod', 'ModSet', 'load_mods', 'SCHEMA']
