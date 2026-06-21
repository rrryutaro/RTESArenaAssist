"""i18n_mods.py — ユーザー translation mod のローダ（表示翻訳のみ）。

`<user_data>/RTESArenaAssist/mods/translations/*.json` を列挙し、表示翻訳の上書きを
locale 別にマージする。ライブ照合には使わない（呼び出し側の責務）。

適用順（deterministic）:
  1. ファイルを列挙。
  2. 各ファイルの priority を読む（無ければ 0）。
  3. priority 昇順 → 正規化ファイル名昇順 に並べる。
  4. その順で適用し、後から適用された text が勝つ
     （＝同一 ID は priority 大が勝つ／同 priority はファイル名後が勝つ）。

schema 不正・読み取り不能なファイルは skip し warning に記録（全体を fail にしない）。
"""
from __future__ import annotations

import glob
import json
import os

SCHEMA = "rtesaa.translation_mod"


class TranslationMod:
    def __init__(self, *, filename: str, locale: str, priority: int,
                 texts: dict[int, str], registry_hash: str):
        self.filename = filename
        self.locale = locale
        self.priority = priority
        self.texts = texts
        self.registry_hash = registry_hash


def _load_one(path: str, warnings: list[str]) -> TranslationMod | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        warnings.append(f"mod unreadable: {os.path.basename(path)}: {exc}")
        return None
    if raw.get("schema") != SCHEMA:
        warnings.append(
            f"mod skipped (bad schema): {os.path.basename(path)}")
        return None
    locale = raw.get("locale")
    if not locale:
        warnings.append(f"mod missing locale: {os.path.basename(path)}")
        return None
    texts: dict[int, str] = {}
    for t in raw.get("texts") or []:
        try:
            texts[int(t["id"])] = str(t["text"])
        except (KeyError, ValueError, TypeError):
            warnings.append(
                f"mod bad text entry in {os.path.basename(path)}: {t!r}")
    try:
        priority = int(raw.get("priority", 0))
    except (ValueError, TypeError):
        priority = 0
    return TranslationMod(
        filename=os.path.basename(path),
        locale=locale,
        priority=priority,
        texts=texts,
        registry_hash=str(raw.get("registry_hash", "")),
    )


class ModSet:
    """読み込み済み mod 群を locale 別にマージしたもの。"""

    def __init__(self, mods: list[TranslationMod], warnings: list[str]):
        self.mods = mods
        self.warnings = warnings
        # locale -> { id: text }（適用順で後勝ち）。
        self._merged: dict[str, dict[int, str]] = {}
        ordered = sorted(
            mods, key=lambda m: (m.priority, m.filename.lower()))
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
    """mods ディレクトリから translation mod を読み込む（不在は空 ModSet）。"""
    warnings: list[str] = []
    mods: list[TranslationMod] = []
    if mods_dir and os.path.isdir(mods_dir):
        for path in sorted(glob.glob(os.path.join(mods_dir, "*.json"))):
            mod = _load_one(path, warnings)
            if mod is not None:
                mods.append(mod)
    return ModSet(mods, warnings)


__all__ = ["TranslationMod", "ModSet", "load_mods", "SCHEMA"]
