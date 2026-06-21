"""
npc_name_translator.py — NPC 生成名解析・言語変換

OpenTESArena の NameRules と NAMECHNK.DAT 由来の部品辞書を用いて、
プロシージャル生成された NPC 名を対象言語表記へ変換する。

API:
  translate_generated_name(name: str, lang: str = "ja") -> str
    生成 NPC 名として解釈できれば対象言語表記、できなければ原文を返す。
"""

from __future__ import annotations

_chunks_data: dict | None = None
_overrides_data: dict | None = None

# ---------------------------------------------------------------------------
# NameRules — OpenTESArena TextAssetLibrary.cpp の定義を Python で再現
#
# Rule types:
#   "I"   = Index          : chunk[c] から 1 要素を選択 (必須)
#   "S"   = String         : 固定文字列 s を出力 (必須)
#   "IC"  = IndexChance    : chunk[c] から選択 (確率 p%)
#   "ISC" = IndexStrChance : chunk[c]+s を出力 (確率 p%)
#
# {raceID: [male_rules, female_rules]}
# ---------------------------------------------------------------------------
_NAME_RULES: dict[int, list[list[dict]]] = {
    0: [
        [{"t": "I", "c": 0}, {"t": "I", "c": 1}, {"t": "S", "s": " "}, {"t": "I", "c": 4}, {"t": "I", "c": 5}],
        [{"t": "I", "c": 2}, {"t": "I", "c": 3}, {"t": "S", "s": " "}, {"t": "I", "c": 4}, {"t": "I", "c": 5}],
    ],
    1: [
        [{"t": "I", "c": 6}, {"t": "I", "c": 7}, {"t": "I", "c": 8}, {"t": "IC", "c": 9, "p": 75}],
        [{"t": "I", "c": 6}, {"t": "I", "c": 7}, {"t": "I", "c": 8}, {"t": "IC", "c": 9, "p": 75}, {"t": "I", "c": 10}],
    ],
    2: [
        [{"t": "I", "c": 11}, {"t": "I", "c": 12}, {"t": "S", "s": " "}, {"t": "I", "c": 15}, {"t": "I", "c": 16}, {"t": "S", "s": "sen"}],
        [{"t": "I", "c": 13}, {"t": "I", "c": 14}, {"t": "S", "s": " "}, {"t": "I", "c": 15}, {"t": "I", "c": 16}, {"t": "S", "s": "sen"}],
    ],
    3: [
        [{"t": "I", "c": 17}, {"t": "I", "c": 18}, {"t": "S", "s": " "}, {"t": "I", "c": 21}, {"t": "I", "c": 22}],
        [{"t": "I", "c": 19}, {"t": "I", "c": 20}, {"t": "S", "s": " "}, {"t": "I", "c": 21}, {"t": "I", "c": 22}],
    ],
    4: [
        [{"t": "I", "c": 23}, {"t": "I", "c": 24}, {"t": "S", "s": " "}, {"t": "I", "c": 27}, {"t": "I", "c": 28}],
        [{"t": "I", "c": 25}, {"t": "I", "c": 26}, {"t": "S", "s": " "}, {"t": "I", "c": 27}, {"t": "I", "c": 28}],
    ],
    5: [
        [{"t": "I", "c": 29}, {"t": "I", "c": 30}, {"t": "S", "s": " "}, {"t": "I", "c": 33}, {"t": "I", "c": 34}],
        [{"t": "I", "c": 31}, {"t": "I", "c": 32}, {"t": "S", "s": " "}, {"t": "I", "c": 33}, {"t": "I", "c": 34}],
    ],
    6: [
        [{"t": "I", "c": 35}, {"t": "I", "c": 36}, {"t": "S", "s": " "}, {"t": "I", "c": 39}, {"t": "I", "c": 40}],
        [{"t": "I", "c": 37}, {"t": "I", "c": 38}, {"t": "S", "s": " "}, {"t": "I", "c": 39}, {"t": "I", "c": 40}],
    ],
    7: [
        [{"t": "I", "c": 41}, {"t": "I", "c": 42}, {"t": "S", "s": " "}, {"t": "I", "c": 45}, {"t": "I", "c": 46}],
        [{"t": "I", "c": 43}, {"t": "I", "c": 44}, {"t": "S", "s": " "}, {"t": "I", "c": 45}, {"t": "I", "c": 46}],
    ],
    **{r: [
        [{"t": "I", "c": 47}, {"t": "IC", "c": 48, "p": 75}, {"t": "I", "c": 49}],
        [{"t": "I", "c": 47}, {"t": "IC", "c": 48, "p": 75}, {"t": "I", "c": 49}],
    ] for r in range(8, 17)},
    **{r: [
        [{"t": "I", "c": 50}, {"t": "IC", "c": 51, "p": 75}, {"t": "I", "c": 52}],
        [{"t": "I", "c": 50}, {"t": "IC", "c": 51, "p": 75}, {"t": "I", "c": 52}],
    ] for r in range(17, 21)},
    21: [
        [{"t": "I", "c": 50}, {"t": "I", "c": 52}, {"t": "I", "c": 53}],
        [{"t": "I", "c": 50}, {"t": "I", "c": 52}, {"t": "I", "c": 53}],
    ],
    22: [
        [{"t": "ISC", "c": 54, "s": " ", "p": 25}, {"t": "I", "c": 55}, {"t": "I", "c": 56}, {"t": "I", "c": 57}],
        [{"t": "ISC", "c": 54, "s": " ", "p": 25}, {"t": "I", "c": 55}, {"t": "I", "c": 56}, {"t": "I", "c": 57}],
    ],
    23: [
        [{"t": "I", "c": 55}, {"t": "I", "c": 56}, {"t": "I", "c": 57}],
        [{"t": "I", "c": 55}, {"t": "I", "c": 56}, {"t": "I", "c": 57}],
    ],
}

for _race_id in range(8):
    _forename_rules: list[list[dict]] = []
    for _gender_rules in _NAME_RULES[_race_id]:
        _cut: list[dict] = []
        for _r in _gender_rules:
            if _r.get("t") == "S" and _r.get("s") == " ":
                break
            _cut.append(_r)
        _forename_rules.append(_cut)
    _NAME_RULES[100 + _race_id] = _forename_rules

# 使用範囲: raceID 0..8 のチャンクインデックスセット (696 スロット)
_USED_CHUNKS_0_8: frozenset[int] = frozenset(
    r["c"] for gender_rules in (_NAME_RULES[r] for r in range(9))
    for rules in gender_rules
    for r in rules
    if r["t"] in ("I", "IC", "ISC")
)


_NNC_CAT = "npc_name_chunks"


def _iter_nnc():
    """生成名部品を (kind, chunk_idx, entry_idx, en, surface) で yield する。

    kind='chunk'|'literal'。v2 公開 runtime 有効時は source_id 経路（`namechnk:<chunk>:<idx>`）。
    chunk_idx/entry_idx は source_id から導出（原文込み string-ID 不使用）。
    literals は source_id を持たず localpack 非収録のため v2 では非対象（user-env
    の pack も literals を含まない・名前合成 literal は別経路）。未有効時は従来の originals＋text(id)。
    """
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_NNC_CAT):
        for e in i18n.v2_category_entries(_NNC_CAT):
            sid = e.get("source_id")
            if not sid:
                continue  # literals（curation）は v2 非対象
            parts = sid.split(":")
            if len(parts) != 3 or parts[0] != "namechnk":
                continue
            ci = parts[1]
            try:
                ei = int(parts[2])
            except ValueError:
                continue
            en = e.get("original")
            if not en:
                continue
            text = e.get("text")
            surface = text if (text and text != en) else None
            yield "chunk", ci, ei, en, surface
    else:
        for id_, e in i18n.originals(_NNC_CAT).items():
            if not isinstance(e, dict):
                continue
            en = e.get("original", "")
            translated = i18n.text(id_)
            # 未訳は text() が原文(en)へフォールバックするため None 扱い（旧の surface 欠落と一致）。
            surface = translated if (translated and translated != en) else None
            parts = id_.split(".")
            if len(parts) >= 4 and parts[1] == "chunks":
                ci = parts[2]
                try:
                    ei = int(parts[3])
                except ValueError:
                    continue
                yield "chunk", ci, ei, en, surface
            elif len(parts) >= 3 and parts[1] == "literals" and en:
                yield "literal", None, None, en, surface


def _load() -> None:
    """翻訳切替コアから生成名部品を旧 npc_name_chunks 形へ再構築（遅延）。

    新構造 id: `npc_name_chunks.chunks.<chunk_idx>.<entry_idx>`（original=en・訳=surface）/
    `npc_name_chunks.literals.<literal>`。値は現在言語で格納（active==lang 前提）。
    npc_name_overrides は空config（words/full_names 共に0）のため空 dict とする。
    """
    global _chunks_data, _overrides_data
    if _chunks_data is not None:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    chunks: dict[str, list[dict]] = {}
    literals: dict[str, dict] = {}
    for kind, ci, ei, en, surface in _iter_nnc():
        if kind == "chunk":
            entry: dict = {"index": ei, "en": en, "translations": {}}
            if surface is not None:
                entry["translations"][lang] = {"surface": surface}
            chunks.setdefault(ci, []).append(entry)
        elif kind == "literal":
            if surface is not None:
                literals[en] = {"translations": {lang: {"surface": surface}}}
    for ci in chunks:
        chunks[ci].sort(key=lambda x: x["index"])
    _chunks_data = {"chunks": chunks, "literals": literals}
    _overrides_data = {}


def _chunk_entries(chunk_idx: int) -> list[str]:
    """chunk_idx のエントリ文字列リストを返す。"""
    chunks = (_chunks_data or {}).get("chunks", {})
    return [e["en"] for e in chunks.get(str(chunk_idx), [])]


def _chunk_translation(chunk_idx: int, entry_idx: int, lang: str) -> str | None:
    """チャンクスロットの翻訳を返す。未登録の場合 None。"""
    chunks = (_chunks_data or {}).get("chunks", {})
    entries = chunks.get(str(chunk_idx), [])
    for e in entries:
        if e["index"] == entry_idx:
            return e.get("translations", {}).get(lang, {}).get("surface")
    return None


def _literal_translation(literal: str, lang: str) -> str | None:
    """literals セクションの翻訳を返す。未登録の場合 None。"""
    literals = (_chunks_data or {}).get("literals", {})
    return literals.get(literal, {}).get("translations", {}).get(lang, {}).get("surface")


# ---------------------------------------------------------------------------
# NameRules に基づく名前解析
# ---------------------------------------------------------------------------

def _parse_name_with_rules(name: str, rules: list[dict]) -> list[dict] | None:
    """
    name を rules で解析し、部品リストを返す。解析不能なら None。

    各要素:
      {"kind": "chunk", "chunk": ci, "entry_idx": ei, "en": "..."}
      {"kind": "string", "value": "..."}
    """
    chunks_map: dict[int, list[str]] = {}

    def entries(ci: int) -> list[str]:
        if ci not in chunks_map:
            chunks_map[ci] = _chunk_entries(ci)
        return chunks_map[ci]

    def recurse(pos: int, ri: int) -> list[dict] | None:
        if ri == len(rules):
            return [] if pos == len(name) else None
        rule = rules[ri]
        t = rule["t"]

        if t == "S":
            s = rule["s"]
            if name[pos:pos + len(s)] == s:
                rest = recurse(pos + len(s), ri + 1)
                if rest is not None:
                    return [{"kind": "string", "value": s}] + rest
            return None

        elif t == "I":
            ci = rule["c"]
            for ei, en in enumerate(entries(ci)):
                ln = len(en)
                if name[pos:pos + ln] == en:
                    rest = recurse(pos + ln, ri + 1)
                    if rest is not None:
                        return [{"kind": "chunk", "chunk": ci, "entry_idx": ei, "en": en}] + rest
            return None

        elif t == "IC":
            ci = rule["c"]
            # チャンクあり
            for ei, en in enumerate(entries(ci)):
                ln = len(en)
                if name[pos:pos + ln] == en:
                    rest = recurse(pos + ln, ri + 1)
                    if rest is not None:
                        return [{"kind": "chunk", "chunk": ci, "entry_idx": ei, "en": en}] + rest
            # チャンクなし (chance で省略された)
            return recurse(pos, ri + 1)

        elif t == "ISC":
            ci = rule["c"]
            s = rule["s"]
            # チャンク+サフィックスあり
            for ei, en in enumerate(entries(ci)):
                combined = en + s
                ln = len(combined)
                if name[pos:pos + ln] == combined:
                    rest = recurse(pos + ln, ri + 1)
                    if rest is not None:
                        return [
                            {"kind": "chunk", "chunk": ci, "entry_idx": ei, "en": en},
                            {"kind": "string", "value": s},
                        ] + rest
            # なし (chance で省略された)
            return recurse(pos, ri + 1)

        return None

    return recurse(0, 0)


def _try_chunk_decompose(name: str, lang: str) -> str | None:
    """
    全 NameRules で name を解析し、全部品に翻訳があれば言語表記を返す。
    いずれかの部品が未翻訳なら None。
    """
    for race_rules in _NAME_RULES.values():
        for gender_rules in race_rules:
            parts = _parse_name_with_rules(name, gender_rules)
            if parts is None:
                continue
            translated = _translate_parts(parts, lang)
            if translated is not None:
                return translated
    return None


def _translate_parts(parts: list[dict], lang: str) -> str | None:
    """
    部品リストを言語表記へ変換する。未翻訳部品があれば None。

    日本語: " " 区切りを "・" へ置換し、各チャンクを連結する。
    """
    out: list[str] = []
    for part in parts:
        if part["kind"] == "string":
            val = part["value"]
            if lang == "ja":
                if val == " ":
                    out.append("・")
                else:
                    t = _literal_translation(val, lang)
                    if t is None:
                        return None
                    out.append(t)
            else:
                out.append(val)
        else:  # chunk
            t = _chunk_translation(part["chunk"], part["entry_idx"], lang)
            if t is None:
                return None
            out.append(t)
    return "".join(out)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def translate_generated_name(name: str, lang: str = "ja") -> str:
    """
    生成 NPC 名として解釈できれば対象言語表記、できなければ原文を返す。

    優先順:
      1. 完成名 override (full_names)
      2. 空白区切り + 完成語 override (words)
      3. NameRules チャンク解析 + 部品辞書
      4. 原文 fallback
    """
    _load()
    if not name:
        return name

    normalized = " ".join(name.split())

    overrides = _overrides_data or {}
    words_ov = overrides.get("words", {})
    full_ov = overrides.get("full_names", {})

    # 1. 完成名 override
    if normalized in full_ov:
        tr = full_ov[normalized].get("translations", {}).get(lang)
        if tr:
            return tr

    # 2. 空白区切りで全語を words override から翻訳
    word_list = normalized.split(" ")
    if all(w in words_ov and lang in words_ov[w].get("translations", {}) for w in word_list):
        if lang == "ja":
            return "・".join(words_ov[w]["translations"][lang] for w in word_list)
        return " ".join(words_ov[w]["translations"][lang] for w in word_list)

    # 3. チャンク解析 + 部品辞書
    chunk_result = _try_chunk_decompose(normalized, lang)
    if chunk_result is not None:
        return chunk_result

    # 4. 原文 fallback
    return name


if __name__ == "__main__":
    tests = [
        ("Rodyctor Coppercroft", "ja"),
        ("Unknown Npc", "ja"),
        ("Rodyctor Coppercroft", "en"),
        ("Barbyrrya", "ja"),
    ]
    for name, lang in tests:
        result = translate_generated_name(name, lang)
        print(f"[{lang}] {name!r} => {result!r}")
