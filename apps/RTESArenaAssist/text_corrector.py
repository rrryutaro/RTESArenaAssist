"""text_corrector.py — 翻訳結果文の言語別自然化補正パイプライン。

テンプレ翻訳 + placeholder 置換完了後の翻訳結果文に
対して、言語別ルール（`i18n/<lang>/_rules.json` の `text_corrections`）を
順次適用する。ルールは翻訳でない言語別規則のため、翻訳ローダに載らない
`_` 接頭辞ファイルに置く。

API:
  apply_text_corrections(text: str, lang: str, paths=None) -> str
    指定言語の補正ルールを順次適用し、補正済テキストを返す。
    該当言語のルールが未定義 / 空なら原文を返す（pass-through）。
    paths を渡すと、その JSON 群（`{"corrections": {lang: [...]}}` 形式）を
    内蔵ルールの代わりに読み込む（将来のカスタムルール用）。
"""

from __future__ import annotations

import json
import re
from typing import Optional

import i18n_helper as i18n

# キャッシュ: {lang: [(compiled_pattern, replace_str), ...]}。key=(lang, paths)。
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
    """`lang` の補正ルールを `_RULES` にキャッシュする。

    paths 省略時は i18n コア（`i18n/<lang>/_rules.json` の text_corrections）から読む。
    paths 指定時はその JSON 群（旧 `{"corrections": {lang: [...]}}` 形式）を読む。
    """
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
    """言語別補正ルールを text に順次適用する。

    lang に対応するルールが未定義 / 空なら原文をそのまま返す。
    """
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
