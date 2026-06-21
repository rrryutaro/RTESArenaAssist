
from __future__ import annotations

import json
import re
from typing import Optional

import i18n_helper as i18n

_RULES: dict[str, list[tuple[re.Pattern, str]]] = {}
_LOADED_KEY: tuple | None = None


def _compile(rules: list) -> list[tuple[re.Pattern, str]]:
    compiled_list = []
    for rule in rules:
        pattern = rule.get("pattern")
        replace = rule.get("replace", "")
        if not pattern:
            continue
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        compiled_list.append((compiled, replace))
    return compiled_list


def _load_rules(lang: str, paths: Optional[list[str]] = None) -> None:
    global _RULES, _LOADED_KEY
    key = (lang, tuple(paths) if paths is not None else None)
    if _LOADED_KEY == key:
        return
    if paths is None:
        rules = i18n.rules(lang).get("text_corrections", [])
        _RULES = {lang: _compile(rules)}
    else:
        _RULES = {}
        for path in paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            for lg, rules in data.get("corrections", {}).items():
                _RULES.setdefault(lg, []).extend(_compile(rules))
    _LOADED_KEY = key


def apply_text_corrections(text: str, lang: str, paths: Optional[list[str]] = None) -> str:
    if not text or not lang:
        return text
    _load_rules(lang, paths)
    rules = _RULES.get(lang, [])
    if not rules:
        return text
    for compiled, replace in rules:
        text = compiled.sub(replace, text)
    return text


if __name__ == "__main__":
    samples = [
        ("非常に攻撃的な上流貴族の卿・Barbyrrya のために何かを回収してみる気は？", "ja"),
        ("There's a Lord Barbyrrya here.", "en"),
        ("夫人・エリザベスに会いたい。", "ja"),
    ]
    for text, lang in samples:
        result = apply_text_corrections(text, lang)
        print(f"[{lang}] {text!r}")
        print(f"   => {result!r}")
        print()
