"""i18n_source_address.py — 翻訳のコンテンツアドレス（単一定義）。

`source_id` / `source_hash` を**唯一の住所として**定義する
共有モジュール。決定論生成器（Arena 資産→ _original/en 再構築）と、実行時の翻訳
ローダ（overlay の hash で原文同一性を検証）が**同じ規則を共有**するための土台。

要点:
  - キーは安定 `source_id`（位置由来・決定論）。データ種別ごとに規則を固定。
  - `source_hash` は原文を正規化（空白/改行正規化・`%t`/`%nt` 等プレースホルダ温存）した
    ハッシュ。位置キーだけに頼らず本文同一性を検証し、版差を hash 不一致で顕在化。
  - 公開 overlay は `source_id` + `source_hash` + `translation` を持ち、原文全文は含めない。
  - 短い hash・翻訳文はゼロリスクではない。hash は原文復元を助ける情報を足さない。

このモジュール自体に Arena 原文は含まれない（規則のみ）。公開物に同梱してよい。
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# ---------------------------------------------------------------------------
# source_id スキーム
# ---------------------------------------------------------------------------
# 区切りは ":"。各セグメントは正規化（大文字小文字・空白）して安定させる。

KIND_TEMPLATE = "template"        # TEMPLATE.DAT     template:<block>:<record_index>
KIND_INF = "inf"                  # INF @TEXT        inf:<inf_name>:text:<index>
KIND_SPELLMKR = "spellmkr"        # SPELLMKR.TXT     spellmkr:<section>:<index>
KIND_NAMECHNK = "namechnk"        # NAMECHNK.DAT     namechnk:<chunk>:<index>
KIND_QUESTION = "question"        # QUESTION.TXT     question:<question_number>
KIND_TRADE = "tradetext"          # *.DAT trade text  tradetext:<file>:<index>
KIND_DOCS = "docs"                # Docs 由来説明    docs:<doc_kind>:<entry_id>
KIND_ASSIST_SUMMARY = "assist_summary"  # Docs 無し時の独自説明（原文要約でない）
KIND_AEXE = "aexe"                # A.EXE 由来文字列  aexe:<group>:<id>
KIND_CITYDATA = "citydata"        # CITYDATA.NN 由来  citydata:<province>:<location_id>|name
KIND_SPELLSG = "spellsg65"        # SPELLSG.65 標準呪文  spellsg65:standard:<index>
KIND_PUBLIC_BUILTIN = "public_builtin"  # 極小一般 UI literal  public_builtin:<key>
KIND_ARMOR_PREFIX = "armor_prefix"  # composite armor 由来 prefix  armor_prefix:<material>
KIND_SPELL_EFFECT = "spelleffect"   # spell effect 構造合成  spelleffect:<effect_id>:<sub_effect_id>
KIND_MAGIC_ITEM = "magicitem"       # 魔法アイテム合成  magicitem:<item_idx>:<spell_kind>:<spell_idx>
KIND_MATERIAL_ITEM = "materialitem"  # 素材+装身具合成  materialitem:<material_idx>:<acc_idx>

ALL_KINDS = frozenset({
    KIND_TEMPLATE, KIND_INF, KIND_SPELLMKR,
    KIND_NAMECHNK, KIND_QUESTION, KIND_TRADE, KIND_DOCS, KIND_ASSIST_SUMMARY,
    KIND_AEXE, KIND_CITYDATA, KIND_SPELLSG, KIND_PUBLIC_BUILTIN,
    KIND_ARMOR_PREFIX, KIND_SPELL_EFFECT, KIND_MAGIC_ITEM, KIND_MATERIAL_ITEM,
})

_SEP = ":"


def _seg(value) -> str:
    """source_id の 1 セグメントを正規化する（前後空白除去・区切り文字を排除）。

    区切り `:` をセグメント値に含めると id が壊れるため不許可。空セグメントも不許可。
    """
    s = str(value).strip()
    if not s:
        raise ValueError("source_id segment must not be empty")
    if _SEP in s:
        raise ValueError(f"source_id segment must not contain '{_SEP}': {s!r}")
    return s


def _norm_filename(name: str) -> str:
    """ファイル名セグメントを大文字正規化する（INF ファイル名は大文字正規化）。"""
    return _seg(name).upper()


def template_id(block, record_index, copy=None) -> str:
    """TEMPLATE.DAT エントリの source_id。

    block        = TEMPLATE.DAT のブロックキー（例 "0000" / "0002_o"）。
    record_index = その copy 内のレコード添字（'&' 分割 variant・0 始まり）。
    copy         = tileset copy index（OpenTESArena entryLists[index]・0/1/2）。
                   building_entry（#0000-#0004）では **必須**。例: template:0002_o:2:1
                   copy=None は移行用の旧形（copy 次元なし）。最終 overlay の主キーに
                   旧形を残さない。

    例: template_id("0002_o", 1, copy=2) -> "template:0002_o:2:1"
        template_id("0000", 2)            -> "template:0000:2"（旧形・移行 alias 用）
    """
    if copy is None:
        return _SEP.join((KIND_TEMPLATE, _seg(block), _seg(int(record_index))))
    return _SEP.join(
        (KIND_TEMPLATE, _seg(block), _seg(int(copy)), _seg(int(record_index))))


def split_template_id(source_id: str) -> tuple[str, int | None, int]:
    """template source_id を (block, copy|None, record_index) に分解する。

    新形 `template:<block>:<copy>:<index>` と旧形 `template:<block>:<index>` の両方を
    受理する（移行期の alias 照合用）。copy 次元が無い旧形は copy=None を返す。
    """
    kind, parts = parse_source_id(source_id)
    if kind != KIND_TEMPLATE:
        raise ValueError(f"not a template source_id: {source_id!r}")
    if len(parts) == 3:
        return parts[0], int(parts[1]), int(parts[2])
    if len(parts) == 2:
        return parts[0], None, int(parts[1])
    raise ValueError(f"invalid template source_id: {source_id!r}")


def inf_id(inf_name, index) -> str:
    """INF @TEXT エントリの source_id。例: inf:CAS.INF:text:3

    inf_name はファイル名を大文字正規化（CAS.INF / cas.inf → CAS.INF）。
    """
    return _SEP.join((KIND_INF, _norm_filename(inf_name), "text", _seg(int(index))))


def spellmkr_id(section, index) -> str:
    """SPELLMKR.TXT エントリの source_id。例: spellmkr:effects:5"""
    return _SEP.join((KIND_SPELLMKR, _seg(section), _seg(int(index))))


def namechnk_id(chunk, index) -> str:
    """NAMECHNK.DAT 部品の source_id。例: namechnk:3:12

    原文部品はローカル限定。翻訳/置換ルールは原文なし overlay に分離する。
    """
    return _SEP.join((KIND_NAMECHNK, _seg(chunk), _seg(int(index))))


def question_id(question_number) -> str:
    """QUESTION.TXT のキャラ作成質問 source_id。例: question:11

    OpenTESArena TextAssetLibrary::initQuestionTxt が 40 問にパースする loose ファイル。
    question_number は 1 始まりの問番号。
    """
    return _SEP.join((KIND_QUESTION, _seg(int(question_number))))


def tradetext_id(dat_file, index) -> str:
    """トレード会話テキスト（TAVERN/SELLING/EQUIP/MUGUILD.DAT）の source_id。例: tradetext:tavern:0

    OpenTESArena TextAssetLibrary::loadTradeText が array で読む loose ファイル。
    dat_file は拡張子なし小文字（tavern 等）、index は 0 始まり配列位置。
    """
    return _SEP.join((KIND_TRADE, _seg(str(dat_file).lower()), _seg(int(index))))


def aexe_id(group, entry_id) -> str:
    """A.EXE 由来ハードコード文字列の source_id。例: aexe:akey:A100.0

    group は採取系統（akey=npc_dialog A-key UI 等）、entry_id はその系統内の識別子。
    オフセットはライブメモリ採取（arena_aexe）で得る＝原文を source_id に含めない。
    """
    return _SEP.join((KIND_AEXE, _seg(group), _seg(entry_id)))


def aexe_table_id(group, table, index) -> str:
    """A.EXE/ACD 固定表の構造 source_id。例: aexe:calendar:month_names:0

    表示語由来の label（month_morning_star 等）を入れず、table/index の構造のみを使う。
    `_aexe_template` の `src_table`（"<group>.<table>"）＋`src_index` から組む。
    """
    return _SEP.join((KIND_AEXE, _seg(group), _seg(table), _seg(int(index))))


def spellsg65_id(index) -> str:
    """SPELLSG.65（標準呪文マスタ）の source_id。例: spellsg65:standard:16

    OpenTESArena `BinaryAssetLibrary::initStandardSpells` が読む固定ファイル＝save slot
    非依存。index は SpellData 配列位置（0 始まり）。surface は再生成時にユーザーの
    SPELLSG.65 から読む＝原文を source_id に含めない。
    """
    return _SEP.join((KIND_SPELLSG, "standard", _seg(int(index))))


def public_builtin_id(key) -> str:
    """極小一般 UI literal（Yes/No 等）の source_id。例: public_builtin:generic.yes

    Arena 抽出 source ではなく Assist UI でもない、公開安全な generic literal。
    surface は生成時に最小 allowlist から注入する（Arena 資産・save に依存しない）。
    """
    return _SEP.join((KIND_PUBLIC_BUILTIN, _seg(str(key))))


def armor_prefix_id(material) -> str:
    """composite armor name table 由来の素材 prefix の source_id。例: armor_prefix:leather

    A.EXE の `leather/chain/plateArmorNames` と base `armorNames` の差分で prefix を導出する
    （`MaterialNames` とは別系統）。surface は再生成時にユーザー A.EXE harvest から
    導出＝原文を source_id に含めない。material は leather/chain/plate。
    """
    return _SEP.join((KIND_ARMOR_PREFIX, _seg(str(material).lower())))


def spell_effect_id(effect_id, sub_effect_id=0) -> str:
    """spell effect の構造合成 source_id。例: spelleffect:0:3（Cause Curse）

    `spell_effect_structure.surface_for(effect_id, sub_effect_id)` で EN 表示を再構成する。
    表示語ラベルでなく effect_id/sub_effect_id の構造のみを使う＝
    原文を source_id に含めない。surface は再生成時に構造から決定論合成。
    """
    return _SEP.join((KIND_SPELL_EFFECT, _seg(int(effect_id)), _seg(int(sub_effect_id))))


def magic_item_id(item_idx, spell_kind, spell_idx) -> str:
    """魔法アイテム名の合成 source_id。例: magicitem:0:misc:0（Mark of Light）

    A.EXE の `spellcastingItemNames[item_idx]` ＋ `{attack,defensive,misc}SpellNames[spell_idx]`
    を結合して EN 表示を再構成する。spell_kind は attack/defensive/misc。
    surface は再生成時に harvest table から合成＝原文を source_id に含めない。
    """
    return _SEP.join((KIND_MAGIC_ITEM, _seg(int(item_idx)),
                      _seg(str(spell_kind)), _seg(int(spell_idx))))


def material_item_id(material_idx, acc_idx) -> str:
    """素材+装身具名の合成 source_id。例: materialitem:5:1（Mithril Belt）

    A.EXE/ACD.EXE の `materialNames[material_idx]` ＋ `enhancementItemNames[acc_idx]` を結合して
    EN 表示を再構成する。surface は再生成時に harvest table から合成。
    """
    return _SEP.join((KIND_MATERIAL_ITEM, _seg(int(material_idx)), _seg(int(acc_idx))))


def citydata_province_name_id(province_index) -> str:
    """CITYDATA.NN の province 名の source_id。例: citydata:0:name

    province_index は 0 始まり（CITYDATA の province 宣言順）。原文（地名）は含めない。
    """
    return _SEP.join((KIND_CITYDATA, _seg(int(province_index)), "name"))


def citydata_location_id(province_index, location_id) -> str:
    """CITYDATA.NN の location 名の source_id。例: citydata:0:8

    location_id は OTA getLocationData 順（0..7=cityStates / 8..15=towns /
    16..31=villages / 32=secondDungeon / 33=firstDungeon / 34..47=randomDungeons）。
    原文（地名）は含めない＝構造位置のみ。
    """
    return _SEP.join(
        (KIND_CITYDATA, _seg(int(province_index)), _seg(int(location_id))))


def docs_id(doc_kind, entry_id) -> str:
    """Docs 由来説明の source_id。例: docs:class:mage"""
    return _SEP.join((KIND_DOCS, _seg(doc_kind), _seg(entry_id)))


def assist_summary_id(entry_id) -> str:
    """Docs 無し時の Assist 独自説明の source_id（原文要約でない・別名前空間）。

    例: assist_summary:class:mage
    """
    return _SEP.join((KIND_ASSIST_SUMMARY, _seg(entry_id)))


def parse_source_id(source_id: str) -> tuple[str, tuple[str, ...]]:
    """source_id を (kind, parts) に分解する。kind が未知なら ValueError。"""
    parts = source_id.split(_SEP)
    if not parts:
        raise ValueError(f"invalid source_id: {source_id!r}")
    kind = parts[0]
    if kind not in ALL_KINDS:
        raise ValueError(f"unknown source_id kind: {kind!r} in {source_id!r}")
    return kind, tuple(parts[1:])


# ---------------------------------------------------------------------------
# source_hash（原文正規化＋ハッシュ）
# ---------------------------------------------------------------------------
# 正規化方針（保守的・本文の意味差は保存する）:
#   1. Unicode NFC 正規化（合成済みへ統一）。
#   2. 改行を LF へ統一（CRLF / CR → LF）。
#   3. 各行末の空白（半角/タブ）を除去。
#   4. 文字列全体の前後空白・空行を除去。
#   行内の連続空白は **畳まない**（意味のある整形を壊さないため）。
#   プレースホルダ（%t / %nt / %cn 等）は通常テキストなので正規化で変化しない。
#
# 意図: 同一版・同一エントリは常に同一 hash（決定論）。語の違い
#       （"freezing" vs "cold" 等）は別 hash になり版差として検出される。

HASH_LENGTH = 16  # sha256 hex の先頭 16 桁（64bit）。原文復元を助けない最小情報。

_LINE_TRAIL_WS = re.compile(r"[ \t]+(?=\n)")


def normalize_source_text(text: str) -> str:
    """原文を source_hash 計算用に正規化する（上記方針）。決定論。"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFC", str(text))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = _LINE_TRAIL_WS.sub("", s)        # 行末空白除去
    s = s.strip()                         # 全体の前後空白/空行除去
    return s


def source_hash(text: str, *, length: int = HASH_LENGTH) -> str:
    """正規化原文の sha256 hex 先頭 length 桁を返す（既定 16）。

    length は drift 検出に十分かつ情報最小。同一正規化原文 → 同一 hash。
    """
    norm = normalize_source_text(text)
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return digest[:length]


def hash_matches(text: str, expected_hash: str) -> bool:
    """与えた原文の source_hash が expected_hash（長さ可変）と一致するか。

    overlay 側の hash 長に合わせて先頭比較する（短縮 hash 同士でも判定可能）。
    """
    if not expected_hash:
        return False
    got = source_hash(text, length=max(len(expected_hash), HASH_LENGTH))
    return got[:len(expected_hash)] == expected_hash


# ---------------------------------------------------------------------------
# overlay / manifest のフィールド名（単一定義・generator と loader が共有）
# ---------------------------------------------------------------------------

# 翻訳 overlay エントリ（公開物・原文全文を含めない）:
#   { "<source_id>": {OVERLAY_HASH: "<source_hash>", OVERLAY_TRANSLATION: "<訳>"} }
# 旧来の素文字列 {id:"訳"} も後方互換で受理する（移行期）。
OVERLAY_HASH = "src"            # 原文同一性検証用の source_hash
OVERLAY_TRANSLATION = "t"       # 訳文

# ゴールデンマニフェスト（公開物・原文なし・情報最小化）:
#   { "version": int, "generator": str, "arena_fingerprint": str,
#     "digest": "<全体ダイジェスト>",
#     "entries": { "<source_id>": "<source_hash>" } }
MANIFEST_VERSION = "version"
MANIFEST_GENERATOR = "generator"
MANIFEST_FINGERPRINT = "arena_fingerprint"
MANIFEST_DIGEST = "digest"
MANIFEST_ENTRIES = "entries"


def manifest_digest(entries: dict[str, str]) -> str:
    """エントリ (source_id -> source_hash) 全体の決定論ダイジェスト。

    source_id 昇順に連結して sha256。順序非依存にするためソートする。
    全体の欠落/余剰/本文ズレを 1 値で突合せるための指標。
    """
    parts = []
    for sid in sorted(entries):
        parts.append(sid)
        parts.append(entries[sid])
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _hash_equal(a: str, b: str) -> bool:
    """2 つの source_hash が一致するか（短い方の長さで先頭比較）。

    生成器は HASH_LENGTH 固定だが、将来 hash 長が変わっても突合せが壊れないよう
    短縮 hash 同士でも比較できるようにする（overlay 側の hash_matches と同方針）。
    """
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def compare_manifests(golden_entries: dict[str, str],
                      local_entries: dict[str, str]) -> dict:
    """ゴールデンマニフェスト（参照）とローカル生成のエントリを突合せる。

    「Assist 使用範囲で生成が足りないことがあってはならない」を仕組みで担保するための
    照合プリミティブ。原文を一切扱わず source_id + source_hash のみで判定する（公開安全）。

    golden_entries / local_entries はいずれも {source_id: source_hash}。

    Returns:
      {
        "missing": [...],  # golden にあり local に無い id（= 生成が足りない）
        "extra":   [...],  # local にあり golden に無い id（= 想定外の余剰）
        "drift":   [...],  # 両方にあるが source_hash が異なる id（= 本文ズレ）
        "ok": bool,        # 3 つとも空なら True
        "counts": {"golden": n, "local": n, "missing": n, "extra": n, "drift": n},
      }
    """
    gset, lset = set(golden_entries), set(local_entries)
    missing = sorted(gset - lset)
    extra = sorted(lset - gset)
    drift = sorted(
        sid for sid in (gset & lset)
        if not _hash_equal(golden_entries[sid], local_entries[sid]))
    return {
        "missing": missing,
        "extra": extra,
        "drift": drift,
        "ok": not (missing or extra or drift),
        "counts": {
            "golden": len(golden_entries), "local": len(local_entries),
            "missing": len(missing), "extra": len(extra), "drift": len(drift),
        },
    }
