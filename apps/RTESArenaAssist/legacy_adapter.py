"""legacy_adapter.py — 移行 adapter `legacy_originals_to_v2_originals`。

既存の文字列 ID `_original/<category>.json`（`{legacy_id: {original, src_hash}}`）を、
採番台帳由来の整数 ID へ載せ替えて v2 localpack の `originals[int_id]` / `audit[str(int_id)]`
を生成する。既存生成器の出力を変えずに整数 ID 化する移行中専用の層であり、全カテゴリ移行後に
削除する。

ルール:
  - `arena_generated` カテゴリのみ localpack originals に入れる。
  - `assist_bundled` / `live_surface` / `derived` は localpack に入れない。
  - 台帳に無い legacy ID を勝手に新規採番しない（warning/degraded で報告）。
  - 旧 `src_hash` は audit へ引き継ぐ。original 値は `_original.original`（Arena surface）。
"""
from __future__ import annotations

import json
import os


def migrate_originals(
        registry: dict,
        original_by_category: dict[str, dict[str, dict]],
        ) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    """台帳＋既存 _original から (originals, audit, warnings) を生成。

    registry: i18n_id_registry.json（カテゴリ＋entries: id/legacy_id/source_policy）。
    original_by_category: { category: { legacy_id: {"original":.., "src_hash":..} } }。
    """
    originals: dict[int, str] = {}
    audit: dict[str, dict] = {}
    warnings: list[str] = []

    for cat in registry.get("categories", []):
        name = cat.get("category")
        if cat.get("source_policy") != "arena_generated":
            continue
        # 呼び出し側が渡したカテゴリのみ移行する（coverage 取れた分から増分）。
        if name not in original_by_category:
            continue
        src = original_by_category.get(name, {})
        for entry in cat.get("entries", []):
            if entry.get("retired"):
                continue
            legacy = entry.get("legacy_id")
            if not legacy:
                # spell_effect 等の構造由来は別 provider が生成する。
                continue
            rec = src.get(legacy)
            if rec is None:
                warnings.append(
                    f"{name}: legacy '{legacy}' not in _original (degraded)")
                continue
            text = rec.get("original")
            if text is None or text == "":
                warnings.append(
                    f"{name}: legacy '{legacy}' has empty original (degraded)")
                continue
            eid = int(entry["id"])
            originals[eid] = text
            ent = {"status": "migrated", "category": name}
            if rec.get("src_hash"):
                ent["src_hash"] = rec["src_hash"]
            audit[str(eid)] = ent
    return originals, audit, warnings


def load_original_by_category(i18n_dir: str,
                              categories: list[str]) -> dict[str, dict]:
    """`i18n/_original/<cat>.json` を読み込む（{cat: {legacy_id: {...}}}）。"""
    out: dict[str, dict] = {}
    for cat in categories:
        path = os.path.join(i18n_dir, "_original", cat + ".json")
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        out[cat] = {k: v for k, v in raw.items()
                    if not k.startswith("_") and isinstance(v, dict)}
    return out


__all__ = ["migrate_originals", "load_original_by_category"]
