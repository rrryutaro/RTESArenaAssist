"""spell_effect_compose.py — effect-text 合成ヘルパー群。

spell_reader から分離した effect-text 合成ヘルパー群。挙動不変。
"""

from __future__ import annotations
import re

# ──────────────────────────────────────────────────────────────
# 効果合成用の内部定数テーブル
# ──────────────────────────────────────────────────────────────

# Effect ID は効果カテゴリ、subEffects/affectedAttrs が対象を補う。255 は未使用スロット。
# 表示文字列(en,ja)をコードに直書きせず、effect_id/sub_id/attr_id → **翻訳ID**
# (mages.*) の対応のみ保持し、表示は i18n から現在言語で取得する。原文照合アンカーは原文から引く。
# 構成語(target/element/attribute/sub)→翻訳ID。
_DAMAGE_TARGET_IDS = {0: "mages.Health", 1: "mages.Fatigue", 2: "mages.Spell Points"}
_HEAL_TARGET_IDS = {0: "mages.Fatigue", 1: "mages.Health", 2: "mages.Spell Points"}
_ELEMENT_SUB_IDS = {0: "mages.Fire", 1: "mages.Cold", 2: "mages.Shock",
                    3: "mages.Magic", 4: "mages.Poison"}
_ATTRIBUTE_IDS = {0: "mages.Strength", 1: "mages.Intelligence", 2: "mages.Willpower",
                  3: "mages.Agility", 4: "mages.Speed", 5: "mages.Endurance",
                  6: "mages.Personality", 7: "mages.Luck"}
# 合成効果は完成ID(prefix+sub の連結でなく Arena 完成名)優先。(effect_id, sub_id) → 完成翻訳ID。
_DAMAGE_COMPOSITE_IDS = {0: "mages.Damage Health", 1: "mages.Damage Fatigue",
                         2: "mages.Damage Spell Points"}
_CONT_DAMAGE_COMPOSITE_IDS = {0: "mages.Continuous Damage Health",
                              1: "mages.Continuous Damage Fatigue",
                              2: "mages.Continuous Damage Spell Points"}
_HEAL_COMPOSITE_IDS = {0: "mages.Heal Fatigue", 1: "mages.Heal Health",
                       2: "mages.Heal Spell Points"}
_CAUSE_COMPOSITE_IDS = {0: "mages.Cause Disease", 1: "mages.Cause Poison",
                        2: "mages.Cause Paralyzation", 3: "mages.Cause Curse"}
_CURE_COMPOSITE_IDS = {0: "mages.Cure Disease", 1: "mages.Cure Poison",
                       2: "mages.Cure Paralyzation", 3: "mages.Cure Curse"}
_CREATE_COMPOSITE_IDS = {0: "mages.Create Shield", 1: "mages.Create Wall",
                         2: "mages.Create Floor"}
_DESTROY_COMPOSITE_IDS = {0: "mages.Destroy Wall", 1: "mages.Destroy Floor"}
_SIMPLE_EFFECT_IDS = {
    5: "mages.Designate as Non-Target",
    # effect_id 7/8/14 はライブ採取の effect 名配列（ACD.EXE image_base+0x40CC7・24 件）と
    # 既知 effect_id の照合で確定した構造写像 effect_id = 配列index+1（既知 21 件で完全一致）から。
    # 注: simple 扱いは推定（配列は標準名のみ・sub 要素の有無は当該効果スペルで要確認）。
    7: "mages.Disintegrate", 8: "mages.Dispel", 14: "mages.Imprison",
    15: "mages.Invisibility",
    16: "mages.Levitate", 17: "mages.Light", 18: "mages.Lock", 19: "mages.Open",
    20: "mages.Regenerate", 21: "mages.Silence", 22: "mages.Spell Absorption",
    23: "mages.Spell Reflection", 24: "mages.Spell Resistance",
}
# prefix のみの完成ID(attr/element 合成で完成ID が無い場合に prefix+component を翻訳ID で表示合成)。
_PREFIX_ID = {9: "mages.Drain Attribute", 10: "mages.Elemental Resistance",
              11: "mages.Fortify Attribute", 13: "mages.Transfer Attribute"}

# ──────────────────────────────────────────────────────────────
# 効果テキストのテンプレート翻訳
# Arena は Casting Cost や level 等の数値を埋め込んだ rendered text を
# anchor+0x1044 に書き出す。元テンプレートはバイナリ内にある。
# rendered text からパターン照合してテンプレートを特定し、和訳する。
# 観測サンプル:
#   Fire Dart  : "1 to 2 pts damage to health +3 to 4 pts per 1 level(s)."
#   Light Heal : "+1 to 2 pts to Health + 4 to 5 pts per 1 level(s)."
# 全パターンを網羅するには更なる呪文サンプルが必要。
# ──────────────────────────────────────────────────────────────
_EFFECT_TARGET_JA = {
    "health":    "ヘルス",
    "Health":    "ヘルス",
    "spell pts": "呪文ポイント",
    "Spell Pts": "呪文ポイント",
    "fatigue":   "疲労",
    "Fatigue":   "疲労",
}

_TEMPLATES = [
    # Damage type: "X to Y pts damage to <target> +A to B pts per N level(s)."
    (re.compile(
        r"^(\d+)\s+to\s+(\d+)\s+pts\s+damage\s+to\s+(\w+(?:\s+\w+)?)"
        r"\s*\+\s*(\d+)\s+to\s+(\d+)\s+pts\s+per\s+(\d+)\s+level\(s\)\.?$"),
     "damage"),
    # Heal type: "+X to Y pts to <target> + A to B pts per N level(s)."
    (re.compile(
        r"^\+\s*(\d+)\s+to\s+(\d+)\s+pts\s+to\s+(\w+(?:\s+\w+)?)"
        r"\s*\+\s*(\d+)\s+to\s+(\d+)\s+pts\s+per\s+(\d+)\s+level\(s\)\.?$"),
     "heal"),
    # Drain type: "X to Y pts drain to <target> +A to B pts per N level(s)."
    (re.compile(
        r"^(\d+)\s+to\s+(\d+)\s+pts\s+drain\s+to\s+(\w+(?:\s+\w+)?)"
        r"\s*\+\s*(\d+)\s+to\s+(\d+)\s+pts\s+per\s+(\d+)\s+level\(s\)\.?$"),
     "drain"),
]


def _lookup_pair(table: dict, key: int) -> tuple[str, str]:
    """互換ヘルパ（旧 API）。現在は ID ベース解決へ移行済。"""
    pair = table.get(key)
    if pair is not None:
        return pair
    return (f"Unknown({key})", "—")


def _active_effect_slot(effects: list[int]) -> int:
    """SpellData の3効果スロットから最初の使用スロットを返す。"""
    for i, effect_id in enumerate(effects[:3]):
        if effect_id != 0xFF:
            return i
    return 0


def _effect_display_ids(effect_id: int, sub_id: int, attr_id: int) -> list[str]:
    """効果(effect_id/sub_id/attr_id) → 表示翻訳ID 列。

    1要素=完成ID（mages.X）／2要素=prefix+component の表示合成（attr/element 合成で完成ID 無し）
    ／空=degraded（未知効果）。コード内に (en,ja) 表示文字列を持たず ID のみ保持する。
    """
    if effect_id == 0:
        cid = _CAUSE_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id == 1:
        cid = _CONT_DAMAGE_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id == 2:
        cid = _CREATE_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id == 3:
        cid = _CURE_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id == 4:
        cid = _DAMAGE_COMPOSITE_IDS.get(sub_id) or _DAMAGE_COMPOSITE_IDS.get(attr_id)
        return [cid] if cid else []
    if effect_id == 6:
        cid = _DESTROY_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id in (9, 11):  # Drain / Fortify Attribute X（完成ID 無し＝prefix+component 合成）
        comp = _ATTRIBUTE_IDS.get(sub_id) or _ATTRIBUTE_IDS.get(attr_id)
        return [_PREFIX_ID[effect_id], comp] if comp else [_PREFIX_ID[effect_id]]
    if effect_id == 10:  # Elemental Resistance X
        comp = _ELEMENT_SUB_IDS.get(sub_id)
        return [_PREFIX_ID[10], comp] if comp else [_PREFIX_ID[10]]
    if effect_id == 12:
        cid = _HEAL_COMPOSITE_IDS.get(sub_id)
        return [cid] if cid else []
    if effect_id == 13:
        return [_PREFIX_ID[13]]
    sid = _SIMPLE_EFFECT_IDS.get(effect_id)
    return [sid] if sid else []


def _id_anchor(id_str: str) -> str:
    """翻訳ID → 原文照合アンカー surface（原文）。未収録は ID 末尾語（=surface）へ。

    `en`（ユーザー編集可能な英語翻訳レイヤ）は照合に使わない。
    """
    import i18n_helper as i18n
    o = i18n.original(id_str)
    return o if o else id_str.split(".", 1)[-1]


def _resolve_effect_name(effect_id: int, sub_id: int,
                         attr_id: int) -> tuple[str, str]:
    """effects/subEffects/affectedAttrs の組み合わせを (照合アンカー en, 表示 ja) へ変換する。

    en＝原文照合アンカー（原文由来・本文照合用）／ja＝表示訳（i18n 現在訳・ja レイヤ）。
    コード内 (en,ja) 直書きを廃し翻訳ID から解決する。
    """
    if effect_id == 0xFF:
        return ("(none)", "(なし)")
    ids = _effect_display_ids(effect_id, sub_id, attr_id)
    if not ids:
        return (f"Unknown({effect_id})", "—")
    import i18n_helper as i18n
    en_parts, ja_parts = [], []
    for id_str in ids:
        anchor = _id_anchor(id_str)
        ja = i18n.lang_value_in(id_str, "ja")
        en_parts.append(anchor)
        ja_parts.append(ja if ja else anchor)
    return (" ".join(en_parts), " ".join(ja_parts))


def _effect_details_from_arrays(
        effects: list[int],
        sub_effects: list[int],
        affected_attrs: list[int]) -> list[dict]:
    """SpellData の最大3効果スロットを表示用 detail 配列へ展開する。"""
    details: list[dict] = []
    for slot, effect_id in enumerate(effects[:3]):
        if effect_id == 0xFF:
            continue
        sub_id = sub_effects[slot] if slot < len(sub_effects) else 0
        attr_id = affected_attrs[slot] if slot < len(affected_attrs) else 0
        effect_en, effect_ja = _resolve_effect_name(effect_id, sub_id, attr_id)
        display_ids = _effect_display_ids(effect_id, sub_id, attr_id)
        details.append({
            "slot": slot,
            "effect_id": effect_id,
            "sub_effect_id": sub_id,
            "affected_attr_id": attr_id,
            # 表示は display_ids を i18n 現在訳で、照合は anchor を原文で解決する。
            # effect_en＝照合アンカー surface（原文由来）／effect_ja＝表示訳（互換・i18n 由来）。
            "effect_display_ids": display_ids,
            "effect_anchor_id": display_ids[0] if len(display_ids) == 1 else None,
            "effect_en": effect_en,
            "effect_ja": effect_ja,
            "text_en": "",
            "text_ja": "",
        })
    return details


def _decode_spell_effect_segments(raw: bytes) -> list[str]:
    """効果本文バッファを Arena の NUL 区切りチャンクとして読む。"""
    if not raw:
        return []
    m = re.search(rb"\x00{4,}", raw)
    end = m.start() if m else len(raw)
    segments: list[str] = []
    for seg in raw[:end].split(b"\x00"):
        chars: list[str] = []
        for b in seg:
            if 0x20 <= b <= 0x7E:
                chars.append(chr(b))
            else:
                chars.append(" ")
        text = " ".join("".join(chars).split()).strip()
        if text:
            segments.append(text)
    return segments


def _decode_spell_effect_text(raw: bytes) -> str:
    """効果本文を、Arena の埋め込み NUL 区切りを保ったまま1文へ戻す。"""
    return " ".join(_decode_spell_effect_segments(raw)).strip()


def _effect_template_ids(effect_en: str) -> set[int]:
    """効果名から、対応し得る SPELLMKR.TXT テンプレート番号を返す。"""
    effect = (effect_en or "").strip()
    table = {
        "Cause Disease": {0},
        "Cause Poison": {1},
        "Cause Paralyzation": {3},
        "Cause Curse": {4},
        "Continuous Damage Health": {6},
        "Continuous Damage Fatigue": {7},
        "Continuous Damage Spell Points": {8},
        "Create Shield": {9, 32},
        "Create Wall": {10},
        "Create Floor": {11},
        "Cure Disease": {12},
        "Cure Poison": {13},
        "Cure Paralyzation": {15},
        "Cure Curse": {16},
        "Damage Health": {18, 24},
        "Damage Fatigue": {19},
        "Damage Spell Points": {20},
        "Designate as Non-Target": {21},
        "Destroy Wall": {22},
        "Destroy Floor": {23},
        "Drain Attribute": {27},
        "Elemental Resistance": {28},
        "Fortify Attribute": {29},
        "Heal Fatigue": {30},
        "Heal Health": {30},
        "Heal Spell Points": {30},
        "Transfer Attribute": {31},
        "Invisibility": {33},
        "Levitate": {34},
        "Light": {35},
        "Lock": {36},
        "Open": {37},
        "Regenerate": {38},
        "Silence": {39},
        "Spell Absorption": {40},
        "Spell Reflection": {41},
        "Spell Resistance": {42},
    }
    if effect.startswith("Elemental Resistance "):
        return {28}
    if effect.startswith("Drain Attribute "):
        return {27}
    if effect.startswith("Fortify Attribute "):
        return {29}
    return table.get(effect, set())


def _normalize_spell_effect_text(
        text_en: str,
        effect_en: str,
        *,
        allow_mismatch_fallback: bool = False) -> tuple[str, str]:
    """効果本文をテンプレートで正規化し、効果名と合う翻訳だけを返す。"""
    if not text_en:
        return "", ""
    try:
        from spell_effect_text import match_template
        matched = match_template(text_en)
    except Exception:  # noqa: BLE001
        matched = None
    if matched:
        template_id, normalized_en, ja = matched
        expected = _effect_template_ids(effect_en)
        if expected and template_id not in expected:
            if allow_mismatch_fallback:
                return text_en, translate_effect_text(text_en)
            return "", ""
        return normalized_en, ja
    return text_en, translate_effect_text(text_en)


def _strip_effect_heading(text_en: str, effect_en: str) -> str:
    """効果一覧見出し（例: ``Damage Health``）を本文先頭から除く。"""
    text = (text_en or "").strip()
    effect = (effect_en or "").strip()
    if not text or not effect:
        return text
    if text.startswith(effect):
        return text[len(effect):].lstrip(" :-\t\r\n")
    return text


def _is_effect_heading_text(text_en: str, effect_en: str) -> bool:
    text = (text_en or "").strip()
    effect = (effect_en or "").strip()
    return bool(effect and (text == effect or text.startswith(effect + ":")))


def _effect_heading_index(
        segment: str,
        indexes_by_effect: dict[str, list[int]]) -> int | None:
    text = (segment or "").strip()
    if not text:
        return None
    for effect, indexes in indexes_by_effect.items():
        if not indexes:
            continue
        if _is_effect_heading_text(text, effect):
            return indexes.pop(0)
    return None


def _attach_effect_texts_from_segments(
        segments: list[str],
        details: list[dict]) -> list[dict] | None:
    """NUL チャンク列から効果見出しごとに本文を割り当てる。"""
    if not segments or not details:
        return None
    out = [dict(d) for d in details]
    indexes_by_effect: dict[str, list[int]] = {}
    for idx, detail in enumerate(out):
        effect = detail.get("effect_en", "")
        if effect and effect != "(none)":
            indexes_by_effect.setdefault(effect, []).append(idx)

    current_idx: int | None = None
    assigned: dict[int, list[str]] = {}
    saw_heading = False
    for segment in segments:
        heading_idx = _effect_heading_index(segment, indexes_by_effect)
        if heading_idx is not None:
            current_idx = heading_idx
            assigned.setdefault(current_idx, [])
            saw_heading = True
            continue
        if current_idx is not None:
            assigned.setdefault(current_idx, []).append(segment)

    if not saw_heading:
        return None
    for idx, parts in assigned.items():
        segment = " ".join(parts).strip()
        effect = out[idx].get("effect_en", "")
        normalized_en, text_ja = _normalize_spell_effect_text(
            segment, effect, allow_mismatch_fallback=True)
        if not normalized_en and segment:
            normalized_en = segment
            text_ja = translate_effect_text(segment)
        out[idx]["text_en"] = normalized_en
        out[idx]["text_ja"] = text_ja
    return out


def _effect_text_start_pattern(effect_en: str) -> re.Pattern | None:
    effect = (effect_en or "").strip()
    table = {
        "Cause Disease": r"\d+%\s+chance\s+to\s+inflict\s+disease",
        "Cause Poison": r"\d+%\s+chance\s+to\s+inflict\s+poison",
        "Cause Paralyzation": r"\d+%\s+chance\s+to\s+paralyze",
        "Cause Curse": r"\d+%\s+chance\s+to\s+curse\s+target\(s\)",
        "Damage Health": r"\d+\s+to\s+\d+\s+pts\s+(?:of\s+)?damage\s+to\s+health",
        "Damage Fatigue": r"\d+\s+to\s+\d+\s+pts\s+(?:of\s+)?damage\s+to\s+fatigue",
        "Damage Spell Points": (
            r"\d+\s+to\s+\d+\s+pts\s+(?:of\s+)?damage\s+to\s+spell\s+pts"),
        "Heal Health": r"\+\s*\d+\s+to\s+\d+\s+pts\s+to\s+Health",
        "Heal Fatigue": r"\+\s*\d+\s+to\s+\d+\s+pts\s+to\s+Fatigue",
        "Heal Spell Points": r"\+\s*\d+\s+to\s+\d+\s+pts\s+to\s+Spell\s+Points",
        "Create Shield": r"\d+\s+hit\s+pts\s+shield\s+created",
        "Create Wall": r"\d+\s+wall\(s\)\s+permanently\s+created",
        "Regenerate": r"Regenerate\s+\d+\s+health\s+points",
        "Levitate": r"Caster\s+can\s+float\s+for\s+\d+\s+rnd\(s\)",
        "Light": r"Creates\s+a\s+globe\s+of\s+light",
    }
    pattern = table.get(effect)
    if pattern is None and effect.startswith("Continuous Damage "):
        target = effect.removeprefix("Continuous Damage ").lower()
        pattern = (
            r"Cause\s+\d+\s+to\s+\d+\s+pts\s+of\s+damage\s+to\s+"
            + re.escape(target))
    if pattern is None and effect.startswith("Drain Attribute "):
        attr = effect.removeprefix("Drain Attribute ")
        pattern = (
            r"\d+\s+pts\s+of\s+" + re.escape(attr)
            + r"\s+drained\s+from\s+target\(s\)")
    if pattern is None:
        return None
    return re.compile(pattern, re.IGNORECASE)


def _attach_effect_texts_by_template_starts(
        text: str,
        details: list[dict]) -> list[dict] | None:
    """効果見出しが無い本文列を、各効果テンプレの開始形で分割する。"""
    if not text or len(details) <= 1:
        return None
    starts: list[tuple[int, int]] = []
    search_from = 0
    for idx, detail in enumerate(details):
        pattern = _effect_text_start_pattern(detail.get("effect_en", ""))
        if pattern is None:
            continue
        match = pattern.search(text, search_from)
        if match is None:
            continue
        starts.append((idx, match.start()))
        search_from = match.start() + 1
    if not starts:
        return None

    # 先頭効果の開始形が欠けても、次効果の開始より前に本文断片があれば前効果へ渡す。
    if starts[0][0] > 0 and starts[0][1] > 0:
        prefix = text[:starts[0][1]].strip()
        current_idx = starts[0][0]
        current_effect = (
            details[current_idx].get("effect_en", "")
            if 0 <= current_idx < len(details) else "")
        is_heading = _is_effect_heading_text(prefix, current_effect)
        if not is_heading:
            is_heading = any(
                _is_effect_heading_text(prefix, d.get("effect_en", ""))
                for d in details)
        if not is_heading:
            starts.insert(0, (starts[0][0] - 1, 0))
    starts.sort(key=lambda item: item[1])

    out = [dict(d) for d in details]
    for order, (detail_idx, start) in enumerate(starts):
        end = starts[order + 1][1] if order + 1 < len(starts) else len(text)
        if detail_idx < 0 or detail_idx >= len(out):
            continue
        segment = text[start:end].strip()
        effect = out[detail_idx].get("effect_en", "")
        normalized_en, text_ja = _normalize_spell_effect_text(
            segment, effect, allow_mismatch_fallback=True)
        if not normalized_en and segment:
            normalized_en = segment
            text_ja = translate_effect_text(segment)
        out[detail_idx]["text_en"] = normalized_en
        out[detail_idx]["text_ja"] = text_ja
    return out


def _attach_effect_texts(
        text_en: str,
        details: list[dict],
        segments: list[str] | None = None) -> list[dict]:
    """0x1044 の複数効果本文を effect_details の各スロットへ割り当てる。"""
    out = [dict(d) for d in details]
    segmented = _attach_effect_texts_from_segments(segments or [], out)
    if segmented is not None:
        text = (text_en or "").strip()
        if text and any(not d.get("text_en") for d in segmented):
            by_template = _attach_effect_texts_by_template_starts(
                text, segmented)
            if by_template is not None:
                for idx, detail in enumerate(segmented):
                    if detail.get("text_en") or idx >= len(by_template):
                        continue
                    fallback = by_template[idx]
                    if fallback.get("text_en"):
                        detail["text_en"] = fallback.get("text_en", "")
                        detail["text_ja"] = fallback.get("text_ja", "")
        return segmented
    text = (text_en or "").strip()
    if not out:
        return out
    if not text:
        return out

    occurrences: list[tuple[int, int, str]] = []
    for detail in out:
        effect = detail.get("effect_en", "")
        if not effect or effect == "(none)":
            continue
        pattern = (
            r"(?<![A-Za-z])" + re.escape(effect) + r"(?![A-Za-z])")
        for match in re.finditer(pattern, text):
            occurrences.append((match.start(), match.end(), effect))
    occurrences.sort(key=lambda x: x[0])

    if not occurrences:
        if len(out) == 1:
            effect = out[0].get("effect_en", "")
            normalized_en, text_ja = _normalize_spell_effect_text(text, effect)
            out[0]["text_en"] = normalized_en
            out[0]["text_ja"] = text_ja
        else:
            by_template = _attach_effect_texts_by_template_starts(text, out)
            if by_template is not None:
                return by_template
        return out

    detail_indexes_by_effect: dict[str, list[int]] = {}
    for idx, detail in enumerate(out):
        detail_indexes_by_effect.setdefault(
            detail.get("effect_en", ""), []).append(idx)

    used_occurrence_indexes: list[tuple[int, int, int]] = []
    for occ_idx, (_, _, effect) in enumerate(occurrences):
        candidates = detail_indexes_by_effect.get(effect, [])
        if not candidates:
            continue
        detail_idx = candidates.pop(0)
        used_occurrence_indexes.append((occ_idx, detail_idx, occurrences[occ_idx][0]))

    for order, (occ_idx, detail_idx, _) in enumerate(used_occurrence_indexes):
        start = occurrences[occ_idx][0]
        end = (
            used_occurrence_indexes[order + 1][2]
            if order + 1 < len(used_occurrence_indexes)
            else len(text)
        )
        detail = out[detail_idx]
        effect = detail.get("effect_en", "")
        segment = _strip_effect_heading(text[start:end], effect)
        normalized_en, text_ja = _normalize_spell_effect_text(
            segment, effect, allow_mismatch_fallback=True)
        if not normalized_en and segment:
            normalized_en = segment
            text_ja = translate_effect_text(segment)
        detail["text_en"] = normalized_en
        detail["text_ja"] = text_ja
    return out


def _synthesize_spellmaker_effect_text(detail: dict, analyzer, anchor: int):
    effect = detail.get("effect_en", "")
    slot = max(0, min(int(detail.get("slot", 0) or 0), 2))
    try:
        from mages_spellmaker import read_form_values
    except Exception:  # noqa: BLE001
        return "", ""
    try:
        if effect == "Cause Poison":
            vals = read_form_values(analyzer, anchor, "FORM4", slot=slot)
            needed = (
                "Chance", "Deterioration", "per Rnds", "Increase",
                "per Levels", "Duration")
            if not all(k in vals for k in needed):
                return "", ""
            text = (
                f"{vals['Chance']}% chance to inflict poison. "
                f"Damage is {vals['Deterioration']} pts per "
                f"{vals['per Rnds']} rnd(s). +{vals['Increase']}% every "
                f"{vals['per Levels']} level(s). Spell duration is "
                f"{vals['Duration']} rnd(s) per level."
            )
            return _normalize_spell_effect_text(
                text, effect, allow_mismatch_fallback=True)
        if effect == "Damage Health":
            vals = read_form_values(analyzer, anchor, "FORM1", slot=slot)
            needed = (
                "Range min", "Range max", "Increase min",
                "Increase max", "Levels")
            if not all(k in vals for k in needed):
                return "", ""
            text = (
                f"{vals['Range min']} to {vals['Range max']} pts damage "
                f"to health +{vals['Increase min']} to "
                f"{vals['Increase max']} pts per {vals['Levels']} level(s)."
            )
            return _normalize_spell_effect_text(
                text, effect, allow_mismatch_fallback=True)
        if effect.startswith("Continuous Damage "):
            vals = read_form_values(analyzer, anchor, "FORM2", slot=slot)
            needed = (
                "Range min", "Range max", "Increase min",
                "Increase max", "Levels", "Strikes")
            if not all(k in vals for k in needed):
                return "", ""
            target = effect.removeprefix("Continuous Damage ").lower()
            text = (
                f"Cause {vals['Range min']} to {vals['Range max']} pts "
                f"of damage to {target} every {vals['Strikes']} rnd(s). "
                f"Duration is {vals['Strikes']} rnd(s). Damage is + "
                f"{vals['Increase min']} to {vals['Increase max']} pts "
                f"every {vals['Levels']} level(s)."
            )
            return _normalize_spell_effect_text(
                text, effect, allow_mismatch_fallback=True)
        if effect.startswith("Drain Attribute "):
            vals = read_form_values(analyzer, anchor, "FORM6A", slot=slot)
            needed = (
                "Decrease", "Rate of Recovery",
                "Recovery per Rnds", "Duration")
            if not all(k in vals for k in needed):
                return "", ""
            attr = effect.removeprefix("Drain Attribute ")
            text = (
                f"{vals['Decrease']} pts of {attr} drained from target(s) "
                f"for {vals['Duration']} rnd(s) per level. Target(s) "
                f"recover {attr} at {vals['Rate of Recovery']} pts per "
                f"{vals['Recovery per Rnds']} rnd(s)."
            )
            return _normalize_spell_effect_text(
                text, effect, allow_mismatch_fallback=True)
    except Exception:  # noqa: BLE001
        return "", ""
    return "", ""


def _fill_missing_spellmaker_effect_texts(
        details: list[dict], analyzer, anchor: int) -> list[dict]:
    out = [dict(d) for d in details]
    for detail in out:
        if detail.get("text_en"):
            continue
        text_en, text_ja = _synthesize_spellmaker_effect_text(
            detail, analyzer, anchor)
        if text_en:
            detail["text_en"] = text_en
            detail["text_ja"] = text_ja
    return out


def _target_word_ja(word: str) -> str:
    return _EFFECT_TARGET_JA.get(word, _EFFECT_TARGET_JA.get(word.lower(), word))


def translate_effect_text(text_en: str) -> str:
    """rendered な効果テキストを日本語に翻訳する。

    既知テンプレートにマッチしなければ空文字を返す。
    """
    if not text_en:
        return ""
    # SPELLMKR.TXT の全43効果テンプレで翻訳を試みる（中立モジュール）。
    try:
        from spell_effect_text import translate as _set
        ja = _set(text_en)
        if ja:
            return ja
    except Exception:  # noqa: BLE001
        pass
    s = text_en.strip()
    for regex, kind in _TEMPLATES:
        m = regex.match(s)
        if not m:
            continue
        x, y, target, a, b, n = m.groups()
        target_ja = _target_word_ja(target.strip())
        if kind == "damage":
            return (f"{target_ja}に{x}〜{y}ポイントのダメージ、"
                    f"{n}レベル毎に+{a}〜{b}ポイント")
        if kind == "heal":
            return (f"{target_ja}を{x}〜{y}ポイント回復、"
                    f"{n}レベル毎に+{a}〜{b}ポイント")
        if kind == "drain":
            return (f"{target_ja}を{x}〜{y}ポイント吸収、"
                    f"{n}レベル毎に+{a}〜{b}ポイント")
    return ""
