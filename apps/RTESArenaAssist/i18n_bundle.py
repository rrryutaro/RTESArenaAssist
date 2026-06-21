"""i18n_bundle.py — Assist 内蔵の単一翻訳 bundle のローダ。

`i18n_bundle.json`（categories + locales）を読み、整数 ID 解決に必要な索引を作る。
Arena 原文そのものは持たない（原文は localpack 側）。

fail（読み込み拒否＝例外）:
  - schema が未知。
  - schema_version が互換不能（サポート版より新しい）。
  - categories / locales の必須構造が壊れている（型不正・id 重複）。

warning（読み込み継続・収集のみ）:
  - registry_hash / registry_version は bundle 自身では判定しない（localpack/mod 側で照合）。
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "rtesaa.i18n_bundle"
SUPPORTED_SCHEMA_VERSION = 1


def compute_registry_hash(raw: dict) -> str:
    """ID 集合の決定論ハッシュ（registry_hash 用）。

    registry = ID 集合の版。locale（訳）は版に含めない（訳変更で hash を動かさない）。
    対象＝schema_version / registry_version ＋ 各 entry の id/category/source_policy/
    source_provider/source（id 昇順で正規化）。
    """
    rows: list[tuple] = []
    for cat in raw.get("categories") or []:
        name = cat.get("category")
        policy = cat.get("source_policy")
        provider = cat.get("source_provider")
        for entry in cat.get("entries") or []:
            rows.append((
                int(entry["id"]), name, policy, provider,
                json.dumps(entry.get("source"), sort_keys=True,
                           ensure_ascii=False),
            ))
    rows.sort(key=lambda r: r[0])
    payload = {
        "schema_version": int(raw.get("schema_version", 0)),
        "registry_version": int(raw.get("registry_version", 0)),
        "rows": rows,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


class BundleError(Exception):
    """bundle が読み取り不能（schema 非互換・構造破損）。fail 相当。"""


class Bundle:
    """読み込み済み bundle の索引。"""

    def __init__(self, raw: dict):
        self.schema_version: int = int(raw.get("schema_version", 0))
        self.registry_version: int = int(raw.get("registry_version", 0))
        self.registry_hash: str = str(raw.get("registry_hash", ""))
        self.warnings: list[str] = []

        # id -> category メタ（category/source_policy/source_provider）。
        self._cat_by_id: dict[int, dict] = {}
        # category 名 -> category メタ + entries。
        self.categories: dict[str, dict] = {}
        # locale -> { id: text }。
        self._locale_texts: dict[str, dict[int, str]] = {}
        # derived redirect: placeholder int id -> target int id。
        self._redirect: dict[int, int] = {}

        self._ingest_categories(raw.get("categories"))
        self._ingest_locales(raw.get("locales"))

    # --- 構築 ---
    def _ingest_categories(self, cats: object) -> None:
        if not isinstance(cats, list):
            raise BundleError("bundle.categories must be a list")
        for cat in cats:
            if not isinstance(cat, dict):
                raise BundleError("bundle.categories[] must be objects")
            name = cat.get("category")
            policy = cat.get("source_policy")
            if not name or not policy:
                raise BundleError(
                    f"category missing name/source_policy: {cat!r}")
            entries = cat.get("entries") or []
            if not isinstance(entries, list):
                raise BundleError(f"category {name} entries must be a list")
            meta = {
                "category": name,
                "source_policy": policy,
                "source_provider": cat.get("source_provider"),
                "id_range": cat.get("id_range"),
                "entries": entries,
            }
            self.categories[name] = meta
            for entry in entries:
                if not isinstance(entry, dict) or "id" not in entry:
                    raise BundleError(
                        f"entry missing id in category {name}: {entry!r}")
                eid = int(entry["id"])
                if eid in self._cat_by_id:
                    raise BundleError(f"duplicate entry id: {eid}")
                self._cat_by_id[eid] = meta
                rt = entry.get("redirect_to")
                if rt is not None:
                    self._redirect[eid] = int(rt)

    def _ingest_locales(self, locales: object) -> None:
        if locales is None:
            self.warnings.append("bundle has no locales")
            return
        if not isinstance(locales, list):
            raise BundleError("bundle.locales must be a list")
        for loc in locales:
            if not isinstance(loc, dict):
                raise BundleError("bundle.locales[] must be objects")
            tag = loc.get("locale")
            if not tag:
                raise BundleError("locale entry missing 'locale'")
            texts = loc.get("texts") or []
            table: dict[int, str] = {}
            for t in texts:
                table[int(t["id"])] = str(t["text"])
            self._locale_texts[tag] = table

    # --- 参照 ---
    def category_of(self, id: int) -> dict | None:
        return self._cat_by_id.get(int(id))

    def source_policy_of(self, id: int) -> str | None:
        meta = self._cat_by_id.get(int(id))
        return meta.get("source_policy") if meta else None

    def redirect_of(self, id: int) -> int | None:
        """derived redirect target 整数 ID（無ければ None）。"""
        return self._redirect.get(int(id))

    def locale_text(self, id: int, locale: str) -> str | None:
        table = self._locale_texts.get(locale)
        if table is None:
            return None
        return table.get(int(id))

    def has_locale(self, locale: str) -> bool:
        return locale in self._locale_texts

    def locales(self) -> list[str]:
        return list(self._locale_texts.keys())

    def all_ids(self) -> list[int]:
        return list(self._cat_by_id.keys())


def load_bundle_obj(raw: dict) -> Bundle:
    """dict から bundle を読み込む（schema 検証つき）。"""
    schema = raw.get("schema")
    if schema != SCHEMA:
        raise BundleError(f"unknown bundle schema: {schema!r}")
    ver = int(raw.get("schema_version", 0))
    if ver > SUPPORTED_SCHEMA_VERSION:
        raise BundleError(
            f"bundle schema_version {ver} newer than supported "
            f"{SUPPORTED_SCHEMA_VERSION}")
    return Bundle(raw)


def load_bundle(path: str) -> Bundle:
    """ファイルパスから bundle を読み込む。"""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return load_bundle_obj(raw)


__all__ = ["Bundle", "BundleError", "load_bundle", "load_bundle_obj",
           "compute_registry_hash", "SCHEMA", "SUPPORTED_SCHEMA_VERSION"]
