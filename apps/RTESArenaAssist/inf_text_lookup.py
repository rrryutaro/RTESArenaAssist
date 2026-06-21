"""
inf_text_lookup.py  —  INF @TEXT 翻訳テーブル ルックアップモジュール

データソースは i18n 統一構造（`i18n/_original/inf_text.json` ＋ `<lang>/inf_text.json`）。
エントリ本体（原文・type・question/correct/wrong 等の EN アンカー）は `_original` から、
訳は現在言語レイヤ（`i18n_helper.lang_only`）から解決する。riddle は
`<base>.question/.correct/.wrong` の 3 id を束ねて `{question,correct,wrong}` を復元する。
display（補足付き訳）は `<base>.display` id を参照する。
"""

from __future__ import annotations

import re

import i18n_helper as i18n

_CATEGORY = "inf_text"

# bundle kind が運ぶ構造 type（label=type 無し＝None）。
_KIND_TYPES = frozenset({"key", "lore", "riddle", "lore_once", "key_lore"})

# 構造 source_id `inf:<inf>:text:<idx>`（riddle field 無し）から (inf,idx) を復元する。
# localpack rich を持たない entry（Assist 作 chargen UI 等）を公開 bundle の id 単位
# 訳で解決するための fallback。:question 等の field 付き riddle source_id は除外し、
# rich 経路に委ねる。
_INF_STRUCT_SID_RE = re.compile(r"^inf:([^:]+):text:(\d+)$")


def _parse_inf_struct_sid(sid: str | None) -> tuple[str, int] | None:
    if not sid:
        return None
    m = _INF_STRUCT_SID_RE.match(sid)
    if not m:
        return None
    return (m.group(1), int(m.group(2)))

# (inf_upper, idx) → entry（_original 由来 ＋ "_id"=その id）。lazy 構築。
_index: dict[tuple[str, int], dict] = {}
_loaded = False


def _load_v2() -> dict[tuple[str, int], dict]:
    """公開 v2 runtime から (inf,idx)→entry を構築する（legacy_id_map 非依存）。

    entry 構造キー/表示変種/riddle 候補本文は localpack rich メタ（user-env 限定）から、type は
    bundle kind から、訳は source_id 経路（get_translation 内で解決）。rich を持つ entry のみ
    _index 対象（field sub／.display／source_id 無は rich 無で自然除外）。
    """
    idx: dict[tuple[str, int], dict] = {}
    for e in i18n.v2_category_entries(_CATEGORY):
        sid = e.get("source_id")
        rich = e.get("rich")
        if isinstance(rich, dict) and rich.get("inf") is not None \
                and rich.get("idx") is not None:
            inf = rich.get("inf")
            ridx = rich.get("idx")
            entry = dict(rich)
        else:
            # rich 無し（localpack 未収録＝Assist 作 chargen UI 等）。構造 source_id
            # から (inf,idx) を復元し、訳は id 単位（text_by_source_id・公開 bundle）で
            # 解決する。localpack 非依存の公開経路。
            parsed = _parse_inf_struct_sid(sid)
            if parsed is None:
                continue
            inf, ridx = parsed
            entry = {"inf": inf, "idx": ridx}
            # 原文（_original＝Arena 実テキスト）は localpack の original surface から取る。
            # 翻訳言語の英語（i18n/en）と混同しない。surface 未収録（localpack 未再生成）の
            # entry は原文無しのままとし、表示の原文側はライブ本文／rich(text_display)に委ねる
            # （rich を持つ entry は上の分岐で text_display を保持する）。
            orig = e.get("original")
            if orig:
                entry["text"] = orig
                entry["text_panel"] = orig
                entry["text_display"] = orig
        kind = e.get("kind")
        entry["type"] = kind if kind in _KIND_TYPES else None
        entry["_sid"] = sid
        entry["_v2"] = True
        idx[(str(inf).upper(), int(ridx))] = entry
    return idx


def _base_of(entry_id: str) -> str:
    """id 末尾の surface（`.0`）を落とした base id を返す。"""
    head, _, _ = entry_id.rpartition(".")
    return head or entry_id


def load(path: str | None = None) -> None:
    """i18n 構造からメモリキャッシュ（(inf,idx)→entry）を構築する。

    ``path`` は後方互換のため受け取るが未使用（データソースは i18n 構造に一本化）。
    """
    global _index, _loaded
    if i18n.v2_public_enabled(_CATEGORY):
        try:
            _index = _load_v2()
            _loaded = True
        except (KeyError, ValueError, TypeError):
            _loaded = False
        return
    _index = {}
    try:
        for entry_id, e in i18n.originals(_CATEGORY).items():
            if not isinstance(e, dict):
                continue
            inf = e.get("inf")
            idx = e.get("idx")
            if inf is None or idx is None:
                continue
            entry = dict(e)
            entry["_id"] = entry_id
            _index[(str(inf).upper(), int(idx))] = entry
        _loaded = True
    except (KeyError, ValueError, TypeError):
        _loaded = False
    # 公開（frozen）: _original 非同梱で originals は空。inf_text は安全 enable-set
    # 外（部分カバレッジのため value-safe に含めない）だが、v2 公開 runtime が
    # ロード済なら source_id 経路（localpack rich-meta・public-safe）で索引できる。
    # enable-set 非依存で公開安全経路を使う consumer 是正（ASK ABOUT/ステータス
    # 表示と同型）。これがないと chargen / ダンジョン INF が公開で全て未訳になる。
    if not _index and i18n.v2_public_enabled(None):
        try:
            _index = _load_v2()
            _loaded = True
        except (KeyError, ValueError, TypeError):
            pass


def _ensure_loaded() -> None:
    if not _loaded:
        load()


def lookup(inf_name: str, text_index: int) -> dict | None:
    """(INFファイル名, テキストインデックス) で完全一致検索。"""
    _ensure_loaded()
    return _index.get((inf_name.upper(), text_index))


def lookup_by_text(inf_name: str, body: str, max_prefix: int = 50) -> dict | None:
    """
    テキスト内容の前方一致でエントリを検索する（フォールバック用）。
    TRIGGER_BLOCK は改行を空白に変換するため、比較前に正規化する。

    比較長は candidate（``text`` フィールド）の実文字数を使う。
    これにより、同じ 50 文字前方一致を持つ複数エントリ
    （例: クラスアドバイスの Mage / Healer は属性フレーズ "intelligent and willful" を共有）を、
    クラス名部分まで含めた全文で一意に区別できる。

    ``max_prefix`` は仕様書で「``text`` フィールドの推奨格納長（先頭50文字）」を指す参考値。
    現在のロジックでは比較に直接は使わない（candidate の長さがそのまま比較長になる）。
    """
    _ensure_loaded()
    if not body:
        return None

    def _norm(s: str) -> str:
        return s.replace("\r", " ").replace("\n", " ").strip()

    body_norm = _norm(body)
    inf_upper = inf_name.upper()
    for (inf, _idx), e in _index.items():
        # inf_name が空のとき（INFファイル不明）は全エントリを対象に検索
        if inf_upper and inf != inf_upper:
            continue
        candidate = e.get("text") or e.get("question") or ""
        cand_norm = _norm(candidate)
        if not cand_norm:
            continue
        if body_norm[:len(cand_norm)].upper() == cand_norm.upper():
            return e
    return None


def lookup_by_substring(inf_name: str, body: str,
                        min_fragment_len: int = 16) -> dict | None:
    """body が候補エントリ本文の **substring** として現れるエントリを返す。

    トリガー本文が live buffer の都合で複数行のうち最終行断片だけしか
    観測できない場合のフォールバック。lookup_by_text の前方一致では
    途中行をマッチできないため、本関数で「候補本文の中に body が
    部分一致する」エントリを探す。

    制約:
    - inf_name で候補を絞ること (空 inf_name は全エントリ対象だが
      誤爆リスクが高いため、呼出側で必要に応じて inf_name を指定する)。
    - body が空白除去後 ``min_fragment_len`` 文字未満の場合は None
      (短い fragment は複数エントリと一致しやすく誤爆するため)。
    - 候補が複数見つかった場合は None を返す
      (どのエントリと結びつくか確定できないため安全側に倒す)。
    """
    _ensure_loaded()
    if not body:
        return None

    def _norm(s: str) -> str:
        return s.replace("\r", " ").replace("\n", " ").strip()

    body_norm = _norm(body)
    if len(body_norm) < min_fragment_len:
        return None
    body_upper = body_norm.upper()
    inf_upper = inf_name.upper()
    matches: list[dict] = []
    for (inf, _idx), e in _index.items():
        if inf_upper and inf != inf_upper:
            continue
        candidate = e.get("text") or e.get("question") or ""
        cand_norm = _norm(candidate)
        if not cand_norm:
            continue
        if body_upper in cand_norm.upper():
            matches.append(e)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


def get_translation(entry: dict, lang: str = "ja") -> str | dict | None:
    """
    エントリから翻訳テキストを返す（現在言語レイヤ・原文フォールバックなし）。

    - lore / lore_once / key_lore: 文字列（未翻訳は空文字）
    - riddle: {"question": ..., "correct": ..., "wrong": ...}（規則b・3 id を束ねる）
    - key: None（翻訳なし）

    ``lang`` は後方互換のため残すが、表示言語は i18n の現在言語で解決する
    （言語切替は再起動方式・単一住所）。
    """
    if entry is None:
        return None
    if entry.get("type") == "key":
        return None
    if entry.get("_v2"):
        sid = entry.get("_sid") or ""
        if entry.get("type") == "riddle":
            return {
                fld: (i18n.text_by_source_id(f"{sid}:{fld}", category=_CATEGORY) or "")
                for fld in ("question", "correct", "wrong")
            }
        return i18n.text_by_source_id(sid, category=_CATEGORY) or ""
    base = _base_of(entry.get("_id", ""))
    if entry.get("type") == "riddle":
        return {
            fld: (i18n.lang_only(f"{base}.{fld}") or "")
            for fld in ("question", "correct", "wrong")
        }
    return i18n.lang_only(entry.get("_id", "")) or ""


def get_translation_display(entry: dict, lang: str = "ja") -> str | None:
    """
    エントリから補足説明付き翻訳テキストを返す（二段スキーマ）。

    優先順（タブ JA フォールバック）:
    1. display id（``<base>.display``）が現在言語に存在 → それを返す
    2. 基本翻訳（``<id>``）が現在言語に存在 → fallback として返す
    3. いずれもなし → None

    riddle / key 等の特殊 type は基本翻訳と同じ扱い（None）。
    """
    if entry is None:
        return None
    if entry.get("type") in ("key", "riddle"):
        return None
    if entry.get("_v2"):
        sid = entry.get("_sid") or ""
        val = i18n.text_by_source_id(f"{sid}:display", category=_CATEGORY)
        if val:
            return val
        return i18n.text_by_source_id(sid, category=_CATEGORY)
    base = _base_of(entry.get("_id", ""))
    val = i18n.lang_only(f"{base}.display")
    if val:
        return val
    # フォールバック: 基本翻訳
    return i18n.lang_only(entry.get("_id", ""))


def get_text_panel(entry: dict) -> str:
    """
    エントリから翻訳パネル EN 側の表示テキストを返す。

    フォールバック規則:
    1. text_panel が存在 → それを返す
    2. text_display が存在 → fallback として返す
    3. text → 最終フォールバック
    """
    if entry is None:
        return ""
    return (entry.get("text_panel")
            or entry.get("text_display")
            or entry.get("text", ""))


def get_text_display(entry: dict) -> str:
    """
    エントリから翻訳タブ EN 側の表示テキストを返す。

    フォールバック規則:
    1. text_display が存在 → それを返す
    2. text_panel が存在 → fallback として返す
    3. text → 最終フォールバック
    """
    if entry is None:
        return ""
    return (entry.get("text_display")
            or entry.get("text_panel")
            or entry.get("text", ""))


def all_entries_for_inf(inf_name: str) -> list[dict]:
    """指定 INF ファイルのエントリを idx 順で返す。"""
    _ensure_loaded()
    inf_upper = inf_name.upper()
    result = [e for (inf, _), e in _index.items() if inf == inf_upper]
    return sorted(result, key=lambda e: e["idx"])


def all_inf_names() -> list[str]:
    """DBに含まれる INF ファイル名一覧（大文字・ソート済み）。"""
    _ensure_loaded()
    seen: set[str] = set()
    names = []
    for (inf, _) in _index:
        if inf not in seen:
            seen.add(inf)
            names.append(inf)
    return sorted(names)
