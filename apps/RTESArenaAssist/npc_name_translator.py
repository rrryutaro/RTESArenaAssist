
from __future__ import annotations

_chunks_data: dict | None = None
_overrides_data: dict | None = None

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

_USED_CHUNKS_0_8: frozenset[int] = frozenset(
    r["c"] for gender_rules in (_NAME_RULES[r] for r in range(9))
    for rules in gender_rules
    for r in rules
    if r["t"] in ("I", "IC", "ISC")
)


_NNC_CAT = "npc_name_chunks"


def _iter_nnc():
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_NNC_CAT):
        for e in i18n.v2_category_entries(_NNC_CAT):
            sid = e.get("source_id")
            if not sid:
                continue
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
    chunks = (_chunks_data or {}).get("chunks", {})
    return [e["en"] for e in chunks.get(str(chunk_idx), [])]


def _chunk_translation(chunk_idx: int, entry_idx: int, lang: str) -> str | None:
    chunks = (_chunks_data or {}).get("chunks", {})
    entries = chunks.get(str(chunk_idx), [])
    for e in entries:
        if e["index"] == entry_idx:
            return e.get("translations", {}).get(lang, {}).get("surface")
    return None


def _literal_translation(literal: str, lang: str) -> str | None:
    literals = (_chunks_data or {}).get("literals", {})
    return literals.get(literal, {}).get("translations", {}).get(lang, {}).get("surface")



def _parse_name_with_rules(name: str, rules: list[dict]) -> list[dict] | None:
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
            for ei, en in enumerate(entries(ci)):
                ln = len(en)
                if name[pos:pos + ln] == en:
                    rest = recurse(pos + ln, ri + 1)
                    if rest is not None:
                        return [{"kind": "chunk", "chunk": ci, "entry_idx": ei, "en": en}] + rest
            return recurse(pos, ri + 1)

        elif t == "ISC":
            ci = rule["c"]
            s = rule["s"]
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
            return recurse(pos, ri + 1)

        return None

    return recurse(0, 0)


def _try_chunk_decompose(name: str, lang: str) -> str | None:
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
        else:
            t = _chunk_translation(part["chunk"], part["entry_idx"], lang)
            if t is None:
                return None
            out.append(t)
    return "".join(out)



def translate_generated_name(name: str, lang: str = "ja") -> str:
    _load()
    if not name:
        return name

    normalized = " ".join(name.split())

    overrides = _overrides_data or {}
    words_ov = overrides.get("words", {})
    full_ov = overrides.get("full_names", {})

    if normalized in full_ov:
        tr = full_ov[normalized].get("translations", {}).get(lang)
        if tr:
            return tr

    word_list = normalized.split(" ")
    if all(w in words_ov and lang in words_ov[w].get("translations", {}) for w in word_list):
        if lang == "ja":
            return "・".join(words_ov[w]["translations"][lang] for w in word_list)
        return " ".join(words_ov[w]["translations"][lang] for w in word_list)

    chunk_result = _try_chunk_decompose(normalized, lang)
    if chunk_result is not None:
        return chunk_result

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
