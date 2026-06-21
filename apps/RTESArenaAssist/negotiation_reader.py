"""negotiation_reader.py — NEGOTBUT.IMG (ハッグル交渉) 画面のテキスト読取。

- 主信号: `+0x929E` の **未置換テンプレ** (`%s`/`%lu`/`%i`/`%mm` 形式)
- 従信号: `+0x987A` の **置換済み multi-chunk** (NUL 区切り、行折り返しで分割)
- テンプレ拘束 prefix match で suffix 残骸 ("gold fo" 等) を確実除去

テンプレを主信号、置換済み値を従信号として扱う。chunk 結合を緩く取り、
本文確定はテンプレ拘束 prefix match に委ねることで、残骸 chunk の混入を
防ぐ。

NEGOTBUT.IMG / TAVERN.DAT 専用 profile (= room haggling) として実装。
SELLBUT.IMG 等の汎用化は NEGOTIATION_PROFILES table 拡張で対応する。

API:
  read_negotiation_message(analyzer, anchor) -> str | None
  BUTTON_LABELS_EN: tuple[str, ...]
  BUTTON_LABELS_JA: tuple[str, ...]
"""
from __future__ import annotations

import re
from typing import Optional

from arena_bridge import ArenaMemoryAnalyzer


# anchor 相対固定の offset（観測ベースの仮説）
NEGOT_TEMPLATE_OFFSET = 0x929E
NEGOT_TEMPLATE_MAXLEN = 256
NEGOT_RENDERED_OFFSET = 0x987A
NEGOT_RENDERED_MAXLEN = 256

# 旧名互換 (外部参照防止のため残置)
NEGOT_MESSAGE_OFFSET = NEGOT_RENDERED_OFFSET
NEGOT_MESSAGE_MAXLEN = NEGOT_RENDERED_MAXLEN


# 互換: NEGOTBUT.IMG のボタンラベル
BUTTON_LABELS_EN: tuple[str, ...] = ("ACCEPT", "COUNTER", "REJECT")
BUTTON_LABELS_JA: tuple[str, ...] = ("承諾", "対案", "拒否")


# NEGOTIATION_PROFILES:
# IMG ごとに固定ボタンラベルを持つ。本文経路 (+0x929E / +0x987A) は IMG
# 共通で汎用 reader を使う。新 IMG は ここに 1 entry 追加するだけで対応。
#
# 観測:
#   NEGOTBUT.IMG: ACCEPT / COUNTER / REJECT
#   YESNO.IMG:    YES / NO / CANCEL
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
    """IMG 名から negotiation profile (buttons_en/ja) を返す。

    対応 IMG でなければ None。
    """
    return NEGOTIATION_PROFILES.get(img_name)


# room haggling 用 C placeholder -> Arena placeholder map
# (NEGOTBUT.IMG / TAVERN.DAT 専用)
_PLACEHOLDER_MAP = {
    "%i": "%nr",
    "%lu": "%a",
    "%u": "%a",
    "%d": "%a",
    "%mm": "%a",
}

# C placeholder の正規表現 (長いものから順にマッチ、`%lu`/`%mm` を `%l`/`%m`
# 単独より優先したいため固定 list で iterate)
_C_PH_PATTERN = re.compile(
    r"%(?:lu|mm|s|i|u|d)"  # 順序重要: 長い token を先頭に
)

# Arena placeholder の正規表現 (`%nr` / `%a`)
_ARENA_PH_PATTERN = re.compile(r"%([a-z][a-z0-9]*)\b")


def _escape_literal_flexible_ws(text: str) -> str:
    """literal 部分を escape し、空白/改行の連続は ``\\s+`` に揃える。"""
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
    """C placeholder を Arena placeholder に正規化する。

    例: `"I'll let you have the %s for only %lu gold pieces. What do you think?"`
        → `"I'll let you have the %nr for only %a gold pieces. What do you think?"`

    テンプレに含まれる `\\t` (= Arena の字下げ / 改行ヒント) は
    rendered 側では普通の空白として現れるため、半角空白に置換しておく
    (rendered との不一致対策)。
    """
    # \t を半角空白へ正規化 (rendered と整合)
    s = raw_template.replace("\t", " ")
    string_count = 0

    def _replace(m: re.Match) -> str:
        nonlocal string_count
        token = m.group(0)
        if token == "%s":
            # %s は文脈により店主名/アイテム名など別値を複数持つ。
            # 2 回目以降を別 placeholder 名へ分け、prefix match の
            # backreference 制約に巻き込まない。
            string_count += 1
            return "%nr" if string_count == 1 else f"%nr{string_count}"
        return _PLACEHOLDER_MAP.get(token, token)
    return _C_PH_PATTERN.sub(_replace, s)


def _template_to_prefix_regex(canonical: str) -> Optional[re.Pattern]:
    """正規化テンプレを prefix match 用 regex にする。

    - `%nr` / `%a` は named group (`(?P<nr>.+?)` / `(?P<a>.+?)`) として展開
    - 同じ placeholder が 2 回目以降に出る場合は backreference `(?P=nr)`
    - literal 部分は `re.escape` で escape
    - literal の連続空白は `\\s+` に変換し、rendered 側で空白数が異なる
      ケースも吸収する (chunk 結合時の空白マージに対応)。
    - `re.match` で prefix match できるように先頭 `^` のみ付ける
    """
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
    """raw を NUL 区切り printable ASCII chunk に分解し、半角空白で連結。

    chunk 結合は緩く取り (= 残骸も含めて全部結合)、本文確定は呼び出し側で
    テンプレ拘束 prefix match に任せる。

    chunk 長制約は緩く (`>= 1`) 取り、2 文字 chunk ('an' 等) も拾う。
    短文 chunk の連続でも本文をカバーできるよう max_chunks を 32 とする。
    """
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
    """指定 offset から NUL 終端 ASCII 文字列を読む。失敗時 None。"""
    try:
        buf = analyzer.read_bytes(anchor + off, max_len)
    except (OSError, AttributeError):
        return None
    nul = buf.find(b"\x00")
    end = nul if nul != -1 else len(buf)
    if end == 0:
        return None
    text = buf[:end].decode("ascii", errors="replace")
    # printable 比率 sanity check
    if not text:
        return None
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / len(text) < 0.9:
        return None
    return text


def extract_negotiation_body(template_raw: str, rendered: Optional[str]
                              ) -> Optional[str]:
    """テンプレ拘束で rendered の prefix を本文として抽出する (純関数、テスト用)。

    手順:
      1. template_raw を Arena placeholder に正規化
      2. canonical に placeholder が含まれない場合:
         - placeholder-free な静的 popup (例: "You are unsuccessful...",
           "You successfully got into a room..." 等) は rendered が
           stale でも template_raw で本文確定する。
         - rendered が template と match するなら従来通り prefix match
           hit を返し、match しなくても template_raw を返す。
      3. canonical に placeholder が含まれる場合:
         - 従来通り rendered と prefix match
         - match しなければ None (rendered の更新待ち)

    Returns:
      本文 (suffix 残骸除去済) または None
    """
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
        # placeholder-free な静的 popup template は rendered が前 popup の
        # 残骸のままでも、template_raw を本文として返す。
        return template_raw
    return None


def read_negotiation_message(analyzer: "ArenaMemoryAnalyzer",
                              anchor: int) -> Optional[str]:
    """NEGOTBUT.IMG ハッグルメッセージを取得する (テンプレ拘束 prefix match)。

      - 主信号: `+0x929E` の未置換テンプレ
      - 従信号: `+0x987A` の置換済 multi-chunk
      - テンプレ拘束 prefix match で本文確定 (suffix 残骸除去)

    どちらかの読み込みに失敗、または match miss なら None。
    fallback で「残骸込み全文」は返さない。
    """
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
    """診断ログ用に raw / canonical / rendered / matched をまとめて返す。

    Returns: (raw_template, canonical_template, rendered, matched)
    """
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
