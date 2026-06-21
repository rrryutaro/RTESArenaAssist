"""POPUP11.IMG NPC 応答テキスト候補の読み取りと選択。

ASK ABOUT? 系の応答テキストは Arena 内部の複数バッファに書かれる:
  - anchor + 0x929E (NPC 会話と同バッファ、Where is... 直接応答 等)
  - anchor + 0x1044 (旧来の NPC dialog buffer)
  - anchor + 0x9A9E (message_buf、詳細場所一覧経由の応答時にも出現)

本モジュールは 3 候補を全て読み、`npc_dialog_lookup.lookup()` がヒットする
候補を最優先で返す。lookup ヒットしない場合は、printable ASCII で長さ最大の
ものを fallback として返す。
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

_log = logging.getLogger(__name__)

# 応答候補の読取オフセット（優先順位は読取順に依存しない。lookup ヒットで選ぶ）
RESPONSE_OFFSETS: tuple[int, ...] = (0x929E, 0x1044, 0x9A9E)
RESPONSE_READ_LEN = 512
MIN_RESPONSE_LEN = 5
RESPONSE_SCAN_START = 0x1044
RESPONSE_SCAN_LEN = 0x300
RESPONSE_SCAN_WINDOW = 220

# 現在表示中テキストへの anchor 相対 pointer 候補。
# 上位バイト (= +0xA845) は既存の npc_phase と同一値。下位バイトまで読むと
# 0x1044 / 0x9A9E のどちらを画面が指しているかを判定できる。
CURRENT_TEXT_PTR_OFFSET = 0xA844
_EMBEDDED_RESPONSE_MARKERS: tuple[str, ...] = (
    "Fixing that ",
    "Sure I could fix that ",
    "Fine. I can get it done in ",
    "Fine, I'll charge you ",
    "I can cut down the time",
    "I can cut the cost",
    "Then I'll get started",
    "Good, I'll get to it",
    "I understand. You might consider",
    "Well, if you change your mind",
)
_EMBEDDED_RESPONSE_TERMINATORS: tuple[str, ...] = (
    "Sound fair?",
    "get started?",
    "Is that okay?",
    "How many days can you wait?",
    "How much gold do you want to spend?",
    "right away...",
    "as soon as I can.",
    "very fair prices...",
    "I'll be here.",
)
_RAW_C_PLACEHOLDER_RE = re.compile(r"%(?:lu|ld|u|d|s|mm|i|t|a)\b")


class ResponseCandidate(NamedTuple):
    text: str
    lookup_hit: bool
    source_offset: int


def read_current_text_pointer(analyzer, anchor: int) -> int | None:
    """現在表示中テキストへの anchor 相対 pointer 候補を読む。

    ASK ABOUT? 判定で使っている `anchor + 0xA844` u16 LE。
    上位バイトは既存の `+0xA845` phase と同じ値になる。
    """
    try:
        raw = analyzer.read_bytes(anchor + CURRENT_TEXT_PTR_OFFSET, 2)
    except (OSError, AttributeError):
        return None
    if len(raw) < 2:
        return None
    return raw[0] | (raw[1] << 8)


def candidate_contains_pointer(candidate: ResponseCandidate,
                               ptr: int | None) -> bool:
    """pointer が candidate の source_offset から RESPONSE_READ_LEN 以内かを判定。"""
    if ptr is None:
        return False
    return (candidate.source_offset <= ptr
            < candidate.source_offset + RESPONSE_READ_LEN)


def _read_one(analyzer, anchor: int, offset: int) -> str:
    try:
        raw = analyzer.read_bytes(anchor + offset, RESPONSE_READ_LEN)
    except (OSError, AttributeError):
        return ""
    if not raw:
        return ""
    # 先頭の非 ASCII バイト（ポインタ等）をスキップして本文を抽出
    start = 0
    while start < len(raw) and not (0x20 <= raw[start] <= 0x7E):
        start += 1
    if start >= len(raw):
        return ""
    nul = raw.find(b"\x00", start)
    end = nul if nul != -1 else len(raw)
    text = raw[start:end].decode("ascii", errors="replace").strip()
    if len(text) < MIN_RESPONSE_LEN:
        return ""
    # printable 比率が低いものは破棄（ポインタ混在領域の誤読対策）
    printable = sum(1 for c in text if 0x20 <= ord(c) <= 0x7E)
    if printable / max(len(text), 1) < 0.85:
        return ""
    return text


def _lookup_embedded_response(text: str, ndl) -> str | None:
    """ステータス文字列の後ろに埋もれた応答本文を辞書 hit で切り出す。

    武具店 Repair の費用確認では `Gold left : N` 系の共有ステータス表示と
    修理見積もり本文が同じ +0x1044 に残り、先頭から読むと辞書 miss になる。
    既知の応答開始 marker 以降だけを候補化し、辞書 hit したものだけ採用する。
    """
    if not text or ndl is None:
        return None
    for marker in _EMBEDDED_RESPONSE_MARKERS:
        start = text.find(marker)
        if start <= 0:
            continue
        candidate = text[start:].strip()
        try:
            if ndl.lookup(candidate) is not None:
                return candidate
        except Exception:
            continue
    return None


def _has_unrendered_c_placeholder(text: str) -> bool:
    """C printf placeholder が未置換の raw template 候補かを判定する。"""
    return bool(_RAW_C_PLACEHOLDER_RE.search(text or ""))


def _normalize_printable_window(raw: bytes) -> str:
    """制御バイトで分割された描画済み文を lookup 用の 1 行に正規化する。"""
    chars = [chr(b) if 0x20 <= b <= 0x7E else " " for b in raw]
    return " ".join("".join(chars).split())


def _trim_embedded_response(text: str) -> str:
    """既知の終端句までを応答本文として切り出す。"""
    best_end: int | None = None
    for terminator in _EMBEDDED_RESPONSE_TERMINATORS:
        pos = text.find(terminator)
        if pos == -1:
            continue
        end = pos + len(terminator)
        if best_end is None or end < best_end:
            best_end = end
    if best_end is not None:
        return text[:best_end].strip()
    return text.strip()


def _scan_embedded_response_region(analyzer, anchor: int, ndl
                                   ) -> list[ResponseCandidate]:
    """+0x1044 周辺に後置される描画済み応答本文を辞書 hit で拾う。

    Repair 見積もりは raw template が +0x1044 に残る一方、
    描画済み本文が同じ応答領域の後方(+0x1116 付近)へ書かれることがある。
    さらに金額と "gold" の間に NUL/制御バイトが挟まるため `_read_one` では
    文が途中で切れる。既知 marker から短い window を読み、制御バイトを
    空白として再連結したうえで辞書 hit した候補だけ採用する。
    """
    if ndl is None:
        return []
    try:
        raw = analyzer.read_bytes(anchor + RESPONSE_SCAN_START,
                                  RESPONSE_SCAN_LEN)
    except (OSError, AttributeError):
        return []
    if not raw:
        return []

    candidates: list[ResponseCandidate] = []
    seen: set[tuple[int, str]] = set()
    for marker in _EMBEDDED_RESPONSE_MARKERS:
        marker_b = marker.encode("ascii", errors="ignore")
        pos = raw.find(marker_b)
        while pos != -1:
            window = raw[pos:pos + RESPONSE_SCAN_WINDOW]
            text = _trim_embedded_response(
                _normalize_printable_window(window))
            if text and not _has_unrendered_c_placeholder(text):
                try:
                    hit = ndl.lookup(text) is not None
                except Exception:
                    hit = False
                if hit:
                    source_offset = RESPONSE_SCAN_START + pos
                    key = (source_offset, text)
                    if key not in seen:
                        candidates.append(ResponseCandidate(
                            text=text,
                            lookup_hit=True,
                            source_offset=source_offset,
                        ))
                        seen.add(key)
            pos = raw.find(marker_b, pos + 1)
    return candidates


def read_response_candidates_all(analyzer, anchor: int
                                  ) -> list[ResponseCandidate]:
    """全 RESPONSE_OFFSETS から候補を読み、リストで返す。

    呼び出し側で「prev と異なる candidate を優先」など制御するために
    全候補を返す。read_response_candidate は本関数の薄いラッパー。
    """
    try:
        import npc_dialog_lookup as ndl
    except ImportError:
        ndl = None

    candidates: list[ResponseCandidate] = []
    for off in RESPONSE_OFFSETS:
        text = _read_one(analyzer, anchor, off)
        if not text:
            continue
        hit = False
        if ndl is not None and not _has_unrendered_c_placeholder(text):
            try:
                hit = ndl.lookup(text) is not None
            except Exception:
                hit = False
            if not hit:
                embedded = _lookup_embedded_response(text, ndl)
                if embedded:
                    text = embedded
                    hit = True
        candidates.append(ResponseCandidate(
            text=text, lookup_hit=hit, source_offset=off))

    seen_candidates = {(c.source_offset, c.text) for c in candidates}
    for scanned in _scan_embedded_response_region(analyzer, anchor, ndl):
        key = (scanned.source_offset, scanned.text)
        if key in seen_candidates:
            continue
        candidates.append(scanned)
        seen_candidates.add(key)
    return candidates


def read_response_candidate(analyzer, anchor: int) -> ResponseCandidate | None:
    """応答候補を読み、最良のものを返す。

    判定優先順位:
      1. `npc_dialog_lookup.lookup()` がヒットする候補（複数あれば先頭オフセット優先）
      2. lookup ヒットしないが MIN_RESPONSE_LEN 以上の printable text のうち長さ最大
      3. なし → None
    """
    candidates = read_response_candidates_all(analyzer, anchor)
    if not candidates:
        return None

    hits = [c for c in candidates if c.lookup_hit]
    if hits:
        return hits[0]

    # フォールバック: 最長候補
    return max(candidates, key=lambda c: len(c.text))
