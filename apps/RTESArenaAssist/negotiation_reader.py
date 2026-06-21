from __future__ import annotations

import re
from typing import Optional

from arena_bridge import ArenaMemoryAnalyzer


NEGOT_TEMPLATE_OFFSET = 0x929E
NEGOT_TEMPLATE_MAXLEN = 256
NEGOT_RENDERED_OFFSET = 0x987A
NEGOT_RENDERED_MAXLEN = 256

NEGOT_MESSAGE_OFFSET = NEGOT_RENDERED_OFFSET
NEGOT_MESSAGE_MAXLEN = NEGOT_RENDERED_MAXLEN


BUTTON_LABELS_EN: tuple[str, ...] = ("ACCEPT", "COUNTER", "REJECT")
BUTTON_LABELS_JA: tuple[str, ...] = ("承諾", "対案", "拒否")


NEGOTIATION_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "NEGOTBUT.IMG": {
        "buttons_en": ("ACCEPT", "COUNTER", "REJECT"),
        "buttons_ja": ("承諾", "対案", "拒否"),
    },
    "YESNO.IMG": {
        "buttons_en": ("YES", "NO", "CANCEL"),
        "buttons_ja": ("はい", "いいえ", "キャンセル"),
    },
}


def get_negotiation_profile(img_name: str) -> Optional[dict]:
    return NEGOTIATION_PROFILES.get(img_name)


_PLACEHOLDER_MAP = {
    "%i": "%nr",
    "%lu": "%a",
    "%u": "%a",
    "%d": "%a",
    "%mm": "%a",
}

_C_PH_PATTERN = re.compile(
    r"%(?:lu|mm|s|i|u|d)"
)

_ARENA_PH_PATTERN = re.compile(r"%([a-z][a-z0-9]*)\b")


def _escape_literal_flexible_ws(text: str) -> str:
    parts: list[str] = []
    for part in re.split(r"(\s+)", text):
        if not part:
            continue
        if part.isspace():
            parts.append(r"\s+")
        else:
            parts.append(re.escape(part))
    return "".join(parts)


def _canonicalize_template(raw_template: str) -> str:
    s = raw_template.replace("\t", " ")
    string_count = 0

    def _replace(m: re.Match) -> str:
        nonlocal string_count
        token = m.group(0)
        if token == "%s":
            string_count += 1
            return "%nr" if string_count == 1 else f"%nr{string_count}"
        return _PLACEHOLDER_MAP.get(token, token)
    return _C_PH_PATTERN.sub(_replace, s)


def _template_to_prefix_regex(canonical: str) -> Optional[re.Pattern]:
    seen: set[str] = set()
    out_parts: list[str] = []
    last_end = 0
    for m in _ARENA_PH_PATTERN.finditer(canonical):
        name = m.group(1)
        out_parts.append(_escape_literal_flexible_ws(
            canonical[last_end:m.start()]))
        if name in seen:
            out_parts.append(f"(?P={name})")
        else:
            out_parts.append(f"(?P<{name}>.+?)")
            seen.add(name)
        last_end = m.end()
    out_parts.append(_escape_literal_flexible_ws(canonical[last_end:]))
    pattern_str = "^" + "".join(out_parts)
    try:
        return re.compile(pattern_str, re.DOTALL)
    except re.error:
        return None


def _decode_chunks(raw: bytes, max_chunks: int = 32) -> str:
    chunks: list[str] = []
    n = len(raw)
    pos = 0
    while pos < n and len(chunks) < max_chunks:
        if raw[pos] == 0x00:
            pos += 1
            continue
        m = re.match(rb"[\x20-\x7E]+", raw[pos:])
        if not m:
            pos += 1
            continue
        seg = m.group().decode("ascii", errors="replace").strip()
        if seg:
            chunks.append(seg)
        pos += len(m.group())
    return " ".join(chunks).strip()


def _read_nul_terminated_ascii(analyzer, anchor, off, max_len):
    try:
        buf = analyzer.read_bytes(anchor + off, max_len)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    if not text:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def extract_negotiation_body(template_raw: str, rendered: Optional[str]
                              ) -> Optional[str]:
    if not template_raw or not rendered:
        return None
    canonical = _canonicalize_template(template_raw)
    has_placeholder = bool(_ARENA_PH_PATTERN.search(canonical))
    pattern = _template_to_prefix_regex(canonical)
    if pattern is None:
        return None
    m = pattern.match(rendered)
    if m:
        return m.group(0)
    if not has_placeholder:
        return template_raw
    return None


def read_negotiation_message(analyzer: "ArenaMemoryAnalyzer",
                              anchor: int) -> Optional[str]:
    template_raw = _read_nul_terminated_ascii(
        analyzer, anchor, NEGOT_TEMPLATE_OFFSET, NEGOT_TEMPLATE_MAXLEN)
    if not template_raw:
        return None
    try:
        rendered_raw = analyzer.read_bytes(
            anchor + NEGOT_RENDERED_OFFSET, NEGOT_RENDERED_MAXLEN)
    except (OSError, AttributeError):
        return None
    rendered = _decode_chunks(rendered_raw)
    if not rendered:
        return None
    body = extract_negotiation_body(template_raw, rendered)
    return body


def read_negotiation_diagnostic(analyzer: "ArenaMemoryAnalyzer",
                                  anchor: int) -> tuple[
        Optional[str], Optional[str], Optional[str], Optional[str]]:
    raw_template = _read_nul_terminated_ascii(
        analyzer, anchor, NEGOT_TEMPLATE_OFFSET, NEGOT_TEMPLATE_MAXLEN)
    canonical = (_canonicalize_template(raw_template)
                 if raw_template else None)
    try:
        rendered_raw = analyzer.read_bytes(
            anchor + NEGOT_RENDERED_OFFSET, NEGOT_RENDERED_MAXLEN)
        rendered = _decode_chunks(rendered_raw) or None
    except (OSError, AttributeError):
        rendered = None
    matched = (extract_negotiation_body(raw_template, rendered)
               if raw_template and rendered else None)
    return raw_template, canonical, rendered, matched


__all__ = [
    "NEGOT_TEMPLATE_OFFSET",
    "NEGOT_TEMPLATE_MAXLEN",
    "NEGOT_RENDERED_OFFSET",
    "NEGOT_RENDERED_MAXLEN",
    "NEGOT_MESSAGE_OFFSET",
    "NEGOT_MESSAGE_MAXLEN",
    "BUTTON_LABELS_EN",
    "BUTTON_LABELS_JA",
    "NEGOTIATION_PROFILES",
    "get_negotiation_profile",
    "extract_negotiation_body",
    "read_negotiation_message",
    "read_negotiation_diagnostic",
]
