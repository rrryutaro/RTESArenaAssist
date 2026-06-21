"""localpack_builder.py — 採番台帳＋_original から v2 localpack を構築する runtime 中核。

`legacy_adapter`（arena_generated の既存 surface を整数 ID へ）＋`spell_effect_structure`
（効果構造生成）で `originals[int_id]`／`audit` を作り、`i18n_localpack` で単一ファイルへ書く。

オフライン生成器（`tools/gen_localpack.py`）と実ユーザー環境の `arena_local_data.build_local_pack`
の双方から呼ぶ共通実装。original_by_cat の供給元（disk/pack）に依存しない。
"""
from __future__ import annotations

import i18n_localpack as _ilp
import legacy_adapter as _adapter
import spell_effect_structure as _ses


def build_originals(registry: dict,
                    original_by_cat: dict[str, dict[str, dict]],
                    ) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    """(originals, audit, warnings) を生成する。

    registry: i18n_id_registry.json。
    original_by_cat: { category: { legacy_id: {"original":.., "src_hash":..} } }
        （arena_generated カテゴリのみ消費・spell_effect は構造から自前生成）。
    """
    originals, audit, warnings = _adapter.migrate_originals(
        registry, original_by_cat)
    for cat in registry.get("categories", []):
        if cat.get("category") != "spell_effect":
            continue
        for eid, info in _ses.build_originals(cat.get("entries", [])).items():
            originals[eid] = info["text"]
            audit[str(eid)] = {
                "status": info.get("status", "verified"),
                "category": "spell_effect",
                "provider": "spell_effect_structure",
            }
    return originals, audit, warnings


def _as_ids(value) -> list[int]:
    """source_id_map の値（v2=list / v1=int 互換）を整数 ID list へ正規化。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [int(x) for x in value]
    return [int(value)]


def ids_for_source_id(source_id_map: dict, source_id: str) -> list[int]:
    """source_id に対応する整数 ID 群（multi-target）。未登録は空 list。"""
    return _as_ids(source_id_map.get(source_id))


def single_id_for_source_id(source_id_map: dict, source_id: str) -> int:
    """list 長 1 の source_id を単一 ID で返す（clean カテゴリ用・複数/不在は例外）。"""
    ids = ids_for_source_id(source_id_map, source_id)
    if len(ids) != 1:
        raise ValueError(
            f"source_id {source_id!r} maps to {len(ids)} ids (expected 1)")
    return ids[0]


def build_originals_by_source_id(
        source_id_map: dict,
        surface_by_source_id: dict[str, str],
        *,
        provider: str = "",
        status: str = "generated",
        category_by_id: dict[int, str] | None = None,
        ) -> tuple[dict[int, str], dict[str, dict], list[str]]:
    """公開経路: provider 生成の {source_id: surface} を source_id_map で整数 ID へ解決。

    legacy_id_map に依存しない（user-env 公開ビルド経路）。map に無い source_id は
    勝手に採番せず warning/degraded。**1 source_id→複数 ID（multi-target）は同 surface を
    全 target へ fan-out**（共有テーブル disambiguation）。
    """
    originals: dict[int, str] = {}
    audit: dict[str, dict] = {}
    warnings: list[str] = []
    cat_by_id = category_by_id or {}
    for source_id, surface in surface_by_source_id.items():
        ids = ids_for_source_id(source_id_map, source_id)
        if not ids:
            warnings.append(f"source_id not in map (degraded): {source_id}")
            continue
        if not surface:
            warnings.append(f"empty surface (degraded): {source_id}")
            continue
        for nid in ids:
            originals[nid] = surface
            entry = {"status": status, "source_id": source_id,
                     "provider": provider}
            if nid in cat_by_id:
                entry["target_category"] = cat_by_id[nid]
            audit[str(nid)] = entry
    return originals, audit, warnings


def write_localpack(out_path: str,
                    registry: dict,
                    original_by_cat: dict[str, dict[str, dict]],
                    *,
                    registry_hash: str,
                    arena_fingerprint: str = "") -> dict:
    """v2 localpack を書き出し、サマリ（件数・warnings）を返す。"""
    originals, audit, warnings = build_originals(registry, original_by_cat)
    _ilp.build_localpack(
        out_path, originals,
        registry_hash=registry_hash,
        arena_fingerprint=arena_fingerprint,
        audit=audit)
    return {"originals": len(originals), "warnings": warnings}


def rich_meta_by_id(source_id_map: dict,
                    rich_by_source_id: dict[str, dict]) -> dict[int, dict]:
    """provider 生成の {source_id: rich_meta} を source_id_map で整数 ID へ解決する。

    consumer 移行 rich メタ（inf/idx/表示変種等）を localpack へ載せる用（user-env 限定）。
    multi-target は全 target へ fan-out。map に無い source_id は除外（degraded）。
    """
    out: dict[int, dict] = {}
    for source_id, meta in rich_by_source_id.items():
        if not isinstance(meta, dict):
            continue
        for nid in ids_for_source_id(source_id_map, source_id):
            out[nid] = meta
    return out


def write_localpack_by_source_id(out_path: str,
                                 source_id_map: dict,
                                 surface_by_source_id: dict[str, str],
                                 *,
                                 registry_hash: str,
                                 spell_effect_entries: list[dict] | None = None,
                                 rich_by_source_id: dict[str, dict] | None = None,
                                 arena_fingerprint: str = "",
                                 generated_assets: dict[str, bytes] | None = None,
                                 provider: str = "") -> dict:
    """**公開経路（user-env）**: provider 生成の {source_id: surface} を source_id_map で整数 ID へ
    解決して v2 localpack を書く（legacy_id_map 非依存）。

    spell_effect は source_id を持たず（effect 構造で provider 直生成）、bundle の spell_effect
    entries（`source` の effect 構造）から `spell_effect_structure` で originals を足す。
    map に無い source_id は採番せず warning/degraded（build_originals_by_source_id 準拠）。
    """
    originals, audit, warnings = build_originals_by_source_id(
        source_id_map, surface_by_source_id, provider=provider)
    for entry in (spell_effect_entries or []):
        src = entry.get("source") or {}
        result = _ses.surface_for(
            int(src.get("effect_id", _ses.NONE)),
            int(src.get("sub_effect_id", 0)),
            int(src.get("affected_attr_id", 0)),
        )
        if result is None:
            continue
        text, status = result
        eid = int(entry["id"])
        originals[eid] = text
        audit[str(eid)] = {"status": status, "category": "spell_effect",
                           "provider": "spell_effect_structure"}
    rich = rich_meta_by_id(source_id_map, rich_by_source_id or {})
    # 再写像キャッシュ: 入力 surface（source_id→Arena surface）を localpack に保存し、bundle/registry
    # 変更時に localpack 単独で再写像できるようにする（採取をやり直さない）。
    _ilp.build_localpack(
        out_path, originals,
        registry_hash=registry_hash,
        arena_fingerprint=arena_fingerprint,
        audit=audit,
        rich_meta=rich or None,
        generated_assets=generated_assets or None,
        v2_surfaces=dict(surface_by_source_id) or None,
        v2_rich=dict(rich_by_source_id) if rich_by_source_id else None)
    return {"originals": len(originals), "warnings": warnings,
            "rich_meta": len(rich),
            "generated_assets": len(generated_assets or {})}


__all__ = ["build_originals", "write_localpack", "write_localpack_by_source_id",
           "build_originals_by_source_id", "ids_for_source_id", "rich_meta_by_id"]
