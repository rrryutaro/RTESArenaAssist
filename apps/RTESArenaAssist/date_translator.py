"""date_translator.py — TES 暦の日付・状況テキストを和訳

ステータス表示（位置/時刻/日付/重量/健康）の各行翻訳ヘルパーを提供する。

  例（実機の 5 行表示）:
    You are in Imperial Dungeons.
    It is 12:21 in the afternoon.
    The date is Tirdas, 1st of Hearthfire in the year 3E 389
    You are currently carrying 0 kg out of 82 kg.
    You are healthy.

ステータス表示は単一経路（`poll_controller._poll_status_template_parse` が FILLED
テンプレを `template_parser.parse_filled` で構造化し、`template_parser.render_status`
が本モジュールの `_translate_status_line` へ各行翻訳を委譲）で描画される。本モジュールは
行/日付の翻訳のみを担い、バッファ読取や表示判定は行わない。

各行のパターンは将来の翻訳対象が増えた際に拡張する想定。マッチしない行は None。
"""
from __future__ import annotations
import re
from typing import Optional, Tuple

# ──────────────────────────────────────────────────────────────
# TES 暦の曜日（7 日制）
# ──────────────────────────────────────────────────────────────
# DAY_JA は i18n status_buffer_text へ移行（de-bypass）。

# ──────────────────────────────────────────────────────────────
# TES 暦の月名（12 ヶ月制、Tamriel calendar）
# ──────────────────────────────────────────────────────────────
# MONTH_JA は i18n status_buffer_text へ移行（de-bypass）。

# ERA_JA は i18n status_buffer_text へ移行（de-bypass）。

# 例: "Tirdas, 1st of Hearthfire in the year 3E 389"
DATE_PATTERN = re.compile(
    r"^\s*(\w+)\s*,\s*(\d+)(?:st|nd|rd|th)?\s+of\s+(.+?)\s+in\s+the\s+year\s+(\d+)E\s+(\d+)\s*$",
    re.IGNORECASE,
)

# ──────────────────────────────────────────────────────────────
# status バッファの列挙語（曜日/月/時間帯/健康）の表面 → 同梱訳 index。
# ──────────────────────────────────────────────────────────────
# status ポップアップを解釈するための固定語彙（上の各正規表現と同じく解析用）。
# 解決は i18n.value() を優先し、未解決時は表面→index で同梱訳キー
# status_buffer_text.<group>.<index> を direct-id 解決する（公開 v2 単独で原文アンカー
# 非依存。value() は live_surface 非有効＋原文非同梱の公開では空になるため）。
_DAY_EN = ("Sundas", "Morndas", "Tirdas", "Middas", "Turdas", "Fredas", "Loredas")
_MONTH_EN = ("Morning Star", "Sun's Dawn", "First Seed", "Rain's Hand", "Second Seed",
             "Mid Year", "Sun's Height", "Last Seed", "Hearthfire", "Frostfall",
             "Sun's Dusk", "Evening Star")
_PART_EN = ("morning", "afternoon", "evening", "night")
_HEALTH_EN = ("healthy", "diseased", "poisoned", "cursed", "blessed",
              "paralyzed", "wounded", "bleeding")


def _sbt_value(group: str, surface: str, en_list: tuple) -> Optional[str]:
    """status_buffer_text の列挙語を解決する。

    解決順: ①`i18n.value()`（dev は disk 由来 / カテゴリ有効時は live-surface で解決）→
    ②表面→index の同梱訳 direct-id（`status_buffer_text.<group>.<index>`・公開安全）。
    未知語は None。
    """
    import i18n_helper as i18n
    v = i18n.value("status_buffer_text", surface)
    if v is not None:
        return v
    try:
        idx = en_list.index(surface)
    except ValueError:
        return None
    return i18n.text_opt(f"status_buffer_text.{group}.{idx}")


def parse_and_translate(text: str) -> Optional[Tuple[str, str]]:
    """TES 形式の日付文字列を翻訳して (原文, 和訳) を返す。

    Args:
        text: 候補テキスト（NPC_DIALOG バッファから読んだ生の文字列）

    Returns:
        (原文, 和訳) のタプル。日付形式でない場合は None
    """
    if not text:
        return None
    m = DATE_PATTERN.match(text)
    if not m:
        return None

    import i18n_helper as i18n
    day_en, day_num, month_en, era_num, year_num = m.groups()
    # day_en は曜日（厳密一致）、month_en は柔軟マッチ
    day_key = day_en.strip()
    day_ja = _sbt_value("day", day_key, _DAY_EN)
    if day_ja is None:
        return None

    # 月名はそのまま辞書引きを試み、ダメなら正規化（複数空白→単一）
    month_key = re.sub(r"\s+", " ", month_en.strip())
    month_ja = _sbt_value("month", month_key, _MONTH_EN)
    if month_ja is None:
        return None

    era_ja = (i18n.value("status_buffer_text", era_num)
              or i18n.text("status_buffer_text.era_fallback").replace("{era}", era_num))

    en = text.strip()
    # 日本語表記は「年→月→日→曜日」の順序。
    ja = (i18n.text("status_buffer_text.date_format")
          .replace("{era}", era_ja).replace("{year}", year_num)
          .replace("{month}", month_ja).replace("{day}", day_num)
          .replace("{weekday}", day_ja))
    return (en, ja)


# ──────────────────────────────────────────────────────────────
# 状況テキスト（複数行）の行ごと翻訳パターン
# ──────────────────────────────────────────────────────────────
LOCATION_PATTERN    = re.compile(r"^You are in\s+(.+?)\.?\s*$")
TIME_PATTERN        = re.compile(r"^It is\s+(\d+):(\d+)\s+in the\s+(\w+)\.?\s*$")
DATE_HEADER_PATTERN = re.compile(r"^The date is\s+(.+?)\s*$")
LOAD_PATTERN        = re.compile(r"^You are currently carrying\s+([\d.]+)\s*kg\s+out of\s+([\d.]+)\s*kg\.?\s*$")
HEALTH_PATTERN      = re.compile(r"^You are\s+(\w+)\.?\s*$")

# PART_OF_DAY_JA は i18n status_buffer_text へ移行（de-bypass）。

# HEALTH_JA は i18n status_buffer_text へ移行（de-bypass）。


def _translate_status_line(line: str) -> Optional[str]:
    """ステータステキストの 1 行を和訳して返す。マッチしない場合 None。

    判定順序: 場所 → 時刻 → 日付ヘッダ → 重量 → 単独日付 → 健康（last fallback）。
    HEALTH_PATTERN は「You are X」一般形のため最後に試行する（"You are in X."
    のような他の "You are" パターンを誤って拾わないよう）。
    また NPC_DIALOG バッファには bare date 行のみが入っていた場合があるため、
    DATE_HEADER 不一致時の単独日付フォールバックを HEALTH の手前に置いて
    実質「You are X」に化けないよう順序を制御する。
    """
    import i18n_helper as i18n
    if not line:
        return None
    m = LOCATION_PATTERN.match(line)
    if m:
        loc_en = m.group(1)
        try:
            import location_lookup
            loc_ja = location_lookup.lookup(loc_en) or loc_en
        except ImportError:
            loc_ja = loc_en
        return i18n.text("status_buffer_text.line_location").replace(
            "{location}", loc_ja)
    m = TIME_PATTERN.match(line)
    if m:
        h, mn, part = m.groups()
        part_ja = _sbt_value("part", part.lower(), _PART_EN) or part
        return (i18n.text("status_buffer_text.line_time")
                .replace("{hour}", h).replace("{minute}", mn)
                .replace("{part}", part_ja))
    m = DATE_HEADER_PATTERN.match(line)
    if m:
        date_part = m.group(1).rstrip(".").strip()
        result = parse_and_translate(date_part)
        if result is not None:
            _, ja = result
            return i18n.text("status_buffer_text.line_date").replace("{date}", ja)
        return None
    m = LOAD_PATTERN.match(line)
    if m:
        cur, mx = m.groups()
        return (i18n.text("status_buffer_text.line_load")
                .replace("{current}", cur).replace("{max}", mx))
    # bare date (例: "Tirdas, 1st of Hearthfire in the year 3E 389") への
    # フォールバック。HEALTH_PATTERN より前に試行する。
    bare_date = parse_and_translate(line)
    if bare_date is not None:
        _, ja = bare_date
        return i18n.text("status_buffer_text.line_date").replace("{date}", ja)
    m = HEALTH_PATTERN.match(line)
    if m:
        state = m.group(1).lower()
        state_ja = _sbt_value("health", state, _HEALTH_EN) or state
        return i18n.text("status_buffer_text.line_state").replace("{state}", state_ja)
    return None


# ──────────────────────────────────────────────────────────────
# 簡易セルフテスト（python date_translator.py で実行）
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    samples = [
        "Tirdas, 1st of Hearthfire in the year 3E 389",
        "Loredas, 23rd of Sun's Dusk in the year 3E 401",
        "Morndas, 2nd of Rain's Hand in the year 3E 389",
        # 否定例
        "Hello world",
        "",
        "1st of Hearthfire",
    ]
    print("=== parse_and_translate (single date line) ===")
    for s in samples:
        result = parse_and_translate(s)
        print(f"  IN : {s!r}")
        print(f"  OUT: {result!r}")
    print()
    print("=== _translate_status_line (per line) ===")
    for line in (
        "You are in Imperial Dungeons.",
        "It is 12:21 in the afternoon.",
        "The date is Tirdas, 1st of Hearthfire in the year 3E 389",
        "You are currently carrying 0 kg out of 82 kg.",
        "You are healthy.",
    ):
        print(f"  {line!r} -> {_translate_status_line(line)!r}")
        print("  --- 和訳 ---")
        for line in ja.split("\n"):
            print(f"    {line}")
