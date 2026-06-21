"""
npc_dialog_lookup.py — NPC会話テンプレート照合・翻訳ルックアップ

npc_dialog.json をバックエンドとして使用し、街中 NPC の ASK ABOUT ダイアログを
テンプレートと照合して日本語翻訳を返す。

API:
  lookup(text: str) -> tuple[str, dict] | None
  format_japanese(ja_template: str, placeholders: dict) -> str
  translate_placeholder(name: str, value: str, lang: str) -> str
"""

from __future__ import annotations

import json
import re

from npc_name_translator import translate_generated_name

# キャッシュ: list of (regex, ja_template, placeholder_count, is_exact, literal_chars)
# literal_chars = en テンプレから placeholder を除いた文字数 (汎用テンプレの
# 過剰マッチを回避するため)
_COMPILED: list[tuple[re.Pattern, str, int, bool, int]] = []
_LOADED = False

# 閉集合 (網羅的に語彙が確定している) placeholder の照合用選択肢。
# placeholder_values.json の `_meta.closed == true` かつ values を持つ
# placeholder のみ対象。{name: "northeast|northwest|...|west"} (最長一致順)。
# これらは `_template_to_regex` で `.+?` ではなく選択肢としてアンカーされ、
# 直前の多語 placeholder (例: 酒場名 %nt = "Blue Giants") を正しく取らせる。
# 照合は英語原文に対して行うため (出力言語に非依存)、多言語で一様に機能する。
_CLOSED_PH_ALT: dict[str, str] = {}
_CLOSED_PH_LOADED = False
# 旧 placeholder_values の _meta.closed==true だった placeholder 名（網羅的語彙）。
# 旧データでは %di（方角）のみ。新構造は placeholder 単位 _meta を持たないため定数化。
_CLOSED_PLACEHOLDERS: frozenset[str] = frozenset({"di"})

# placeholder_values は id が `placeholder_values.%<name>.<slug(en)>.0`（surface 全件 0）。
# 公開版は原文を同梱しないため `_PH_VALUES`（原文逆引き）が空になる。ライブ値から
# スラッグを作り placeholder_values 自身の**公開済み訳を direct-id 解決**すれば
# 公開版でも解決できる（location_lookup._slug と同等の正規化）。slug 導出可能な subgroup のみ対象。
_PH_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PH_DIRECT_ID_NAMES: frozenset[str] = frozenset({"cn", "lp", "ct", "oc", "t", "di",
                                                 "g", "g2", "g3"})

# placeholder_values の値翻訳 subgroup（v2 mixed-mode resolver の対象）。
# %r（relations）は別カテゴリ（既存 value_in("relations") 経路を維持）。%g/%g2/%g3 は同 surface が
# 文法格で別訳（her は %g2「彼女を」/%g3「彼女の」・it も同様＝訳違い重複）のため section(subgroup) 込みで
# 解決する（本集合には入れず translate_placeholder で section 指定）。
_PV_VALUE_SUBGROUPS: frozenset[str] = frozenset({"ra", "t", "oc", "ct", "oth", "di",
                                                 "lp", "cn", "tem"})


def _ph_slug(en: str) -> str:
    """placeholder_values の app_id スラッグへ決定論変換（location_lookup._slug と同等）。"""
    s = en.strip().lower().replace("'", "")
    return _PH_SLUG_NON_ALNUM.sub("_", s).strip("_")


def _ph_direct_id(name: str, value: str) -> str | None:
    """`placeholder_values.%<name>.<slug(value)>.0` を direct-id 解決する（原文非依存）。

    公開版でも同梱の `placeholder_values` から訳が出る。未登録は None
    （現在言語→fallback 連鎖→原文 で解決・公開版は原文非同梱のため未登録=None）。
    """
    import i18n_helper as i18n
    return i18n.text_opt(f"placeholder_values.%{name}.{_ph_slug(value)}.0")


def _load_closed_ph() -> None:
    """placeholder_values.json から閉集合 placeholder の選択肢を構築する。

    `_meta.closed == true` のものだけを対象とし、`values[].key.en` を
    最長一致順 (長い語を先頭) に並べて `|` 連結する。網羅的でない (= リストに
    無い実値が来る可能性がある) placeholder をアンカーするとマッチ全失敗
    (無翻訳) になるため、明示フラグ付きのみを安全に対象とする。
    """
    global _CLOSED_PH_LOADED
    if _CLOSED_PH_LOADED:
        return
    _CLOSED_PH_LOADED = True
    import i18n_helper as i18n
    # 旧 placeholder_values の _meta.closed==true は %di（方角）のみ。新構造は
    # placeholder 単位の _meta を持たないため、閉集合 placeholder 名を定数で保持する。
    words_by_name: dict[str, list[str]] = {}
    for id_, e in i18n.originals("placeholder_values").items():
        if not isinstance(e, dict):
            continue
        m = re.match(r"placeholder_values\.%([a-z0-9]+)\.", id_)
        if not m or m.group(1) not in _CLOSED_PLACEHOLDERS:
            continue
        en_val = (e.get("original", "") or "").strip()
        if en_val:
            words_by_name.setdefault(m.group(1), []).append(en_val)
    # 公開版（原文非同梱で originals 空）: 同梱訳の id から閉集合語彙を導出する
    # （%di は en==slug の方角語＝id の slug 部がそのまま語彙）。最長一致順は下で担保。
    if not words_by_name:
        for sid in i18n.lang_ids("placeholder_values"):
            m = re.match(r"placeholder_values\.%([a-z0-9]+)\.(.+)\.[^.]+$", sid)
            if m and m.group(1) in _CLOSED_PLACEHOLDERS:
                words_by_name.setdefault(m.group(1), []).append(m.group(2))
    for name, words in words_by_name.items():
        # 最長一致順: 長い語を先頭に (例 northeast を north より先に照合させ
        # "northeast" が "north"+"east" に割れるのを防ぐ)。同長は辞書順で安定化。
        words = sorted(set(words), key=lambda w: (-len(w), w))
        _CLOSED_PH_ALT[name] = "|".join(re.escape(w) for w in words)


def _literal_chars(en: str) -> int:
    """en テンプレから placeholder (%xxx) を除いた文字数 (= literal 長)。"""
    return len(re.sub(r"%[a-z][a-z0-9]*", "", en))

# %doc 専用ルックアップ: {normalized_en: {lang: translated_value}} (placeholder なし variant)
_DOC_VALUES: dict[str, dict[str, str]] = {}

# %doc regex ルックアップ: list of (regex, ja_template, ph_count) (placeholder あり variant)
_DOC_COMPILED: list[tuple[re.Pattern, str, int]] = []

# placeholder values ルックアップ: {(placeholder_name, en_value): {lang: translated_value}}
# ra / t / oc / ct / oth をカバーする
_PH_VALUES: dict[tuple[str, str], dict[str, str]] = {}
# classes.json フォールバック: {en_value: ja_value}
_CLASS_VALUES: dict[str, str] = {}
_PH_LOADED = False

# npc_traits.json ルックアップ: {en_trait: ja_trait}
_TRAIT_VALUES: dict[str, str] = {}
_TRAITS_LOADED = False

# items.json drinks カテゴリ ルックアップ (%nd 用)
# {en_drink: ja_drink}
_DRINKS_VALUES: dict[str, str] = {}
_DRINKS_LOADED = False


def _items_section_map(section: str) -> dict[str, str]:
    """items カテゴリの指定サブセクションの en→現在言語訳 を返す（コア経由）。"""
    import i18n_helper as i18n
    out: dict[str, str] = {}
    for id_, e in i18n.originals("items").items():
        parts = id_.split(".")
        if len(parts) < 2 or parts[1] != section or not isinstance(e, dict):
            continue
        en = e.get("original", "")
        ja = i18n.text(id_)
        if en and ja and ja != id_:
            out[en] = ja
    # 公開ビルド（originals 空）は v2_category_entries で当該 section を補完する。
    for ent in i18n.v2_category_entries("items"):
        if (ent.get("context") or {}).get("section") != section:
            continue
        en, ja = ent.get("original"), ent.get("text")
        if en and ja:
            out.setdefault(en, ja)
    return out


def _load_drinks() -> None:
    """items の drinks サブセクションから en→ja マップを構築する。"""
    global _DRINKS_LOADED, _DRINKS_VALUES
    if _DRINKS_LOADED:
        return
    _DRINKS_LOADED = True
    _DRINKS_VALUES.update(_items_section_map("drinks"))


# items.json rooms カテゴリ ルックアップ (%nr 用)
_ROOMS_VALUES: dict[str, str] = {}
_ROOMS_LOADED = False


def _load_rooms() -> None:
    """items の rooms サブセクションから en→ja マップを構築する。"""
    global _ROOMS_LOADED, _ROOMS_VALUES
    if _ROOMS_LOADED:
        return
    _ROOMS_LOADED = True
    _ROOMS_VALUES.update(_items_section_map("rooms"))


# items.json 全カテゴリ flat ルックアップ (%ni 用、汎用アイテム名)
_ITEMS_FLAT: dict[str, str] = {}
_ITEMS_FLAT_LOADED = False


def _load_items_flat() -> None:
    """items.json の全カテゴリから en→ja を flat に取得する。

    weapons / shields / accessories / armors_by_material / potions /
    quest_items / spellcasting_items / drinks / rooms 等を全部含む。
    重複時は先勝ち。
    """
    global _ITEMS_FLAT_LOADED, _ITEMS_FLAT
    if _ITEMS_FLAT_LOADED:
        return
    _ITEMS_FLAT_LOADED = True
    import i18n_helper as i18n
    # items 全エントリを平坦化（先勝ち）。
    for id_, e in i18n.originals("items").items():
        if not isinstance(e, dict):
            continue
        en = e.get("original", "")
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja
    # 公開ビルド（originals 空）は v2_category_entries で items を補完（先勝ち）。
    for ent in i18n.v2_category_entries("items"):
        en = ent.get("original")
        ja = ent.get("text")
        if en and ja:
            _ITEMS_FLAT.setdefault(en, ja)
    # 魔術師ギルドの品名（ポーション/呪文/魔法アイテム名）も %ni 用に統合（先勝ち）。
    # 交渉本文の %ni に "Mark of Light" 等の魔法アイテム名が入るため。
    for id_, e in i18n.originals("mages").items():
        en = e.get("original", "") if isinstance(e, dict) else ""
        if not en or en in _ITEMS_FLAT:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _ITEMS_FLAT[en] = ja


# items.json key_materials カテゴリ ルックアップ (%nk 用、鍵の材質名)
# 武具材質 (magical_materials) の Iron 等とは別カテゴリで管理し、
# 鍵文脈固有の翻訳 (Iron → 鉄 等) を扱う。
_KEY_MATERIALS: dict[str, str] = {}
_KEY_MATERIALS_LOADED = False


def _load_key_materials() -> None:
    """items の key_materials サブセクション（鍵材質名）から en→ja を構築する。"""
    global _KEY_MATERIALS_LOADED, _KEY_MATERIALS
    if _KEY_MATERIALS_LOADED:
        return
    _KEY_MATERIALS_LOADED = True
    _KEY_MATERIALS.update(_items_section_map("key_materials"))


# placeholder_preprocessing.json ルックアップ
# 形式: _PP_RULES[lang][placeholder_name] = [(compiled_pattern, replace_str), ...]
# 言語別に placeholder regex でキャプチャした原文値を辞書 lookup 前に正規化する。
# 未定義言語/未定義 placeholder は pass-through。
# placeholder 前処理ルールは言語別規則（翻訳でない）のため i18n/<lang>/_rules.json の
# placeholder_preprocessing から読む。{lang: {ph_name: [(re, repl)]}}。
_PP_RULES: dict[str, dict[str, list[tuple[re.Pattern, str]]]] = {}


def _load_placeholder_preprocessing(lang: str) -> dict[str, list[tuple[re.Pattern, str]]]:
    """`lang` の placeholder 前処理ルールをコンパイルしてキャッシュ・返す。"""
    if lang in _PP_RULES:
        return _PP_RULES[lang]
    import i18n_helper as i18n
    per_ph: dict[str, list[tuple[re.Pattern, str]]] = {}
    pp = i18n.rules(lang).get("placeholder_preprocessing", {})
    for ph_name, rules in pp.get("placeholders", {}).items():
        if not isinstance(rules, list):
            continue
        compiled_list = per_ph.setdefault(ph_name, [])
        for rule in rules:
            pattern = rule.get("pattern")
            replace = rule.get("replace", "")
            if not pattern:
                continue
            try:
                compiled = re.compile(pattern)
            except re.error:
                continue
            compiled_list.append((compiled, replace))
    _PP_RULES[lang] = per_ph
    return per_ph


def _preprocess_placeholder_value(name: str, value: str, lang: str) -> str:
    """placeholder 値を言語別ルールで前処理する。

    辞書ルックアップ前に冠詞等を剥がして正規化するための前処理。
    ルール未定義の言語 / placeholder は pass-through (value をそのまま返す)。
    """
    if not value or not lang or not name:
        return value
    rules = _load_placeholder_preprocessing(lang).get(name, [])
    if not rules:
        return value
    for compiled, replace in rules:
        value = compiled.sub(replace, value)
    return value

# %ds 構造分解パターン: <trait> <occupation> called <title> <name>
_DS_PATTERN = re.compile(r"^(.+?)\s+(\w+)\s+called\s+(\w+)\s+(.+)$")

# placeholder 名の全種類（% を含まない短縮名）。正規表現グループ名として使用。
# タバーンクエスト系 (#0086-) で使われる %a (amount=金額) / %da (date=日付) /
# %omq (object name = クエストアイテム名) も登録。
_PLACEHOLDER_NAMES: frozenset[str] = frozenset([
    "a", "a2", "an", "ccs", "cll", "cn", "cn2", "cp", "ct", "da", "di",
    "doc", "ds", "en",
    "fn", "fq", "g", "g2", "g3", "hc", "hod", "jok", "lp", "mi",
    "mn", "mt", "n", "nc", "nc2", "nd", "ne", "nh", "nhd", "ni",
    "nk", "nr",
    "nt", "o", "oap", "oc", "omq", "oth", "pcf", "pcn", "qc", "qt", "r", "ra",
    "rcn", "rf", "sn", "st", "t", "tan", "tem", "tg", "tl", "tq", "tt",
])
# cp (current province) / cll (current location = メインクエストの固有ダンジョン名) /
# ccs (city-state name) / rcn (region city name) は、メインストーリーの
# 「Where is（聖杖ダンジョン）」応答テンプレ (TEMPLATE.DAT #1305 / #1306) で使われる
# 地名 placeholder。いずれも静的地名のため location.json (+%cn) で翻訳する。
# nd (named drink)。
# nr (named room) / ni (named item) / nc2 (named condition)
# (= A.EXE 由来テンプレ群)。
# nk (named key material) は鍵文脈固有 (Ruby/Iron/Jade 等)、
# items.json/key_materials を参照。


def _template_to_regex(en_template: str) -> re.Pattern | None:
    """英語テンプレを照合用正規表現にコンパイルする。

    %xxx → (?P<xxx>.+?) に変換し、残りの記号をエスケープする。
    同一 placeholder が複数回出現する場合は 2 回目以降を (?P=xxx) に変換する。
    """
    seen: set[str] = set()
    # longest-match で % トークンを処理するため降順ソートは不要（全て %+英字数字 形式）
    # placeholder を一括で置換するため split ではなく re.sub を使う
    pattern_parts: list[str] = []
    pos = 0
    text = en_template
    token_re = re.compile(r"%([a-z][a-z0-9]*)")

    last = 0
    for m in token_re.finditer(text):
        name = m.group(1)
        # literal 部分をエスケープ
        pattern_parts.append(re.escape(text[last:m.start()]))
        if name in _PLACEHOLDER_NAMES:
            if name not in seen:
                alt = _CLOSED_PH_ALT.get(name)
                if alt:
                    # 閉集合 placeholder: 語彙を選択肢でアンカー (大文字小文字許容・
                    # 後続が英字なら不成立=部分一致防止)。直前の多語 placeholder に
                    # 残りを正しく取らせる。
                    pattern_parts.append(
                        f"(?P<{name}>(?i:{alt}))(?![A-Za-z])")
                else:
                    pattern_parts.append(f"(?P<{name}>.+?)")
                seen.add(name)
            else:
                pattern_parts.append(f"(?P={name})")
        else:
            # 未知の placeholder はリテラル扱いせずワイルドカードにする
            pattern_parts.append(r".+?")
        last = m.end()
    pattern_parts.append(re.escape(text[last:]))

    full_pattern = "^" + "".join(pattern_parts) + "$"
    try:
        return re.compile(full_pattern, re.DOTALL)
    except re.error:
        return None


_NPCD_CAT = "npc_dialog"
_PH_RE_NPCD = re.compile(r"%([a-zA-Z][a-zA-Z0-9]*)")


def _npcd_ph_of(en: str) -> list[str]:
    """surface から placeholder 名を出現順・重複排除で抽出（npc_dialog は個数のみ使用）。"""
    seen: list[str] = []
    for m in _PH_RE_NPCD.finditer(en):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def _npcd_key_int(source_id: str | None) -> int:
    """source_id から旧テンプレ key（%doc 帯 262-362 判定用）を導出。template:<block>:... の
    block が数値なら int、A-key（aexe/tradetext）や非数値 block は -1（%doc 帯外で挙動同等）。"""
    if source_id and source_id.startswith("template:"):
        try:
            return int(source_id.split(":")[1])
        except (ValueError, IndexError):
            return -1
    return -1


def _resolve_npcd_ref(ref) -> str | None:
    """%doc の遅延訳解決（v1=text(id_) / v2=text_by_source_id(source_id)）。"""
    import i18n_helper as i18n
    kind, val = ref
    if kind == "sid":
        return i18n.text_by_source_id(val, category=_NPCD_CAT)
    return i18n.text(val)


def _iter_npcd():
    """NPC 会話テンプレを (en_raw, tmpl, ph_list, key_int, ref) で yield する。v2 公開 runtime
    有効時は source_id 経路（placeholders は surface から個数導出・key_int は source_id から）。
    curation 変種（source_id 無・localpack 非収録）は original None で自然除外（live で出ない
    正規化のため照合に不要）。未有効は従来の originals＋text(id)。"""
    import i18n_helper as i18n
    if i18n.v2_public_enabled(_NPCD_CAT):
        for e in i18n.v2_category_entries(_NPCD_CAT):
            en_raw = e.get("original")
            if not en_raw:
                continue
            tmpl = e.get("text")
            if not tmpl:
                continue
            sid = e.get("source_id")
            yield en_raw, tmpl, _npcd_ph_of(en_raw), _npcd_key_int(sid), ("sid", sid)
    else:
        for id_, entry in i18n.originals(_NPCD_CAT).items():
            en_raw = entry.get("original", "") if isinstance(entry, dict) else ""
            if not en_raw:
                continue
            tmpl = i18n.text(id_)
            if not tmpl:
                continue
            parts = id_.split(".")
            try:
                key_int = int(parts[1]) if len(parts) >= 2 else -1
            except ValueError:
                key_int = -1
            yield (en_raw, tmpl, entry.get("placeholders", []) or [], key_int,
                   ("id", id_))


def _load() -> None:
    global _COMPILED, _LOADED, _DOC_VALUES, _DOC_COMPILED
    if _LOADED:
        return
    # テンプレ regex コンパイル前に閉集合 placeholder の選択肢を用意する
    # (_template_to_regex が _CLOSED_PH_ALT を参照するため)。
    _load_closed_ph()
    # 照合は original（言語中立）で行い、表示テンプレは現在言語の訳を焼く（切替は再起動方式）。
    entries: list[tuple[re.Pattern, str, int, bool, int]] = []
    doc_entries: list[tuple[re.Pattern, str, int]] = []
    for en_raw, tmpl, ph_list, key_int, ref in _iter_npcd():
        # 辞書 original も lookup 入力 (= " ".join(text.split())) と同じ正規化を行う。
        en = " ".join(en_raw.split())
        ph_count = len(ph_list)
        is_exact = (ph_count == 0)
        literal_len = _literal_chars(en)
        compiled = _template_to_regex(en)
        if compiled is None:
            continue
        entries.append((compiled, tmpl, ph_count, is_exact, literal_len))

        if 262 <= key_int <= 362:
            if not ph_list:
                # %doc (placeholder なし variant): 訳は呼び出し時に言語別解決（多言語対応）。
                _DOC_VALUES[en] = {"ref": ref}
            else:
                doc_entries.append((compiled, tmpl, ph_count))

    # ソート優先度:
    #  1. exact match (placeholder なし) を最優先で照合
    #     → 短い generic テンプレ (例 "You have %nc2.") が完全一致 (例
    #        "You have arrived.") を奪うのを防止
    #  2. literal 文字数の多い順 (= "You have found %ni key." が
    #     "You have %nc2." より優先される)
    #  3. placeholder 数の多い順 (制約が強いテンプレを優先)
    entries.sort(key=lambda x: (not x[3], -x[4], -x[2]))
    _COMPILED = entries
    doc_entries.sort(key=lambda x: -x[2])
    _DOC_COMPILED = doc_entries
    _LOADED = True


def _load_ph() -> None:
    """races / placeholder_values / classes を翻訳切替コアから _PH_VALUES / _CLASS_VALUES へロードする。

    値は現在言語で格納する（translate_placeholder は active==lang 前提で .get(lang)）。
    旧と同じ順序: races → placeholder_values(%ra 等を上書き) → classes。
    """
    global _PH_VALUES, _CLASS_VALUES, _PH_LOADED
    if _PH_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    # races（先）
    for id_, e in i18n.originals("races").items():
        en_val = e.get("original", "") if isinstance(e, dict) else ""
        if en_val:
            ja = i18n.text(id_)
            if ja and ja != id_:
                _PH_VALUES[("ra", en_val)] = {lang: ja}
    # placeholder_values（id 末尾に placeholder 名: placeholder_values.%<name>.<slug>.<surface>）
    for id_, e in i18n.originals("placeholder_values").items():
        if not isinstance(e, dict):
            continue
        m = re.match(r"placeholder_values\.%([a-z0-9]+)\.", id_)
        if not m:
            continue
        name = m.group(1)
        en_val = e.get("original", "")
        if not en_val:
            continue
        ja = i18n.text(id_)
        if ja and ja != id_:
            _PH_VALUES[(name, en_val)] = {lang: ja}
    # classes
    for id_, e in i18n.originals("classes").items():
        en_val = e.get("original", "") if isinstance(e, dict) else ""
        if en_val:
            ja = i18n.text(id_)
            if ja and ja != id_:
                _CLASS_VALUES[en_val] = ja
    _PH_LOADED = True


def _load_traits() -> None:
    """npc_traits を翻訳切替コアから _TRAIT_VALUES へロードする。"""
    global _TRAIT_VALUES, _TRAITS_LOADED
    if _TRAITS_LOADED:
        return
    import i18n_helper as i18n
    if i18n.v2_public_enabled("npc_traits"):
        # 公開 v2 経路：bundle entry の original(localpack surface)→text(訳)。
        # original None の entry は未登録＝lookup で en surface へ
        # graceful fallback（_TRAIT_VALUES.get(trait_en, trait_en)）。
        for e in i18n.v2_category_entries("npc_traits"):
            en_val = (e.get("original") or "").strip()
            if en_val:
                _TRAIT_VALUES[en_val] = e.get("text") or ""
    else:
        for id_, e in i18n.originals("npc_traits").items():
            en_val = (e.get("original", "") if isinstance(e, dict) else "").strip()
            if en_val:
                ja = i18n.text(id_)
                _TRAIT_VALUES[en_val] = ja if (ja and ja != id_) else ""
    _TRAITS_LOADED = True


# 日付翻訳キャッシュ (calendar.json から weekday / month を一度だけロード)
_CALENDAR_WEEKDAYS: dict[str, dict[str, str]] = {}
_CALENDAR_MONTHS: dict[str, dict[str, str]] = {}
_CALENDAR_LOADED = False


def _load_calendar() -> None:
    global _CALENDAR_LOADED
    if _CALENDAR_LOADED:
        return
    import i18n_helper as i18n
    lang = i18n.current_lang()
    try:
        for id_, e in i18n.originals("calendar").items():
            if not isinstance(e, dict):
                continue
            cat = e.get("category", "")
            en = e.get("original", "")
            if not en:
                continue
            ja = i18n.text(id_)
            if not ja or ja == id_:
                continue
            if cat == "weekday":
                _CALENDAR_WEEKDAYS[en] = {lang: ja}
            elif cat == "month":
                _CALENDAR_MONTHS[en] = {lang: ja}
    except (OSError, json.JSONDecodeError):
        pass
    _CALENDAR_LOADED = True


# Arena 日付パターン
# - 短形式: "<Weekday>, <D>(st|nd|rd|th) of <Month>"
# - 長形式 (ジャーナル日付ヘッダー): "... in the year <Era> <Year>"
_DATE_PATTERN_SHORT = re.compile(
    r"^([A-Z][a-z]+),\s+(\d+)(?:st|nd|rd|th)\s+of\s+([A-Z][A-Za-z'\s]+?)$")
_DATE_PATTERN_FULL = re.compile(
    r"^([A-Z][a-z]+),\s+(\d+)(?:st|nd|rd|th)\s+of\s+([A-Z][A-Za-z'\s]+?)"
    r"\s+in\s+the\s+year\s+([0-9]+E)\s+(\d+)$")

# Arena 年代記号 → 日本語
def _translate_date(value: str, lang: str) -> str:
    """%da (date) を構造分解して翻訳する。

    短形式: "Middas, 2nd of Hearthfire" → "ミダス、薪木の月 2 日"
    長形式: "Tirdas, 1st of Hearthfire in the year 3E 389"
            → "ティルダス、薪木の月 1 日、第三紀 389 年"
    パターンにマッチしない場合は原文 value を返す。
    """
    import i18n_helper as i18n
    _load_calendar()
    text = value.strip()

    # 長形式 (ジャーナル日付ヘッダー) を先に試す
    m_full = _DATE_PATTERN_FULL.match(text)
    if m_full:
        weekday_en = m_full.group(1)
        day_str = m_full.group(2)
        month_en = m_full.group(3).strip()
        era_en = m_full.group(4)
        year_str = m_full.group(5)
        weekday_ja = _CALENDAR_WEEKDAYS.get(weekday_en, {}).get(lang, weekday_en)
        month_ja = _CALENDAR_MONTHS.get(month_en, {}).get(lang, month_en)
        era_ja = i18n.value_in("eras", era_en, lang) or era_en
        return f"{weekday_ja}、{month_ja} {day_str} 日、{era_ja} {year_str} 年"

    # 短形式 fallback
    m_short = _DATE_PATTERN_SHORT.match(text)
    if m_short:
        weekday_en = m_short.group(1)
        day_str = m_short.group(2)
        month_en = m_short.group(3).strip()
        weekday_ja = _CALENDAR_WEEKDAYS.get(weekday_en, {}).get(lang, weekday_en)
        month_ja = _CALENDAR_MONTHS.get(month_en, {}).get(lang, month_en)
        return f"{weekday_ja}、{month_ja} {day_str} 日"

    return value


def _translate_static_place(value: str, lang: str) -> str:
    """静的地名 (州 / 都市国家 / 固有ダンジョン名) を翻訳する。

    %cp (province) / %cll (main quest dungeon) / %ccs (city-state) /
    %rcn (region city) で共通利用。location.json を優先し、未登録なら
    placeholder_values.json の %cn (都市名) でフォールバックする。
    どちらにも無ければ原文 value を返す。
    """
    if lang == "en":
        return value
    name = (value or "").strip()
    if not name:
        return value
    try:
        from location_lookup import lookup as _loc_lookup
        loc = _loc_lookup(name)
        if loc:
            return loc
    except Exception:  # noqa: BLE001
        pass
    _load_ph()
    cn = _PH_VALUES.get(("cn", name), {}).get(lang)
    if cn:
        return cn
    return value


def _translate_nt(value: str, lang: str) -> str:
    """%nt (inn / tavern name) を dynamic_places.json 経由で翻訳する。"""
    if lang == "en":
        return value
    from dynamic_place_lookup import lookup as _place_lookup
    translated = _place_lookup(value)
    return translated if translated else value


# タバーンクエスト系 %ds 用パターン
# 例: "man called Mad Carolayne of Ebon Wastes"
#   group 1 = social descriptor ("man"/"woman"/"old man" 等)
#   group 2 = trait + name ("Mad Carolayne")
#   group 3 = locale ("Ebon Wastes")
_DS_TAVERN_QUEST_PATTERN = re.compile(
    r"^(.+?)\s+called\s+(.+?)\s+of\s+(.+)$")

def _translate_ds(value: str, lang: str) -> str:
    """%ds (NPC description string) を構造分解して翻訳する。

    パターン:
      1. ASK ABOUT 系: "<trait> <occupation> called <title> <name>"
         (例: "old man called Sir John")
      2. タバーンクエスト系: "<descriptor> called <trait_name> of <locale>"
         (例: "man called Mad Carolayne of Ebon Wastes")

    どちらにもマッチしない場合は原文 value をそのまま返す（fallback）。
    """
    if lang == "en":
        return value

    # パターン 1: 既存 ASK ABOUT 系
    m = _DS_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        trait_en, occupation_en, title_en, name_en = (
            m.group(1), m.group(2), m.group(3), m.group(4))
        _load_traits()
        # trait / occupation / title は原文非同梱の構成（_PH_VALUES / _TRAIT_VALUES が空）でも
        # 解決するよう direct-id 経路を使う：occupation/title は translate_placeholder(%oc/%t)、
        # trait は npc_traits の direct-id（同梱訳キー npc_traits.trait_<slug>.0）。
        trait_ja = (
            _TRAIT_VALUES.get(trait_en)
            or i18n.text_opt(f"npc_traits.trait_{_ph_slug(trait_en)}.0")
            or trait_en)
        occupation_ja = translate_placeholder("oc", occupation_en, lang) or occupation_en
        title_ja = translate_placeholder("t", title_en, lang) or title_en
        name_ja = translate_generated_name(name_en, lang)
        return f"{trait_ja}{occupation_ja}の{title_ja}・{name_ja}"

    # パターン 2: タバーンクエスト系
    # 例: "man called Mad Carolayne of Ebon Wastes"
    m = _DS_TAVERN_QUEST_PATTERN.match(value)
    if m:
        import i18n_helper as i18n
        descriptor_en = m.group(1).strip()
        named_en = m.group(2).strip()
        locale_en = m.group(3).strip()
        _load_traits()
        descriptor_ja = (
            i18n.value("descriptors", descriptor_en.lower()) or descriptor_en)

        # named = "<trait> <name>" の分解を試す:
        # 先頭単語が _TRAIT_VALUES に存在すれば trait と判定し残りを name 扱い。
        # 翻訳がなければ named_en を丸ごと固有名として扱う (フォールバック)。
        named_ja = named_en
        parts = named_en.split(None, 1)
        if len(parts) == 2:
            maybe_trait, maybe_name = parts
            trait_ja_local = _TRAIT_VALUES.get(maybe_trait)
            if trait_ja_local:
                name_ja_local = translate_generated_name(maybe_name, lang)
                named_ja = f"{trait_ja_local}{name_ja_local}"
        if named_ja == named_en:
            # trait 分解できなかった場合は generated_name に丸投げ
            translated_name = translate_generated_name(named_en, lang)
            if translated_name and translated_name != named_en:
                named_ja = translated_name

        # locale (= "Ebon Wastes" 等) の翻訳経路:
        # %ds の "of <locale>" は施設名/都市/省名/動的地名のいずれかに該当する。
        # placeholder_values.json の %cn / %lp / %ct / dynamic_places の順で
        # 既存辞書経路を試す。場当たり的な 1 語固定置換は避ける。
        locale_ja = locale_en
        _load_ph()
        for _ph_name in ("cn", "lp", "ct"):
            _result = _PH_VALUES.get((_ph_name, locale_en), {}).get(lang)
            if _result:
                locale_ja = _result
                break
        if locale_ja == locale_en:
            try:
                from dynamic_place_lookup import lookup as _place_lookup
                place_result = _place_lookup(locale_en)
                if place_result:
                    locale_ja = place_result
            except Exception:  # noqa: BLE001
                pass

        # 「<locale> の <named> という <descriptor>」形式で整形
        return f"{locale_ja} の {named_ja} という {descriptor_ja}"

    return value


def translate_placeholder(name: str, value: str, lang: str = "ja") -> str:
    """placeholder 名と観測値を受け取り、辞書経由で翻訳値を返す。

    マッチしない場合は原文 value をそのまま返す（fallback）。

    入口で `_preprocess_placeholder_value()` を呼び、`placeholder_preprocessing.json`
    に定義された言語別ルール (英語冠詞除去等) を適用する。未定義言語/placeholder
    は pass-through。
    """
    if not value:
        return value
    # 言語別 placeholder 値前処理 (placeholder_preprocessing.json)
    value = _preprocess_placeholder_value(name, value, lang)
    # v2 経路（既定オフ）。placeholder_values の値翻訳 subgroup を公開安全な
    # mixed-mode resolver（%oc=arena_generated originals／derived=redirect→target／live_surface=
    # observations）で解決する。未解決（未観測・未照合）は下の v1 経路へフォールバックする。
    if name in _PV_VALUE_SUBGROUPS or name in ("g", "g2", "g3"):
        import i18n_helper as i18n
        if i18n.v2_public_enabled("placeholder_values"):
            # %g/%g2/%g3 は同 surface が文法格で別訳＝subgroup(section)込みで曖昧解消する。
            section = f"%{name}" if name in ("g", "g2", "g3") else None
            v2 = i18n.value_by_surface("placeholder_values", value,
                                       section=section, lang=lang)
            if v2 is not None:
                return v2
    if name in ("n", "fn", "rf"):
        if lang != "en":
            return translate_generated_name(value, lang)
        return value
    if name == "doc":
        _load()
        normalized = " ".join(value.split())
        doc_entry = _DOC_VALUES.get(normalized)
        if doc_entry is not None:
            resolved = _resolve_npcd_ref(doc_entry["ref"])
            if resolved:
                return resolved
        for compiled, ja_tmpl, _ in _DOC_COMPILED:
            m = compiled.match(normalized)
            if m:
                nested = m.groupdict()
                result = ja_tmpl
                for ph_name, ph_val in nested.items():
                    if ph_val:
                        translated_val = translate_placeholder(ph_name, ph_val, lang)
                        result = result.replace(f"%{ph_name}", translated_val)
                return result
        return value
    if name in ("ra", "t", "oc", "ct", "oth", "di", "lp", "cn", "tem"):
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        # 公開版（原文非同梱で _PH_VALUES 空）でも解決する。
        # %cn/%lp/%ct/%oc/%t/%di = placeholder_values 自身の direct-id（訳を保存）。
        if name in _PH_DIRECT_ID_NAMES:
            direct = _ph_direct_id(name, value)
            if direct is not None:
                return direct
        # %oth = id 非導出だが npc_dialog(pack) に 80/80 一意一致・訳一致のため逆引き。
        if name == "oth":
            import i18n_helper as i18n
            nd = i18n.value("npc_dialog", value)
            if nd is not None:
                return nd
        if name == "oc":
            return _CLASS_VALUES.get(value, value)
        return value
    if name in ("cp", "cll", "ccs", "rcn"):
        # メインストーリー「Where is（聖杖ダンジョン）」応答の地名 placeholder。
        return _translate_static_place(value, lang)
    if name == "nt":
        return _translate_nt(value, lang)
    if name == "ds":
        return _translate_ds(value, lang)
    # タバーンクエスト系で頻出する placeholder の翻訳
    if name in ("a", "a2"):
        # 金額/日数などの数値 — そのまま
        return value
    if name == "da":
        # 日付 (date): calendar.json (weekday/month) で構造分解翻訳
        # "Middas, 2nd of Hearthfire" → "ミダス、薪木の月 2 日" のような形式
        if lang == "en":
            return value
        return _translate_date(value, lang)
    if name == "omq":
        # quest item — 固有名扱いで原文維持
        return value
    if name == "r":
        # relation (sister, brother, mother 等) — relations カテゴリ経由
        import i18n_helper as i18n
        return i18n.value_in("relations", value.lower(), lang) or value
    if name in ("g", "g2", "g3"):
        # gender pronoun (g=he/she, g2=him/her, g3=his/her) — 既存 placeholder_values.json 経由
        _load_ph()
        result = _PH_VALUES.get((name, value), {}).get(lang)
        if result is not None:
            return result
        # 公開版（_PH_VALUES 空）: placeholder_values 自身の direct-id
        # （pronouns 未解決待ちにせず name 込み id で文法差を保つ）。
        direct = _ph_direct_id(name, value)
        if direct is not None:
            return direct
        # フォールバック (pronouns カテゴリ経由)
        import i18n_helper as i18n
        return i18n.value_in("pronouns", value.lower(), lang) or value
    if name in ("fq", "ne"):
        # NPC name (依頼者 / 護衛対象 = 動的生成名)
        if lang != "en":
            return translate_generated_name(value, lang)
        return value
    if name == "o":
        # organization (Dark Brotherhood 等) — 固有名扱いで原文維持
        return value
    if name == "tl":
        # travel location (地名) — 動的場所名翻訳
        if lang != "en":
            from dynamic_place_lookup import lookup as _place_lookup
            translated = _place_lookup(value)
            return translated if translated else value
        return value
    if name == "nd":
        # named drink (酒名) — items.json drinks カテゴリで翻訳
        if lang == "en":
            return value
        _load_drinks()
        return _DRINKS_VALUES.get(value, value)
    if name == "nr":
        # named room (部屋名) — items.json rooms カテゴリで翻訳
        if lang == "en":
            return value
        _load_rooms()
        return _ROOMS_VALUES.get(value, value)
    if name == "ni":
        # named item (汎用アイテム名) — items.json 全カテゴリ横断ルックアップ
        if lang == "en":
            return value
        _load_items_flat()
        translated = _ITEMS_FLAT.get(value)
        if translated:
            return translated
        try:
            from equipment_shop_list_reader import translate_equipment_shop_name
            translated = translate_equipment_shop_name(value)
            return translated if translated else value
        except Exception:  # noqa: BLE001
            return value
    if name == "nk":
        # named key material (鍵の材質: Ruby/Iron/Brass 等) — items.json/key_materials
        # で翻訳。鍵文脈固有の訳 (Iron → 鉄 等・武具材質の「アイアン」とは別) を扱う。
        # surface は冠詞剥がし済みの材質名 (status.key_names の "a Ruby" → "Ruby")。
        if lang == "en":
            return value
        _load_key_materials()
        return _KEY_MATERIALS.get(value, value)
    if name == "nc2":
        # named condition (状態名) — 現状は passthrough (= 後日辞書化)
        return value
    return value


# ── 街到着メッセージ（travel arrival popup）─────────────────────
# 構成: A.EXE 由来の固定前置き + フレーバー(#1422 町 / #1423 村)。前置きは
# TEMPLATE.DAT に無い固定書式のため、構造分解して各要素を翻訳・再合成する。
_ARRIVAL_RE = re.compile(
    r"^You have arrived in (?P<loc>.+?) in (?P<prov>.+?) Province\.\s*"
    r"The date is (?P<date>.+?)\s+It took (?P<days>\d+) days? to reach your goal\.\s*"
    r"(?P<flavor>.*)$",
    re.DOTALL)
_SETTLEMENT_RE = re.compile(
    r"^The (?P<type>Village|Town|City-State|City) of (?P<name>.+)$")
def _translate_settlement_location(loc: str, lang: str) -> str:
    """到着地名 "The Village/Town/City of X" を JA 化する。"""
    if lang == "en":
        return loc
    import i18n_helper as i18n
    m = _SETTLEMENT_RE.match(loc.strip())
    if not m:
        # 直接の地名（都市国家名等）→ 静的地名ルックアップ
        return _translate_static_place(loc.strip(), lang)
    type_ja = i18n.value_in("settlement_types", m.group("type"), lang) or m.group("type")
    name_ja = _translate_static_place(m.group("name").strip(), lang)
    return f"{type_ja}「{name_ja}」"


def _translate_arrival(text: str, lang: str = "ja") -> str | None:
    """街到着メッセージを構造分解して JA を返す。非該当は None。"""
    if lang == "en":
        return None
    m = _ARRIVAL_RE.match(text)
    if not m:
        return None
    loc_ja = _translate_settlement_location(m.group("loc"), lang)
    prov_ja = _translate_static_place(m.group("prov"), lang)
    date_ja = _translate_date(m.group("date"), lang)
    days = m.group("days")
    flavor_ja = ""
    flavor = (m.group("flavor") or "").strip()
    if flavor:
        r = lookup(flavor)  # フレーバーは #1422/#1423 に委譲
        flavor_ja = format_japanese(r[0], r[1], lang) if r is not None else flavor
    result = (f"{prov_ja}地方の{loc_ja}に到着した。"
              f"日付は{date_ja}。目的地まで{days}日かかった。")
    if flavor_ja:
        result += " " + flavor_ja
    return result


def lookup(text: str) -> tuple[str, dict] | None:
    """英語テキストを NPC 会話辞書と照合し、(ja_template, placeholders) を返す。

    マッチしない場合は None を返す。
    """
    if not text:
        return None
    # メモリから読み出したテキストには画面折り返し由来の改行・連続空白が
    # 含まれることがあるため、辞書テンプレ（半角空白区切り）と照合できるよう
    # 単一の半角空白に正規化する。
    text = " ".join(text.split())
    _load()

    # 街到着メッセージ（合成文）は構造分解で完全な JA を組み立てて返す。
    arrival = _translate_arrival(text, "ja")
    if arrival is not None:
        return (arrival, {})

    for compiled, ja, ph_count, is_exact, _literal_len in _COMPILED:
        m = compiled.match(text)
        if m:
            placeholders = m.groupdict()
            return (ja, placeholders)
    return None


def format_japanese(ja_template: str, placeholders: dict, lang: str = "ja") -> str:
    """ja テンプレ内の %xxx を placeholders の値で置換して返す。

    値が None または空の場合は %xxx をそのまま残す。
    各 placeholder 値は translate_placeholder() 経由で辞書照合・翻訳される。
    辞書未登録の値は原文のまま（fallback）。
    """
    result = ja_template
    for name, value in sorted(
            placeholders.items(), key=lambda item: len(item[0]),
            reverse=True):
        if value:
            translated = translate_placeholder(name, value, lang)
            result = result.replace(f"%{name}", translated)
    from text_corrector import apply_text_corrections
    result = apply_text_corrections(result, lang)
    return result


if __name__ == "__main__":
    # 単体動作確認用サンプル
    samples = [
        "Greetings, I am John, a Mage. I cast spells for a living.",
        "They call me Maria the Warrior. I fight for a living.",
        "I am called Tom, the Daggerfall Bard. You know, I play music for a living.",
        "Good day, sir. My name is Alice the skilled Healer. I heal the sick for a living.",
        "The boys call me Lily. I'm a whore.",
        "How would like to recover something for a friend of mine, a highly aggressive aristocrat called Lord Barbyrrya? You can find this person at the Blue Giants, you know the inn southwest of here? I'm sure you'll be paid nicely.",
    ]
    for s in samples:
        result = lookup(s)
        if result:
            ja_template, ph = result
            output = format_japanese(ja_template, ph)
            print(f"EN: {s}")
            print(f"PH: {ph}")
            print(f"JA: {output}")
        else:
            print(f"EN: {s}")
            print(f"JA: <no match>")
        print()
