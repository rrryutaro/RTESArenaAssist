
import re

import i18n_helper as i18n


def _load_chargen_class_ja() -> dict[str, str]:
    out: dict[str, str] = {}
    for e in i18n.v2_category_entries("classes"):
        en = e.get("original")
        ja = e.get("text")
        if en and ja and en not in out:
            out[en] = ja
    if out:
        return out
    for id_, entry in i18n.originals("classes").items():
        en = entry.get("original") if isinstance(entry, dict) else None
        if not en:
            continue
        ja = i18n.text_opt(id_)
        if ja and en not in out:
            out[en] = ja
    return out


class _LazyClassJaMap(dict):

    def _ensure(self) -> None:
        if not self:
            loaded = _load_chargen_class_ja()
            if loaded:
                self.update(loaded)

    def get(self, key, default=None):  # noqa: A003
        self._ensure()
        return super().get(key, default)

    def items(self):
        self._ensure()
        return super().items()

    def __contains__(self, key) -> bool:
        self._ensure()
        return super().__contains__(key)


_CHARGEN_OPENING_HINT_ADDR = 0x10764C10
_CHARGEN_OPENING_MAXLEN = 1024
_CHARGEN_OPENING_FULLREAD = 4096
_CHARGEN_OPENING_SCAN_START = 0x10000000
_CHARGEN_OPENING_SCAN_END   = 0x12000000
_CHARGEN_OPENING_PREFIXES = (
    "Do not fear for it is I",
)


_CHARGEN_GOYENOW_HINT_ADDR = 0x106D0930
_CHARGEN_GOYENOW_HINT_CHECKLEN = 32
_CHARGEN_GOYENOW_PREFIX = b"Go ye now in peace"
_CHARGEN_GOYENOW_SCAN_START = 0x10600000
_CHARGEN_GOYENOW_SCAN_END   = 0x10800000


_GARBAGE_NPC_PATTERNS = (
    re.compile(r"^[A-Z]+\.\d+$"),
    re.compile(r"^[A-Z0-9_]+\.[A-Z]+$"),
    re.compile(r"^[a-zA-Z][a-zA-Z0-9_@]{0,7}\.[a-zA-Z0-9]{1,3}$"),
    re.compile(r"^\S{1,20}\.[a-zA-Z0-9]{1,3}$"),
    re.compile(r"^[+-]?\d{1,3}$"),
)


def _is_garbage_npc_buffer(text: str) -> bool:
    if not text:
        return False
    s = text.strip()
    if not s:
        return False
    for pat in _GARBAGE_NPC_PATTERNS:
        if pat.match(s):
            return True
    if len(s) < 4:
        return False
    printable = sum(1 for c in s if 0x20 <= ord(c) < 0x7F)
    if printable / max(len(s), 1) < 0.5:
        return True
    return False


def _looks_like_cinematic(text: str) -> bool:
    if not text or len(text) < 20:
        return False
    printable = sum(1 for c in text if 0x20 <= ord(c) < 0x7F or c in "\r\n\t")
    return (printable / max(len(text), 1)) >= 0.85


_CHARGEN_NAME_RE = re.compile(r'will be thy name,\s+(\w+)\?', re.IGNORECASE)

_CHARGEN_CLASS_JA: dict[str, str] = _LazyClassJaMap()

_CHARGEN_PEOPLE_JA: dict[str, str] = {
    "Bretons": "ブレトン", "Redguards": "レッドガード", "Nords": "ノルド",
    "Dark Elves": "ダークエルフ", "High Elves": "ハイエルフ", "Wood Elves": "ウッドエルフ",
    "Khajiit": "カジート", "Argonians": "アルゴニアン", "Imperials": "インペリアル",
}

_CHARGEN_RACE_INF_TO_JA: dict[str, str] = {
    "BRETON":    "ブレトン",
    "REDGUARD":  "レッドガード",
    "NORD":      "ノルド",
    "DARK_ELF":  "ダークエルフ",
    "HIGH_ELF":  "ハイエルフ",
    "WOOD_ELF":  "ウッドエルフ",
    "KHAJIIT":   "カジート",
    "ARGONIAN":  "アルゴニアン",
}


_PROVINCE_ALIASES = {"summerset isle": "glossary.summerset_isle.0"}


def _translate_province(en: str) -> str:
    if not en:
        return en
    from location_lookup import lookup as _loc_lookup
    ja = _loc_lookup(en)
    if ja:
        return ja
    alias_id = _PROVINCE_ALIASES.get(en.strip().lower())
    if alias_id:
        ja = i18n.text_opt(alias_id)
        if ja:
            return ja
    return en


_CHARGEN_DYNAMIC_PATTERNS: list[tuple] = [
    (
        re.compile(r'From where dost thou hail', re.IGNORECASE),
        "_CHARGEN_PROVINCE_",
        re.compile(r'From where dost thou hail,\s+(.+?)\s+the\s+(\w+)\?', re.IGNORECASE),
        lambda m: {"[name]": m.group(1),
                   "[クラス]": _CHARGEN_CLASS_JA.get(m.group(2), m.group(2))},
        None,
    ),
    (
        re.compile(r'Thou hast chosen .+?, land of the', re.IGNORECASE),
        "_CHARGEN_PROVINCE_CONFIRM_",
        re.compile(r'Thou hast chosen (.+?), land of the (.+?)\.', re.IGNORECASE),
        lambda m: {"[プロヴィンス]": _translate_province(m.group(1)),
                   "[種族]": _CHARGEN_PEOPLE_JA.get(m.group(2), m.group(2))},
        "\n\nYes\nNo",
    ),
    (
        re.compile(r'Then thou wilt be known as the', re.IGNORECASE),
        "_CHARGEN_COMPLETE_",
        re.compile(
            r'Then thou wilt be known as the (\w+) (.+?), who wouldst call (.+?), land of the (.+?), h(?:er|is) home\.',
            re.IGNORECASE),
        lambda m: {"[クラス]": _CHARGEN_CLASS_JA.get(m.group(1), m.group(1)),
                   "[name]": m.group(2),
                   "[プロヴィンス]": _translate_province(m.group(3)),
                   "[種族]": _CHARGEN_PEOPLE_JA.get(m.group(4), m.group(4))},
        None,
    ),
]
