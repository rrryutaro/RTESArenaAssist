"""journal_reader.py — Logbook (ジャーナル) render buffer の読み取り + 翻訳。

仕組み:
  Arena は LOGBOOK.IMG 表示時、anchor + 0x2E2BD1 (= JOURNAL_BUFFER_OFFSET)
  以降の render buffer に現在表示中の単一クエストエントリを書き込む。
  内容は日付ヘッダー (赤文字、Tirdas, ... in the year 3E NNN\r\n) +
  クエスト本文 (黒文字、You have agreed to ...) が連続して 1 つの
  ASCII 文字列として並ぶ。末尾は NUL or "*" などのカーソル記号。

本モジュールは以下を提供:
  read_journal_text(analyzer, anchor): 本文 (date_line, body_text) を返す
  translate_journal_text(date_en, body_en): (date_ja, body_ja) を返す
"""
from __future__ import annotations

from typing import Optional

from arena_bridge import (
    ArenaMemoryAnalyzer, JOURNAL_BUFFER_OFFSET, JOURNAL_BUFFER_MAXLEN,
)


def _decode_ascii_chunks(raw: bytes) -> str:
    """NUL を区切りとせず、printable ASCII chunks を改行で結合して返す。

    日付ヘッダー直後に NUL があり本文が続く構造を扱うため、
    最初の NUL で truncate せず、複数 chunk を結合する。
    各 chunk 内は printable ASCII (0x20-0x7E) + \\r \\n のみ許容。
    """
    chunks: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        # printable run を抽出
        j = i
        while j < n and (0x20 <= raw[j] <= 0x7E or raw[j] in (0x0A, 0x0D)):
            j += 1
        if j > i:
            piece = raw[i:j].decode("ascii", errors="replace")
            # 4 文字以上の意味ある chunk のみ採用 (= 単一バイトノイズを除外)
            if len(piece.strip()) >= 4:
                chunks.append(piece)
        # 非 printable / NUL を skip
        while j < n and not (0x20 <= raw[j] <= 0x7E or raw[j] in (0x0A, 0x0D)):
            j += 1
        i = j
    return "\n".join(chunks)


def read_journal_raw(analyzer: "ArenaMemoryAnalyzer",
                     anchor: int) -> Optional[str]:
    """ジャーナル render buffer から複数 printable chunk を結合して返す。

    日付ヘッダーと本文が NUL 区切りで連続格納されているケースに対応する。
    空 / 完全 bin の場合は None。
    """
    try:
        raw = analyzer.read_bytes(
            anchor + JOURNAL_BUFFER_OFFSET, JOURNAL_BUFFER_MAXLEN)
    except (OSError, AttributeError):
        return None
    text = _decode_ascii_chunks(raw)
    if not text or len(text.strip()) < 5:
        return None
    return text


_DATE_LINE_PREFIX_RE = None


def _looks_like_date_line(line: str) -> bool:
    """日付ヘッダー候補かを判定 (= 曜日カンマ + day + 月名 を含む)。"""
    import re
    return bool(re.match(r"^[A-Z][a-z]+,\s+\d+", line.strip()))


def split_journal_lines(text: str) -> tuple[Optional[str], Optional[str]]:
    """ジャーナル本文を (日付ヘッダー行, クエスト本文) に分解する。

    Arena 表示形式:
        "Tirdas, 1st of Hearthfire in the year 3E 389\\r\\n
         You have agreed to escort Carolayne's sister, Belladolda
         Hawkhart, to Conclave of Riana by Middas, 2nd of Hearthfire. *"

    NUL 区切り chunk が結合された結果も同じく改行で分かれる。
    末尾の " *" カーソル記号や前後空白は除去する。
    """
    if not text:
        return (None, None)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in normalized.split("\n") if ln.strip()]
    if not lines:
        return (None, None)

    # 日付らしい行を特定 (= 最初に "Tirdas, 1st of ..." パターン)
    date_idx = -1
    for i, ln in enumerate(lines):
        if _looks_like_date_line(ln):
            date_idx = i
            break
    if date_idx == -1:
        # 日付行が見つからない場合は先頭を日付扱い、残りを本文
        date_line = lines[0]
        body_lines = lines[1:]
    else:
        date_line = lines[date_idx]
        body_lines = lines[date_idx + 1:]

    body_text = " ".join(body_lines).strip()
    if body_text.endswith("*"):
        body_text = body_text[:-1].strip()
    return (date_line or None, body_text or None)


def translate_journal(date_en: Optional[str],
                      body_en: Optional[str],
                      lang: str = "ja"
                      ) -> tuple[Optional[str], Optional[str]]:
    """日付ヘッダー行と本文を翻訳する。

    date: npc_dialog_lookup._translate_date (フル形式) で翻訳
    body: npc_dialog_lookup.lookup でテンプレ照合 → format_japanese

    どちらも lookup miss / pattern miss の場合は原文を返す。
    """
    import npc_dialog_lookup as ndl

    date_ja: Optional[str] = None
    body_ja: Optional[str] = None

    if date_en:
        try:
            date_ja = ndl._translate_date(date_en, lang)
        except Exception:  # noqa: BLE001
            date_ja = date_en

    if body_en:
        try:
            result = ndl.lookup(body_en)
            if result:
                ja_tmpl, ph = result
                body_ja = ndl.format_japanese(ja_tmpl, ph, lang)
            else:
                body_ja = None  # 辞書未登録
        except Exception:  # noqa: BLE001
            body_ja = None

    return (date_ja, body_ja)


__all__ = [
    "read_journal_raw",
    "split_journal_lines",
    "translate_journal",
]
