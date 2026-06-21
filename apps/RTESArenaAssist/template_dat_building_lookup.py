"""template_dat_building_lookup.py — 入店メッセージのテンプレート照合・翻訳ルックアップ

template_dat_building_entry.json をバックエンドとして使用し、街中で建物に入った
直後に表示される入店メッセージ（TEMPLATE.DAT #0000-#0004 由来）を、テンプレート
照合により日本語訳して返す。

対応する建物（仕様用語）:
  - #0000: 謁見室入室メッセージ (Palace audience chamber)
  - #0001: 魔術師ギルド 入店メッセージ (Mages Guild)
  - #0002: 宿屋 入店メッセージ (Tavern / Inn)
  - #0003: 神殿 入店メッセージ (Temple)
  - #0004: 装備店 入店メッセージ (Equipment store)

API:
  lookup(text: str) -> tuple[str, dict] | None
      照合に成功した場合 (日本語訳済テキスト, メタ情報) を返す。失敗時は None。
      メタ情報には matched_key / matched_letter / placeholders が含まれる。
"""

from __future__ import annotations

import re

# (compiled_regex, ja_template, key, letter, placeholders, variant_index,
#  source_id, copy, source_hash)
_COMPILED: list[tuple[re.Pattern, str, str, str | None, list[str], int,
                      str | None, int | None, str | None]] = []
# (normalized_en, ja, key, letter, variant_index, source_id, copy, source_hash)
_LITERAL: list[tuple[str, str, str, str | None, int,
                     str | None, int | None, str | None]] = []
# source_hash -> [source_id]（全 copy 横断。同一原文が複数 copy に在る時の候補列挙用）
_HASH_TO_SIDS: dict[str, list[str]] = {}
_LOADED = False
# 完全一致失敗時の高類似度フォールバックしきい値（これ未満は別メッセージとみなす）。
_FUZZY_MIN_RATIO = 0.90
_PARTIAL_PREFIX_MIN = 80
_PARTIAL_TAIL_MIN = 24

# placeholder 名のセット。これに含まれる名前のみ regex グループ化対象。
# placeholder 体系のうち、本辞書に出現するもの。
_PLACEHOLDER_NAMES: frozenset[str] = frozenset({
    "nt", "tem", "en",
    "t", "rf", "cn", "st", "cn2", "ct",
})


def _template_to_regex(en_template: str) -> re.Pattern | None:
    """英語テンプレを照合用正規表現にコンパイルする。

    %xxx → (?P<xxx>.+?) に変換し、残りの記号をエスケープする。
    同一 placeholder の 2 回目以降は (?P=xxx) を使う。
    """
    seen: set[str] = set()
    parts: list[str] = []
    token_re = re.compile(r"%([a-z][a-z0-9]*)")
    last = 0
    for m in token_re.finditer(en_template):
        name = m.group(1)
        parts.append(re.escape(en_template[last:m.start()]))
        if name in _PLACEHOLDER_NAMES:
            if name not in seen:
                parts.append(f"(?P<{name}>.+?)")
                seen.add(name)
            else:
                parts.append(f"(?P={name})")
        else:
            parts.append(r".+?")
        last = m.end()
    parts.append(re.escape(en_template[last:]))
    full_pattern = "^" + "".join(parts) + "$"
    try:
        return re.compile(full_pattern, re.DOTALL)
    except re.error:
        return None


_CAT = "template_dat_building_entry"
_PH_RE = re.compile(r"%([a-zA-Z][a-zA-Z0-9]*)")


def _placeholders_of(en: str) -> list[str]:
    """surface から placeholder 名を出現順・重複排除で抽出（arena_regen と同規則）。"""
    seen: list[str] = []
    for m in _PH_RE.finditer(en):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def _derive_meta(source_id: str, en: str):
    """`template:<block>:<copy>:<idx>`＋surface から (key, letter, copy, idx, placeholders,
    source_hash) を導出する（v2 公開経路＝原文込み string-ID を使わない）。

    block=`key_letter`。全 576 building_entry で導出値＝旧来の格納値が完全一致する。
    """
    import i18n_source_address as sa
    parts = source_id.split(":")
    block, copy, idx = parts[1], int(parts[2]), int(parts[3])
    if "_" in block:
        key, letter = block.rsplit("_", 1)
    else:
        key, letter = block, None
    return key, letter, copy, idx, _placeholders_of(en), sa.source_hash(en)


def _iter_entries():
    """入店メッセージの (en, ja, source_id, key, letter, copy, idx, placeholders, source_hash) を
    yield する。v2 公開 runtime 有効カテゴリは source_id 経路（メタは
    source_id＋surface から導出）、未有効は従来の originals＋text(id)。en 非空のみ。
    """
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_CAT):
        for e in i18n.v2_category_entries(_CAT):
            en = e.get("original")
            sid = e.get("source_id")
            if not en or not sid:
                continue
            key, letter, copy, idx, ph, sh = _derive_meta(sid, en)
            yield en, e.get("text"), sid, key, letter, copy, idx, ph, sh
    else:
        for id_, entry in i18n.originals(_CAT).items():
            if not isinstance(entry, dict):
                continue
            en = entry.get("original", "")
            if not en:
                continue
            try:
                idx = int(id_.split(".")[-1])
            except ValueError:
                idx = 0
            yield (en, i18n.text(id_), entry.get("source_id"),
                   entry.get("key", ""), entry.get("letter"), entry.get("copy"),
                   idx, entry.get("placeholders", []) or [], entry.get("source_hash"))


def _load() -> None:
    global _COMPILED, _LITERAL, _HASH_TO_SIDS, _LOADED
    if _LOADED:
        return
    # 照合は言語中立 original で行い、表示テンプレは現在言語の訳を焼く（切替は再起動方式）。
    # 全 tileset copy（0/1/2）が候補に載るため copy 軸未確定でも全 copy を照合する。
    compiled: list = []
    literal: list = []
    hash_to_sids: dict[str, list[str]] = {}
    for en, ja, source_id, key, letter, copy, idx, ph_list, source_hash in _iter_entries():
        # hash_to_sids は ja 有無に依らず収集（同一原文の copy 横断候補列挙用）。
        if source_hash and source_id:
            hash_to_sids.setdefault(source_hash, []).append(source_id)
        if not ja:
            continue
        pattern = _template_to_regex(en)
        if pattern is None:
            continue
        compiled.append((pattern, ja, key, letter, ph_list, idx,
                         source_id, copy, source_hash))
        # placeholder の無い literal 本文は、完全一致失敗時の高類似度
        # フォールバック照合用に正規化 EN を保持する。
        if not ph_list:
            literal.append((" ".join(en.split()), ja, key, letter, idx,
                            source_id, copy, source_hash))
    for sids in hash_to_sids.values():
        sids.sort()
    _COMPILED = compiled
    _LITERAL = literal
    _HASH_TO_SIDS = hash_to_sids
    _LOADED = True


def _meta(key: str, letter: str | None, source_id: str | None,
          copy: int | None, source_hash: str | None, **extra) -> dict:
    """lookup の戻り meta を組み立てる（source_id/copy/candidates を含める）。

    source_id_candidates = 同一 source_hash を持つ全 source_id（複数 copy 横断）。
    copy 選択器が未確定の間は断定せず候補列挙にとどめる（city type 等で固定しない）。
    """
    candidates = _HASH_TO_SIDS.get(source_hash or "", [])
    meta = {
        "matched_key": key,
        "matched_letter": letter,
        "source_id": source_id,
        "copy": copy,
        "source_id_candidates": list(candidates),
        "placeholders": {},
        "placeholders_ja": {},
    }
    meta.update(extra)
    return meta


def _translate_facility(value: str, category: str) -> str:
    """施設名 placeholder (%nt / %tem / %en) を dynamic_place_lookup 経由で翻訳する。

    category を明示することで、prefix が一致しない場合の fallback (= tavern 扱い)
    を避ける。失敗時は英文を返す。
    """
    try:
        from dynamic_place_lookup import lookup as _place_lookup
    except ImportError:
        return value
    translated = _place_lookup(value, category=category)
    return translated if translated else value


def _translate_st(value: str) -> str:
    """%st (外交関係状態) を現在言語に翻訳する。未収録は英文を返す。"""
    import i18n_helper as i18n
    return i18n.value("status_terms", value.lower()) or value


def _translate_placeholder(name: str, value: str) -> str:
    """placeholder の動的翻訳。

    施設名 (%nt / %tem / %en) は dynamic_place_lookup を category 指定で
    呼び、その他 (%t / %rf / %cn / %ct / %di / %g 等) は
    npc_dialog_lookup.translate_placeholder() に委譲して既存辞書群
    (placeholder_values / titles / races / npc_name_translator 等) を活用する。

    - %cn2 は %cn と同じ意味論 (隣国名) として cn で lookup
    - %st は外交関係状態 (peace/war/truce 等) を _translate_st で
    - 未対応の placeholder は英文を返す
    """
    if not value:
        return value
    if name == "nt":
        return _translate_facility(value, category="tavern")
    if name == "tem":
        return _translate_facility(value, category="temple")
    if name == "en":
        return _translate_facility(value, category="equipment_store")
    if name == "st":
        return _translate_st(value)
    # %cn2 は意味的に %cn と同じ (隣国名)。下流の placeholder_values 経由
    # 辞書では %cn しか持たないため、ここで delegate 名を差し替える。
    delegate_name = "cn" if name == "cn2" else name
    try:
        from npc_dialog_lookup import translate_placeholder as _npc_tp
        return _npc_tp(delegate_name, value, lang="ja")
    except ImportError:
        return value


def _format_ja(ja_template: str, placeholders: dict[str, str]) -> str:
    """日本語テンプレ内の %xxx を実値で置換する。"""
    result = ja_template
    # 長い名前から置換して短い名前の prefix 競合を避ける
    for name in sorted(placeholders, key=len, reverse=True):
        value = _translate_placeholder(name, placeholders[name])
        result = result.replace(f"%{name}", value)
    return result


def _common_prefix_len(a: str, b: str) -> int:
    """2文字列の共通接頭長。"""
    limit = min(len(a), len(b))
    i = 0
    while i < limit and a[i] == b[i]:
        i += 1
    return i


def _best_contained_tail_len(needle: str, haystack: str) -> int:
    """needle のうち haystack に含まれる最長連続断片長を返す。"""
    import difflib
    if not needle or not haystack:
        return 0
    match = difflib.SequenceMatcher(None, needle, haystack).find_longest_match(
        0, len(needle), 0, len(haystack))
    return match.size


def _partial_literal_match(
    normalized: str,
) -> tuple[str, str, str | None, str | None, int | None, str | None, int, int] | None:
    """長文入店メッセージの前半+末尾断片から literal を一意照合する。

    Arena は長い入店文を複数バッファに分割し、中間行を通常の候補構築で
    拾えないことがある。全文一致/高類似度には届かないが、十分長い接頭部と
    同一テンプレ内の末尾断片が揃う場合だけ採用する。
    戻り値: (ja, key, letter, source_id, copy, source_hash, prefix_len, tail_len)。
    """
    # 最高スコアの候補群を集める。全 copy が候補になるため、同一本文が複数 copy に
    # ある（同点）のは正常。同点が「異なる訳」のときだけ真に曖昧として棄却する
    # （同一訳の copy 違いは曖昧でない・copy 共有）。
    best_score: tuple[int, int] = (0, 0)
    best_group: list = []
    for en, ja, key, letter, _idx, source_id, copy, source_hash in _LITERAL:
        prefix_len = _common_prefix_len(normalized, en)
        if prefix_len < _PARTIAL_PREFIX_MIN:
            continue
        tail = normalized[prefix_len:].strip()
        tail_len = _best_contained_tail_len(tail, en[prefix_len:])
        if tail_len < _PARTIAL_TAIL_MIN:
            continue
        score = (prefix_len, tail_len)
        cand = (ja, key, letter, source_id, copy, source_hash, prefix_len, tail_len)
        if score > best_score:
            best_score = score
            best_group = [cand]
        elif score == best_score:
            best_group.append(cand)
    if not best_group:
        return None
    # 同点が複数の (key,letter) にまたがる = 別メッセージで真に曖昧 → 棄却。
    if len({(c[1], c[2]) for c in best_group}) > 1:
        return None
    # 同一 (key,letter) の copy 違いは曖昧でない。selector 未確定の間は
    # 最小 copy を決定論的に採用し、候補は meta(source_id_candidates) に残す。
    best_group.sort(key=lambda c: (c[4] if c[4] is not None else 0))
    return best_group[0]


def lookup(text: str) -> tuple[str, dict] | None:
    """英文入店メッセージを照合し、日本語訳 + メタ情報を返す。

    Returns:
        (translated_ja, meta) where meta has:
            - matched_key: "0002" 等
            - matched_letter: "f" 等 (None の場合あり)
            - placeholders: {name: en_value} の dict
            - placeholders_ja: {name: ja_value} の dict
        None if 照合失敗
    """
    _load()
    normalized = " ".join(text.split())
    if not normalized:
        return None

    for (pattern, ja_template, key, letter, ph_list, _idx,
         source_id, copy, source_hash) in _COMPILED:
        m = pattern.match(normalized)
        if m is None:
            continue
        placeholders_en = {name: m.group(name) for name in ph_list if name in m.groupdict()}
        placeholders_ja = {
            name: _translate_placeholder(name, value)
            for name, value in placeholders_en.items()
        }
        translated = _format_ja(ja_template, placeholders_en)
        meta = _meta(key, letter, source_id, copy, source_hash)
        meta["placeholders"] = placeholders_en
        meta["placeholders_ja"] = placeholders_ja
        return translated, meta

    # 完全一致が無い場合の高類似度フォールバック（placeholder 無し literal のみ）。
    # TEMPLATE.DAT の条件付き語等で実機レンダリングが辞書本文と微差を生じても、
    # 最も近い variant を採用する。別メッセージ誤一致を避けるため高しきい値。
    import difflib
    best_ratio = 0.0
    best = None
    for en, ja, key, letter, idx, source_id, copy, source_hash in _LITERAL:
        ratio = difflib.SequenceMatcher(None, normalized, en).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = (ja, key, letter, source_id, copy, source_hash)
    if best is not None and best_ratio >= _FUZZY_MIN_RATIO:
        ja, key, letter, source_id, copy, source_hash = best
        return ja, _meta(key, letter, source_id, copy, source_hash,
                         fuzzy_ratio=round(best_ratio, 3))
    partial = _partial_literal_match(normalized)
    if partial is not None:
        ja, key, letter, source_id, copy, source_hash, prefix_len, tail_len = partial
        return ja, _meta(key, letter, source_id, copy, source_hash,
                         partial_prefix_len=prefix_len, partial_tail_len=tail_len)
    return None


def is_building_entry_message(text: str) -> bool:
    """指定テキストが建物入店メッセージにマッチするか判定する（軽量版）。"""
    return lookup(text) is not None
