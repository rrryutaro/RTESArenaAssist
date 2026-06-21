from __future__ import annotations

import hashlib
import re
import unicodedata


KIND_TEMPLATE = "template"
KIND_INF = "inf"
KIND_SPELLMKR = "spellmkr"
KIND_NAMECHNK = "namechnk"
KIND_QUESTION = "question"
KIND_TRADE = "tradetext"
KIND_DOCS = "docs"
KIND_ASSIST_SUMMARY = "assist_summary"
KIND_AEXE = "aexe"
KIND_CITYDATA = "citydata"
KIND_SPELLSG = "spellsg65"
KIND_PUBLIC_BUILTIN = "public_builtin"
KIND_ARMOR_PREFIX = "armor_prefix"
KIND_SPELL_EFFECT = "spelleffect"
KIND_MAGIC_ITEM = "magicitem"
KIND_MATERIAL_ITEM = "materialitem"

ALL_KINDS = frozenset({
    KIND_TEMPLATE, KIND_INF, KIND_SPELLMKR,
    KIND_NAMECHNK, KIND_QUESTION, KIND_TRADE, KIND_DOCS, KIND_ASSIST_SUMMARY,
    KIND_AEXE, KIND_CITYDATA, KIND_SPELLSG, KIND_PUBLIC_BUILTIN,
    KIND_ARMOR_PREFIX, KIND_SPELL_EFFECT, KIND_MAGIC_ITEM, KIND_MATERIAL_ITEM,
})

_SEP = ":"


def _seg(value) -> str:
    s = str(value).strip()
    if not s:
        raise ValueError("source_id segment must not be empty")
    if _SEP in s:
        raise ValueError(f"source_id segment must not contain '{_SEP}': {s!r}")
    return s


def _norm_filename(name: str) -> str:
    return _seg(name).upper()


def template_id(block, record_index, copy=None) -> str:
    if copy is None:
        return _SEP.join((KIND_TEMPLATE, _seg(block), _seg(int(record_index))))
    return _SEP.join(
        (KIND_TEMPLATE, _seg(block), _seg(int(copy)), _seg(int(record_index))))


def split_template_id(source_id: str) -> tuple[str, int | None, int]:
    kind, parts = parse_source_id(source_id)
    if kind != KIND_TEMPLATE:
        raise ValueError(f"not a template source_id: {source_id!r}")
    if len(parts) == 3:
        return parts[0], int(parts[1]), int(parts[2])
    if len(parts) == 2:
        return parts[0], None, int(parts[1])
    raise ValueError(f"invalid template source_id: {source_id!r}")


def inf_id(inf_name, index) -> str:
    return _SEP.join((KIND_INF, _norm_filename(inf_name), "text", _seg(int(index))))


def spellmkr_id(section, index) -> str:
    return _SEP.join((KIND_SPELLMKR, _seg(section), _seg(int(index))))


def namechnk_id(chunk, index) -> str:
    return _SEP.join((KIND_NAMECHNK, _seg(chunk), _seg(int(index))))


def question_id(question_number) -> str:
    return _SEP.join((KIND_QUESTION, _seg(int(question_number))))


def tradetext_id(dat_file, index) -> str:
    return _SEP.join((KIND_TRADE, _seg(str(dat_file).lower()), _seg(int(index))))


def aexe_id(group, entry_id) -> str:
    return _SEP.join((KIND_AEXE, _seg(group), _seg(entry_id)))


def aexe_table_id(group, table, index) -> str:
    return _SEP.join((KIND_AEXE, _seg(group), _seg(table), _seg(int(index))))


def spellsg65_id(index) -> str:
    return _SEP.join((KIND_SPELLSG, "standard", _seg(int(index))))


def public_builtin_id(key) -> str:
    return _SEP.join((KIND_PUBLIC_BUILTIN, _seg(str(key))))


def armor_prefix_id(material) -> str:
    return _SEP.join((KIND_ARMOR_PREFIX, _seg(str(material).lower())))


def spell_effect_id(effect_id, sub_effect_id=0) -> str:
    return _SEP.join((KIND_SPELL_EFFECT, _seg(int(effect_id)), _seg(int(sub_effect_id))))


def magic_item_id(item_idx, spell_kind, spell_idx) -> str:
    return _SEP.join((KIND_MAGIC_ITEM, _seg(int(item_idx)),
                      _seg(str(spell_kind)), _seg(int(spell_idx))))


def material_item_id(material_idx, acc_idx) -> str:
    return _SEP.join((KIND_MATERIAL_ITEM, _seg(int(material_idx)), _seg(int(acc_idx))))


def citydata_province_name_id(province_index) -> str:
    return _SEP.join((KIND_CITYDATA, _seg(int(province_index)), "name"))


def citydata_location_id(province_index, location_id) -> str:
    return _SEP.join(
        (KIND_CITYDATA, _seg(int(province_index)), _seg(int(location_id))))


def docs_id(doc_kind, entry_id) -> str:
    return _SEP.join((KIND_DOCS, _seg(doc_kind), _seg(entry_id)))


def assist_summary_id(entry_id) -> str:
    return _SEP.join((KIND_ASSIST_SUMMARY, _seg(entry_id)))


def parse_source_id(source_id: str) -> tuple[str, tuple[str, ...]]:
    parts = source_id.split(_SEP)
    if not parts:
        raise ValueError(f"invalid source_id: {source_id!r}")
    kind = parts[0]
    if kind not in ALL_KINDS:
        raise ValueError(f"unknown source_id kind: {kind!r} in {source_id!r}")
    return kind, tuple(parts[1:])



HASH_LENGTH = 16

_LINE_TRAIL_WS = re.compile(r"[ \t]+(?=\n)")


def normalize_source_text(text: str) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFC", str(text))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _LINE_TRAIL_WS.sub("", s)
    s = s.strip()
    return s


def source_hash(text: str, *, length: int = HASH_LENGTH) -> str:
    norm = normalize_source_text(text)
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return digest[:length]


def hash_matches(text: str, expected_hash: str) -> bool:
    if not expected_hash:
        return False
    got = source_hash(text, length=max(len(expected_hash), HASH_LENGTH))
    return got[:len(expected_hash)] == expected_hash



OVERLAY_HASH = "src"
OVERLAY_TRANSLATION = "t"

MANIFEST_VERSION = "version"
MANIFEST_GENERATOR = "generator"
MANIFEST_FINGERPRINT = "arena_fingerprint"
MANIFEST_DIGEST = "digest"
MANIFEST_ENTRIES = "entries"


def manifest_digest(entries: dict[str, str]) -> str:
    parts = []
    for sid in sorted(entries):
        parts.append(sid)
        parts.append(entries[sid])
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _hash_equal(a: str, b: str) -> bool:
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def compare_manifests(golden_entries: dict[str, str],
                      local_entries: dict[str, str]) -> dict:
    gset, lset = set(golden_entries), set(local_entries)
    missing = sorted(gset - lset)
    extra = sorted(lset - gset)
    drift = sorted(
        sid for sid in (gset & lset)
        if not _hash_equal(golden_entries[sid], local_entries[sid]))
    return {
        "missing": missing,
        "extra": extra,
        "drift": drift,
        "ok": not (missing or extra or drift),
        "counts": {
            "golden": len(golden_entries), "local": len(local_entries),
            "missing": len(missing), "extra": len(extra), "drift": len(drift),
        },
    }
