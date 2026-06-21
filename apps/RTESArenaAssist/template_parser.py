"""template_parser.py — printf テンプレート + filled ペアによる状態抽出（試験的）

EXE 静的データ領域内に存在する printf 形式の status template と、その filled 版
（icon4 クリック等で書き換わる動的バッファ）から、可変部分を抽出して和訳する。

  TEMPLATE 内容:
    "You are in %s.\\rIt is %s.\\rThe date is %s"
    "You are currently carrying %d kg out of %d kg.\\r"

  FILLED 例:
    "You are in Imperial Dungeons.\\r"
    "It is 12:09 in the afternoon.\\r"
    "The date is Tirdas, 1st of Hearthfire in the year 3E 389\\r"
    "You are currently carrying 0 kg out of 82 kg.\\r"
    "You are healthy.\\r"

アドレス解決の優先順位（自動スキャン）:
  1. 接続中キャッシュ（_TEMPLATE_ADDR_CACHE）が有効ならそれを使用
  2. anchor + TEMPLATE_ANCHOR_DELTA (0x5B7B) を試行（高速パス）
  3. 失敗時は指定範囲をスキャンして TEMPLATE を探索しキャッシュに保存

FILLED の TEMPLATE からの固定 delta = FILLED_DELTA (0x38A3) は不変。
"""
from __future__ import annotations
import re
from typing import Optional, Dict, Tuple

# フォールバック絶対アドレス（観測値）
TEMPLATE_ADDR = 0x10700FCB
FILLED_ADDR   = 0x1070486E

# anchor 相対 delta（観測で確認済み）
TEMPLATE_ANCHOR_DELTA = 0x5B7B
FILLED_ANCHOR_DELTA   = 0x941E

# TEMPLATE → FILLED の固定 delta
FILLED_DELTA = 0x38A3  # FILLED_ADDR - TEMPLATE_ADDR

# テンプレート存在確認用 prefix
EXPECTED_TEMPLATE_PREFIX = b"You are in %s."

# 接続中アドレスキャッシュ
_TEMPLATE_ADDR_CACHE: Optional[int] = None
_FILLED_ADDR_CACHE:   Optional[int] = None

# テンプレート由来のパース正規表現
STATUS_PATTERN = re.compile(
    r"You are in (?P<location>.+?)\.\r"
    r"It is (?P<time>.+?)\.\r"
    r"The date is (?P<date>.+?)\r"
    r"You are currently carrying (?P<weight>\d+) kg out of (?P<weight_max>\d+) kg\.\r"
    r"(?:You are (?P<health>.+?)\.\r)?"
)

# スキャン設定
_SCAN_BELOW = 0x400000   # anchor から下方向にスキャンする最大バイト数
_SCAN_ABOVE = 0x600000   # anchor から上方向にスキャンする最大バイト数
_SCAN_CHUNK = 0x10000


def _read_string(analyzer, addr: int, length: int = 512) -> str:
    """指定アドレスから length バイト読んで \\x00 まで切り詰めた ASCII を返す。"""
    if analyzer is None:
        return ""
    try:
        b = analyzer.read_bytes(addr, length)
    except (OSError, AttributeError):
        return ""
    if b"\x00" in b:
        b = b[: b.index(b"\x00")]
    return b.decode("ascii", errors="replace")


def _check_addr(analyzer, template_addr: int) -> bool:
    """指定アドレスに EXPECTED_TEMPLATE_PREFIX が存在するか確認する。"""
    try:
        prefix = analyzer.read_bytes(template_addr, len(EXPECTED_TEMPLATE_PREFIX))
        return prefix == EXPECTED_TEMPLATE_PREFIX
    except (OSError, AttributeError):
        return False


def _scan_for_template(analyzer, anchor: int) -> Optional[Tuple[int, int]]:
    """TEMPLATE 文字列をメモリスキャンして (template_addr, filled_addr) を返す。

    anchor の前後 _SCAN_BELOW / _SCAN_ABOVE バイトを _SCAN_CHUNK 単位でスキャン。
    """
    target = EXPECTED_TEMPLATE_PREFIX
    scan_start = max(0x10000000, anchor - _SCAN_BELOW)
    scan_end   = anchor + _SCAN_ABOVE
    addr = scan_start
    while addr < scan_end:
        try:
            data = analyzer.read_bytes(addr, _SCAN_CHUNK)
            idx = data.find(target)
            if idx >= 0:
                t_addr = addr + idx
                f_addr = t_addr + FILLED_DELTA
                return (t_addr, f_addr)
        except (OSError, AttributeError):
            pass
        addr += _SCAN_CHUNK
    return None


def _resolve_addrs(analyzer, anchor: Optional[int]) -> Optional[Tuple[int, int]]:
    """TEMPLATE / FILLED アドレスを解決して返す。失敗時は None。

    優先順位:
      1. 接続中キャッシュ（有効な場合）
      2. anchor + TEMPLATE_ANCHOR_DELTA（高速パス）
      3. フォールバック絶対アドレス（後方互換）
      4. 全域スキャン（キャッシュに保存）
    """
    global _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE

    # 1. キャッシュ確認
    if _TEMPLATE_ADDR_CACHE is not None:
        if _check_addr(analyzer, _TEMPLATE_ADDR_CACHE):
            return (_TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE)
        # キャッシュが無効になっていたらクリア
        _TEMPLATE_ADDR_CACHE = None
        _FILLED_ADDR_CACHE   = None

    # 2. anchor 相対 delta（高速パス）
    if anchor is not None:
        t_addr = anchor + TEMPLATE_ANCHOR_DELTA
        if _check_addr(analyzer, t_addr):
            _TEMPLATE_ADDR_CACHE = t_addr
            _FILLED_ADDR_CACHE   = t_addr + FILLED_DELTA
            return (_TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE)

    # 3. フォールバック絶対アドレス
    if _check_addr(analyzer, TEMPLATE_ADDR):
        _TEMPLATE_ADDR_CACHE = TEMPLATE_ADDR
        _FILLED_ADDR_CACHE   = FILLED_ADDR
        return (TEMPLATE_ADDR, FILLED_ADDR)

    # 4. フルスキャン（anchor が必要）
    if anchor is None:
        return None
    result = _scan_for_template(analyzer, anchor)
    if result is None:
        return None
    _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE = result
    return result


def parse_filled(analyzer, anchor: int = None) -> Optional[Dict[str, str]]:
    """FILLED バッファを読んで status template に合致すれば dict を返す。

    Args:
        analyzer: アタッチ済み memory analyzer
        anchor:   スキャン時に使用。None でも高速パス・フォールバックを試行
    """
    if analyzer is None:
        return None

    addrs = _resolve_addrs(analyzer, anchor)
    if addrs is None:
        return None

    _, filled_addr = addrs
    text = _read_string(analyzer, filled_addr, 512)
    if not text:
        return None
    m = STATUS_PATTERN.search(text)
    if m is None:
        return None
    parsed = {k: (v if v is not None else "") for k, v in m.groupdict().items()}
    return parsed


def reset_cache() -> None:
    """プロセス切断・再接続時にアドレスキャッシュをクリアする。"""
    global _TEMPLATE_ADDR_CACHE, _FILLED_ADDR_CACHE
    _TEMPLATE_ADDR_CACHE = None
    _FILLED_ADDR_CACHE   = None


def render_status(parsed: Dict[str, str]) -> Tuple[str, str, str]:
    """parsed dict（location/time/date/weight/health）から (原文, 和訳, サマリ) を生成する。

    各行の翻訳は `date_translator._translate_status_line`（status_buffer_text 辞書解決・
    公開 v2 単独で direct-id 解決）へ委譲し、status バッファ経路と単一の解決経路を共有する。
    サマリは表示撤去済み（呼び出し側で破棄）のため空文字を返す。
    """
    from date_translator import _translate_status_line

    location   = parsed.get("location", "")
    time_str   = parsed.get("time", "")
    date_str   = parsed.get("date", "")
    weight     = parsed.get("weight", "")
    weight_max = parsed.get("weight_max", "")
    health     = parsed.get("health", "")

    en_lines: list = []
    ja_lines: list = []

    def _add(en: str) -> None:
        ja = _translate_status_line(en)
        en_lines.append(en)
        ja_lines.append(ja if ja is not None else en)

    if location:
        _add(f"You are in {location}.")
    if time_str:
        _add(f"It is {time_str}.")
    if date_str:
        _add(f"The date is {date_str}")
    if weight and weight_max:
        _add(f"You are currently carrying {weight} kg out of {weight_max} kg.")
    if health:
        _add(f"You are {health}.")

    return ("\n".join(en_lines), "\n".join(ja_lines), "")
