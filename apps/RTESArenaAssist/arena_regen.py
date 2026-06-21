from __future__ import annotations

import hashlib
import re

import i18n_source_address as sa

GENERATOR_VERSION = "be-2"
CATEGORY = "template_dat_building_entry"
KEY_PREFIX = f"{CATEGORY}."

TARGET_BLOCKS = ("0000", "0001", "0002", "0003", "0004")
_KEY_RE = re.compile(r"^#([0-9]+)([a-zA-Z]?)$")
_PLACEHOLDER_RE = re.compile(r"%([a-zA-Z][a-zA-Z0-9]*)")


def parse_template_dat_bytes(raw: bytes) -> list[dict]:
    text = raw.decode("latin-1", errors="replace")
    lines = text.splitlines()
    entries: list[dict] = []
    seen_count: dict[tuple[str, str], int] = {}
    i = 0
    while i < len(lines):
        m = _KEY_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        key, letter = m.group(1), m.group(2) or ""
        buf: list[str] = []
        j = i + 1
        while j < len(lines) and not _KEY_RE.match(lines[j].strip()):
            buf.append(lines[j])
            j += 1
        body = "\n".join(buf)
        values = [" ".join(part.split()) for part in body.split("&")]
        values = [v for v in values if v]
        copy_idx = seen_count.get((key, letter), 0)
        seen_count[(key, letter)] = copy_idx + 1
        entries.append({"key": key, "letter": letter,
                        "copy": copy_idx, "values": values})
        i = j
    return entries


def _placeholders(value: str) -> list[str]:
    seen: list[str] = []
    for m in _PLACEHOLDER_RE.finditer(value):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def regenerate_building_entry_bytes(raw: bytes) -> dict[str, dict]:
    entries = parse_template_dat_bytes(raw)
    out: dict[str, dict] = {}
    for e in entries:
        if e["key"] not in TARGET_BLOCKS:
            continue
        block = f"{e['key']}_{e['letter']}" if e["letter"] else e["key"]
        copy = e["copy"]
        for vi, value in enumerate(e["values"]):
            app_id = f"{KEY_PREFIX}{block}.copy{copy}.{vi}"
            out[app_id] = {
                "original": value,
                "source_id": sa.template_id(block, vi, copy=copy),
                "source_hash": sa.source_hash(value),
                "key": e["key"],
                "letter": e["letter"] or None,
                "copy": copy,
                "placeholders": _placeholders(value),
            }
    return out


def build_original_json(new_entries: dict[str, dict]) -> dict:
    out: dict[str, dict] = {}
    for app_id in sorted(new_entries):
        e = new_entries[app_id]
        out[app_id] = {
            "original": e["original"],
            "source_id": e["source_id"],
            "source_hash": e["source_hash"],
            "key": e["key"],
            "letter": e["letter"],
            "copy": e["copy"],
            "placeholders": e["placeholders"],
        }
    return out



NPC_DIALOG_GENERATOR_VERSION = "npcd-1"
NPC_DIALOG_CATEGORY = "npc_dialog"
NPC_DIALOG_KEY_PREFIX = f"{NPC_DIALOG_CATEGORY}."

_NPC_DIALOG_FLATTEN = {"0014": tuple("abcdefghijkl")}


def _npc_block_label(key: str) -> str:
    return f"{int(key):04d}"


def _npc_emit(out: dict[str, dict], block: str, values: list[str]) -> None:
    for vi, value in enumerate(values):
        app_id = f"{NPC_DIALOG_KEY_PREFIX}{block}.{vi}"
        out[app_id] = {
            "original": value,
            "source_id": sa.template_id(block, vi),
            "source_hash": sa.source_hash(value),
            "placeholders": sorted(set(_placeholders(value))),
        }


def regenerate_npc_dialog_bytes(raw: bytes) -> dict[str, dict]:
    entries = parse_template_dat_bytes(raw)
    by_key_letter: dict[tuple[str, str], list[str]] = {}
    for e in entries:
        if e["copy"] != 0:
            continue
        by_key_letter[(e["key"], e["letter"])] = e["values"]

    out: dict[str, dict] = {}
    for (key, letter), values in by_key_letter.items():
        if letter or key in TARGET_BLOCKS:
            continue
        _npc_emit(out, _npc_block_label(key), values)
    for block, letters in _NPC_DIALOG_FLATTEN.items():
        flat: list[str] = []
        seen: set[str] = set()
        for letter in letters:
            for v in by_key_letter.get((block, letter), []):
                if v not in seen:
                    seen.add(v)
                    flat.append(v)
        if flat:
            _npc_emit(out, block, flat)
    return out


def build_npc_dialog_original_json(new_entries: dict[str, dict]) -> dict:
    out: dict[str, dict] = {}
    for app_id in sorted(new_entries):
        e = new_entries[app_id]
        out[app_id] = {
            "original": e["original"],
            "source_id": e["source_id"],
            "source_hash": e["source_hash"],
            "placeholders": e["placeholders"],
        }
    return out


def fingerprint_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_manifest(new_entries: dict[str, dict], fingerprint: str,
                    category: str, generator_version: str) -> dict:
    entries = {e["source_id"]: e["source_hash"] for e in new_entries.values()}
    return {
        sa.MANIFEST_VERSION: generator_version,
        sa.MANIFEST_GENERATOR: f"arena_regen/{generator_version}",
        sa.MANIFEST_FINGERPRINT: fingerprint,
        sa.MANIFEST_DIGEST: sa.manifest_digest(entries),
        "category": category,
        sa.MANIFEST_ENTRIES: entries,
    }


def build_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint, CATEGORY, GENERATOR_VERSION)


def build_npc_dialog_manifest(new_entries: dict[str, dict],
                              fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, NPC_DIALOG_GENERATOR_VERSION)



INF_TEXT_GENERATOR_VERSION = "inf-1"
INF_TEXT_CATEGORY = "inf_text"


def _parse_inf_text_section(raw: bytes, inf_name: str) -> list[dict]:
    lines = raw.decode("latin-1", errors="replace").splitlines()

    def new_cur() -> dict:
        return {"inf": inf_name, "idx": None, "type": None, "key_id": None,
                "text_lines": [], "params": None, "riddle_lines": [],
                "answers": [], "correct_lines": [], "wrong_lines": [],
                "riddle_mode": None}

    out: list[dict] = []
    cur = new_cur()
    in_text = False

    def flush() -> None:
        nonlocal cur
        if cur["idx"] is None:
            return
        t = cur["type"]
        e: dict = {"inf": cur["inf"], "idx": cur["idx"]}
        if t == "key":
            if cur["text_lines"]:
                e.update(type="key_lore", key_id=cur["key_id"],
                         text="\n".join(cur["text_lines"]))
            else:
                e.update(type="key", key_id=cur["key_id"])
        elif t == "lore_once":
            e.update(type="lore_once", text="\n".join(cur["text_lines"]))
        elif t == "riddle":
            e.update(type="riddle", params=cur["params"],
                     question="\n".join(cur["riddle_lines"]),
                     answers=cur["answers"],
                     correct="\n".join(cur["correct_lines"]),
                     wrong="\n".join(cur["wrong_lines"]))
        else:
            if not cur["text_lines"]:
                return
            e.update(type="lore", text="\n".join(cur["text_lines"]))
        out.append(e)

    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if line.startswith("@"):
            sec = line.strip()
            if sec == "@TEXT":
                flush(); cur = new_cur(); in_text = True
            elif in_text:
                flush(); cur = new_cur(); in_text = False
            continue
        if not in_text:
            continue
        if line.startswith("*TEXT"):
            flush(); cur = new_cur()
            parts = line.split()
            if len(parts) >= 2:
                try:
                    cur["idx"] = int(parts[1])
                except ValueError:
                    pass
            continue
        if cur["idx"] is None:
            continue
        stripped = line.strip()
        if stripped == "":
            if cur["type"] == "riddle" and cur["riddle_mode"] == "riddle":
                cur["riddle_lines"].append("")
            continue
        if cur["type"] == "riddle":
            if stripped.startswith(":"):
                cur["answers"].append(stripped[1:])
            elif stripped.startswith("`CORRECT"):
                cur["riddle_mode"] = "correct"
            elif stripped.startswith("`WRONG"):
                cur["riddle_mode"] = "wrong"
            elif cur["riddle_mode"] == "riddle":
                cur["riddle_lines"].append(line)
            elif cur["riddle_mode"] == "correct":
                cur["correct_lines"].append(line)
            elif cur["riddle_mode"] == "wrong":
                cur["wrong_lines"].append(line)
            continue
        if cur["type"] == "lore_once":
            cur["text_lines"].append(line); continue
        if cur["type"] == "key":
            cur["text_lines"].append(line); continue
        if cur["type"] is None:
            if stripped.startswith("+"):
                try:
                    cur["key_id"] = int(stripped[1:].strip())
                    cur["type"] = "key"; continue
                except ValueError:
                    pass
            elif stripped.startswith("^"):
                parts = stripped[1:].split()
                if len(parts) >= 2:
                    try:
                        cur["params"] = [int(parts[0]), int(parts[1])]
                        cur["type"] = "riddle"; cur["riddle_mode"] = "riddle"
                        continue
                    except ValueError:
                        pass
            elif stripped.startswith("~"):
                cur["type"] = "lore_once"
                rest = line[line.find("~") + 1:]
                if rest:
                    cur["text_lines"].append(rest)
                continue
        if cur["type"] is None:
            cur["type"] = "lore"
        cur["text_lines"].append(line)

    if in_text:
        flush()
    return out


def _inf_entry(original: str, source_id: str, extra: dict) -> dict:
    e = {"original": original, "source_id": source_id,
         "source_hash": sa.source_hash(original)}
    e.update(extra)
    return e


def regenerate_inf_text_bytes(inf_files: dict[str, bytes]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for inf_name in sorted(inf_files):
        if not inf_name.upper().endswith(".INF"):
            continue
        for pe in _parse_inf_text_section(inf_files[inf_name], inf_name.upper()):
            inf, idx, t = pe["inf"], pe["idx"], pe["type"]
            base = f"{INF_TEXT_CATEGORY}.{inf}_{idx}.0"
            sid = sa.inf_id(inf, idx)
            common = {"inf": inf, "idx": idx, "type": t}
            if t in ("lore", "lore_once"):
                out[base] = _inf_entry(pe["text"], sid,
                                       {**common, "text": pe["text"]})
            elif t == "key_lore":
                out[base] = _inf_entry(pe["text"], sid,
                                       {**common, "key_id": pe["key_id"],
                                        "text": pe["text"]})
            elif t == "key":
                out[base] = _inf_entry("", sid,
                                       {**common, "key_id": pe["key_id"]})
            elif t == "riddle":
                out[base] = _inf_entry("", sid, {
                    **common, "params": pe["params"], "question": pe["question"],
                    "answers": pe["answers"], "correct": pe["correct"],
                    "wrong": pe["wrong"]})
                for field in ("question", "correct", "wrong"):
                    text = pe[field]
                    if not text:
                        continue
                    out[f"{INF_TEXT_CATEGORY}.{inf}_{idx}.{field}"] = _inf_entry(
                        text, f"{sid}:{field}", {"type": "riddle", "field": field})
    return out


def build_inf_text_original_json(new_entries: dict[str, dict]) -> dict:
    return {app_id: new_entries[app_id] for app_id in sorted(new_entries)}


def build_inf_text_manifest(new_entries: dict[str, dict],
                            fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           INF_TEXT_CATEGORY, INF_TEXT_GENERATOR_VERSION)



CHARGEN_QUESTION_GENERATOR_VERSION = "question-2"
_CHARGEN_QUESTION_NUMBER_RE = re.compile(r"^\s*\d+\.\s*")
_CHARGEN_CATEGORY_MARKER_RE = re.compile(r"\s*\(5[lcv]\)\s*")


def _parse_question_txt(raw: bytes) -> list[tuple[str, str, str, str]]:
    text = raw.decode("latin-1", errors="replace")
    questions: list[tuple[str, str, str, str]] = []
    desc = a = b = c = ""
    mode = "D"
    for line in text.split("\n"):
        first = line[0] if line else ""
        if first.isalpha():
            if first == "a":
                mode = "A"
            elif first == "b":
                mode = "B"
            elif first == "c":
                mode = "C"
        elif first.isdigit():
            if mode != "D":
                questions.append((desc, a, b, c))
                desc = a = b = c = ""
            mode = "D"
        nl = line + "\n"
        if mode == "D":
            desc += nl
        elif mode == "A":
            a += nl
        elif mode == "B":
            b += nl
        elif mode == "C":
            c += nl
    questions.append((desc, a, b, c))
    return questions


def _curate_question(desc: str) -> str:
    s = _CHARGEN_QUESTION_NUMBER_RE.sub("", desc)
    return re.sub(r"\s+", " ", s).strip()


def _curate_answer(ans: str) -> str:
    s = re.sub(r"\s+", " ", ans).strip()
    return _CHARGEN_CATEGORY_MARKER_RE.sub("", s).strip()


def regenerate_chargen_questions(raw: bytes) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i, (desc, a, b, c) in enumerate(_parse_question_txt(raw), start=1):
        text = _curate_question(desc)
        if not text:
            continue
        answers = [_curate_answer(x) for x in (a, b, c) if x.strip()]
        full = "\n".join([text, *answers])
        inf = f"_CHARGEN_Q_{i}_"
        sid = sa.question_id(i)
        base = f"{INF_TEXT_CATEGORY}.{inf}_0.0"
        out[base] = _inf_entry(text, sid,
                               {"inf": inf, "idx": 0, "type": "lore", "text": text,
                                "text_display": full, "text_panel": full})
        out[f"{INF_TEXT_CATEGORY}.{inf}_0.display"] = _inf_entry(
            full, f"{sid}:display", {"type": "lore", "field": "display"})
    return out


def build_chargen_questions_manifest(new_entries: dict[str, dict],
                                     fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           INF_TEXT_CATEGORY, CHARGEN_QUESTION_GENERATOR_VERSION)



ATRADE_GENERATOR_VERSION = "atrade-1"
_ATRADE_TAVERN_BASE = 500
_ATRADE_PLACEHOLDER_REMAP = (("%i", "%nr"), ("%mm", "%a"))


def _atrade_remap(s: str) -> str:
    s = s.replace("\t", " ")
    for src, dst in _ATRADE_PLACEHOLDER_REMAP:
        s = s.replace(src, dst)
    return s


def _read_dat_strings(raw: bytes) -> list[str]:
    return [s.decode("latin-1", errors="replace") for s in raw.split(b"\x00") if s]


def regenerate_atrade_tavern(raw: bytes) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i, s in enumerate(_read_dat_strings(raw)):
        text = _atrade_remap(s).rstrip()
        app_id = f"{NPC_DIALOG_KEY_PREFIX}A{_ATRADE_TAVERN_BASE + i}.0"
        out[app_id] = {
            "original": text,
            "source_id": sa.tradetext_id("tavern", i),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }
    return out


def build_atrade_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, ATRADE_GENERATOR_VERSION)



ATRADE_SHOP_GENERATOR_VERSION = "atradeshop-1"
_ATRADE_SHOP_SINGLES = (("A601.0", "equip", 9), ("A602.0", "equip", 39),
                        ("A603.0", "equip", 41))


def _atrade_shop_curate(s: str) -> str:
    s = s.replace("%i gold", "%a gold")
    s = s.replace("%i", "%ni").replace("%mm", "%a")
    return re.sub(r"\s+", " ", s).strip()


def regenerate_atrade_shops(equip_raw: bytes, selling_raw: bytes,
                            muguild_raw: bytes) -> dict[str, dict]:
    dats = {"equip": _read_dat_strings(equip_raw),
            "selling": _read_dat_strings(selling_raw),
            "muguild": _read_dat_strings(muguild_raw)}
    out: dict[str, dict] = {}

    def emit(app_id: str, datkey: str, idx: int) -> None:
        strs = dats[datkey]
        if idx >= len(strs):
            return
        text = _atrade_shop_curate(strs[idx])
        out[f"{NPC_DIALOG_KEY_PREFIX}{app_id}"] = {
            "original": text,
            "source_id": sa.tradetext_id(datkey, idx),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }

    for app_id, datkey, idx in _ATRADE_SHOP_SINGLES:
        emit(app_id, datkey, idx)
    for f in range(5):
        for v in range(15):
            emit(f"A{604 + f}.{v}", "equip", f * 15 + v)
            emit(f"A{609 + f}.{v}", "selling", f * 15 + v)
        for v in range(9):
            emit(f"A{614 + f}.{v}", "muguild", f * 15 + (v // 3 + 2) * 3 + v % 3)
    return out


def build_atrade_shop_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, ATRADE_SHOP_GENERATOR_VERSION)



AKEY_REPAIR_GENERATOR_VERSION = "akeyrepair-1"
_AKEY_AMT_PH = re.compile(r"%(?:t|a|mm)\b")
_AKEY_REPAIR_MAP = {
    "A182.0": ("1424", 1, ()),
    "A183.0": ("1424", 0, ()),
    "A184.0": ("1425", 0, ()),
    "A185.0": ("1426", 0, (("gp", "gold"),)),
    "A185.1": ("1426", 0, ()),
    "A186.0": ("1427", 0, ()),
    "A186.1": ("1427", 1, ()),
    "A187.0": ("1428", 0, ()),
    "A187.1": ("1428", 1, ()),
    "A188.0": ("1417", 0, ()),
    "A188.1": ("1418", 0, (("cost, but", "cost but"),)),
    "A188.2": ("1418", 0, ()),
}


def _akey_repair_curate(s: str, subs) -> str:
    s = s.replace("%i", "%ni")
    amt = iter(("%a", "%a2"))
    s = _AKEY_AMT_PH.sub(lambda m: next(amt, m.group(0)), s)
    s = re.sub(r"\s+", " ", s).strip()
    for a, b in subs:
        s = s.replace(a, b)
    return s


def regenerate_akey_repair(template_raw: bytes) -> dict[str, dict]:
    ents = {(e["key"], e["copy"]): e for e in parse_template_dat_bytes(template_raw)}
    out: dict[str, dict] = {}
    for akey, (block, vi, subs) in _AKEY_REPAIR_MAP.items():
        e = ents.get((block, 0))
        if not e or vi >= len(e["values"]):
            continue
        text = _akey_repair_curate(e["values"][vi], subs)
        out[f"{NPC_DIALOG_KEY_PREFIX}{akey}"] = {
            "original": text,
            "source_id": sa.template_id(block, vi, copy=0),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }
    return out


def build_akey_repair_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, AKEY_REPAIR_GENERATOR_VERSION)




def _akey_repair_curation_excluded() -> frozenset:
    pos: dict[tuple, list] = {}
    for akey, (block, vi, subs) in _AKEY_REPAIR_MAP.items():
        pos.setdefault((block, vi), []).append((akey, bool(subs)))
    excluded = set()
    for siblings in pos.values():
        if len(siblings) > 1:
            for akey, has_subs in siblings:
                if has_subs:
                    excluded.add(akey)
    return frozenset(excluded)


_AKEY_REPAIR_CURATION = _akey_repair_curation_excluded()
_AKEY_NUM_RE = re.compile(r"^A(\d+)\.(\d+)$")


def akey_structural_source_id(akey: str, aexe_akey_keys) -> str | None:
    spec = _AKEY_REPAIR_MAP.get(akey)
    if spec is not None:
        if akey in _AKEY_REPAIR_CURATION:
            return None
        block, vi, _subs = spec
        return sa.template_id(block, vi, copy=0)
    if akey in aexe_akey_keys:
        return sa.aexe_id("akey", akey)
    for sid_akey, datkey, idx in _ATRADE_SHOP_SINGLES:
        if akey == sid_akey:
            return sa.tradetext_id(datkey, idx)
    m = _AKEY_NUM_RE.match(akey)
    if not m:
        return None
    num, sub = int(m.group(1)), int(m.group(2))
    if 500 <= num <= 599 and sub == 0:
        return sa.tradetext_id("tavern", num - _ATRADE_TAVERN_BASE)
    if 604 <= num <= 608:
        return sa.tradetext_id("equip", (num - 604) * 15 + sub)
    if 609 <= num <= 613:
        return sa.tradetext_id("selling", (num - 609) * 15 + sub)
    if 614 <= num <= 618:
        return sa.tradetext_id("muguild", (num - 614) * 15 + (sub // 3 + 2) * 3 + sub % 3)
    return None



AKEY_UI_GENERATOR_VERSION = "akeyui-2"
_AKEY_EXE_PH = re.compile(r"%l?[sduSDU]\d*")


def _akey_seg(raw: str) -> str:
    cut = raw.find("\r")
    return raw[:cut] if cut >= 0 else raw


def _akey_remap(text: str, phs: list) -> str:
    it = iter(phs)
    return _AKEY_EXE_PH.sub(lambda m: next(it, m.group(0)), text)


def regenerate_akey_ui(raw_map: dict, template: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for akey, spec in template.items():
        raw = raw_map.get(akey)
        if raw is None:
            continue
        mode = spec.get("mode", "seg")
        phs = spec.get("ph", [])
        if mode == "seg":
            text = _akey_remap(_akey_seg(raw), phs).rstrip(" ")
            text += " " * int(spec.get("trail", 0))
        elif mode == "seg_suffix":
            text = _akey_seg(raw).rstrip(" ") + spec.get("suffix", "")
        elif mode == "full":
            text = _akey_remap(raw.replace("\r", ""), phs).rstrip(" ")
        elif mode == "join_ws":
            joined = re.sub(r"\s+", " ", raw.replace("\r", " ")).strip()
            text = _akey_remap(joined, phs)
            rs = spec.get("rstrip")
            if rs:
                text = text.rstrip(rs + " ")
        else:
            continue
        app_id = f"{NPC_DIALOG_KEY_PREFIX}{akey}"
        out[app_id] = {
            "original": text,
            "source_id": sa.aexe_id("akey", akey),
            "source_hash": sa.source_hash(text),
            "placeholders": _placeholders(text),
        }
    return out


def build_akey_ui_manifest(new_entries: dict[str, dict], fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_DIALOG_CATEGORY, AKEY_UI_GENERATOR_VERSION)



CHARGEN_UI_GENERATOR_VERSION = "chargenui-1"

_CHARGEN_CLASS_ORDER = (
    "MAGE", "SPELLSWORD", "BATTLEMAGE", "SORCEROR", "HEALER", "NIGHTBLADE",
    "BARD", "BURGLAR", "ROGUE", "ACROBAT", "THIEF", "ASSASSIN", "MONK",
    "ARCHER", "RANGER", "BARBARIAN", "WARRIOR", "KNIGHT",
)
_CHARGEN_RACE_ORDER = (
    "BRETON", "REDGUARD", "NORD", "DARK_ELF", "HIGH_ELF", "WOOD_ELF",
    "KHAJIIT", "ARGONIAN",
)
_CHARGEN_UI_SINGLE = {
    "": "choose_class_creation",
    "10Q": "class_questions_intro",
    "CHOOSE_CLASS": "choose_class_list",
    "GENDER": "choose_gender",
    "CHOOSE_ATTRIBUTES": "choose_attributes",
    "BONUS_REMAINING": "choose_attributes_bonus_points_remaining",
    "APPEARANCE": "choose_appearance",
    "GOYENOW": "confirmed_race4",
}


def _chargen_norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\r", " ")).strip()


def _chargen_ui_src(table: str, key) -> str:
    return sa._SEP.join((sa.KIND_AEXE, "char_creation", str(table), str(key)))


def _chargen_ui_emit(out: dict, name: str, text: str, src_id: str) -> None:
    inf = "_CHARGEN_" + (f"{name}_" if name else "")
    base = f"{INF_TEXT_CATEGORY}.{inf}_0.0"
    out[base] = _inf_entry(text, src_id,
                           {"inf": inf, "idx": 0, "type": "lore", "text": text,
                            "text_display": text, "text_panel": text})
    out[f"{INF_TEXT_CATEGORY}.{inf}_0.display"] = _inf_entry(
        text, f"{src_id}:display", {"type": "lore", "field": "display"})


def regenerate_chargen_ui(cc: dict, class_names: list, pref_attrs: list,
                          race_descs: list) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, key in _CHARGEN_UI_SINGLE.items():
        raw = cc.get(key)
        if not raw:
            continue
        _chargen_ui_emit(out, name, _chargen_norm(raw),
                         _chargen_ui_src("ui", key))
    sc = cc.get("suggested_class")
    if sc:
        fmt = _chargen_norm(sc)
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            if i >= len(class_names):
                break
            text = fmt.replace("%s", class_names[i], 1)
            _chargen_ui_emit(out, f"RESULT_{cls}", text,
                             _chargen_ui_src("result", i))
    cr3 = cc.get("confirmed_race3")
    if cr3:
        fmt = _chargen_norm(cr3)
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            if i >= len(class_names) or i >= len(pref_attrs):
                break
            text = fmt.replace("%s", pref_attrs[i], 1).replace("%s", class_names[i], 1)
            _chargen_ui_emit(out, f"CLASS_ADVICE_{cls}", text,
                             _chargen_ui_src("advice", i))
    cr2 = cc.get("confirmed_race2")
    if cr2:
        prefix = _chargen_norm(cr2)
        for i, race in enumerate(_CHARGEN_RACE_ORDER):
            if i >= len(race_descs):
                break
            desc = _chargen_norm(race_descs[i])
            text = f"{prefix} {desc}".strip()
            _chargen_ui_emit(out, f"RACE_{race}", text,
                             _chargen_ui_src("race", i))
    return out


_chargen_ui_sid_cache: dict[str, str] | None = None


def _chargen_ui_source_id_map() -> dict[str, str]:
    global _chargen_ui_sid_cache
    if _chargen_ui_sid_cache is None:
        out: dict[str, str] = {}

        def emit(name: str, base: str) -> None:
            inf = "_CHARGEN_" + (f"{name}_" if name else "")
            out[f"{inf}_0.0"] = base
            out[f"{inf}_0.display"] = base + ":display"

        for name, key in _CHARGEN_UI_SINGLE.items():
            emit(name, _chargen_ui_src("ui", key))
        for i, cls in enumerate(_CHARGEN_CLASS_ORDER):
            emit(f"RESULT_{cls}", _chargen_ui_src("result", i))
            emit(f"CLASS_ADVICE_{cls}", _chargen_ui_src("advice", i))
        for i, race in enumerate(_CHARGEN_RACE_ORDER):
            emit(f"RACE_{race}", _chargen_ui_src("race", i))
        _chargen_ui_sid_cache = out
    return _chargen_ui_sid_cache


def chargen_ui_source_id(inf_rest: str) -> str | None:
    if inf_rest.startswith("_CHARGEN_Q_"):
        return None
    return _chargen_ui_source_id_map().get(inf_rest)



NPC_NAME_CHUNKS_GENERATOR_VERSION = "namechnk-1"
NPC_NAME_CHUNKS_CATEGORY = "npc_name_chunks"


def regenerate_npc_name_chunks_bytes(raw: bytes) -> dict[str, dict]:
    import struct
    out: dict[str, dict] = {}
    off = 0
    chunk_idx = 0
    n = len(raw)
    while off + 3 <= n:
        chunk_length = struct.unpack_from("<H", raw, off)[0]
        if chunk_length <= 0:
            break
        string_count = raw[off + 2]
        so = off + 3
        for si in range(string_count):
            end = raw.find(b"\x00", so)
            if end < 0:
                break
            value = raw[so:end].decode("latin-1")
            so = end + 1
            app_id = f"{NPC_NAME_CHUNKS_CATEGORY}.chunks.{chunk_idx}.{si}"
            out[app_id] = {
                "original": value,
                "source_id": sa.namechnk_id(chunk_idx, si),
                "source_hash": sa.source_hash(value),
            }
        off += chunk_length
        chunk_idx += 1
    return out


def build_npc_name_chunks_original_json(new_entries: dict[str, dict]) -> dict:
    return {app_id: new_entries[app_id] for app_id in sorted(new_entries)}


def build_npc_name_chunks_manifest(new_entries: dict[str, dict],
                                   fingerprint: str) -> dict:
    return _build_manifest(new_entries, fingerprint,
                           NPC_NAME_CHUNKS_CATEGORY,
                           NPC_NAME_CHUNKS_GENERATOR_VERSION)


AEXE_MANIFEST_GENERATOR_VERSION = "aexe-1"


def build_aexe_manifest(category: str, original_json: dict[str, dict],
                        fingerprint: str) -> dict:
    entries = {sa.aexe_id(category, k): sa.source_hash(v.get("original", ""))
               for k, v in original_json.items()}
    return {
        sa.MANIFEST_VERSION: AEXE_MANIFEST_GENERATOR_VERSION,
        sa.MANIFEST_GENERATOR: f"arena_regen/{AEXE_MANIFEST_GENERATOR_VERSION}",
        sa.MANIFEST_FINGERPRINT: fingerprint,
        sa.MANIFEST_DIGEST: sa.manifest_digest(entries),
        "category": category,
        sa.MANIFEST_ENTRIES: entries,
    }


__all__ = [
    "GENERATOR_VERSION", "CATEGORY", "TARGET_BLOCKS",
    "parse_template_dat_bytes", "regenerate_building_entry_bytes",
    "build_original_json", "fingerprint_bytes", "build_manifest",
    "NPC_DIALOG_GENERATOR_VERSION", "NPC_DIALOG_CATEGORY",
    "regenerate_npc_dialog_bytes", "build_npc_dialog_original_json",
    "build_npc_dialog_manifest",
    "INF_TEXT_GENERATOR_VERSION", "INF_TEXT_CATEGORY",
    "regenerate_inf_text_bytes", "build_inf_text_original_json",
    "build_inf_text_manifest",
    "CHARGEN_QUESTION_GENERATOR_VERSION", "regenerate_chargen_questions",
    "build_chargen_questions_manifest",
    "CHARGEN_UI_GENERATOR_VERSION", "regenerate_chargen_ui",
    "ATRADE_GENERATOR_VERSION", "regenerate_atrade_tavern", "build_atrade_manifest",
    "ATRADE_SHOP_GENERATOR_VERSION", "regenerate_atrade_shops", "build_atrade_shop_manifest",
    "AKEY_REPAIR_GENERATOR_VERSION", "regenerate_akey_repair", "build_akey_repair_manifest",
    "AKEY_UI_GENERATOR_VERSION", "regenerate_akey_ui", "build_akey_ui_manifest",
    "NPC_NAME_CHUNKS_GENERATOR_VERSION", "NPC_NAME_CHUNKS_CATEGORY",
    "regenerate_npc_name_chunks_bytes", "build_npc_name_chunks_original_json",
    "build_npc_name_chunks_manifest",
    "AEXE_MANIFEST_GENERATOR_VERSION", "build_aexe_manifest",
]
