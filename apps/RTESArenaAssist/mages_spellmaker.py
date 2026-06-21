# -*- coding: utf-8 -*-
"""mages_spellmaker.py — 魔術師ギルド Spellmaker の FORM カタログと数値読み取り（完全分離）。

観測結果の FORM カタログに基づく。武具店/神殿/宿屋の
コードを呼ばず本ファイルに閉じて実装する（中立な analyzer.read_bytes のみ使用）。

数値入力画面は15+2 FORM に有界。SpellData レコード 0x57E6 に u16 LE・6バイト間隔で
パラメータが格納される（grp index 0..5）。編集中効果の値が入る列は登録スロット番号
（slot 0/1/2 = 列 +0/+2/+4）。FORM はその効果の入力レイアウトを定める。
"""
from __future__ import annotations

import logging
import html
import re

_log = logging.getLogger("RTESArenaAssist")

# SpellData レコード（u16 LE, 6バイト間隔で grp が並ぶ）
SPELLDATA_OFFSET = 0x57E6
_GRP_OFFS = [0x57E6, 0x57EC, 0x57F2, 0x57F8, 0x57FE, 0x5804]

# 効果タイトル → FORM 名（実測。未掲載効果は同型 FORM へ後追い）
EFFECT_TO_FORM = {
    "Damage": "FORM1",
    "Continuous Damage": "FORM2",
    "Cause Disease": "FORM4",
    "Cause Poison": "FORM4A",
    "Cause Curse": "FORM5",
    "Fortify Attribute": "FORM6",
    "Drain Attribute": "FORM6A",
    "Light": "FORM8",
    "Create Shield": "FORM9",
    "Designate as Non-Target": "FORM10",
    "Levitate": "FORM11",
    "Create Wall": "FORM13",
    "Regenerate": "FORM15",
}

# FORM → grp index→ラベル（実測）。None は未使用 grp。
# 表記は英語ラベル（翻訳辞書側で JA に変換）。
FORM_FIELDS = {
    "FORM1": {0: "Range min", 1: "Range max", 2: "Increase min",
              3: "Increase max", 4: "Levels"},
    "FORM2": {0: "Range min", 1: "Range max", 2: "Increase min",
              3: "Increase max", 4: "Levels", 5: "Strikes"},
    "FORM3": {0: "Chance", 1: "Increase", 4: "per Levels"},
    "FORM4": {0: "Chance", 1: "Increase", 2: "Deterioration",
              3: "per Rnds", 4: "per Levels", 5: "Duration"},
    "FORM5": {0: "Chance", 1: "Increase", 2: "Duration per Lv",
              4: "Increase per Lv", 5: "Duration"},
    "FORM6": {0: "Increase", 1: "Rate of Release", 4: "Release per Rnds",
              5: "Duration"},
    "FORM6A": {0: "Decrease", 1: "Rate of Recovery", 4: "Recovery per Rnds",
               5: "Duration"},
    "FORM7": {0: "Decrease"},
    "FORM8": {0: "Light level", 5: "Duration"},
    "FORM9": {0: "Strength", 1: "Increase", 4: "Levels"},
    "FORM10": {0: "Chance", 1: "Increase", 2: "Duration per Lv",
               4: "Increase per Lv", 5: "Duration"},
    "FORM11": {0: "Base Time", 1: "Increase", 4: "per Levels"},
    "FORM13": {0: "Number"},
    "FORM15": {0: "Gain", 1: "Every", 4: "For"},
}
# 別名（同一レイアウト）
FORM_ALIASES = {"FORM4A": "FORM4", "FORM12": "FORM3", "FORM14": "FORM5"}

# FORM フィールドラベルの日本語訳（数値入力画面の翻訳表示用）
FORM_FIELD_JA = {
    "Range min": "射程 最小", "Range max": "射程 最大",
    "Increase min": "増加 最小", "Increase max": "増加 最大",
    "Levels": "レベル", "Strikes": "回数", "Chance": "確率",
    "Increase": "増加", "Deterioration": "悪化",
    "per Rnds": "毎ラウンド", "per Levels": "毎レベル", "Duration": "持続",
    "Duration per Lv": "持続/レベル", "Increase per Lv": "増加/レベル",
    "Rate of Release": "解放率", "Release per Rnds": "解放/ラウンド",
    "Rate of Recovery": "回復率", "Recovery per Rnds": "回復/ラウンド",
    "Decrease": "減少", "Light level": "光量", "Strength": "強度",
    "Base Time": "基本時間", "Number": "数",
    "Gain": "獲得", "Every": "毎", "For": "期間",
}


def field_label_ja(label_en: str) -> str:
    """FORM フィールドラベルの日本語訳。未登録は原文。"""
    return FORM_FIELD_JA.get(label_en, label_en)


def _u16(analyzer, anchor: int, off: int):
    try:
        raw = analyzer.read_bytes(anchor + off, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def resolve_form(effect_title: str) -> str | None:
    """効果タイトル（例 'Damage Health'）から FORM を解決する。"""
    title = (effect_title or "").strip()
    if not title:
        return None
    # 先頭一致（'Damage Health' → 'Damage', 'Drain Attribute Strength' → 'Drain Attribute'）
    for effect, form in EFFECT_TO_FORM.items():
        if title == effect or title.startswith(effect + " ") or title.startswith(effect):
            return form
    return None


def read_form_values(analyzer, anchor: int, form: str,
                     slot: int = 0) -> dict[str, int]:
    """指定 FORM の各フィールド値を SpellData レコードから読む。

    slot: 編集中効果の登録スロット番号（0=列+0 / 1=列+2 / 2=列+4）。既定 0。
    戻り値: {ラベル: 値}。読めない grp は除外。
    """
    form = FORM_ALIASES.get(form, form)
    fields = FORM_FIELDS.get(form)
    if not fields:
        return {}
    col = 0 if slot <= 0 else min(slot, 2) * 2
    out: dict[str, int] = {}
    for grp, label in fields.items():
        base = _GRP_OFFS[grp]
        v = _u16(analyzer, anchor, base + col)
        if v is not None:
            out[label] = v
    if out and all(v == 0 for v in out.values()):
        return {}
    return out


def all_form_labels() -> set[str]:
    """全 FORM のラベル集合（翻訳辞書の網羅チェック用）。"""
    out: set[str] = set()
    for fields in FORM_FIELDS.values():
        out.update(fields.values())
    return out


# 各 FORM の数値入力画面レイアウト（FORM画像で確定）。ゲーム画面の行
# 構成を再現する。``{Field}`` は read_form_values の値で置換する。EN/JA 両方を定義
# し、翻訳タブで原文・訳の両方を出せるようにする。
FORM_LAYOUT_EN: dict[str, list[str]] = {
    "FORM1": ["Range: {Range min} to {Range max}",
              "Increase: {Increase min} to {Increase max} per {Levels} Levels"],
    "FORM2": ["Range: {Range min} to {Range max}",
              "Increase: {Increase min} to {Increase max} per {Levels} Levels",
              "Strikes: {Strikes} times"],
    "FORM3": ["Chance: {Chance}%",
              "Increase: {Increase}% per {per Levels} Levels"],
    "FORM4": ["Chance: {Chance}%",
              "Increase: {Increase}% per {per Levels} Levels",
              "Deterioration: {Deterioration} pts per {per Rnds} Rnds",
              "Duration: {Duration} Rnds per level"],
    "FORM5": ["Chance: {Chance}%",
              "Increase: {Increase}% per {Increase per Lv} Levels",
              "Duration: {Duration} Rnds per {Duration per Lv} level"],
    "FORM6": ["Increase: {Increase} pts", "Duration: {Duration} Rnds",
              "Rate of Release: {Rate of Release} pts per {Release per Rnds} Rnds"],
    "FORM6A": ["Decrease: {Decrease} pts", "Duration: {Duration} Rnds",
               "Rate of Recovery: {Rate of Recovery} pts per {Recovery per Rnds} Rnds"],
    "FORM7": ["Decrease: {Decrease} pts"],
    "FORM8": ["Light level: {Light level}", "Duration: {Duration} Rnds"],
    "FORM9": ["Strength: {Strength} Hit Points",
              "Increase: {Increase} Hits per {Levels} Levels"],
    "FORM10": ["Chance: {Chance}%",
               "Increase: {Increase}% per {Increase per Lv} Levels",
               "Duration: {Duration} Rnds per {Duration per Lv} level"],
    "FORM11": ["Base Time: {Base Time} Rnds",
               "Increase: {Increase} Rnds per {per Levels} Levels"],
    "FORM13": ["Number: {Number}"],
    "FORM15": ["Gain: {Gain} Hit Points", "Every: {Every} Rnds",
               "For: {For} Rnds per level"],
}
FORM_LAYOUT_JA: dict[str, list[str]] = {
    "FORM1": ["射程: {Range min}〜{Range max}",
              "増加: {Increase min}〜{Increase max} / {Levels}レベルごと"],
    "FORM2": ["射程: {Range min}〜{Range max}",
              "増加: {Increase min}〜{Increase max} / {Levels}レベルごと",
              "回数: {Strikes}回"],
    "FORM3": ["確率: {Chance}%", "増加: {Increase}% / {per Levels}レベルごと"],
    "FORM4": ["確率: {Chance}%", "増加: {Increase}% / {per Levels}レベルごと",
              "悪化: {Deterioration}ポイント / {per Rnds}ラウンドごと",
              "持続: {Duration}ラウンド / レベルごと"],
    "FORM5": ["確率: {Chance}%", "増加: {Increase}% / {Increase per Lv}レベルごと",
              "持続: {Duration}ラウンド / {Duration per Lv}レベルごと"],
    "FORM6": ["強化: {Increase}ポイント", "持続: {Duration}ラウンド",
              "放出率: {Rate of Release}ポイント / {Release per Rnds}ラウンドごと"],
    "FORM6A": ["減少: {Decrease}ポイント", "持続: {Duration}ラウンド",
               "回復率: {Rate of Recovery}ポイント / {Recovery per Rnds}ラウンドごと"],
    "FORM7": ["減少: {Decrease}ポイント"],
    "FORM8": ["光レベル: {Light level}", "持続: {Duration}ラウンド"],
    "FORM9": ["強度: {Strength}ヒットポイント",
              "増加: {Increase}ヒット / {Levels}レベルごと"],
    "FORM10": ["確率: {Chance}%", "増加: {Increase}% / {Increase per Lv}レベルごと",
               "持続: {Duration}ラウンド / {Duration per Lv}レベルごと"],
    "FORM11": ["基本時間: {Base Time}ラウンド",
               "増加: {Increase}ラウンド / {per Levels}レベルごと"],
    "FORM13": ["数: {Number}"],
    "FORM15": ["回復: {Gain}ヒットポイント", "間隔: {Every}ラウンドごと",
               "持続: {For}ラウンド/レベル"],
}
# レイアウト同一の別名（アセット重複）
for _src, _dsts in {"FORM4": ["FORM4A"], "FORM3": ["FORM12"],
                    "FORM5": ["FORM14"]}.items():
    for _dst in _dsts:
        FORM_LAYOUT_EN[_dst] = FORM_LAYOUT_EN[_src]
        FORM_LAYOUT_JA[_dst] = FORM_LAYOUT_JA[_src]


def _fill_layout(lines: list[str], values: dict) -> list[str]:
    """``{Field}`` トークンを values で置換した行を返す（未取得はダッシュ）。"""
    out: list[str] = []
    for line in lines:
        s = line
        for field, val in values.items():
            s = s.replace("{" + field + "}", str(val))
        out.append(re.sub(r"\{[^}]+\}", "—", s))
    return out


def format_form_layout(form: str, values: dict) -> tuple[list[str], list[str]]:
    """FORM の画面配置を再現した (EN行, JA行) を返す。未定義なら ([], [])。"""
    f = resolve_form(form) or form
    en = FORM_LAYOUT_EN.get(f)
    ja = FORM_LAYOUT_JA.get(f)
    if not en or not ja:
        return ([], [])
    return (_fill_layout(en, values), _fill_layout(ja, values))


def _fmt_value(values: dict, key: str, suffix: str = "") -> str:
    if key not in values:
        return "—"
    return f"{values[key]}{suffix}"


def _line(label_en: str, label_ja: str, en_value: str, ja_value: str = "") -> str:
    body = f"{label_en}（{label_ja}）: {en_value}"
    if ja_value:
        body += f" / {ja_value}"
    return body


def format_form_display(form: str, values: dict) -> list[str]:
    """翻訳タブ向けの bilingual FORM 表示行を返す。

    ゲーム画面の英語レイアウトをそのまま併記するのではなく、入力項目の
    原文ラベルと訳語を 1 つのラベルにまとめ、値側は日本語で読める単位に整える。
    """
    base_form = resolve_form(form) or form
    f = FORM_ALIASES.get(base_form, base_form)
    if f == "FORM1":
        return [
            _line("Range", "射程",
                  f"{_fmt_value(values, 'Range min')}〜{_fmt_value(values, 'Range max')}"),
            _line("Increase", "増加",
                  f"{_fmt_value(values, 'Increase min')}〜{_fmt_value(values, 'Increase max')}"
                  f" / {_fmt_value(values, 'Levels')}レベルごと"),
        ]
    if f == "FORM2":
        return [
            *_line_form1(values),
            _line("Strikes", "回数",
                  f"{_fmt_value(values, 'Strikes')}回"),
        ]
    if f in ("FORM3", "FORM12"):
        return [
            _line("Chance", "確率", _fmt_value(values, "Chance", "%"),
                  ""),
            _line("Increase", "増加", _fmt_value(values, "Increase", "%"),
                  f"{_fmt_value(values, 'per Levels')}レベルごと"),
        ]
    if f in ("FORM4", "FORM4A"):
        return [
            _line("Chance", "確率", _fmt_value(values, "Chance", "%"),
                  ""),
            _line("Increase", "増加", _fmt_value(values, "Increase", "%"),
                  f"{_fmt_value(values, 'per Levels')}レベルごと"),
            _line("Deterioration", "悪化",
                  f"{_fmt_value(values, 'Deterioration')}ポイント",
                  f"{_fmt_value(values, 'per Rnds')}ラウンドごと"),
            _line("Duration", "持続",
                  f"{_fmt_value(values, 'Duration')}ラウンド",
                  "レベルごと"),
        ]
    if f in ("FORM5", "FORM14", "FORM10"):
        return [
            _line("Chance", "確率", _fmt_value(values, "Chance", "%"),
                  ""),
            _line("Increase", "増加", _fmt_value(values, "Increase", "%"),
                  f"{_fmt_value(values, 'Increase per Lv')}レベルごと"),
            _line("Duration", "持続",
                  f"{_fmt_value(values, 'Duration')}ラウンド",
                  f"{_fmt_value(values, 'Duration per Lv')}レベルごと"),
        ]
    if f == "FORM6":
        return [
            _line("Increase", "増加",
                  f"{_fmt_value(values, 'Increase')}ポイント"),
            _line("Duration", "持続",
                  f"{_fmt_value(values, 'Duration')}ラウンド"),
            _line("Rate of Release", "解放率",
                  f"{_fmt_value(values, 'Rate of Release')}ポイント",
                  f"{_fmt_value(values, 'Release per Rnds')}ラウンドごと"),
        ]
    if f == "FORM6A":
        return [
            _line("Decrease", "減少",
                  f"{_fmt_value(values, 'Decrease')}ポイント"),
            _line("Duration", "持続",
                  f"{_fmt_value(values, 'Duration')}ラウンド"),
            _line("Rate of Recovery", "回復率",
                  f"{_fmt_value(values, 'Rate of Recovery')}ポイント",
                  f"{_fmt_value(values, 'Recovery per Rnds')}ラウンドごと"),
        ]
    if f == "FORM7":
        return [_line("Decrease", "減少",
                      f"{_fmt_value(values, 'Decrease')}ポイント")]
    if f == "FORM8":
        return [
            _line("Light level", "光量", _fmt_value(values, "Light level")),
            _line("Duration", "持続",
                  f"{_fmt_value(values, 'Duration')}ラウンド"),
        ]
    if f == "FORM9":
        return [
            _line("Strength", "強度",
                  f"{_fmt_value(values, 'Strength')}ヒットポイント"),
            _line("Increase", "増加",
                  f"{_fmt_value(values, 'Increase')}ヒット",
                  f"{_fmt_value(values, 'Levels')}レベルごと"),
        ]
    if f == "FORM11":
        return [
            _line("Base Time", "基本時間",
                  f"{_fmt_value(values, 'Base Time')}ラウンド"),
            _line("Increase", "増加",
                  f"{_fmt_value(values, 'Increase')}ラウンド",
                  f"{_fmt_value(values, 'per Levels')}レベルごと"),
        ]
    if f == "FORM13":
        return [_line("Number", "数", _fmt_value(values, "Number"))]
    if f == "FORM15":
        return [
            _line("Gain", "獲得",
                  f"{_fmt_value(values, 'Gain')}ヒットポイント"),
            _line("Every", "毎",
                  f"{_fmt_value(values, 'Every')}ラウンドごと"),
            _line("For", "期間",
                  f"{_fmt_value(values, 'For')}ラウンド/レベル"),
        ]
    return [
        _line(k, field_label_ja(k), str(v))
        for k, v in values.items()
    ]


def _html_label(label: str) -> str:
    m = re.fullmatch(r"(.+?)（(.+?)）", label)
    if not m:
        return label
    return f"{m.group(1)} / {m.group(2)}"


def _value_html(value: str) -> str:
    parts: list[str] = []
    for part in re.split(r"(\d+|—)", value):
        if not part:
            continue
        esc = html.escape(part)
        if re.fullmatch(r"\d+|—", part):
            parts.append(
                "<span style='background-color:#1c2e3f;"
                "border:1px solid #2a4258;border-radius:3px;"
                "padding:1px 5px;color:#ffffff;font-weight:bold;'>"
                f"{esc}</span>"
            )
        else:
            parts.append(esc)
    return "".join(parts)


def format_form_display_html(
        form: str, values: dict, *, cost: int | None = None,
        title_en: str = "", title_ja: str = "") -> str:
    """数値入力画面の翻訳タブ向け HTML 表示を返す。

    QLabel の rich text として描く前提で、ラベル列と値列を分けて揃える。
    文字列版 ``format_form_display`` と同じ値を使い、本文の意味は変えない。
    """
    lines = list(format_form_display(form, values))
    if cost is not None:
        lines.append(f"Spell Cost（呪文コスト）: {cost}")

    title = ""
    if title_en or title_ja:
        if title_en and title_ja and title_en != title_ja:
            title = (
                f"{html.escape(title_en)} "
                f"<span style='color:#a0c4d8;'>{html.escape(title_ja)}</span>"
            )
        else:
            title = html.escape(title_ja or title_en)

    rows: list[str] = []
    for line in lines:
        if ": " in line:
            label, value = line.split(": ", 1)
        else:
            label, value = line, ""
        rows.append(
            "<tr>"
            "<td style='color:#7ab8d4;font-weight:bold;"
            "padding:2px 18px 2px 0;white-space:nowrap;vertical-align:top;'>"
            f"{html.escape(_html_label(label))}"
            "</td>"
            "<td style='color:#c9d1e0;padding:2px 0;vertical-align:top;'>"
            f"{_value_html(value)}"
            "</td>"
            "</tr>"
        )

    title_html = (
        "<div style='color:#c9d1e0;font-weight:bold;margin-bottom:6px;'>"
        f"{title}</div>"
        if title else ""
    )
    return (
        "<div style='line-height:1.35;'>"
        f"{title_html}"
        "<table style='border-collapse:collapse;margin-top:2px;'>"
        + "".join(rows) +
        "</table></div>"
    )


def _line_form1(values: dict) -> list[str]:
    return [
        _line("Range", "射程",
              f"{_fmt_value(values, 'Range min')}〜{_fmt_value(values, 'Range max')}"),
        _line("Increase", "増加",
              f"{_fmt_value(values, 'Increase min')}〜{_fmt_value(values, 'Increase max')}"
              f" / {_fmt_value(values, 'Levels')}レベルごと"),
    ]


def _effect_details(analyzer, anchor: int) -> list[dict]:
    try:
        from spell_reader import read_spell_detail
        data = read_spell_detail(analyzer, anchor)
    except Exception:  # noqa: BLE001
        _log.exception("spellmaker effect detail read failed")
        return []
    details = data.get("effect_details", [])
    if isinstance(details, list) and details:
        return [d for d in details if isinstance(d, dict)]
    effect_en = data.get("effect_en", "")
    if not effect_en or effect_en == "(none)":
        return []
    return [{
        "slot": data.get("effect_slot", 0),
        "effect_en": effect_en,
        "effect_ja": data.get("effect_ja", ""),
        "text_en": data.get("text_en", ""),
        "text_ja": data.get("text_ja", ""),
    }]


def _same_form(form_a: str | None, form_b: str | None) -> bool:
    if not form_a or not form_b:
        return False
    return FORM_ALIASES.get(form_a, form_a) == FORM_ALIASES.get(form_b, form_b)


def resolve_edit_slot(analyzer, anchor: int, effect_title: str = "") -> int:
    """現在の FORM 入力が対応する SpellData 効果スロットを推定する。

    修正時は効果タイトルと一致する既存効果を使う。追加時は、使用済みスロットの
    次の列を使うことで、直前効果 slot0 の残留値を表示しない。
    """
    title = (effect_title or "").strip()
    details = _effect_details(analyzer, anchor)
    if title:
        for detail in details:
            if detail.get("effect_en") == title:
                slot = detail.get("slot", 0)
                return max(0, min(int(slot or 0), 2))
    used = [
        int(detail.get("slot", idx) or 0)
        for idx, detail in enumerate(details)
        if detail.get("effect_en") and detail.get("effect_en") != "(none)"
    ]
    if used:
        return max(0, min(len(set(used)), 2))
    return 0


def resolve_effect_title_from_record(analyzer, anchor: int,
                                     form: str = "") -> str:
    """FORM 名から SpellData 内の対象効果名を補完する。"""
    details = _effect_details(analyzer, anchor)
    if not details:
        return ""
    wanted_form = FORM_ALIASES.get(form, form)
    if wanted_form:
        for detail in reversed(details):
            effect = detail.get("effect_en", "")
            if _same_form(resolve_form(effect), wanted_form):
                return effect
    for detail in reversed(details):
        effect = detail.get("effect_en", "")
        if effect and effect != "(none)":
            return effect
    return ""


__all__ = [
    "SPELLDATA_OFFSET", "EFFECT_TO_FORM", "FORM_FIELDS", "FORM_ALIASES",
    "resolve_form", "read_form_values", "all_form_labels",
    "format_form_layout", "format_form_display", "format_form_display_html",
    "FORM_LAYOUT_EN", "FORM_LAYOUT_JA",
    "resolve_edit_slot", "resolve_effect_title_from_record",
]
