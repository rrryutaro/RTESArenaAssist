# -*- coding: utf-8 -*-
"""spell_effect_text.py — 呪文効果の説明文テンプレ翻訳（中立リーダ）。

ゲームは効果説明を SPELLMKR.TXT のテンプレ(#00〜#42, %0〜%5 / %a / %b / %c / %f
プレースホルダ)から値を埋めて描画する。本モジュールは描画済みテキストを各テンプレの
正規表現で照合し、対応する日本語テンプレへ値を差し込んで翻訳する。施設に依存しない
中立ヘルパーで、spell_reader.translate_effect_text から利用する。

EN テンプレはユーザー環境の Arena 資産（SPELLMKR.TXT）から実行時に読む。
"""
from __future__ import annotations

import os
import re

# EN テンプレ（SPELLMKR.TXT #00〜#42）は公開版で原文を同梱しないため内蔵しない。
# `_en_templates()` がユーザー環境（docs loose / GLOBAL.BSA）から実行時に読む。

# JA 翻訳資産は i18n カテゴリ spell_effect_text に持つ。
# EN テンプレは runtime SPELLMKR から読む(公開非同梱)・JA は bundle 同梱。
# template→i18n の id、%c/%b/%f の値語→surface 逆引き(value)で解決する。


def _template_ja(idx: int) -> str | None:
    """SPELLMKR テンプレ idx の JA を i18n から返す(未収録は None)。"""
    import i18n_helper as i18n
    return i18n.text_opt(f"spell_effect_text.template.{idx}")


_PLACEHOLDER_RE = re.compile(r"%(\d|a|b|c|f)")


def _parse_spellmkr(data: str) -> dict[int, str]:
    """SPELLMKR.TXT 本文を {idx: テンプレ文} に分解する（#NN 区切り・空白畳み）。"""
    out: dict[int, str] = {}
    for m in re.finditer(r"#(\d+)\r?\n(.*?)(?=#\d+\r?\n|$)", data, re.S):
        out[int(m.group(1))] = " ".join(m.group(2).split())
    return out


def _en_templates() -> dict[int, str]:
    """EN テンプレを SPELLMKR.TXT から読む（公開版は原文を同梱しない）。

    loose な SPELLMKR.TXT を優先し、無ければユーザー Arena install の VFS
    （GLOBAL.BSA・TXT 非暗号）から読む。どちらも無ければ空（EN テンプレ非依存経路のみ動作）。
    """
    loose = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs", "ARENA-data",
        "TXT", "SPELLMKR.TXT")
    try:
        if os.path.isfile(loose):
            with open(loose, "r", encoding="latin-1") as f:
                out = _parse_spellmkr(f.read())
            if out:
                return out
    except OSError:
        pass
    try:
        from runtime_paths import install_vfs
        vfs = install_vfs()
        if vfs is not None:
            data = vfs.read("SPELLMKR.TXT")
            if data is not None:
                return _parse_spellmkr(data.decode("latin-1", errors="replace"))
    except Exception:  # noqa: BLE001 - 解決失敗は空テンプレで継続
        pass
    return {}


_COMPILED: list[tuple[re.Pattern, list[str], int]] | None = None


def _build() -> list[tuple[re.Pattern, list[str], int]]:
    """各 EN テンプレ → (regex, placeholder順, idx) を構築する。"""
    out: list[tuple[re.Pattern, list[str], int]] = []
    for idx, en in _en_templates().items():
        if _template_ja(idx) is None:
            continue
        order: list[str] = []
        seen: dict[str, str] = {}
        parts: list[str] = []
        last = 0
        # %% を一旦保護
        for m in re.finditer(r"%%|%(\d|a|b|c|f)", en):
            parts.append(re.escape(en[last:m.start()]))
            tok = m.group(0)
            if tok == "%%":
                parts.append("%")
            else:
                name = tok[1:]
                gid = f"p_{name}"
                if name in seen:
                    parts.append(f"(?P={gid})")
                else:
                    seen[name] = gid
                    order.append(name)
                    if name in ("b",):
                        parts.append(f"(?P<{gid}>\\w*)")
                    elif name in ("c",):
                        parts.append(f"(?P<{gid}>[A-Za-z]+)")
                    elif name in ("f",):
                        parts.append(f"(?P<{gid}>[^.]+?)")
                    else:
                        parts.append(f"(?P<{gid}>\\d+)")
            last = m.end()
        parts.append(re.escape(en[last:]))
        pattern = "^" + "".join(parts) + r"\.?\s*$"
        try:
            out.append((re.compile(pattern), order, idx))
        except re.error:
            continue
    return out


def _candidate_prefixes(text_en: str) -> list[str]:
    """残留文字列が後ろに混ざった場合に、成立し得る文末候補を長い順で返す。"""
    s = " ".join((text_en or "").split()).strip()
    if not s:
        return []
    out: list[str] = [s]
    for m in re.finditer(r"\.", s):
        cand = s[:m.end()].strip()
        if cand and cand not in out:
            out.append(cand)
    return sorted(out, key=len, reverse=True)


def _translate_value(name: str, value: str) -> str:
    import i18n_helper as i18n
    if name == "c":
        return i18n.value("spell_effect_text", value) or value
    if name in ("b", "f"):
        v = value.strip()
        if name == "b" and v == "":
            # %b 不在(空文字)は専用 id で解決(surface 逆引き不可のため)。
            return i18n.text_opt("spell_effect_text.slot_b_absent") or ""
        return i18n.value("spell_effect_text", v) or v
    return value


def match_template(text_en: str) -> tuple[int, str, str] | None:
    """描画済み効果説明文に対応する (template_id, 正規化EN, JA) を返す。"""
    global _COMPILED
    if not text_en:
        return None
    if _COMPILED is None:
        _COMPILED = _build()
    for s in _candidate_prefixes(text_en):
        for pattern, order, idx in _COMPILED:
            m = pattern.match(s)
            if not m:
                continue
            ja = _template_ja(idx) or ""
            for name in order:
                val = _translate_value(name, m.group(f"p_{name}"))
                ja = ja.replace(f"%{name}", val)
            ja = ja.replace("%%", "%")
            return idx, s, ja
    return None


def normalize(text_en: str) -> str:
    """残留文字列を落とした、テンプレート一致済みのEN文を返す。"""
    matched = match_template(text_en)
    return matched[1] if matched else " ".join((text_en or "").split()).strip()


def translate(text_en: str) -> str:
    """描画済み効果説明文を日本語に翻訳する。未対応は空文字を返す。"""
    matched = match_template(text_en)
    return matched[2] if matched else ""


__all__ = ["match_template", "normalize", "translate"]
