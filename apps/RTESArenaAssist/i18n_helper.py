"""
i18n_helper.py — 翻訳切替コア（単一層）

新構造を実行時に読み、現在言語 + フォールバック連鎖で id→文字列を解決する単一の層。
UI もゲームテキストもこの層に集約し、消費側は辞書ファイルを直読みしない。

構造:
  i18n/_meta.json           中央言語メタ（単一住所）: {languages:{<bcp47>:{...}}, _default_fallback}
  i18n/_original/<cat>.json  原文アンカー: {id:{original?, placeholders?, src_hash, terms?}}
  i18n/<bcp47>/<cat>.json    各言語の訳: {id: "訳"} または {id:{value,status}}

公開 API:
  init(base_dir, lang=None)        起動時初期化（lang 未指定なら system locale→英語既定）
  tr(key, **kwargs)                UI 文字列（id=意味キー）。未解決はキーを返す
  tr_n(key, n, **kwargs)           複数形対応 UI 文字列
  text(id)                         任意 id を現在言語→fallback→原文 で解決
  text_opt(id)                     未解決時 None（呼び側でフォールバック制御したい場合）
  original(id)                     原文アンカー文字列（無ければ None）
  originals(category)              {id:{original,...}}（ゲームテキスト照合器が消費）
  glossary(term_id)                用語集の現在言語正典訳（無ければ None）
  set_language(lang)               動的切替（language_changed 発火）
  current_lang() / current_meta() / available_languages() / direction() / font_hint()
"""

from __future__ import annotations

import json
import locale
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# モジュールレベル状態
# ---------------------------------------------------------------------------
_BASE_DIR: str = ""
_I18N_DIR: str = ""
_lang: str = "en"

_meta_all: dict[str, dict[str, Any]] = {}        # bcp47 -> meta
_default_fallback: str = "en"

_lang_cache: dict[str, dict[str, str]] = {}       # bcp47 -> merged {id: str}（構造値は value に畳む）
_lang_raw_cache: dict[str, dict[str, Any]] = {}   # bcp47 -> raw {id: str|dict}（語形保持・未畳み）
_rules_cache: dict[str, dict[str, Any]] = {}      # bcp47 -> i18n/<lang>/_rules.json（言語別処理ルール）
_original_merged: dict[str, str] = {}             # id -> original
_originals_by_cat: dict[str, dict[str, Any]] = {}  # category -> {id: {original,...}}
_value_index: dict[str, dict[str, str]] = {}      # category -> {original: id}（逆引き索引・遅延構築）

# Qt シグナル（PySide6 が利用可能な場合のみ有効）
try:
    from PySide6.QtCore import QObject, Signal

    class _I18nSignals(QObject):
        language_changed = Signal(str)

    signals = _I18nSignals()
except ImportError:
    signals = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 初期化
# ---------------------------------------------------------------------------

# ── v2 翻訳基盤（整数 ID）への段階委譲（既定オフ＝dev 挙動不変）──
# 2 系統ある:
#   _V2_COMPAT      … dev-only 互換ブリッジ（旧 string-ID→legacy_id_map→整数ID）。
#                     legacy_id_map（原文断片含・公開DENY）依存＝**公開ビルド不可**。
#   _V2_PUBLIC 系   … 公開安全 runtime（source_id→公開 source_id_map→整数ID）。legacy_id_map 非依存。
#                     consumer が Arena 原文込み旧 string-ID でなく source_id を渡す。
_V2_COMPAT = None  # i18n_compat.V2Compat | None（dev-only）

_V2_PUBLIC = None             # i18n_v2.I18nV2 | None（公開安全・legacy_id_map 非依存）
_V2_SOURCE_ID_MAP = None      # {source_id: [int_id,...]}（公開 source_id_map）
_V2_RUNTIME_ENABLED = False   # i18n_v2_runtime_enabled（総合）
_V2_CATEGORIES_ENABLED: set = set()   # i18n_v2_category_enabled.<category>
_V2_VALUE_INDEX: dict = {}    # category -> {localpack original surface: int_id}（live-surface 逆引き）
_V2_SURFACE_WARNINGS: dict = {}  # category -> [訳違い重複 surface,...]（category-scoped 事前検査）
_V2_SLOT_INDEX: dict = {}     # category -> {slot: int_id}（公開 bundle の context.slot 構造キー）
_V2_SECTION_INDEX: dict = {}  # category -> {(section, surface): int_id}（context.section 曖昧解消）
_V2_DEGRADED_ACCEPTED: dict = {}  # category -> set(int_id)（D 受容＝mixed-complete 分母除外）

# v1 lang コード（ja/en/es）→ v2 locale tag（ja-JP 等）。i18n_compat と同方針（公開安全）。
_V2_LOCALE_TAG = {"ja": "ja-JP", "en": "en-US", "es": "es-ES"}

# Phase 5 安全 enable-set（公開ビルド忠実検証で確定）。
# 公開ビルドの localpack は source_id 経路（provisioned surface のみ）＋ live_surface 観測で構築される。
#
# (1) value-safe＝**実 localpack（build_local_pack 生成・source_id originals のみ）で value() の全
#     surface が解決＝有効化しても現行（v1）から訳が後退しない** arena_generated カテゴリ。
#     **重要**: 実 localpack は observations を持たない（`_write_v2_localpack` は source_id originals
#     のみ書く・runtime 観測記録経路は未実装）。よって live_surface カテゴリは公開 v2 で解決できず
#     （恒久 degrade）本集合に含めない。
_PHASE5_VALUE_SAFE = frozenset({
    "calendar", "chargen_race_descriptions", "classes", "equipment_suffixes",
    "item_enchantments", "location_types", "protect_locations", "races",
    "spells", "titles", "template_dat_building_entry",
})
# (2) iterator-safe＝iterator 消費（`v2_category_entries` 経路）で consumer 出力が v1 と等価な
#     カテゴリ。localpack.originals（source_id）で解決＝observations 不要。value() raw では curation
#     entry が落ちるが当該カテゴリは value() で消費されない。consumer 経路の後退なしは dedicated
#     parity で実証済（npc_name_chunks=完全一致／npc_dialog=差は curation 正規化変種 2 件のみ）。
_PHASE5_ITERATOR_SAFE = frozenset({"npc_dialog", "npc_name_chunks"})
# (4) degraded-complete＝D 受容 register で genuine-D（ACD 概念非存在で解決経路
#     なし）を mixed-complete gate の分母から除外し、残る provisioned が公開忠実 localpack で
#     全解決するカテゴリ。enable すると source-backed entry は JA、D accepted entry は EN 後退
#     （製品判断）。consumer は value()/value_in()（pronouns/relations/descriptors/
#     status_terms）または v2_category_entries（npc_traits・_load_traits）で v2 公開経路に乗る。
_PHASE5_DEGRADED_COMPLETE = frozenset({
    "pronouns", "npc_traits", "relations", "descriptors", "status_terms",
})
# (5) mixed-complete＝consumed3 の source-back/retire を出し切り、全 active entry が
#     localpack originals（source_id）で解決する（degraded 0・retired は分母外）カテゴリ。
#     mages 121/121・item_materials 11/11 が非source 0＝enable しても EN 後退ゼロ（fresh localpack で
#     mixed-complete gate 通過を実証）。composite surface は ACD harvest 依存ゆえ
#     localpack 再生成（_AEXE_CONTENT_VERSION srcback27 で強制）が前提＝A.EXE 由来 categories と同契約。
_PHASE5_MIXED_COMPLETE = frozenset({"mages", "item_materials"})
# (3) live_surface pending＝公開 v2 解決に **runtime 観測記録 or value_by_slot consumer 配線** が
#     要るが未実装のカテゴリ。実 localpack で 0 解決（observations 空）＝enable すると ja→en 後退。
#     observation 記録経路（user-env）または clean-ordinal の value_by_slot 配線が入るまで enable-set
#     非追加。placeholder_values は live 部分 138 が同理由で未解決のため保留。
#   degraded-complete 化した 5（pronouns/npc_traits/relations/descriptors/
#   status_terms）は本 pending から外し _PHASE5_DEGRADED_COMPLETE で enable 済み。
_PHASE5_LIVE_SURFACE_PENDING = frozenset({
    "ask_about_menu", "dungeon_messages", "eras", "gods",
    "placeholder_values", "pregame_intro", "status_buffer_text", "ui",
})
# 起動配線（`assist_main`）が settings `i18n_v2_categories` 未指定かつ `i18n_v2_runtime` on のとき
# 既定で使う **実 localpack 実証済み**安全 enable-set。live_surface pending・partial（items 等）・
# degraded（magic/spell_names）・derived・assist_bundled・inf_text は含めない。
PHASE5_ENABLE_SET = (_PHASE5_VALUE_SAFE | _PHASE5_ITERATOR_SAFE
                     | _PHASE5_DEGRADED_COMPLETE | _PHASE5_MIXED_COMPLETE)

# partial カテゴリ（A.EXE テーブル由来 arena_generated で部分カバレッジ）の **未 provision entry の
# observation fallback allowlist**。provision 済 entry は source_id /
# localpack.originals のまま、未 provision entry のみ user-env 専用 `live_surface_observations`
# （source へ入れない runtime 観測 surface）で解決する entry 単位 mixed resolution の対象。
# **本集合は observation fallback を許可するカテゴリ＝enable-set ではない**。実際の enable は
# カテゴリ単位の mixed-complete gate（`v2_category_mixed_complete`）通過後（context 確定可能 entry の
# observation 登録・解決を consumer が実証）に個別追加する。
_PHASE5_PARTIAL_OBS_ALLOWLIST = frozenset({
    "items", "equipment", "mages", "character", "dungeon", "monsters",
    "item_materials",
    # ACD.EXE 固定テーブル由来の再分類（partial）。matched は source_id originals で
    # 解決・unmatched（pronouns hers／relations nephew 等／ask_about_menu 見出し＝ACD.EXE
    # 非存在）は degraded。
    "pronouns", "relations", "ask_about_menu",
    # status_buffer_text の day/month を既存 calendar 表へ共有（19/35）。era(数値)/
    # part/health は非テーブル源で unmatched（degraded）。
    "status_buffer_text",
    # 小 resolver（partial）：descriptors man/woman・status_terms war/peace・
    # npc_traits Mad を ACD 表へ source-back。残は synthetic/D（degraded）。
    "descriptors", "status_terms", "npc_traits",
})


def _v2_locale_tag(lang: str) -> str:
    return _V2_LOCALE_TAG.get((lang or "").lower(), lang)


def enable_v2(*, bundle_path: str, legacy_map_path: str,
              localpack_path: str | None = None,
              mods_dir: str | None = None) -> None:
    """**dev-only** v2 互換委譲を有効化する（旧 string-ID→legacy_id_map→v2・既定オフ）。

    legacy_id_map（原文断片含・公開DENY）依存のため**公開ビルドでは使えない**。
    公開 runtime は `enable_v2_public` を使う。`text_opt`/`original` は legacy_id を解決し、
    未解決のみ従来のディスク解決へフォールバックする（v2 covered 範囲で挙動等価）。
    """
    global _V2_COMPAT
    import i18n_compat
    _V2_COMPAT = i18n_compat.V2Compat.load(
        bundle_path=bundle_path, legacy_map_path=legacy_map_path,
        localpack_path=localpack_path, mods_dir=mods_dir)


def disable_v2() -> None:
    global _V2_COMPAT
    _V2_COMPAT = None


def v2_enabled() -> bool:
    return _V2_COMPAT is not None


def enable_v2_public(*, bundle_path: str, source_id_map_path: str,
                     localpack_path: str | None = None,
                     mods_dir: str | None = None,
                     categories=None) -> None:
    """**公開安全** v2 runtime を有効化する（source_id 経路・legacy_id_map 非依存・既定オフ）。

    consumer は Arena 原文込み旧 string-ID でなく `source_id` を渡し、公開派生 `source_id_map`
    で整数 ID へ解決する。`categories` はカテゴリ単位切替の有効集合
    （None=全カテゴリ・既定は呼出側が空で開始しカテゴリ毎に有効化）。
    """
    global _V2_PUBLIC, _V2_SOURCE_ID_MAP, _V2_RUNTIME_ENABLED, _V2_CATEGORIES_ENABLED
    global _V2_VALUE_INDEX, _V2_SURFACE_WARNINGS, _V2_SLOT_INDEX, _V2_SECTION_INDEX
    global _V2_DEGRADED_ACCEPTED
    import json
    import i18n_v2
    _V2_PUBLIC = i18n_v2.I18nV2.load(
        bundle_path=bundle_path, localpack_path=localpack_path, mods_dir=mods_dir)
    with open(source_id_map_path, encoding="utf-8") as fh:
        _V2_SOURCE_ID_MAP = json.load(fh).get("map", {})
    _V2_DEGRADED_ACCEPTED = _load_degraded_accepted(bundle_path)
    _V2_RUNTIME_ENABLED = True
    _V2_CATEGORIES_ENABLED = set(categories) if categories is not None else None
    _V2_VALUE_INDEX = {}
    _V2_SURFACE_WARNINGS = {}
    _V2_SLOT_INDEX = {}
    _V2_SECTION_INDEX = {}


def disable_v2_public() -> None:
    global _V2_PUBLIC, _V2_SOURCE_ID_MAP, _V2_RUNTIME_ENABLED, _V2_CATEGORIES_ENABLED
    global _V2_VALUE_INDEX, _V2_SURFACE_WARNINGS, _V2_SLOT_INDEX, _V2_SECTION_INDEX
    global _V2_DEGRADED_ACCEPTED
    _V2_PUBLIC = None
    _V2_SOURCE_ID_MAP = None
    _V2_RUNTIME_ENABLED = False
    _V2_CATEGORIES_ENABLED = set()
    _V2_VALUE_INDEX = {}
    _V2_SURFACE_WARNINGS = {}
    _V2_SLOT_INDEX = {}
    _V2_SECTION_INDEX = {}
    _V2_DEGRADED_ACCEPTED = {}


def _load_degraded_accepted(bundle_path: str) -> dict:
    """D 受容 register（`degraded_accepted.json`・bundle 同階層）を読む。

    公開安全（整数 id のみ・原文非含）。category -> set(int_id) を返す。不在/不正は空 dict
    （= 除外なし＝従来挙動）。mixed-complete gate がこの集合を分母から除外する。"""
    import json
    path = os.path.join(os.path.dirname(bundle_path), "degraded_accepted.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        out: dict = {}
        for cat, spec in (data.get("accepted") or {}).items():
            ids = (spec or {}).get("ids") or []
            out[cat] = {int(i) for i in ids}
        return out
    except Exception:  # noqa: BLE001 - register 読込失敗は除外なしで継続
        logger.warning("i18n: degraded_accepted.json 読込失敗（除外なしで継続）", exc_info=True)
        return {}


def enable_v2_public_if_available(*, bundle_path: str, source_id_map_path: str,
                                  localpack_path: str | None,
                                  enabled: bool, categories=None,
                                  user_dir: str | None = None) -> bool:
    """起動配線用: 設定が有効 かつ localpack が存在すれば公開 v2 runtime を有効化する。

    `enabled=False`／localpack 不在／読込失敗なら何もしない（v1 継続＝既定で挙動不変）。
    戻り値＝有効化したか。設定 `i18n_v2_runtime` 既定オフのため、未設定環境では常に v1。
    `user_dir` 指定時は有効化後に user-env runtime 観測（partial 救済の記録側）を
    現ロード localpack へ重ねる（公開非含・surface→id 逆引きで解決可能に）。
    """
    if not enabled or not localpack_path or not os.path.exists(localpack_path):
        return False
    try:
        enable_v2_public(bundle_path=bundle_path, source_id_map_path=source_id_map_path,
                         localpack_path=localpack_path, categories=categories)
        if user_dir:
            merge_user_observations(user_dir)
        return True
    except Exception:  # noqa: BLE001 - v2 有効化失敗は起動を妨げない
        logger.warning("i18n: 公開 v2 runtime 有効化失敗（v1 継続）", exc_info=True)
        return False


def v2_public_enabled(category: str | None = None) -> bool:
    """公開 v2 runtime が有効か（category 指定時はそのカテゴリが切替済か）。"""
    if not _V2_RUNTIME_ENABLED or _V2_PUBLIC is None:
        return False
    if category is None or _V2_CATEGORIES_ENABLED is None:
        return True
    return category in _V2_CATEGORIES_ENABLED


def v2_generated_asset(name: str) -> bytes | None:
    """公開 v2 localpack の翻訳外生成資産（world_map.json 等）を bytes で返す。

    Read generated Arena assets (world_map.json etc.) only from the v2 localpack.
    v2 未有効/localpack 未ロード/未収録は None。
    """
    if _V2_PUBLIC is None or getattr(_V2_PUBLIC, "localpack", None) is None:
        return None
    return _V2_PUBLIC.localpack.generated_asset(name)


def _v2_ids_for_source_id(source_id: str) -> list:
    v = (_V2_SOURCE_ID_MAP or {}).get(source_id)
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _v2_pick_id(source_id: str, category: str | None):
    """source_id → 整数 ID（multi-target は category で曖昧解消・既定は先頭）。未登録は None。"""
    ids = _v2_ids_for_source_id(source_id)
    if not ids:
        return None
    if len(ids) > 1 and category is not None and _V2_PUBLIC is not None:
        for i in ids:
            c = _V2_PUBLIC.category_of(int(i))
            if c and c.get("category") == category:
                return int(i)
    return int(ids[0])


def text_by_source_id(source_id: str, *, category: str | None = None,
                      lang: str | None = None) -> str | None:
    """source_id → 公開 source_id_map → 整数 ID → 表示訳（公開安全・legacy_id_map 非依存）。

    共有テーブル（multi-target）は `category` で曖昧解消する。未解決は None。
    """
    if _V2_PUBLIC is None:
        return None
    nid = _v2_pick_id(source_id, category)
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))


def original_by_source_id(source_id: str, *, category: str | None = None) -> str | None:
    """source_id → 整数 ID → localpack original（ライブ照合アンカー・公開安全）。未解決は None。"""
    if _V2_PUBLIC is None:
        return None
    nid = _v2_pick_id(source_id, category)
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_original_surface(nid)


def v2_category_entries(category: str, *, lang: str | None = None) -> list:
    """カテゴリの (id, source_id, original, text) を v2 スタックから列挙する（公開安全）。

    consumer 移行用 enabler＝旧 `originals(category)`＋`text(id)` の置換。bundle の entry から
    source_id と現在言語訳、localpack から original（ライブ照合アンカー）を取る（legacy_id_map
    非依存）。localpack 未ロード時 original=None。retired は除外。未有効/未知カテゴリは空 list。
    """
    if _V2_PUBLIC is None:
        return []
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return []
    loc = _v2_locale_tag(lang or _lang)
    out = []
    for e in meta.get("entries", []):
        if e.get("retired"):
            continue
        eid = int(e["id"])
        out.append({
            "id": eid,
            "source_id": (e.get("source") or {}).get("source_id"),
            "kind": e.get("kind"),
            "original": _V2_PUBLIC.resolve_original_surface(eid),
            "text": _V2_PUBLIC.resolve_text(eid, loc),
            "rich": _V2_PUBLIC.rich_meta(eid),
            # context（section 等・非原文構造ラベル）＝consumer の section filter 用
            # （items 等の iterate-by-id 移行）。公開安全（原文非含）。
            "context": e.get("context") or {},
        })
    return out


def v2_bundle_categories() -> list:
    """公開 v2 bundle に収録されたカテゴリ一覧（公開安全・ソート済み・enable 非依存）。

    公開ビルドは disk `i18n/_original` 非同梱で `original_categories()` が空になるため、
    辞書タブ等のカテゴリ列挙はこの bundle 由来一覧へフォールバックする。未ロードは空。
    """
    if _V2_PUBLIC is None:
        return []
    try:
        return sorted(_V2_PUBLIC.bundle.categories.keys())
    except Exception:  # noqa: BLE001
        return []


def _v2_value_index(category: str) -> dict:
    """カテゴリの surface → 整数 ID 逆引き索引（first-win・キャッシュ）。

    surface の出所は **entry 単位の mixed resolution**（固定順）：
      ①arena_generated（localpack.originals＝source/golden アンカー）→②live_surface
      （localpack の `live_surface_observations`＝runtime 観測・別 section）。
    pure カテゴリ（全 arena_generated／全 live_surface）はどちらか一方のみ命中＝挙動不変。
    placeholder_values のように source_policy が subgroup で混在するカテゴリでは、source-backed
    （%oc）は originals・live_surface（%di 等）は observations から、同一索引に共存する。
    索引は **category-scoped**＝同一 surface が別カテゴリで別訳でも混線しない。構築時に
    カテゴリ内の **訳違い重複**（同 surface→別訳）を事前検査し `_V2_SURFACE_WARNINGS` へ記録する
    （first-win では破綻するため・items の Gold/Iron/Silver で実証）。
    """
    idx = _V2_VALUE_INDEX.get(category)
    if idx is None:
        idx = {}
        dup_warn: list[str] = []
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                loc = _v2_locale_tag(_lang)
                for e in meta.get("entries", []):
                    if e.get("retired"):
                        continue
                    eid = int(e["id"])
                    # 固定順 mixed: originals（arena_generated）優先・無ければ observations（live_surface）。
                    o = _V2_PUBLIC.resolve_original_surface(eid)
                    if not isinstance(o, str):
                        o = _V2_PUBLIC.resolve_live_surface(eid)
                    if not isinstance(o, str):
                        continue
                    prev = idx.get(o)
                    if prev is None:
                        idx[o] = eid
                    elif prev != eid:
                        # 訳違い重複の検査：同 surface の別 ID が別訳なら破綻シグナル。
                        t_prev = _V2_PUBLIC.resolve_text(prev, loc)
                        t_cur = _V2_PUBLIC.resolve_text(eid, loc)
                        if t_prev != t_cur and o not in dup_warn:
                            dup_warn.append(o)
        _V2_VALUE_INDEX[category] = idx
        _V2_SURFACE_WARNINGS[category] = dup_warn
        if dup_warn:
            logger.warning(
                "i18n v2: category %r has %d surface(s) with conflicting "
                "translations (value_by_surface first-win unsafe): %s",
                category, len(dup_warn), dup_warn[:5])
    return idx


def v2_surface_conflicts(category: str) -> list:
    """カテゴリの訳違い重複 surface 一覧（category-scoped 事前検査結果・空＝一意安全）。

    `value_by_surface(category, ...)` 委譲の安全性検査用。索引未構築なら構築する。
    """
    _v2_value_index(category)
    return list(_V2_SURFACE_WARNINGS.get(category, []))


def _v2_section_index(category: str) -> dict:
    """カテゴリの (section, surface) → 整数 ID 索引（キャッシュ）。

    公開 bundle の `context.section`（構造ラベル・非原文）と localpack original surface から構築。
    訳違い重複 surface（items の Gold/Iron/Silver＝section 依存で別訳）を section 込みで曖昧解消する
    公開安全経路。
    """
    idx = _V2_SECTION_INDEX.get(category)
    if idx is None:
        idx = {}
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                for e in meta.get("entries", []):
                    if e.get("retired"):
                        continue
                    section = (e.get("context") or {}).get("section")
                    if section is None:
                        continue
                    eid = int(e["id"])
                    # 固定順 mixed（originals=arena_generated→observations=live_surface・%g 等）。
                    o = _V2_PUBLIC.resolve_original_surface(eid)
                    if not isinstance(o, str):
                        o = _V2_PUBLIC.resolve_live_surface(eid)
                    if isinstance(o, str):
                        idx.setdefault((section, o), eid)
        _V2_SECTION_INDEX[category] = idx
    return idx


def value_by_surface(category: str, original_text: str,
                     *, section: str | None = None,
                     lang: str | None = None) -> str | None:
    """カテゴリ内で原文 surface を逆引きし v2 で訳を返す（公開安全・live-surface 経路）。
    localpack の original→整数 ID 逆引き索引（first-win）で解決＝原文込み string-ID
    不使用。未有効/未登録は None。`value()`/`value_in()` が v2 有効カテゴリで委譲する。

    `section` 指定時は (section, surface) で曖昧解消（訳違い重複の category-scoped 解決・
    items の Gold/Iron/Silver）。section 不一致で未登録なら section なし first-win へはフォールバックしない
    （誤訳防止＝section を渡した呼び側は厳密一致を要求する）。"""
    if _V2_PUBLIC is None or not original_text:
        return None
    if section is not None:
        nid = _v2_section_index(category).get((section, original_text))
        if nid is None:
            return None
        return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))
    nid = _v2_value_index(category).get(original_text)
    if nid is None:
        return None
    # fail-closed: 同一 surface がカテゴリ内で別訳へ割れる場合、bare 逆引きは
    # 曖昧なため None を返す（first-win で誤訳しない）。呼び側は section/context で曖昧解消する。
    if original_text in _V2_SURFACE_WARNINGS.get(category, ()):
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))


def value_section(category: str, original_text: str, section: str) -> str | None:
    """section 込みでカテゴリ値訳を返す（公開安全 context.section 曖昧解消）。

    呼出元が施設コンテキストから section（drinks/rooms 等・公開安全な非原文キー）を
    知っている surface 消費 consumer 用。v2 有効カテゴリでは `value_by_surface(section=…)`
    で section-scoped 解決（conflict bare 誤訳を fail-closed）。v2 無効（v1）では
    従来の `value()` へ委譲する（section は v1 索引に無く通常解決＝dev 挙動不変）。"""
    if not original_text:
        return None
    if v2_public_enabled(category):
        return value_by_surface(category, original_text, section=section)
    return value(category, original_text)


def _v2_slot_index(category: str) -> dict:
    """カテゴリの公開 bundle 構造キー slot → 整数 ID 索引（キャッシュ）。

    live_surface の clean 序数カテゴリ（bundle entry に `context.slot`）用。surface でなく
    runtime の slot（game memory の enum index 等・非原文）から id を引く公開ビルド経路。
    """
    idx = _V2_SLOT_INDEX.get(category)
    if idx is None:
        idx = {}
        if _V2_PUBLIC is not None:
            meta = _V2_PUBLIC.bundle.categories.get(category)
            if meta:
                for e in meta.get("entries", []):
                    if e.get("retired"):
                        continue
                    slot = (e.get("context") or {}).get("slot")
                    if slot is not None and slot not in idx:
                        idx[int(slot)] = int(e["id"])
        _V2_SLOT_INDEX[category] = idx
    return idx


def value_by_slot(category: str, slot: int, *, lang: str | None = None) -> str | None:
    """カテゴリの構造キー slot → 整数 ID → 訳（公開安全・原文非経由）。未有効/未登録は None。

    surface を介さず slot（runtime 観測の非原文 enum index 等）から解決する公開ビルド経路。
    観測 surface に依らないため、_original/observations が無い公開ビルドでも runtime で解決できる。
    """
    if _V2_PUBLIC is None or slot is None:
        return None
    nid = _v2_slot_index(category).get(int(slot))
    if nid is None:
        return None
    return _V2_PUBLIC.resolve_text(nid, _v2_locale_tag(lang or _lang))


def v2_category_mixed_complete(category: str) -> bool:
    """カテゴリの全 active entry が v2 で解決アンカーを持つか（mixed-complete gate）。

    旧 `_original` 撤去と partial カテゴリ enable の前提ゲート。各 non-retired entry が
    **originals（source_id）／observations（runtime 観測）／redirect** のいずれかで解決でき、degraded
    （どれにも該当せず surface 逆引き不能）が 0 件なら True。bundle の ja 自体は全 id に在るため、
    本ゲートは「surface→id 逆引きアンカーの被覆」を見る（value() 消費の後退ゼロ条件）。
    observations は現ロード localpack の状態で評価する（runtime 蓄積前は未充足になりうる）。
    """
    if _V2_PUBLIC is None:
        return False
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return False
    # D 受容 entry は分母から除外（static source 非存在を確定済＝en 後退受容）。
    accepted = _V2_DEGRADED_ACCEPTED.get(category, ())
    for e in meta.get("entries", []):
        if e.get("retired"):
            continue
        eid = int(e["id"])
        if eid in accepted:
            continue
        if _V2_PUBLIC.bundle.redirect_of(eid) is not None:
            continue
        if isinstance(_V2_PUBLIC.resolve_original_surface(eid), str):
            continue
        if isinstance(_V2_PUBLIC.resolve_live_surface(eid), str):
            continue
        return False
    return True


def _v2_clear_surface_caches() -> None:
    """live_surface_obs 変更後に surface 逆引き索引を破棄（次回 lazy 再構築）。"""
    global _V2_VALUE_INDEX, _V2_SECTION_INDEX, _V2_SURFACE_WARNINGS
    _V2_VALUE_INDEX = {}
    _V2_SECTION_INDEX = {}
    _V2_SURFACE_WARNINGS = {}


def register_observation(category: str, id: int, surface: str, *,
                         user_dir: str) -> bool:
    """user-env runtime 観測を記録する（記録側）。

    **公開安全 guard**（surface-only bootstrap 禁止）:
      - `id` は呼び側が公開安全 context（slot/section/owner/enum/直 ID）で**確定済**整数 ID。
      - category は partial allowlist（`_PHASE5_PARTIAL_OBS_ALLOWLIST`）のみ。
      - 当該 id は category の **非 retired かつ未 provision（source_id なし）** entry のみ
        （provision 済は source_id で解決＝観測しない・retired は書かない）。
      - surface 非空。
    成功時 user-env ストア（`live_surface_observations.json`・公開非含）へ追記し、現ロードの
    localpack 観測へ即時反映する（surface→id 逆引きで解決可能に）。guard 不成立は False。
    """
    if _V2_PUBLIC is None or not surface or category not in _PHASE5_PARTIAL_OBS_ALLOWLIST:
        return False
    meta = _V2_PUBLIC.bundle.categories.get(category)
    if not meta:
        return False
    ent = None
    for e in meta.get("entries", []):
        if int(e["id"]) == int(id):
            ent = e
            break
    if ent is None or ent.get("retired"):
        return False
    if (ent.get("source") or {}).get("source_id"):
        return False  # provision 済は source_id 解決＝観測しない
    import arena_local_data as _ald
    if not _ald.append_user_observation(user_dir, int(id), surface):
        return False
    # 現ロード localpack の観測へ即時反映（次回再起動を待たず解決可能に）。
    if _V2_PUBLIC.localpack is not None:
        _V2_PUBLIC.localpack.live_surface_obs[int(id)] = surface
        _v2_clear_surface_caches()
    return True


def merge_user_observations(user_dir: str) -> int:
    """user-env 観測ストアを現ロード localpack の `live_surface_obs` へ重ねる（起動時/有効化後）。

    公開 bundle/localpack には観測 surface を含めない（user-env 限定）。重ねた件数を返す。
    """
    if _V2_PUBLIC is None or _V2_PUBLIC.localpack is None:
        return 0
    import arena_local_data as _ald
    obs = _ald.load_user_observations(user_dir)
    if obs:
        _V2_PUBLIC.localpack.live_surface_obs.update(obs)
        _v2_clear_surface_caches()
    return len(obs)


def init(base_dir: str, lang: str | None = None) -> None:
    """i18n を初期化する。base_dir はアプリのルートディレクトリ。

    lang 未指定時は system locale を BCP 47 として解決し、対象言語が無ければ
    英語（_meta.json の _default_fallback、無ければ "en"）を既定とする。

    原文アンカー(_original)は開発時のみ i18n/_original/ をディスク直読みする
    （公開ビルドは _original を同梱せず、Arena 由来データは v2 localpack から読む）。
    """
    global _BASE_DIR, _I18N_DIR, _lang_cache, _lang_raw_cache, _rules_cache
    global _originals_by_cat, _value_index
    _BASE_DIR = base_dir
    _I18N_DIR = os.path.join(base_dir, "i18n")
    _lang_cache = {}
    _lang_raw_cache = {}
    _rules_cache = {}
    _originals_by_cat = {}
    _value_index = {}
    _load_meta()
    _load_originals()
    resolved = _resolve_initial_lang(lang)
    _set_active(resolved)


# ---- Assist 所有 i18n データの読込（disk=_I18N_DIR 優先・無ければ exe 内 seed）----
# 公開 frozen では `i18n/` を `_internal` に置かない（seed=exe 内）。dev/テストは base_dir/i18n を
# 直読み（挙動不変）。disk を先に試し、無いときだけ seed（app_resources）へフォールバックする。

def _i18n_read_text(*parts: str) -> "str | None":
    """i18n/<parts...> をテキスト読みする（disk 優先・seed フォールバック）。無ければ None。"""
    try:
        with open(os.path.join(_I18N_DIR, *parts), encoding="utf-8") as f:
            return f.read()
    except OSError:
        pass
    try:
        import app_resources
        return app_resources.read_text("/".join(("i18n",) + parts))
    except Exception:  # noqa: BLE001 - seed 不在等は None
        return None


def _i18n_listdir(*parts: str) -> list[str]:
    """i18n/<parts...> 直下の名前一覧（disk 優先・seed フォールバック）。"""
    d = os.path.join(_I18N_DIR, *parts) if parts else _I18N_DIR
    if os.path.isdir(d):
        return sorted(os.listdir(d))
    try:
        import app_resources
        return app_resources.listdir("/".join(("i18n",) + parts))
    except Exception:  # noqa: BLE001
        return []


def _i18n_isdir(*parts: str) -> bool:
    """i18n/<parts...> がディレクトリか（disk 優先・seed フォールバック）。"""
    if os.path.isdir(os.path.join(_I18N_DIR, *parts) if parts else _I18N_DIR):
        return True
    try:
        import app_resources
        return app_resources.is_dir("/".join(("i18n",) + parts))
    except Exception:  # noqa: BLE001
        return False


def _load_meta() -> None:
    """中央言語メタ i18n/_meta.json を読み込む。"""
    global _meta_all, _default_fallback
    _meta_all = {}
    _default_fallback = "en"
    txt = _i18n_read_text("_meta.json")
    if txt is None:
        logger.warning("i18n: failed to load _meta.json")
        return
    try:
        data = json.loads(txt)
        _meta_all = data.get("languages", {}) or {}
        _default_fallback = data.get("_default_fallback", "en") or "en"
    except json.JSONDecodeError as e:
        logger.warning("i18n: failed to parse _meta.json: %s", e)


def _ingest_original_category(category: str, cat: object) -> None:
    """1 カテゴリの原文 dict を内部索引へ取り込む（ディスク _original の畳み込み）。"""
    if not isinstance(cat, dict):
        return
    _originals_by_cat[category] = cat
    for k, v in cat.items():
        if isinstance(v, dict):
            o = v.get("original")
            if isinstance(o, str):
                _original_merged[k] = o


def _load_originals() -> None:
    """原文アンカーをディスク i18n/_original/ から構築する（dev scaffolding）。

    公開ビルドは _original を同梱しないため、このディスク読みは何も載せない。
    公開ランタイムでは v2 localpack（source_id 経路）が唯一の Arena 由来 provider
    であり、この経路へフォールバックしない（未解決を隠さない）。
    """
    global _original_merged, _originals_by_cat
    _original_merged = {}
    _originals_by_cat = {}
    _load_originals_from_disk()


def _load_originals_from_disk() -> None:
    """i18n/_original/<cat>.json をディスクから取り込む（dev scaffolding・無ければ無動作）。

    公開ビルドは disk _original を同梱しないため、このローダは公開ランタイムでは
    何も載せない（= 公開フォールバック源にならない）。
    """
    odir = os.path.join(_I18N_DIR, "_original")
    if not os.path.isdir(odir):
        return
    for fname in sorted(os.listdir(odir)):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        category = fname[:-5]
        try:
            with open(os.path.join(odir, fname), encoding="utf-8") as f:
                cat = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        _ingest_original_category(category, cat)


# ---------------------------------------------------------------------------
# 言語決定（BCP 47 / fallback 連鎖）
# ---------------------------------------------------------------------------

def available_languages() -> list[dict[str, str]]:
    """i18n/ 配下の言語フォルダ（下線始まりを除く）を走査して言語一覧を返す。"""
    results: list[dict[str, str]] = []
    for name in _i18n_listdir():
        if name.startswith("_") or not _i18n_isdir(name):
            continue
        meta = _meta_all.get(name, {})
        results.append({
            "code": name,
            "display_name": meta.get("display_name", name),
            "direction": meta.get("direction", "ltr"),
        })
    return results


def _available_codes() -> set[str]:
    return {entry["code"] for entry in available_languages()}


def _resolve_initial_lang(lang: str | None) -> str:
    """起動時の表示言語を決定する。

    優先順位: 明示指定 → system locale（BCP 47・[:2] しない） → 英語既定。
    いずれも fallback 連鎖で段階解決する。
    """
    avail = _available_codes()
    if not avail:
        return _default_fallback

    # 明示指定（設定保存値）がある場合は、それを段階一致で解決する。
    # 一致しなければ system locale には流さず英語既定へ落とす
    # （「明示設定が消えた → 英語」。OS 推測へ流すのは初回起動=未設定時のみ）。
    if lang:
        match = _match_tag(lang, avail)
        if match:
            return match
    else:
        # 初回起動（未設定）: system locale を BCP 47 として解決
        try:
            sys_lang = locale.getdefaultlocale()[0]
        except (ValueError, TypeError):
            sys_lang = None
        if sys_lang:
            match = _match_tag(sys_lang, avail)
            if match:
                return match

    # 既定言語。_default_fallback(原文言語=en) → en → _meta.json の宣言順で
    # 最初に利用可能な言語、の順で落とす。公開版は i18n/en 非同梱で en が無いため、
    # 宣言順(en,ja,es)の次=ja へ落ちる。`sorted(avail)[0]` だと es に落ちて
    # 英語ロケールのユーザーが初回スペイン語表示になる UX バグになる。
    # 宣言順は _meta.json が単一住所で定める。
    if _default_fallback in avail:
        return _default_fallback
    if "en" in avail:
        return "en"
    for code in _meta_all:
        if code in avail:
            return code
    return sorted(avail)[0]


def _match_tag(tag: str, avail: set[str]) -> str | None:
    """BCP 47 タグを利用可能言語へ段階一致させる。

    例: "zh-Hant-TW" → "zh-Hant" → "zh"。大文字小文字差は吸収する。
    """
    if not tag:
        return None
    tag = tag.replace("_", "-")  # "ja_JP" / "en_US" も受理
    lower_map = {c.lower(): c for c in avail}
    parts = tag.split("-")
    for i in range(len(parts), 0, -1):
        cand = "-".join(parts[:i]).lower()
        if cand in lower_map:
            return lower_map[cand]
    # 言語サブタグだけでの一致（"ja-JP" → "ja"）
    base = parts[0].lower()
    if base in lower_map:
        return lower_map[base]
    for c in avail:
        if c.lower().split("-")[0] == base:
            return c
    return None


def _fallback_chain(lang: str) -> list[str]:
    """指定言語の fallback 連鎖（自身を先頭、既定言語を末尾に保証）。"""
    meta = _meta_all.get(lang, {})
    chain = list(meta.get("fallback_chain", []) or [])
    if lang not in chain:
        chain.insert(0, lang)
    if _default_fallback and _default_fallback not in chain:
        chain.append(_default_fallback)
    return chain


# ---------------------------------------------------------------------------
# 言語データのロード
# ---------------------------------------------------------------------------

def _load_lang_merged(lang: str) -> dict[str, str]:
    """i18n/<lang>/*.json を読み、id→訳 のマージ辞書を返す（キャッシュ）。

    値は素の文字列、または {value,status} 拡張形（value を採用）。空値は格納しない
    （fallback 連鎖を効かせるため）。
    """
    if lang in _lang_cache:
        return _lang_cache[lang]
    merged: dict[str, str] = {}
    for fname in _i18n_listdir(lang):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        txt = _i18n_read_text(lang, fname)
        if txt is None:
            continue
        try:
            cat = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if not isinstance(cat, dict):
            continue
        for k, v in cat.items():
            if isinstance(v, str):
                s = v
            elif isinstance(v, dict):
                s = v.get("value", "")
            else:
                continue
            if s != "":
                merged[k] = s
    _lang_cache[lang] = merged
    return merged


# ---------------------------------------------------------------------------
# 解決 API
# ---------------------------------------------------------------------------

def text_opt(id: str) -> str | None:
    """id を現在言語→fallback 連鎖→原文 で解決する。未解決は None。"""
    if _V2_COMPAT is not None:
        v = _V2_COMPAT.text_opt(id, _lang)
        if v is not None:
            return v
    for lang in _fallback_chain(_lang):
        m = _load_lang_merged(lang)
        v = m.get(id)
        if v:
            return v
    o = _original_merged.get(id)
    if o:
        return o
    return None


def text(id: str) -> str:
    """id を解決して文字列を返す。未解決時は id そのものを返す。"""
    v = text_opt(id)
    if v is not None:
        return v
    logger.debug("i18n: missing id '%s' (lang=%s)", id, _lang)
    return id


def lang_only(id: str) -> str | None:
    """現在言語レイヤの生の訳のみを返す（言語fallback連鎖・原文フォールバックを一切適用しない）。

    未登録・空訳は None。「訳が無い＝空表示」を厳密に区別したい消費側
    （例: inf_text の未訳エントリは EN を出さず空にする旧挙動）向け。
    通常表示は fallback を効かせる text()/text_opt() を使う。
    """
    return _load_lang_merged(_lang).get(id)


def _load_lang_raw(lang: str) -> dict[str, Any]:
    """i18n/<lang>/*.json を読み、id→生値（str または {value,plural,…} dict）を返す（キャッシュ）。

    `_load_lang_merged` と異なり構造値を畳まず、語形（plural 等）を保持する。
    """
    if lang in _lang_raw_cache:
        return _lang_raw_cache[lang]
    raw: dict[str, Any] = {}
    for fname in _i18n_listdir(lang):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        txt = _i18n_read_text(lang, fname)
        if txt is None:
            continue
        try:
            cat = json.loads(txt)
        except json.JSONDecodeError:
            continue
        if isinstance(cat, dict):
            raw.update(cat)
    _lang_raw_cache[lang] = raw
    return raw


def lang_value_in(id: str, lang: str, form: str = "value") -> str | None:
    """指定言語レイヤの値を返す（言語/原文フォールバックなし・語形 form 指定可）。

    構造値 `{value, plural, …}` では `form` のキーを返す。
    素の文字列値は `form == "value"` のときのみ返す。未登録・空・該当語形なしは None。
    複数言語の語形を同時に要する構造データ（arena_data の race plural 等）向け。
    """
    rawval = _load_lang_raw(lang).get(id)
    if isinstance(rawval, dict):
        v = rawval.get(form)
        return v if v else None
    if isinstance(rawval, str):
        return rawval if (form == "value" and rawval) else None
    return None


def rules(lang: str | None = None) -> dict[str, Any]:
    """指定言語の処理ルール `i18n/<lang>/_rules.json` を返す（翻訳でない言語別規則）。

    text_corrections / placeholder_preprocessing / dynamic_places 等の言語別ルール
    （正規表現・地名合成規則）を保持する。`_` 接頭辞のため
    翻訳ローダ（`_load_lang_merged`）には載らない。ファイル不在・未定義言語は `{}`。
    """
    target = lang or _lang
    if target in _rules_cache:
        return _rules_cache[target]
    data: dict[str, Any] = {}
    txt = _i18n_read_text(target, "_rules.json")
    if txt is not None:
        try:
            loaded = json.loads(txt)
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    _rules_cache[target] = data
    return data


def original(id: str) -> str | None:
    """原文アンカー文字列を返す（無ければ None）。"""
    if _V2_COMPAT is not None:
        v = _V2_COMPAT.original(id)
        if v is not None:
            return v
    return _original_merged.get(id)


def originals(category: str) -> dict[str, Any]:
    """指定カテゴリの原文エントリ {id:{original,...}} を返す（照合器が消費）。"""
    return _originals_by_cat.get(category, {})


def original_categories() -> list[str]:
    """原文アンカーを持つカテゴリ一覧（ディスク＋パック overlay 込み・ソート済み）。

    公開版は disk `i18n/_original` 非同梱のため `os.listdir` では空になる。内部索引
    `_originals_by_cat` から列挙すれば pack 収録カテゴリも辞書タブに出る。
    dev は disk 全カテゴリが索引に載るため従来の disk 列挙と同一集合。
    """
    return sorted(_originals_by_cat.keys())


def lang_ids(category: str) -> list[str]:
    """現在言語(＋fallback 連鎖)レイヤに存在する category 配下の id 一覧を返す。

    公開版は `_original` を同梱しないため `originals()` が空になる。翻訳ファイル
    `i18n/<lang>/<category>.json` は公開同梱されるので、その id を列挙すれば原文非依存に
    カテゴリの id 集合を得られる（例: %di 閉集合の語彙を公開版でも構築する用途）。
    """
    prefix = f"{category}."
    out: set[str] = set()
    for lang in _fallback_chain(_lang):
        for k in _load_lang_merged(lang):
            if k.startswith(prefix):
                out.add(k)
    return sorted(out)


def value(category: str, original_text: str) -> str | None:
    """カテゴリ内で原文 original_text を持つ id を逆引きし、現在言語の訳を返す。

    ゲームテキストの値翻訳（地名・種族名・職業名・アイテム名等）の共通経路。
    原文→id 索引は言語非依存のため一度だけ構築しキャッシュする。未登録は None。
    同一原文が複数 id にある場合は先勝ち（id 走査順）。
    """
    if not original_text:
        return None
    # v2 有効カテゴリは公開安全な live-surface 逆引きで解決（原文込み string-ID 不使用）。
    if v2_public_enabled(category):
        return value_by_surface(category, original_text)
    idx = _value_index.get(category)
    if idx is None:
        idx = {}
        for k, e in _originals_by_cat.get(category, {}).items():
            if isinstance(e, dict):
                o = e.get("original")
                if isinstance(o, str) and o not in idx:
                    idx[o] = k
        _value_index[category] = idx
    id_ = idx.get(original_text)
    if id_ is None:
        return None
    return text_opt(id_)


def value_in(category: str, original_text: str, lang: str) -> str | None:
    """カテゴリ内で原文 original_text を id 逆引きし、指定言語レイヤの訳を返す。

    `value()` と異なり言語を明示指定し、言語/原文フォールバックを掛けない
    （指定言語の生訳のみ）。原文/英語の列を別言語で描画する消費側が、現在言語に
    依らず特定言語の訳を要する場合に使う。未登録・該当言語に訳なしは None。
    """
    if not original_text:
        return None
    if v2_public_enabled(category):
        return value_by_surface(category, original_text, lang=lang)
    idx = _value_index.get(category)
    if idx is None:
        idx = {}
        for k, e in _originals_by_cat.get(category, {}).items():
            if isinstance(e, dict):
                o = e.get("original")
                if isinstance(o, str) and o not in idx:
                    idx[o] = k
        _value_index[category] = idx
    id_ = idx.get(original_text)
    if id_ is None:
        return None
    return lang_value_in(id_, lang)


def glossary(term_id: str) -> str | None:
    """用語集 glossary の現在言語正典訳を返す（無ければ None）。"""
    return text_opt(term_id)


def tr(key: str, **kwargs: Any) -> str:
    """UI 文字列を返す（id=意味キー）。未解決はキーをそのまま返す。"""
    s = text(key)
    if kwargs:
        try:
            s = s.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            pass
    return s


def tr_n(key: str, n: int, **kwargs: Any) -> str:
    """複数形対応の UI 文字列取得。plural_form に応じて key_plural を試みる。"""
    plural_form = current_meta().get("plural_form", "no_plural")
    s: str | None = None
    if _needs_plural(plural_form, n):
        s = text_opt(f"{key}_plural")
    if s is None:
        s = text(key)
    try:
        s = s.format(n=n, **kwargs)
    except (KeyError, ValueError, IndexError):
        pass
    return s


# ---------------------------------------------------------------------------
# 言語状態
# ---------------------------------------------------------------------------

def _set_active(lang: str) -> None:
    global _lang, _V2_SURFACE_WARNINGS
    _lang = lang
    _load_lang_merged(lang)
    # 訳違い重複の事前検査は現在言語の訳で判定するため言語切替で破棄（索引自体は言語非依存）。
    _V2_SURFACE_WARNINGS = {}
    _apply_qt_settings()


def set_language(lang: str) -> bool:
    """動的に言語を切り替える。利用可能なら True を返し signal を発火する。"""
    match = _match_tag(lang, _available_codes())
    if not match:
        return False
    _set_active(match)
    if signals is not None:
        signals.language_changed.emit(_lang)
    return True


def current_lang() -> str:
    return _lang


def current_meta() -> dict[str, Any]:
    return dict(_meta_all.get(_lang, {}))


def direction() -> str:
    """現在言語のテキスト方向（"ltr" / "rtl"）。"""
    return current_meta().get("direction", "ltr")


def font_hint() -> str | None:
    """現在言語の推奨フォントスタック文字列（無ければ None）。"""
    return current_meta().get("font_hint") or None


# ---------------------------------------------------------------------------
# 内部ヘルパー
# ---------------------------------------------------------------------------

def _needs_plural(plural_form: str, n: int) -> bool:
    if plural_form == "no_plural":
        return False
    if plural_form == "en_like_2":
        return n != 1
    if plural_form not in ("no_plural", "en_like_2"):
        logger.warning(
            "i18n: plural_form '%s' not fully implemented, using en_like_2",
            plural_form)
        return n != 1
    return False


def _apply_qt_settings() -> None:
    """Qt が利用可能なら direction とフォントを適用する。"""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont

        app = QApplication.instance()
        if app is None:
            return

        if direction() == "rtl":
            app.setLayoutDirection(Qt.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LeftToRight)

        hint = font_hint()
        if hint:
            families = [f.strip() for f in hint.split(",")]
            if families:
                # 現在のアプリフォント（サイズ/ウェイト）を保持し families だけ差し替える。
                # QFont(family) は point size を Qt 既定へリセットするため、言語切替の
                # たびに全体のフォントサイズが変わり表示が見切れる不具合になる。
                font = QFont(app.font())
                font.setFamilies(families)
                app.setFont(font)
    except Exception:  # noqa: BLE001
        pass
